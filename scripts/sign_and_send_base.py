#!/usr/bin/env python3
"""
sign_and_send.py

Flujo completo:
 - crea mensaje (create_message) para RegFactuSistemaFacturacion
 - calcula huella según cadena esperada por AEAT (SHA256 HEX)
 - inserta huella, firma (xmlsec) y envía por mTLS
 - si AEAT responde con RegistroDuplicado / 2007 (primer registro incorrecto),
   hace una consulta automática (ConsultaFactuSistemaFacturacion) usando
   IdPeticionRegistroDuplicado para recuperar los datos de la factura anterior,
   rellena Encadenamiento.RegistroAnterior con IDEmisorFactura/NumSerieFactura/FechaExpedicionFactura/Huella
   y reintenta enviar (solo 1 reintento automático).
 - guarda trazas en /tmp para depuración.

Notas:
 - Ajusta rutas WSDL/XSD/certificados si es necesario.
 - Requiere python-xmlsec o xmlsec1 CLI para firmar; requests para mTLS.
"""
import io
import json
import hashlib
import base64
import subprocess
import time
from pathlib import Path
from pprint import pformat

from lxml import etree

import requests
from zeep import Client, Settings, helpers
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin

# try import xmlsec; if not available we will fallback to xmlsec1 CLI
try:
    import xmlsec
    XMLSEC_AVAILABLE = True
except Exception:
    XMLSEC_AVAILABLE = False

# --------------------------
# CONFIG - ajusta según tu entorno
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
CERT = "/etc/ssl/aeat/cert.pem"
KEY = "/etc/ssl/aeat/key.pem"
CA_BUNDLE = "/etc/ssl/aeat/ca-bundle.pem"
USE_PREPROD = True

# Configuración de factura
IS_FIRST_INVOICE = False  # Cambiar a False si no es la primera factura

# Output files (tmp)
TO_SIGN_FILE = Path("/tmp/to_sign.xml")
SIGNED_FILE = Path("/tmp/signed.xml")
LAST_SENT = Path("/tmp/aeat_last_sent.xml")
LAST_RECEIVED = Path("/tmp/aeat_last_received.xml")
LAST_RECEIVED_JSON = Path("/tmp/aeat_last_received.json")
XMLSEC_CLI_LOG = Path("/tmp/xmlsec.log")

# --------------------------
# HELPER: Find xmldsig
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

# --------------------------
# LocalMappingTransport (Zeep)
# --------------------------
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
        collapsed = re.sub(r'file://+', 'file:///', collapsed)
        return collapsed

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

# --------------------------
# Helpers: huella, xml signing, utils
# --------------------------
def compute_huella_verifactu_payload(payload):
    """
    Build the AEAT input string and return SHA256 hex uppercase.
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
    print("Huella input string:", input_str)
    digest = hashlib.sha256(input_str.encode("utf-8")).hexdigest().upper()
    return digest

def sign_xml_with_xmlsec(xml_elem, key_path=KEY, cert_path=CERT):
    """
    Sign xml_elem in-place using python-xmlsec. Assumes xml_elem is the Envelope
    and that registro_alta element has been marked with attribute Id.
    """
    nodes = xml_elem.xpath('//*[local-name()="RegistroAlta"]')
    if not nodes:
        raise RuntimeError("RegistroAlta not found for signing")
    registro_alta = nodes[0]

    # create template and append to registro_alta (at end)
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

def save_bytes(path: Path, data: bytes):
    path.write_bytes(data)
    print(f"Saved {path}")

def serialize_resp_to_json(resp, path: Path):
    try:
        r = helpers.serialize_object(resp)
    except Exception:
        r = str(resp)
    path.write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    print(f"Wrote parsed response to {path}")

# recursive search util to find invoice data in consulta response
def find_invoice_info(obj):
    """
    Recursively search a serialized zeep object/dict/list for a dict that contains
    IDEmisorFactura, NumSerieFactura, FechaExpedicionFactura and Huella.
    Returns dict with those keys or None.
    """
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

# attempt to call ConsultaFactuSistemaFacturacion with a variety of param names
def attempt_consulta(proxy, cabecera_dict, prev_idpet):
    """
    Try to call proxy.ConsultaFactuSistemaFacturacion with different parameter names.
    Returns parsed response object (zeep) on success or raises last exception.
    """
    candidate_param_names = [
        "IdPeticionRegistro", "IdPeticion", "IDPeticionRegistro", "IdPeticionRegistroDuplicado",
        "IdPeticionRegistroDuplicadoConsulta", "IdPeticionRegistroAnterior", "Peticion", "IdRegistro"
    ]
    last_exc = None
    for pname in candidate_param_names:
        try:
            kwargs = {"Cabecera": cabecera_dict, pname: prev_idpet}
            print(f"Trying Consulta with param '{pname}'")
            resp = proxy.ConsultaFactuSistemaFacturacion(**kwargs)
            return resp
        except Exception as e:
            last_exc = e
    raise last_exc

# --------------------------
# Main flow (with automatic consulta+reintento)
# --------------------------
def main():
    print("=" * 80)
    print("Sign and Send - AEAT Verifactu (with auto consulta/retry)")
    print("=" * 80)

    # basic checks
    if not WSDL_PATH.exists():
        raise SystemExit(f"WSDL not found: {WSDL_PATH}")
    if not Path(CERT).exists():
        raise SystemExit(f"Certificate not found: {CERT}")
    if not Path(KEY).exists():
        raise SystemExit(f"Private key not found: {KEY}")
    if not Path(CA_BUNDLE).exists():
        raise SystemExit(f"CA bundle not found: {CA_BUNDLE}")

    # setup client/proxy
    session = requests.Session()
    session.cert = (CERT, KEY)
    session.verify = CA_BUNDLE

    transport = LocalMappingTransport(local_map=LOCAL_XSD_MAP, docs_dirs=DOCS_DIRS, xsd_san_path=XSD_SAN_PATH, session=session, timeout=60)
    settings = Settings(strict=False, xml_huge_tree=True)
    history = HistoryPlugin()
    client = Client(wsdl=WSDL_PATH.resolve().as_uri(), transport=transport, settings=settings, plugins=[history])

    svc = client.wsdl.services.get("sfVerifactu")
    port_obj = next(iter(svc.ports.values()))
    binding_qname = port_obj.binding.name

    # resolve address
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
    if USE_PREPROD:
        address = address.replace("www1.agenciatributaria.gob.es", "prewww1.aeat.es").replace("www2.agenciatributaria.gob.es", "prewww2.aeat.es")

    proxy = client.create_service(binding_qname, address)
    print(f"Proxy ready (endpoint={address})")

    # Build base payload with Encadenamiento
    # IMPORTANTE: Encadenamiento es OBLIGATORIO - usar PrimerRegistro o RegistroAnterior
    base_registro_alta = {
        "IDVersion": "1.0",
        "IDFactura": {
            "IDEmisorFactura": "35429235X",
            "NumSerieFactura": "F-0003",
            "FechaExpedicionFactura": "25-11-2025"
        },
        "NombreRazonEmisor": "Juan Ejemplo García",
        "DescripcionOperacion": "Suministro de servicios - prueba",
        "TipoFactura": "F2",
        "Desglose": {
            "DetalleDesglose": [
                {
                    "Impuesto": "01",
                    "CalificacionOperacion": "S1",
                    "ClaveRegimen": "01",
                    "TipoImpositivo": "21.00",
                    "BaseImponibleOimporteNoSujeto": "82.64",
                    "CuotaRepercutida": "17.36"
                }
            ]
        },
        "CuotaTotal": "17.36",
        "ImporteTotal": "100.00",
        "SistemaInformatico": {
            "NombreRazon": "Felipe Acosta",
            "NIF": "35429235X",
            "NombreSistemaInformatico": "ERPNext",
            "IdSistemaInformatico": "01",
            "Version": "1.0",
            "NumeroInstalacion": "001",
            "TipoUsoPosibleSoloVerifactu": "N",
            "TipoUsoPosibleMultiOT": "N",
            "IndicadorMultiplesOT": "N"
        },
        "FechaHoraHusoGenRegistro": "2025-11-25T10:00:00+01:00",
        "TipoHuella": "01",
        "Huella": "PLACEHOLDER"
    }

    # Añadir Encadenamiento según si es primera factura o no
    if IS_FIRST_INVOICE:
        base_registro_alta["Encadenamiento"] = {
            "PrimerRegistro": "S"
        }
        print("✓ Configurado como primera factura (PrimerRegistro=S)")
    else:
        # Si no es primera, necesitas los datos de la factura anterior
        # Este ejemplo usa valores placeholder - deberías obtenerlos de tu BD
        base_registro_alta["Encadenamiento"] = {
            "RegistroAnterior": {
                "IDEmisorFactura": "35429235X",
                "NumSerieFactura": "F-0002",
                "FechaExpedicionFactura": "24-11-2025",
                "Huella": "HUELLA_ANTERIOR_PLACEHOLDER"
            }
        }
        print("✓ Configurado con RegistroAnterior (no es primera factura)")

    payload = {
        "Cabecera": {
            "ObligadoEmision": {
                "NIF": "35429235X",
                "NombreRazon": "Juan Ejemplo García"
            }
        },
        "RegistroFactura": [
            {
                "RegistroAlta": base_registro_alta
            }
        ]
    }

    # Primary attempt + optional retry if needed
    def do_send_attempt(attempt_index=1):
        print(f"\n--- Attempt {attempt_index} ---")
        # 1) create preview
        xml_msg = client.create_message(proxy, 'RegFactuSistemaFacturacion', **payload)
        save_bytes(TO_SIGN_FILE, etree.tostring(xml_msg, pretty_print=True, encoding='utf-8'))

        # 2) compute huella (AEAT expected)
        huella_hex = compute_huella_verifactu_payload(payload)
        payload["RegistroFactura"][0]["RegistroAlta"]["Huella"] = huella_hex
        payload["RegistroFactura"][0]["RegistroAlta"]["TipoHuella"] = "01"

        # 3) recreate xml_msg and save
        xml_msg = client.create_message(proxy, 'RegFactuSistemaFacturacion', **payload)
        save_bytes(TO_SIGN_FILE, etree.tostring(xml_msg, pretty_print=True, encoding='utf-8'))

        # 4) ensure Id on RegistroAlta
        nodes = xml_msg.xpath('//*[local-name()="RegistroAlta"]')
        if not nodes:
            raise SystemExit("RegistroAlta not found for signing")
        registro_alta = nodes[0]
        if registro_alta.get("Id") is None:
            registro_alta.set("Id", f"ID-REG-{int(time.time())}")

        # register id and sign
        if XMLSEC_AVAILABLE:
            xmlsec.tree.add_ids(xml_msg.getroottree(), ["Id"])
            sign_xml_with_xmlsec(xml_msg, key_path=KEY, cert_path=CERT)
        else:
            raise SystemExit("python-xmlsec required (or implement xmlsec1 fallback)")

        signed_bytes = etree.tostring(xml_msg, pretty_print=True, encoding='utf-8')
        save_bytes(SIGNED_FILE, signed_bytes)

        # 5) send
        session = requests.Session()
        session.cert = (CERT, KEY)
        session.verify = CA_BUNDLE
        headers = {'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': ''}
        resp_http = session.post(address, data=signed_bytes, headers=headers, timeout=60)

        # save sent/received
        attempt_suffix = f".attempt{attempt_index}"
        save_bytes(LAST_SENT.with_suffix(LAST_SENT.suffix + attempt_suffix), signed_bytes)
        Path("/tmp/aeat_last_received_raw.xml").write_text(resp_http.text, encoding='utf-8')

        try:
            root = etree.fromstring(resp_http.content)
            pretty = etree.tostring(root, pretty_print=True, encoding='utf-8')
            save_bytes(LAST_RECEIVED.with_suffix(LAST_RECEIVED.suffix + attempt_suffix), pretty)
        except Exception:
            LAST_RECEIVED.with_suffix(LAST_RECEIVED.suffix + attempt_suffix).write_text(resp_http.text, encoding='utf-8')

        try:
            serialize_resp_to_json(resp_http.text, LAST_RECEIVED_JSON.with_suffix(".attempt" + str(attempt_index) + ".json"))
        except Exception:
            pass

        return resp_http

    # Primary attempt
    resp_http = do_send_attempt(1)

    # Parse response, detect RegistroDuplicado or error 2007
    doc = etree.fromstring(resp_http.content)
    ns = {
        'tikR': 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/RespuestaSuministro.xsd',
        'tik': 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd'
    }
    # Check for RegistroDuplicado id
    dup_nodes = doc.xpath('//tikR:RegistroDuplicado//tik:IdPeticionRegistroDuplicado', namespaces=ns)
    prev_idpet = dup_nodes[0].text if dup_nodes else None

    # Check for specific error codes in textual response
    code_nodes = doc.xpath('//tikR:CodigoErrorRegistro', namespaces=ns)
    codes = [n.text for n in code_nodes] if code_nodes else []

    # If we found a RegistroDuplicado id OR error 2007, attempt automatic consulta+reintento once
    trigger_retry = False
    if prev_idpet:
        print("Found RegistroDuplicado IdPeticionRegistroDuplicado:", prev_idpet)
        trigger_retry = True
    elif "2007" in codes:
        print("Detected 2007 in response codes")
        trigger_retry = True

    if trigger_retry:
        print("\nAttempting automatic consulta to retrieve invoice data for RegistroAnterior...")

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
                print("Consulta returned, serializing...")
                s = helpers.serialize_object(consulta_resp)
                found_prev = find_invoice_info(s)
                print("Found prev invoice info in consulta response:", found_prev)
            except Exception as e:
                print("Consulta attempt failed:", repr(e))

        if not found_prev:
            try:
                p = LAST_RECEIVED.with_suffix(LAST_RECEIVED.suffix + ".attempt1")
                if p.exists():
                    doc2 = etree.parse(str(p))
                    h = doc2.xpath('//tik:Huella', namespaces=ns)
                    sid = doc2.xpath('//tik:NumSerieFactura', namespaces=ns)
                    sdate = doc2.xpath('//tik:FechaExpedicionFactura', namespaces=ns)
                    sadmin = doc2.xpath('//tik:IDEmisorFactura', namespaces=ns)
                    if h and sid and sdate and sadmin:
                        found_prev = {
                            "IDEmisorFactura": sadmin[0].text,
                            "NumSerieFactura": sid[0].text,
                            "FechaExpedicionFactura": sdate[0].text,
                            "Huella": h[0].text
                        }
                        print("Found prev invoice info in saved response:", found_prev)
            except Exception as e:
                print("Error searching saved response for previous invoice info:", e)

        if not found_prev:
            print("Could not retrieve previous invoice data automatically. Aborting automatic retry.")
        else:
            # inject RegistroAnterior into payload
            payload["RegistroFactura"][0]["RegistroAlta"]["Encadenamiento"] = {
                "RegistroAnterior": {
                    "IDEmisorFactura": found_prev["IDEmisorFactura"],
                    "NumSerieFactura": found_prev["NumSerieFactura"],
                    "FechaExpedicionFactura": found_prev["FechaExpedicionFactura"],
                    "Huella": found_prev["Huella"]
                }
            }
            print("Injected RegistroAnterior into payload:", pformat(payload["RegistroFactura"][0]["RegistroAlta"]["Encadenamiento"]))

            resp_http2 = do_send_attempt(2)
            print("\nSecond attempt response saved. See /tmp files for traces.")
            print(resp_http2.text[:2000])

    print("\nFinished. Check /tmp/aeat_last_sent*.attempt* and /tmp/aeat_last_received*.attempt* for traces.")

if __name__ == "__main__":
    main()