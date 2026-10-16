#!/usr/bin/env python3
"""
Ejemplo de Transport personalizado para Zeep que mapea ciertas URLs de XSD a
ficheros locales sanitizados y corrige URLs malformadas como "https:///home/..."
Cópialo/pegalo entero en bench console y ejecútalo en una sola celda.
"""
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
import requests
from pathlib import Path
import re

# Mapea nombres relevantes a ficheros locales existentes (ajusta rutas si hace falta)
LOCAL_XSD_MAP = {
    "SuministroInformacion.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/docs/SuministroInformacion.xsd.sanitized.imports_rewritten"),
    "SuministroLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/docs/SuministroLR.xsd.sanitized.imports_rewritten"),
    "ConsultaLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/docs/ConsultaLR.xsd.sanitized.imports_rewritten"),
    "RespuestaConsultaLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/docs/RespuestaConsultaLR.xsd.sanitized.imports_rewritten"),
    "RespuestaSuministro.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/docs/RespuestaSuministro.xsd.sanitized.imports_rewritten"),
    "xmldsig-core-schema.xsd.sanitized": Path("/path/to/your/frappe-bench/apps/docs/xmldsig-core-schema.xsd.sanitized"),
}

class LocalMappingTransport(Transport):
    """
    Transport que intercepta las cargas de Zeep y:
      - si la URL contiene cierto nombre de XSD conocido, devuelve el fichero local
      - corrige URLs malformadas del tipo https:///home/... convirtiéndolas a file:///
      - normaliza duplicados de file://file://... si aparecen
      - en caso contrario delega en Transport.load normal
    """
    def load(self, url):
        url_str = str(url)
        # 1) Mapeo directo por nombre conocido
        for name, path in LOCAL_XSD_MAP.items():
            if name in url_str:
                if path.exists():
                    print(f"LocalMappingTransport: mapping {url_str} -> {path}")
                    return path.read_bytes()
                else:
                    print(f"LocalMappingTransport: expected local file not found: {path}")

        # 2) Corregir patrones como https:///home/... o http:///home/... -> file:///home/...
        m = re.match(r'^https?://(/.+)$', url_str)
        if m:
            corrected_path = Path(m.group(1))
            corrected_uri = "file://" + m.group(1)
            if corrected_path.exists():
                print(f"LocalMappingTransport: corrected {url_str} -> {corrected_uri}")
                return corrected_path.read_bytes()

        # 3) Normalizar duplicados file://file://... y leer el fichero resultante si existe
        if url_str.startswith("file://") and "file://file://" in url_str:
            norm = url_str.replace("file://file://", "file://")
            # extraer el path después de file:// (solo la primera aparición)
            local_path = norm.replace("file://", "", 1)
            p = Path(local_path)
            if p.exists():
                print(f"LocalMappingTransport: normalized {url_str} -> {p}")
                return p.read_bytes()

        # 4) Si la URL es file:///abs/path sin scheme duplicado, intentar abrirla (fallará si no existe)
        if url_str.startswith("file://"):
            local_path = url_str.replace("file://", "", 1)
            p = Path(local_path)
            if p.exists():
                print(f"LocalMappingTransport: loading file uri {p}")
                return p.read_bytes()

        # 5) fallback: delegar al comportamiento por defecto
        return super().load(url)

# ------------------------
# Uso: crea el client con este transport y muestra servicios/operaciones
# ------------------------

wsdl_path = Path("/path/to/your/frappe-bench/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.wsdl")
wsdl_uri = wsdl_path.resolve().as_uri()
print("Using WSDL URI:", wsdl_uri)

session = requests.Session()
# Asegúrate de que estas rutas a certificados son correctas para tu entorno
session.cert = ("/etc/ssl/aeat/cert.pem", "/etc/ssl/aeat/key.pem")
session.verify = "/etc/ssl/aeat/ca-bundle.pem"

transport = LocalMappingTransport(session=session, timeout=60)
settings = Settings(strict=False, xml_huge_tree=True)
history = HistoryPlugin()

client = Client(wsdl=wsdl_uri, transport=transport, settings=settings, plugins=[history])
print("WSDL cargado OK. Services:", [s.name for s in client.wsdl.services.values()])

# seleccionar service por nombre
service_name = "sfVerifactu"
svc = None
for s in client.wsdl.services.values():
    if s.name == service_name:
        svc = s
        break

if not svc:
    print("Service no encontrado. Services disponibles:", [s.name for s in client.wsdl.services.values()])
else:
    port_obj = next(iter(svc.ports.values()))
    print("Service:", svc.name, "Port:", port_obj.name)
    print("Operaciones del binding:")
    for opname, op in port_obj.binding._operations.items():
        print("-", opname)

    # intentar extraer address del WSDL para ese port
    addr = None
    xml = client.wsdl.xml
    for svc_el in xml.findall('.//{http://schemas.xmlsoap.org/wsdl/}service'):
        if svc_el.get("name") == svc.name:
            for p_el in svc_el.findall('{http://schemas.xmlsoap.org/wsdl/}port'):
                if p_el.get("name") == port_obj.name:
                    a = p_el.find('{http://schemas.xmlsoap.org/wsdl/soap/}address') or \
                        p_el.find('{http://schemas.xmlsoap.org/wsdl/soap12/}address')
                    if a is not None:
                        addr = a.get("location")
                    break
            break
    print("Resolved endpoint address:", addr)
