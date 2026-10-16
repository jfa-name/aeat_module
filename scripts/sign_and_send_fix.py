#!/usr/bin/env python3
"""
sign_and_send_fix.py
Extensión de sign_and_send.py que:
 - inspecciona los XSDs locales para encontrar VersionType/IDVersion enumeraciones
 - normaliza FechaExpedicionFactura a YYYY-MM-DD si hace falta
 - si encuentra enumeraciones para VersionType, aplica el primer valor válido automáticamente
 - sigue con el flujo: preview -> huella -> firma -> envío
"""
from pathlib import Path
import re
import io
import json
import hashlib
import base64
import subprocess
from lxml import etree

import requests
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin

try:
    import xmlsec
    XMLSEC_AVAILABLE = True
except Exception:
    XMLSEC_AVAILABLE = False

# CONFIG (ajusta si hace falta)
WSDL_PATH = Path("/path/to/your/frappe-bench/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl")
DOCS_DIRS = [
    Path("/path/to/your/frappe-bench/apps/aeat_module/docs"),
    Path("/path/to/your/frappe-bench/apps/docs"),
]
CERT = "/etc/ssl/aeat/cert.pem"
KEY = "/etc/ssl/aeat/key.pem"
CA_BUNDLE = "/etc/ssl/aeat/ca-bundle.pem"
USE_PREPROD = True

# temp files
TO_SIGN_FILE = Path("/tmp/to_sign.xml")
SIGNED_FILE = Path("/tmp/signed.xml")

# ---------------- Helpers to inspect XSDs ----------------
def find_version_enums(xsd_dirs):
    """
    Busca simpleType name=VersionType o element name='IDVersion' en los XSDs y devuelve enumerations encontradas.
    Retorna lista de valores (posible vacía).
    """
    ns = {"xs": "http://www.w3.org/2001/XMLSchema"}
    enums = []
    for base in xsd_dirs:
        for p in Path(base).rglob("*.xsd"):
            try:
                txt = p.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            # quick textual search for the type name
            if "VersionType" in txt or "IDVersion" in txt or "IDVersion" in p.name:
                try:
                    doc = etree.parse(str(p))
                except Exception:
                    continue
                # buscar simpleType name="VersionType"
                for st in doc.findall('.//xs:simpleType[@name="VersionType"]', namespaces=ns):
                    # buscar enumerations
                    for enum in st.findall('.//xs:enumeration', namespaces=ns):
                        val = enum.get("value")
                        if val:
                            enums.append(val)
                # buscar element name="IDVersion" con tipo simple inline
                for el in doc.findall('.//xs:element[@name="IDVersion"]', namespaces=ns):
                    # si element ref a tipo con restriction en otro sitio, we rely on VersionType above
                    # si es simpleType en site:
                    st = el.find('.//xs:simpleType', namespaces=ns)
                    if st is not None:
                        for enum in st.findall('.//xs:enumeration', namespaces=ns):
                            val = enum.get("value")
                            if val:
                                enums.append(val)
    # deduplicate preserving order
    seen = set()
    out = []
    for v in enums:
        if v not in seen:
            out.append(v); seen.add(v)
    return out

def normalize_fecha_iso(payload):
    """
    Normalize IDFactura.FechaExpedicionFactura to YYYY-MM-DD if it looks like DD-MM-YYYY or other common variants.
    Returns True if modified.
    """
    import datetime
    try:
        r = payload["RegistroFactura"][0]["RegistroAlta"]
        fid = r.get("IDFactura", {})
        if not fid:
            return False
        raw = fid.get("FechaExpedicionFactura")
        if not raw:
            return False
        # If already ISO YYYY-MM-DD, done
        if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
            return False
        # Try parse common formats: DD-MM-YYYY, DD/MM/YYYY, YYYYMMDD, etc.
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y%m%d", "%Y/%m/%d"):
            try:
                dt = datetime.datetime.strptime(raw, fmt)
                fid["FechaExpedicionFactura"] = dt.date().isoformat()
                r["IDFactura"] = fid
                return True
            except Exception:
                continue
        # last resort: attempt ISO parse with fromisoformat
        try:
            dt = datetime.datetime.fromisoformat(raw)
            fid["FechaExpedicionFactura"] = dt.date().isoformat()
            r["IDFactura"] = fid
            return True
        except Exception:
            return False
    except Exception:
        return False

# ---------------- small helpers reused ----------------
def compute_huella_from_xml_element(xml_elem):
    try:
        buf = io.BytesIO()
        xml_elem.getroottree().write_c14n(buf, exclusive=True, with_comments=False)
        xml_bytes = buf.getvalue()
    except Exception:
        xml_bytes = etree.tostring(xml_elem, pretty_print=False, encoding='utf-8')
    digest = hashlib.sha256(xml_bytes).digest()
    return base64.b64encode(digest).decode()

def save_bytes(path: Path, data: bytes):
    path.write_bytes(data)
    print(f"Saved {path}")

# ---------------- Main (simplified; integrate with your existing flow) ----------------
def main():
    # inspect XSD for VersionType enumerations
    enums = find_version_enums(DOCS_DIRS)
    print("VersionType enumerations found in XSDs:", enums)

    # (example) If enums non-empty, pick first as default for IDVersion
    # integrate with your payload builder: payload["RegistroFactura"][0]["RegistroAlta"]["IDVersion"] = enums[0]
    # Also make sure the FechaExpedicionFactura is normalized
    # ... (here we only demonstrate the inspections)
    return enums

if __name__ == "__main__":
    main()
