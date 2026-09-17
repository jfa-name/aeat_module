#!/usr/bin/env python3
"""
sign_and_send.py

Implementa process_queue_item(queue_item_name) para ser llamado por el worker.
Flujo:
 1. Cargar Queue Item y Sales Invoice
 2. Mapear Sales Invoice -> payload AEAT
 3. Calcular huella
 4. Crear XML (create_message)
 5. Firmar con xmlsec
 6. Enviar por mTLS
 7. Procesar respuesta y actualizar Queue Item
 8. Manejar reintentos automáticos si es necesario
"""
import io
import json
import hashlib
import base64
import subprocess
import time
import os
from pathlib import Path
from pprint import pformat
from datetime import datetime

from lxml import etree

import requests
from zeep import Client, Settings, helpers
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin

# Import frappe only when running inside Frappe context
try:
    import frappe
    FRAPPE_AVAILABLE = True
except ImportError:
    FRAPPE_AVAILABLE = False

# try import xmlsec
try:
    import xmlsec
    XMLSEC_AVAILABLE = True
except Exception:
    XMLSEC_AVAILABLE = False

# --------------------------
# CONFIG
# --------------------------
WSDL_PATH = Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl")
DOCS_DIRS = [
    Path("/home/develop/workspace/baygroup/apps/aeat_module/docs"),
    Path("/home/develop/workspace/baygroup/apps/docs"),
]
LOCAL_XSD_MAP = {
    "RespuestaConsultaLR.xsd.sanitized.imports_rewritten": DOCS_DIRS[0] / "RespuestaConsultaLR.xsd.sanitized.imports_rewritten",
    "SuministroInformacion.xsd.sanitized.imports_rewritten": DOCS_DIRS[0] / "SuministroInformacion.xsd.sanitized.imports_rewritten",
    "SuministroLR.xsd.sanitized.imports_rewritten": DOCS_DIRS[0] / "SuministroLR.xsd.sanitized.imports_rewritten",
    "ConsultaLR.xsd.sanitized.imports_rewritten": DOCS_DIRS[0] / "ConsultaLR.xsd.sanitized.imports_rewritten",
    "RespuestaSuministro.xsd.sanitized.imports_rewritten": DOCS_DIRS[0] / "RespuestaSuministro.xsd.sanitized.imports_rewritten",
    "xmldsig-core-schema.xsd.sanitized": DOCS_DIRS[1] / "xmldsig-core-schema.xsd.sanitized",
    "SuministroInformacion.xsd": DOCS_DIRS[0] / "SuministroInformacion.xsd",
}

# Paths de trazas - usar /var/log/aeat/ si existe, sino /tmp/
TRACE_DIR = Path("/var/log/aeat") if Path("/var/log/aeat").exists() else Path("/tmp")
TRACE_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------
# HELPERS
# --------------------------
def find_xmldsig_sanitized(docs_dirs):
    candidates = ["xmldsig-core-schema.xsd.sanitized", "xmldsig-core-schema.xsd"]
    for docs in docs_dirs:
        for name in candidates:
            p = docs / name
            if p.exists():
                return p.resolve()
    return None

XSD_SAN_PATH = find_xmldsig_sanitized(DOCS_DIRS)

class LocalMappingTransport(Transport):
    def __init__(self, local_map=None, docs_dirs=None, xsd_san_path=None, *args, **kwargs):
        from pathlib import Path
        super().__init__(*args, **kwargs)
        self.local_map = {k: Path(v) if not isinstance(v, Path) else v for k, v in (local_map or {}).items()}
        self.docs_dirs = docs_dirs or []
        self.xsd_san_path = Path(xsd_san_path) if xsd_san_path and not isinstance(xsd_san_path, Path) else xsd_san_path

    def _collapse_file_scheme(self, s):
        import re
        collapsed = re.sub(r'(file:/*)+', 'file:///', s)
        return re.sub(r'file://+', 'file:///', collapsed)

    def _find_local_by_basename(self, basename):
        p = self.local_map.get(basename)
        if p and p.exists():
            return p.resolve()
        for docs in self.docs_dirs:
            if not docs.exists():
                continue
            cand = docs / basename
            if cand.exists():
                return cand.resolve()
            for f in docs.iterdir():
                if f.is_file() and f.name.endswith(basename):
                    return f.resolve()
        return None

    def load(self, url):
        from pathlib import Path as PathClass
        url_str = str(url)
        url_str = self._collapse_file_scheme(url_str)

        if ("%24XSD_SAN" in url_str or "$XSD_SAN" in url_str) and self.xsd_san_path:
            return self.xsd_san_path.read_bytes()

        try:
            if url_str.startswith("file://"):
                local_candidate = url_str.replace("file://", "", 1)
                basename = PathClass(local_candidate).name
            else:
                basename = PathClass(url_str).name
        except Exception:
            basename = None

        if basename:
            local = self._find_local_by_basename(basename)
            if local and local.exists():
                return local.read_bytes()

        if url_str.startswith("file://"):
            pth = PathClass(url_str.replace("file://", "", 1))
            if pth.exists():
                return pth.read_bytes()

        try:
            return super().load(url_str)
        except Exception:
            if self.xsd_san_path:
                return self.xsd_san_path.read_bytes()
            raise

def compute_huella_verifactu_payload(payload):
    """
    Build AEAT input string and return SHA256 hex uppercase.
    Formato: IDEmisorFactura=X&NumSerieFactura=Y&...
    """
    r = payload["RegistroFactura"][0]["RegistroAlta"]
    idfac = r["IDFactura"]["IDEmisorFactura"]
    numserie = r["IDFactura"]["NumSerieFactura"]
    fechaexp = r["IDFactura"]["FechaExpedicionFactura"]
    tipofact = r["TipoFactura"]
    cuota_total = r.get("CuotaTotal", "")
    importe_total = r.get("ImporteTotal", "")
    huella_field = ""
    fechor = r.get("FechaHoraHusoGenRegistro", "")

    def fmt_amount(x):
        try:
            return "{:.2f}".format(float(x))
        except Exception:
            return str(x)

    cuota_total = fmt_amount(cuota_total)
    importe_total = fmt_amount(importe_total)

    parts = [
        f"IDEmisorFactura={idfac}",
        f"NumSerieFactura={numserie}",
        f"FechaExpedicionFactura={fechaexp}",
        f"TipoFactura={tipofact}",
        f"CuotaTotal={cuota_total}",
        f"ImporteTotal={importe_total}",
        f"Huella={huella_field}",
        f"FechaHoraHusoGenRegistro={fechor}"
    ]
    input_str = "&".join(parts)
    digest = hashlib.sha256(input_str.encode("utf-8")).hexdigest().upper()
    return digest

def sign_xml_with_xmlsec(xml_elem, key_path, cert_path):
    """Sign xml_elem in-place using python-xmlsec"""
    nodes = xml_elem.xpath('//*[local-name()="RegistroAlta"]')
    if not nodes:
        raise RuntimeError("RegistroAlta not found for signing")
    registro_alta = nodes[0]

    signature_node = xmlsec.template.create(
        registro_alta,
        xmlsec.Transform.EXCL_C14N,
        xmlsec.Transform.RSA_SHA256,
        ns='ds'
    )
    registro_alta.append(signature_node)

    ref = xmlsec.template.add_reference(signature_node, xmlsec.Transform.SHA256, uri="#" + registro_alta.get("Id"))
    xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
    xmlsec.template.add_transform(ref, xmlsec.Transform.EXCL_C14N)
    key_info = xmlsec.template.ensure_key_info(signature_node)
    xmlsec.template.add_x509_data(key_info)

    ctx = xmlsec.SignatureContext()
    key = xmlsec.Key.from_file(key_path, xmlsec.KeyFormat.PEM)
    key.load_cert_from_file(cert_path, xmlsec.KeyFormat.PEM)
    ctx.key = key
    xmlsec.tree.add_ids(xml_elem.getroottree(), ["Id"])
    ctx.sign(signature_node)
    return xml_elem

def find_invoice_info(obj):
    """Recursively search for invoice data in consulta response"""
    if isinstance(obj, dict):
        keys = set(obj.keys())
        want = {"IDEmisorFactura", "NumSerieFactura", "FechaExpedicionFactura", "Huella"}
        if want.issubset(keys):
            return {
                "IDEmisorFactura": obj.get("IDEmisorFactura"),
                "NumSerieFactura": obj.get("NumSerieFactura"),
                "FechaExpedicionFactura": obj.get("FechaExpedicionFactura"),
                "Huella": obj.get("Huella")
            }
        for v in obj.values():
            found = find_invoice_info(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_invoice_info(item)
            if found:
                return found
    return None

def attempt_consulta(proxy, cabecera_dict, prev_idpet):
    """Try to call ConsultaFactuSistemaFacturacion with different parameter names"""
    candidate_param_names = [
        "IdPeticionRegistro", "IdPeticion", "IDPeticionRegistro", "IdPeticionRegistroDuplicado",
        "IdPeticionRegistroDuplicadoConsulta", "IdPeticionRegistroAnterior", "Peticion", "IdRegistro"
    ]
    last_exc = None
    for pname in candidate_param_names:
        try:
            kwargs = {"Cabecera": cabecera_dict, pname: prev_idpet}
            resp = proxy.ConsultaFactuSistemaFacturacion(**kwargs)
            return resp
        except Exception as e:
            last_exc = e
    raise last_exc

# --------------------------
# MAPEO: Sales Invoice -> Payload AEAT
# --------------------------
def map_sales_invoice_to_payload(invoice_doc, company_settings, prev_hash=None):
    """
    Mapea Sales Invoice de ERPNext -> payload AEAT.
    IMPORTANTE: Ajusta campos según tu configuración y esquema AEAT.
    """
    # Obtener NIF emisor desde Company Settings
    nif_emisor = company_settings.get("nif_emisor") or invoice_doc.company_tax_id or ""
    
    # Determinar si es primera factura o tiene anterior
    is_first = prev_hash is None or prev_hash == ""
    
    # Serie y número
    series = invoice_doc.get("series") or invoice_doc.get("naming_series") or "F"
    numero = invoice_doc.name
    
    # Fechas
    fecha_exp = str(invoice_doc.posting_date)
    hora_gen = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+01:00")  # Ajustar huso horario
    
    # Tipo factura - mapear según tu lógica
    tipo_factura = "F1"  # Factura completa
    if invoice_doc.is_return:
        tipo_factura = "R1"  # Rectificativa
    
    # Calcular totales
    base_imponible = float(invoice_doc.net_total or 0)
    cuota_total = float(invoice_doc.total_taxes_and_charges or 0)
    importe_total = float(invoice_doc.grand_total or 0)
    
    # Desglose de impuestos - simplificado
    detalle_desglose = []
    for tax in invoice_doc.taxes:
        detalle_desglose.append({
            "Impuesto": "01",  # IVA
            "CalificacionOperacion": "S1",  # Sujeta y no exenta
            "ClaveRegimen": "01",  # General
            "TipoImpositivo": "{:.2f}".format(float(tax.rate or 0)),
            "BaseImponibleOimporteNoSujeto": "{:.2f}".format(base_imponible),
            "CuotaRepercutida": "{:.2f}".format(cuota_total)
        })
    
    # Si no hay impuestos, agregar uno por defecto
    if not detalle_desglose:
        detalle_desglose.append({
            "Impuesto": "01",
            "CalificacionOperacion": "S1",
            "ClaveRegimen": "01",
            "TipoImpositivo": "21.00",
            "BaseImponibleOimporteNoSujeto": "{:.2f}".format(base_imponible),
            "CuotaRepercutida": "{:.2f}".format(cuota_total)
        })
    
    # Sistema Informático
    sistema_informatico = {
        "NombreRazon": company_settings.get("company_name") or invoice_doc.company,
        "NIF": nif_emisor,
        "NombreSistemaInformatico": "ERPNext",
        "IdSistemaInformatico": "01",
        "Version": "1.0",
        "NumeroInstalacion": "001",
        "TipoUsoPosibleSoloVerifactu": "N",
        "TipoUsoPosibleMultiOT": "N",
        "IndicadorMultiplesOT": "N"
    }
    
    # RegistroAlta base
    registro_alta = {
        "IDVersion": "1.0",
        "IDFactura": {
            "IDEmisorFactura": nif_emisor,
            "NumSerieFactura": f"{series}-{numero}",
            "FechaExpedicionFactura": fecha_exp
        },
        "NombreRazonEmisor": company_settings.get("company_name") or invoice_doc.company,
        "DescripcionOperacion": invoice_doc.get("remarks") or "Suministro de bienes/servicios",
        "TipoFactura": tipo_factura,
        "Desglose": {
            "DetalleDesglose": detalle_desglose
        },
        "CuotaTotal": "{:.2f}".format(cuota_total),
        "ImporteTotal": "{:.2f}".format(importe_total),
        "SistemaInformatico": sistema_informatico,
        "FechaHoraHusoGenRegistro": hora_gen,
        "TipoHuella": "01",
        "Huella": "PLACEHOLDER"  # Se calculará después
    }
    
    # Encadenamiento
    if is_first:
        registro_alta["Encadenamiento"] = {"PrimerRegistro": "S"}
    else:
        # Buscar datos de factura anterior - DEBES IMPLEMENTAR LÓGICA REAL
        # Por ahora usamos valores del prev_hash
        registro_alta["Encadenamiento"] = {
            "RegistroAnterior": {
                "IDEmisorFactura": nif_emisor,
                "NumSerieFactura": "PREV_SERIE",  # TODO: obtener de BD
                "FechaExpedicionFactura": "PREV_FECHA",  # TODO: obtener de BD
                "Huella": prev_hash or ""
            }
        }
    
    # Payload completo
    payload = {
        "Cabecera": {
            "ObligadoEmision": {
                "NIF": nif_emisor,
                "NombreRazon": company_settings.get("company_name") or invoice_doc.company
            }
        },
        "RegistroFactura": [
            {
                "RegistroAlta": registro_alta
            }
        ]
    }
    
    return payload

# --------------------------
# FUNCIÓN PRINCIPAL: process_queue_item
# --------------------------
def process_queue_item(queue_item_name: str) -> dict:
    """
    Procesa un AEAT Queue Item.
    
    Returns:
        dict con {"ok": True/False, "error": str, "meta": {...}}
    """
    if not FRAPPE_AVAILABLE:
        return {"ok": False, "error": "Frappe not available"}
    
    try:
        # 1. Cargar Queue Item
        queue_item = frappe.get_doc("AEAT Queue Item", queue_item_name)
        invoice_name = queue_item.invoice
        company = queue_item.company
        
        # 2. Cargar Sales Invoice
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        
        # 3. Cargar Company Settings
        company_settings = frappe.get_doc("AEAT Company Settings", {"company": company})
        
        # 4. Obtener certificados y configuración
        cert_path = company_settings.get("mtls_client_cert_path") or "/etc/ssl/aeat/cert.pem"
        key_path = company_settings.get("mtls_client_key_path") or "/etc/ssl/aeat/key.pem"
        ca_bundle = company_settings.get("verifactu_ca_bundle") or "/etc/ssl/aeat/ca-bundle.pem"
        
        # Verificar que existan
        if not Path(cert_path).exists():
            return {"ok": False, "error": f"Certificate not found: {cert_path}"}
        if not Path(key_path).exists():
            return {"ok": False, "error": f"Private key not found: {key_path}"}
        
        # 5. Determinar si usar preprod
        use_preprod = company_settings.get("verifactu_use_preprod") or True
        
        # 6. Setup Zeep client
        session = requests.Session()
        session.cert = (cert_path, key_path)
        session.verify = ca_bundle if Path(ca_bundle).exists() else True
        
        transport = LocalMappingTransport(
            local_map=LOCAL_XSD_MAP,
            docs_dirs=DOCS_DIRS,
            xsd_san_path=XSD_SAN_PATH,
            session=session,
            timeout=60
        )
        
        settings = Settings(strict=False, xml_huge_tree=True)
        history = HistoryPlugin()
        
        client = Client(
            wsdl=WSDL_PATH.resolve().as_uri(),
            transport=transport,
            settings=settings,
            plugins=[history]
        )
        
        svc = client.wsdl.services.get("sfVerifactu")
        port_obj = next(iter(svc.ports.values()))
        binding_qname = port_obj.binding.name
        
        # Resolver endpoint
        address = None
        if hasattr(port_obj, 'binding_options') and 'address' in port_obj.binding_options:
            address = port_obj.binding_options['address']
        
        if not address:
            for definition in client.wsdl._definitions.values():
                for svc_def in definition.services.values():
                    if svc_def.name == svc.name:
                        for port_def in svc_def.ports.values():
                            if port_def.name == port_obj.name:
                                address = port_def.binding_options.get('address')
                                break
                        break
                if address:
                    break
        
        if use_preprod:
            address = address.replace("www1.agenciatributaria.gob.es", "prewww1.aeat.es")
            address = address.replace("www2.agenciatributaria.gob.es", "prewww2.aeat.es")
        
        proxy = client.create_service(binding_qname, address)
        
        # 7. Obtener prev_hash desde metadata o calcular
        metadata = json.loads(queue_item.metadata or "{}") if queue_item.metadata else {}
        prev_hash = metadata.get("prev_hash")
        
        # 8. Mapear Sales Invoice -> Payload
        payload = map_sales_invoice_to_payload(invoice, company_settings, prev_hash)
        
        # 9. Función interna para intentar envío
        def do_send_attempt(attempt_num=1):
            # 9.1. Crear XML preview
            xml_msg = client.create_message(proxy, 'RegFactuSistemaFacturacion', **payload)
            
            # 9.2. Calcular huella
            huella_hex = compute_huella_verifactu_payload(payload)
            payload["RegistroFactura"][0]["RegistroAlta"]["Huella"] = huella_hex
            payload["RegistroFactura"][0]["RegistroAlta"]["TipoHuella"] = "01"
            
            # 9.3. Recrear XML con huella
            xml_msg = client.create_message(proxy, 'RegFactuSistemaFacturacion', **payload)
            
            # 9.4. Añadir Id a RegistroAlta
            nodes = xml_msg.xpath('//*[local-name()="RegistroAlta"]')
            if not nodes:
                raise RuntimeError("RegistroAlta not found")
            registro_alta = nodes[0]
            if registro_alta.get("Id") is None:
                registro_alta.set("Id", f"ID-REG-{invoice_name}-{int(time.time())}")
            
            # 9.5. Firmar
            if not XMLSEC_AVAILABLE:
                return {"ok": False, "error": "python-xmlsec not available"}
            
            xmlsec.tree.add_ids(xml_msg.getroottree(), ["Id"])
            sign_xml_with_xmlsec(xml_msg, key_path=key_path, cert_path=cert_path)
            
            signed_bytes = etree.tostring(xml_msg, pretty_print=True, encoding='utf-8')
            
            # 9.6. Guardar sent
            sent_path = TRACE_DIR / f"aeat_sent_{queue_item_name}_attempt{attempt_num}.xml"
            sent_path.write_bytes(signed_bytes)
            
            # 9.7. Enviar
            send_session = requests.Session()
            send_session.cert = (cert_path, key_path)
            send_session.verify = ca_bundle if Path(ca_bundle).exists() else True
            headers = {'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': ''}
            
            resp_http = send_session.post(address, data=signed_bytes, headers=headers, timeout=60)
            
            # 9.8. Guardar received
            received_path = TRACE_DIR / f"aeat_received_{queue_item_name}_attempt{attempt_num}.xml"
            received_path.write_bytes(resp_http.content)
            
            return {
                "response": resp_http,
                "sent_path": str(sent_path),
                "received_path": str(received_path),
                "huella": huella_hex
            }
        
        # 10. Primer intento
        result = do_send_attempt(1)
        resp_http = result["response"]
        
        # 11. Parsear respuesta
        try:
            doc = etree.fromstring(resp_http.content)
            ns = {
                'tikR': 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/RespuestaSuministro.xsd',
                'tik': 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd'
            }
            
            # Buscar códigos de error
            code_nodes = doc.xpath('//tikR:CodigoErrorRegistro', namespaces=ns)
            codes = [n.text for n in code_nodes] if code_nodes else []
            
            # Buscar RegistroDuplicado
            dup_nodes = doc.xpath('//tikR:RegistroDuplicado//tik:IdPeticionRegistroDuplicado', namespaces=ns)
            prev_idpet = dup_nodes[0].text if dup_nodes else None
            
            # Decisión de reintento
            trigger_retry = False
            if prev_idpet or "2007" in codes:
                trigger_retry = True
            
            if trigger_retry and queue_item.attempts < 3:
                # Intentar consulta y reintento
                frappe.log_error(f"AEAT: Attempting auto-retry for {queue_item_name}", "AEAT Auto-Retry")
                
                cabecera = {
                    "ObligadoEmision": {
                        "NIF": payload["Cabecera"]["ObligadoEmision"]["NIF"],
                        "NombreRazon": payload["Cabecera"]["ObligadoEmision"]["NombreRazon"]
                    }
                }
                
                found_prev = None
                if prev_idpet:
                    try:
                        consulta_resp = attempt_consulta(proxy, cabecera, prev_idpet)
                        s = helpers.serialize_object(consulta_resp)
                        found_prev = find_invoice_info(s)
                    except Exception as e:
                        frappe.log_error(str(e), "AEAT Consulta Failed")
                
                if found_prev:
                    # Actualizar payload con RegistroAnterior
                    payload["RegistroFactura"][0]["RegistroAlta"]["Encadenamiento"] = {
                        "RegistroAnterior": {
                            "IDEmisorFactura": found_prev["IDEmisorFactura"],
                            "NumSerieFactura": found_prev["NumSerieFactura"],
                            "FechaExpedicionFactura": found_prev["FechaExpedicionFactura"],
                            "Huella": found_prev["Huella"]
                        }
                    }
                    
                    # Segundo intento
                    result2 = do_send_attempt(2)
                    resp_http = result2["response"]
                    result = result2
                    
                    # Re-parsear respuesta
                    doc = etree.fromstring(resp_http.content)
                    code_nodes = doc.xpath('//tikR:CodigoErrorRegistro', namespaces=ns)
                    codes = [n.text for n in code_nodes] if code_nodes else []
            
            # 12. Determinar estado final
            if resp_http.status_code == 200 and not codes:
                status = "Accepted"
            elif codes:
                status = "AcceptedWithErrors" if "1000" in codes else "Failed"
            else:
                status = "Failed"
            
            # 13. Actualizar Queue Item
            metadata_updated = metadata.copy()
            metadata_updated.update({
                "huella": result["huella"],
                "sent_path": result["sent_path"],
                "received_path": result["received_path"],
                "response_codes": codes,
                "http_status": resp_http.status_code
            })
            
            return {
                "ok": status in ["Accepted", "AcceptedWithErrors"],
                "meta": {
                    "status": status,
                    "response_code": resp_http.status_code,
                    "response_text": resp_http.text[:500],
                    "sent_path": result["sent_path"],
                    "received_path": result["received_path"],
                    "metadata": json.dumps(metadata_updated, ensure_ascii=False)
                }
            }
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"AEAT Response Parse Error: {queue_item_name}")
            return {
                "ok": False,
                "error": f"Failed to parse response: {str(e)}",
                "meta": {
                    "status": "Failed",
                    "sent_path": result.get("sent_path"),
                    "received_path": result.get("received_path")
                }
            }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"AEAT Process Error: {queue_item_name}")
        return {
            "ok": False,
            "error": str(e)
        }

# --------------------------
# Main para testing standalone
# --------------------------
def main():
    """Para testing directo del script"""
    print("This script is meant to be imported, not run directly.")
    print("Use: from aeat_module.scripts.sign_and_send import process_queue_item")

if __name__ == "__main__":
    main()