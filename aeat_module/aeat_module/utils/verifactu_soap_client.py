# -*- coding: utf-8 -*-
"""
Cliente SOAP real de VERI*FACTU (Fase 2), sustituyendo al `VeriFactuClient`
REST/JSON de `utils/verifactu_client.py`.

Usa el WSDL saneado local (`docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl`,
válido tanto para preprod como para producción: define puertos separados
para cada entorno) vía `zeep`, autenticado por certificado mTLS, y firma el
`RegistroAlta`/`RegistroAnulacion` con `utils/xml_signing` (XMLDSig enveloped,
equivalente XAdES) antes de enviarlo.

El desglose de impuestos (`Desglose/DetalleDesglose`) soporta facturas
multi-tipo (varios IVA/IGIC/exentos en la misma factura) vía
`utils/tax_breakdown.build_desglose`, ver ese módulo para el detalle de
cómo se clasifica cada línea (Item Tax Template / Sales Taxes and Charges
Template / Account).
"""
import os
import time
from pathlib import Path
from typing import Optional

import frappe
from lxml import etree
from zeep import Client, Settings as ZeepSettings

from .wsdl_transport import LocalWsdlTransport
from .xml_signing import sign_registro
from .error_codes import classify_many, any_retryable
from .pkcs12_utils import pfx_to_pem_files
from .tax_breakdown import build_desglose

WSDL_FILENAME = "PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl"

# Puertos definidos en el WSDL para cada entorno (ver docs/CONFIG_TRANSPORT.md)
PORT_BY_ENVIRONMENT = {
    "preprod": "SistemaVerifactuPruebas",
    "prod": "SistemaVerifactu",
}

_NS_RESPUESTA = {
    "tikR": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/RespuestaSuministro.xsd",
}


class VeriFactuSoapError(Exception):
    pass


# TipoFactura que exigen el bloque Destinatarios cumplimentado (error AEAT 1189);
# F2/R5 lo prohíben expresamente (error 1190, facturas simplificadas/tique).
_TIPOS_REQUIEREN_DESTINATARIO = {"F1", "F3", "R1", "R2", "R3", "R4"}


def _build_destinatarios(doc, tipo_factura: str) -> Optional[dict]:
    if tipo_factura not in _TIPOS_REQUIEREN_DESTINATARIO:
        return None

    nif = doc.get("tax_id") or frappe.db.get_value("Customer", doc.get("customer"), "tax_id")
    customer_name = doc.get("customer_name") or doc.get("customer") or ""
    if not nif:
        raise VeriFactuSoapError(
            f"La factura {doc.name} es TipoFactura {tipo_factura}: la AEAT exige el bloque "
            f"Destinatarios (NIF del cliente), pero el cliente '{customer_name}' no tiene NIF "
            "configurado (campo 'Tax ID' en Customer, o 'NIF' en la propia factura)."
        )
    return {"IDDestinatario": [{"NombreRazon": customer_name, "NIF": nif}]}


def _docs_dir():
    return Path(os.path.join(frappe.get_app_path("aeat_module"), "..", "docs"))


class VeriFactuSoapClient:
    """Cliente SOAP por Company. Requiere AEAT Company Settings con
    verifactu_auth_mode='mTLS' y cert+key (PEM o PFX) configurados."""

    def __init__(self, company: str, ctx: dict):
        self.company = company
        self.ctx = ctx
        self.cs = frappe.get_doc("AEAT Company Settings", {"company": company})
        self.environment = ctx.get("environment") or "preprod"
        self.port_name = PORT_BY_ENVIRONMENT.get(self.environment, "SistemaVerifactuPruebas")

        # Rutas PEM temporales generadas al convertir un PFX/P12 (contienen la
        # clave privada en texto plano); se eliminan en `cleanup()`.
        self._temp_cert_files: list[str] = []
        self.cert_path, self.key_path = self._resolve_mtls_cert()

        docs_dir = _docs_dir()
        wsdl_path = docs_dir / WSDL_FILENAME
        if not wsdl_path.exists():
            raise VeriFactuSoapError(f"WSDL local no encontrado: {wsdl_path}")

        transport = LocalWsdlTransport(docs_dir=docs_dir, timeout=30)
        settings = ZeepSettings(strict=False, xml_huge_tree=True)
        self.client = Client(wsdl=wsdl_path.resolve().as_uri(), transport=transport, settings=settings)

        port = self._find_port(self.port_name)
        self.address = port.binding_options.get("address")
        self.binding_qname = port.binding.name
        self.service = self.client.create_service(self.binding_qname, self.address)

    def _find_port(self, port_name: str):
        for svc in self.client.wsdl.services.values():
            for port in svc.ports.values():
                if port.name == port_name:
                    return port
        raise VeriFactuSoapError(f"Puerto '{port_name}' no encontrado en el WSDL")

    def cleanup(self):
        """Borra los ficheros PEM temporales generados a partir de un PFX
        (contienen la clave privada en texto plano en /tmp). Llamar siempre
        tras usar el cliente (ver api_verifactu.py, try/finally)."""
        for path in self._temp_cert_files:
            try:
                os.unlink(path)
            except OSError:
                pass
        self._temp_cert_files = []

    def _resolve_mtls_cert(self):
        """Devuelve (cert_path, key_path) en PEM, convirtiendo desde PFX si
        procede. Lanza VeriFactuSoapError con un mensaje claro si no hay
        certificado configurado (caso actual: sin certificado real de AEAT)."""
        mode = (self.cs.get("verifactu_auth_mode") or "mTLS").strip()
        if mode != "mTLS":
            raise VeriFactuSoapError(
                f"AEAT solo admite autenticación por certificado mTLS (modo configurado: {mode})."
            )

        pfx_path = self.cs.get("mtls_client_pfx_path")
        pfx_file = self.cs.get("mtls_client_pfx_file")
        cert_path = self.cs.get("mtls_client_cert_path")
        key_path = self.cs.get("mtls_client_key_path")

        if pfx_path or pfx_file:
            try:
                pwd = self.cs.get_password("mtls_client_key_password")
            except Exception:
                pwd = None
            if pfx_path:
                pfx_bytes = Path(pfx_path).read_bytes()
            else:
                file_doc = frappe.get_doc("File", {"file_url": pfx_file})
                pfx_bytes = Path(file_doc.get_full_path()).read_bytes()
            pwd_bytes = pwd.encode("utf-8") if pwd else None
            cert_path, key_path = pfx_to_pem_files(pfx_bytes, pwd_bytes)
            self._temp_cert_files.extend([cert_path, key_path])
            return cert_path, key_path

        if cert_path and key_path:
            if not Path(cert_path).exists() or not Path(key_path).exists():
                raise VeriFactuSoapError(
                    f"Certificado/clave mTLS configurados pero no existen en disco "
                    f"(cert={cert_path}, key={key_path})."
                )
            return cert_path, key_path

        raise VeriFactuSoapError(
            "No hay certificado mTLS configurado en AEAT Company Settings "
            f"para '{self.company}' (mtls_client_cert_path/mtls_client_key_path "
            "o mtls_client_pfx_path/mtls_client_pfx_file). Sin certificado real "
            "de la AEAT no es posible enviar a VERI*FACTU."
        )

    def build_registro_alta_payload(self, doc, vf_hash: str, prev_hash: Optional[str],
                                     tipo_factura: str, fecha_expedicion: str,
                                     cuota_total: str, importe_total: str, fecha_hora_gen: str) -> dict:
        nif_emisor = self.ctx.get("nif_emisor") or doc.get("company_tax_id") or ""
        num_serie_factura = doc.name

        detalle_desglose = build_desglose(doc)
        destinatarios = _build_destinatarios(doc, tipo_factura)

        registro_alta = {
            "IDVersion": "1.0",
            "IDFactura": {
                "IDEmisorFactura": nif_emisor,
                "NumSerieFactura": num_serie_factura,
                "FechaExpedicionFactura": fecha_expedicion,
            },
            "NombreRazonEmisor": self.company,
            "TipoFactura": tipo_factura,
            "DescripcionOperacion": doc.get("remarks") or "Suministro de bienes/servicios",
            "Destinatarios": destinatarios,
            "Desglose": {"DetalleDesglose": detalle_desglose},
            "CuotaTotal": cuota_total,
            "ImporteTotal": importe_total,
            "Encadenamiento": (
                {"PrimerRegistro": "S"} if not prev_hash else
                {"RegistroAnterior": {
                    "IDEmisorFactura": nif_emisor,
                    "NumSerieFactura": num_serie_factura,
                    "FechaExpedicionFactura": fecha_expedicion,
                    "Huella": prev_hash,
                }}
            ),
            "SistemaInformatico": {
                "NombreRazon": self.company,
                "NIF": nif_emisor,
                "NombreSistemaInformatico": "ERPNext/Frappe",
                "IdSistemaInformatico": "01",
                "Version": frappe.get_attr("aeat_module.__version__") if False else "1.0",
                "NumeroInstalacion": "001",
                "TipoUsoPosibleSoloVerifactu": "N",
                "TipoUsoPosibleMultiOT": "N",
                "IndicadorMultiplesOT": "N",
            },
            "FechaHoraHusoGenRegistro": fecha_hora_gen,
            "TipoHuella": "01",
            "Huella": vf_hash,
        }

        return {
            "Cabecera": {
                "ObligadoEmision": {"NIF": nif_emisor, "NombreRazon": self.company},
            },
            "RegistroFactura": [{"RegistroAlta": registro_alta}],
        }

    def build_signed_message(self, payload: dict, invoice_name: str, registro_tag: str = "RegistroAlta"):
        xml_msg = self.client.create_message(self.service, "RegFactuSistemaFacturacion", **payload)
        nodes = xml_msg.xpath(f'//*[local-name()="{registro_tag}"]')
        if not nodes:
            raise VeriFactuSoapError(f"No se generó el nodo {registro_tag} en el mensaje SOAP")
        registro = nodes[0]
        reg_id = f"ID-REG-{invoice_name}-{int(time.time())}"
        registro.set("Id", reg_id)

        signed_root = sign_registro(xml_msg, reg_id, self._key_pem(), self._cert_pem())
        return signed_root

    def _key_pem(self) -> bytes:
        return Path(self.key_path).read_bytes()

    def _cert_pem(self) -> bytes:
        return Path(self.cert_path).read_bytes()

    def send_alta(self, doc, vf_hash: str, prev_hash: Optional[str], tipo_factura: str,
                  fecha_expedicion: str, cuota_total: str, importe_total: str,
                  fecha_hora_gen: str, dry_run: bool = False) -> dict:
        payload = self.build_registro_alta_payload(
            doc, vf_hash, prev_hash, tipo_factura, fecha_expedicion, cuota_total, importe_total, fecha_hora_gen
        )
        signed_xml = self.build_signed_message(payload, doc.name)
        signed_bytes = etree.tostring(signed_xml, encoding="utf-8")

        if dry_run:
            return {"ok": True, "dry_run": True, "signed_xml": signed_bytes.decode("utf-8")}

        import requests
        session = requests.Session()
        session.cert = (self.cert_path, self.key_path)
        session.verify = True
        if self.cs.get("verifactu_ca_bundle"):
            session.verify = self.cs.get("verifactu_ca_bundle")
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        resp = session.post(self.address, data=signed_bytes, headers=headers, timeout=60)
        return self._parse_response(doc, payload, signed_bytes, resp)

    def build_registro_anulacion_payload(self, doc, vf_hash: str, prev_hash: Optional[str],
                                         fecha_expedicion: str, fecha_hora_gen: str) -> dict:
        nif_emisor = self.ctx.get("nif_emisor") or doc.get("company_tax_id") or ""
        num_serie_factura = doc.name

        registro_anulacion = {
            "IDVersion": "1.0",
            "IDFactura": {
                "IDEmisorFacturaAnulada": nif_emisor,
                "NumSerieFacturaAnulada": num_serie_factura,
                "FechaExpedicionFacturaAnulada": fecha_expedicion,
            },
            "Encadenamiento": (
                {"PrimerRegistro": "S"} if not prev_hash else
                {"RegistroAnterior": {
                    "IDEmisorFactura": nif_emisor,
                    "NumSerieFactura": num_serie_factura,
                    "FechaExpedicionFactura": fecha_expedicion,
                    "Huella": prev_hash,
                }}
            ),
            "SistemaInformatico": {
                "NombreRazon": self.company,
                "NIF": nif_emisor,
                "NombreSistemaInformatico": "ERPNext/Frappe",
                "IdSistemaInformatico": "01",
                "Version": "1.0",
                "NumeroInstalacion": "001",
                "TipoUsoPosibleSoloVerifactu": "N",
                "TipoUsoPosibleMultiOT": "N",
                "IndicadorMultiplesOT": "N",
            },
            "FechaHoraHusoGenRegistro": fecha_hora_gen,
            "TipoHuella": "01",
            "Huella": vf_hash,
        }

        return {
            "Cabecera": {
                "ObligadoEmision": {"NIF": nif_emisor, "NombreRazon": self.company},
            },
            "RegistroFactura": [{"RegistroAnulacion": registro_anulacion}],
        }

    def send_anulacion(self, doc, vf_hash: str, prev_hash: Optional[str],
                       fecha_expedicion: str, fecha_hora_gen: str, dry_run: bool = False) -> dict:
        payload = self.build_registro_anulacion_payload(doc, vf_hash, prev_hash, fecha_expedicion, fecha_hora_gen)
        signed_xml = self.build_signed_message(payload, doc.name, registro_tag="RegistroAnulacion")
        signed_bytes = etree.tostring(signed_xml, encoding="utf-8")

        if dry_run:
            return {"ok": True, "dry_run": True, "signed_xml": signed_bytes.decode("utf-8")}

        import requests
        session = requests.Session()
        session.cert = (self.cert_path, self.key_path)
        session.verify = True
        if self.cs.get("verifactu_ca_bundle"):
            session.verify = self.cs.get("verifactu_ca_bundle")
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        resp = session.post(self.address, data=signed_bytes, headers=headers, timeout=60)
        return self._parse_response(doc, payload, signed_bytes, resp)

    def _parse_response(self, doc, payload, signed_bytes, resp) -> dict:
        result = {
            "ok": False,
            "http_status": resp.status_code,
            "estado_envio": None,
            "codigos_error": [],
            "retryable": False,
            "raw_response": resp.text,
        }
        try:
            xml_resp = etree.fromstring(resp.content)
            codes = [n.text for n in xml_resp.xpath("//tikR:CodigoErrorRegistro", namespaces=_NS_RESPUESTA)]
            estado_nodes = xml_resp.xpath("//tikR:EstadoRegistro", namespaces=_NS_RESPUESTA)
            result["estado_envio"] = estado_nodes[0].text if estado_nodes else None
            result["codigos_error"] = classify_many(codes) if codes else []
            result["retryable"] = any_retryable(codes) if codes else (resp.status_code >= 500)
            result["ok"] = resp.status_code == 200 and not codes
        except Exception as e:
            result["parse_error"] = str(e)
            result["retryable"] = resp.status_code >= 500

        self._log_transmission(doc, payload, signed_bytes, resp, result)
        return result

    def _log_transmission(self, doc, payload, signed_bytes, resp, result):
        log = frappe.get_doc({
            "doctype": "AEAT Transmission Log",
            "company": self.company,
            "invoice": doc.name,
            "method": "POST",
            "endpoint": self.address,
            "payload_json": frappe.as_json(payload, indent=None),
            "status_code": resp.status_code,
            "response_json": resp.text[:100000],
            "status_text": result.get("estado_envio"),
            "error_code": (result["codigos_error"][0]["code"] if result.get("codigos_error") else None),
            "error_message": (result["codigos_error"][0]["description"] if result.get("codigos_error") else None),
        })
        log.insert(ignore_permissions=True)
