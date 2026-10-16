#!/usr/bin/env python3
# Transport + uso para bench console (pegar todo en una sola celda)
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
import requests
from pathlib import Path
import re
import traceback

class LocalMappingTransport(Transport):
    """Transport que sirve XSD locales cuando Zeep los solicita."""
    def __init__(self, local_xsd_map=None, docs_dirs=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Guardar como atributos de instancia para que sean accesibles en load()
        self.local_xsd_map = local_xsd_map or {}
        self.docs_dirs = docs_dirs or []
    
    @staticmethod
    def find_local_by_basename(basename, local_xsd_map, docs_dirs):
        """Buscar un fichero local que coincida con basename (preferir mapa explícito)."""
        from pathlib import Path as PathClass
        
        # 1) mapa explícito
        p = local_xsd_map.get(basename)
        if p:
            p = PathClass(p) if not isinstance(p, PathClass) else p
            if p.exists():
                return p.resolve()
        # 2) buscar en DOCS_DIRS por nombre exacto o por sufijo
        for docs in docs_dirs:
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
        # Importar módulos dentro del método para evitar problemas de scope en IPython
        import re as re_module
        import traceback as tb_module
        from pathlib import Path as PathClass
        
        # url puede ser una Path, file:// URI, o una URL remota
        url_str = str(url)
        try:
            # debug: mostrar cada petición de URL (comentar si hay mucho ruido)
            print("LocalMappingTransport.load() called for:", url_str)
            # extraer basename razonable
            if url_str.startswith("file://"):
                local_path_candidate = url_str.replace("file://", "", 1)
                basename = PathClass(local_path_candidate).name
            else:
                # para http(s) o rutas relativas coger el nombre final
                basename = PathClass(url_str).name
        except Exception:
            basename = None

        # 1) si tenemos un basename, intentar servir fichero local coincidente
        if basename:
            local = self.find_local_by_basename(basename, self.local_xsd_map, self.docs_dirs)
            if local:
                if local.exists():
                    print(f"LocalMappingTransport: serving local file for basename '{basename}' -> {local}")
                    return local.read_bytes()
                else:
                    print(f"LocalMappingTransport: candidate found but does not exist: {local}")

        # 2) corregir patrones como https:///home/... -> file:///home/...
        m = re_module.match(r'^https?://(/.+)$', url_str)
        if m:
            corrected_path = PathClass(m.group(1))
            if corrected_path.exists():
                print(f"LocalMappingTransport: corrected {url_str} -> file://{m.group(1)}")
                return corrected_path.read_bytes()

        # 3) normalizar duplicados file://file://...
        if url_str.startswith("file://") and "file://file://" in url_str:
            norm = url_str.replace("file://file://", "file://")
            local_path = norm.replace("file://", "", 1)
            p = PathClass(local_path)
            if p.exists():
                print(f"LocalMappingTransport: normalized {url_str} -> {p}")
                return p.read_bytes()

        # 4) si es una file:// válida, intentar abrirla
        if url_str.startswith("file://"):
            pth = PathClass(url_str.replace("file://", "", 1))
            if pth.exists():
                print(f"LocalMappingTransport: loading file uri {pth}")
                return pth.read_bytes()

        # 5) fallback: delegar a transport por defecto (descarga remota)
        try:
            print("LocalMappingTransport: delegating to super().load for", url_str)
            return super().load(url)
        except Exception as e:
            # imprimir traza para depuración y relanzar
            print("LocalMappingTransport: error delegando a super().load:", e)
            tb_module.print_exc()
            raise

# ------------------------
# Configuración: define aquí tus directorios y mapeos
# ------------------------

# Directorios donde buscar XSD locales (ajusta si tu estructura difiere)
DOCS_DIRS = [
    Path("/path/to/your/frappe-bench/apps/aeat_module/docs"),
    Path("/path/to/your/frappe-bench/apps/docs"),
]

# Mapa explícito basename -> path (opcional). Si lo mantienes vacío se buscará por basename en DOCS_DIRS.
LOCAL_XSD_MAP = {
    "RespuestaConsultaLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/RespuestaConsultaLR.xsd.sanitized.imports_rewritten"),
    "SuministroInformacion.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/SuministroInformacion.xsd.sanitized.imports_rewritten"),
    "SuministroLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/SuministroLR.xsd.sanitized.imports_rewritten"),
    "ConsultaLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/ConsultaLR.xsd.sanitized.imports_rewritten"),
    "RespuestaSuministro.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/RespuestaSuministro.xsd.sanitized.imports_rewritten"),
    "xmldsig-core-schema.xsd.sanitized": Path("/path/to/your/frappe-bench/apps/docs/xmldsig-core-schema.xsd.sanitized"),
}

# ------------------------
# Uso: crea el client con este transport y muestra services/operations
# ------------------------
wsdl_path = Path("/path/to/your/frappe-bench/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.wsdl")
wsdl_uri = wsdl_path.resolve().as_uri()
print("Using WSDL URI:", wsdl_uri)

session = requests.Session()
# Ajusta las rutas de certificados a las de tu entorno
session.cert = ("/etc/ssl/aeat/cert.pem", "/etc/ssl/aeat/key.pem")
session.verify = "/etc/ssl/aeat/ca-bundle.pem"

# IMPORTANTE: Pasar local_xsd_map y docs_dirs al constructor
transport = LocalMappingTransport(
    local_xsd_map=LOCAL_XSD_MAP,
    docs_dirs=DOCS_DIRS,
    session=session,
    timeout=60
)
settings = Settings(strict=False, xml_huge_tree=True)
history = HistoryPlugin()

client = Client(wsdl=wsdl_uri, transport=transport, settings=settings, plugins=[history])
print("WSDL cargado OK. Servicios:", [s.name for s in client.wsdl.services.values()])

# seleccionar service por nombre y listar operaciones
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

    # también imprime el endpoint si está en el WSDL
    addr = None
    xml = client.wsdl.xml
    for svc_el in xml.findall('.//{http://schemas.xmlsoap.org/wsdl/}service'):
        if svc_el.get("name") == svc.name:
            for p_el in svc_el.findall('{http://schemas.xmlsoap.org/wsdl/}port'):
                if p_el.get("name") == port_obj.name:
                    a = p_el.find('{http://schemas.xmlsoap.org/wsdl/soap/}address') or p_el.find('{http://schemas.xmlsoap.org/wsdl/soap12/}address')
                    if a is not None:
                        addr = a.get("location")
                    break
            break
    print("Resolved endpoint address:", addr)
