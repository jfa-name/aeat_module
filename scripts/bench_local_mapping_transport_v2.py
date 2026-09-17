#!/usr/bin/env python3
# Transport robusto (pegar en bench console en una sola celda)
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
import requests
from pathlib import Path
import re
import traceback

DOCS_DIRS = [
    Path("/home/develop/workspace/baygroup/apps/aeat_module/docs"),
    Path("/home/develop/workspace/baygroup/apps/docs"),
]

# Mapa explícito (opcional)
LOCAL_XSD_MAP = {
    "RespuestaConsultaLR.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/RespuestaConsultaLR.xsd.sanitized.imports_rewritten"),
    "SuministroInformacion.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/SuministroInformacion.xsd.sanitized.imports_rewritten"),
    "SuministroLR.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/SuministroLR.xsd.sanitized.imports_rewritten"),
    "ConsultaLR.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/ConsultaLR.xsd.sanitized.imports_rewritten"),
    "RespuestaSuministro.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/RespuestaSuministro.xsd.sanitized.imports_rewritten"),
    "xmldsig-core-schema.xsd.sanitized": Path("/home/develop/workspace/baygroup/apps/docs/xmldsig-core-schema.xsd.sanitized"),
    "SuministroInformacion.xsd": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/SuministroInformacion.xsd"),
}

# localizar ruta del XSD sanitizado real (primer candidato válido)
def find_xmldsig_sanitized(docs_dirs):
    """Localizar xmldsig-core-schema.xsd.sanitized"""
    from pathlib import Path as PathClass
    candidates = ["xmldsig-core-schema.xsd.sanitized", "xmldsig-core-schema.xsd"]
    for docs in docs_dirs:
        for name in candidates:
            p = docs / name
            if p.exists():
                return p.resolve()
    return None

XSD_SAN_PATH = find_xmldsig_sanitized(DOCS_DIRS)

if XSD_SAN_PATH:
    print(f"Found xmldsig sanitized: {XSD_SAN_PATH}")
else:
    print("WARNING: xmldsig-core-schema.xsd.sanitized not found")

class LocalMappingTransport(Transport):
    def __init__(self, local_map=None, docs_dirs=None, xsd_san_path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Importar Path dentro del método para IPython
        from pathlib import Path as PathClass
        self.local_map = {k: PathClass(v) if not isinstance(v, PathClass) else v for k, v in (local_map or {}).items()}
        self.docs_dirs = docs_dirs or []
        # Pasar xsd_san_path como parámetro o calcular si no se proporciona
        if xsd_san_path:
            self.xsd_san_path = PathClass(xsd_san_path) if not isinstance(xsd_san_path, PathClass) else xsd_san_path
        else:
            self.xsd_san_path = find_xmldsig_sanitized(self.docs_dirs) if self.docs_dirs else None

    def _collapse_file_scheme(self, s):
        """Colapsar URIs file:// duplicados y malformados"""
        import re as re_module
        # Eliminar repeticiones de file:// y normalizar
        # Ejemplo: file:///home/file:///home/... -> file:///home/...
        collapsed = re_module.sub(r'(file:/*)+', 'file:///', s)
        # Normalizar barras múltiples después del scheme
        collapsed = re_module.sub(r'file://+', 'file:///', collapsed)
        return collapsed

    def _find_local_by_basename(self, basename):
        """Buscar fichero local por basename"""
        from pathlib import Path as PathClass
        
        # 1) mapa explícito
        p = self.local_map.get(basename)
        if p and p.exists():
            return p.resolve()
        
        # 2) buscar en DOCS_DIRS
        for docs in self.docs_dirs:
            if not docs.exists():
                continue
            cand = docs / basename
            if cand.exists():
                return cand.resolve()
            # buscar por sufijo
            for f in docs.iterdir():
                if f.is_file() and f.name.endswith(basename):
                    return f.resolve()
        return None

    def load(self, url):
        import re as re_module
        import traceback as tb_module
        from pathlib import Path as PathClass
        
        url_str = str(url)
        print(f"LocalMappingTransport.load() for: {url_str}")
        
        # 1) Normalizar URIs file:// duplicados o malformados
        url_str = self._collapse_file_scheme(url_str)
        
        # 2) Detectar placeholders $XSD_SAN o %24XSD_SAN y servir xmldsig sanitizado
        if ("$XSD_SAN" in url_str or "%24XSD_SAN" in url_str) and self.xsd_san_path:
            print(f"LocalMappingTransport: placeholder detected -> serving {self.xsd_san_path}")
            return self.xsd_san_path.read_bytes()
        
        # 3) Extraer basename
        try:
            if url_str.startswith("file://"):
                candidate = url_str.replace("file://", "", 1)
                basename = PathClass(candidate).name
            else:
                basename = PathClass(url_str).name
        except Exception:
            basename = None
        
        # 4) Buscar por basename local
        if basename:
            local = self._find_local_by_basename(basename)
            if local:
                if local.exists():
                    print(f"LocalMappingTransport: serving local file for basename '{basename}' -> {local}")
                    return local.read_bytes()
                else:
                    print(f"LocalMappingTransport: candidate found but does not exist: {local}")
        
        # 5) Corregir patrones como https:///home/... -> file:///home/...
        m = re_module.match(r'^https?://(/.+)$', url_str)
        if m:
            p = PathClass(m.group(1))
            if p.exists():
                print(f"LocalMappingTransport: corrected {url_str} -> file://{m.group(1)}")
                return p.read_bytes()
        
        # 6) Si es file:// absoluto, intentar abrir
        if url_str.startswith("file://"):
            pth = PathClass(url_str.replace("file://", "", 1))
            if pth.exists():
                print(f"LocalMappingTransport: loading file uri {pth}")
                return pth.read_bytes()
        
        # 7) Fallback: delegar (esto generará error si no existe)
        try:
            print(f"LocalMappingTransport: delegating to super().load for {url_str}")
            return super().load(url_str)
        except Exception as e:
            print(f"LocalMappingTransport: error delegando a super().load: {e}")
            tb_module.print_exc()
            raise

# ------------------------
# Crear client
# ------------------------
wsdl_candidates = [
    Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl"),
    Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.wsdl"),
]

wsdl_path = None
for w in wsdl_candidates:
    if w.exists():
        wsdl_path = w
        break

if not wsdl_path:
    raise FileNotFoundError("No se encontró ningún WSDL válido")

wsdl_uri = wsdl_path.resolve().as_uri()
print(f"Using WSDL URI: {wsdl_uri}")

session = requests.Session()
session.cert = ("/etc/ssl/aeat/cert.pem", "/etc/ssl/aeat/key.pem")
session.verify = "/etc/ssl/aeat/ca-bundle.pem"

# IMPORTANTE: Pasar xsd_san_path explícitamente al constructor
transport = LocalMappingTransport(
    local_map=LOCAL_XSD_MAP, 
    docs_dirs=DOCS_DIRS, 
    xsd_san_path=XSD_SAN_PATH,
    session=session, 
    timeout=60
)
settings = Settings(strict=False, xml_huge_tree=True)
history = HistoryPlugin()

client = Client(wsdl=wsdl_uri, transport=transport, settings=settings, plugins=[history])
print("WSDL loaded. Services:", [s.name for s in client.wsdl.services.values()])

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

    # extraer endpoint address - método correcto
    addr = None
    # El endpoint está en el binding del port
    if hasattr(port_obj, 'binding_options') and 'address' in port_obj.binding_options:
        addr = port_obj.binding_options['address']
    else:
        # Alternativa: buscar en las definiciones del WSDL
        for definition in client.wsdl._definitions.values():
            for svc_def in definition.services.values():
                if svc_def.name == svc.name:
                    for port_def in svc_def.ports.values():
                        if port_def.name == port_obj.name:
                            addr = port_def.binding_options.get('address')
                            break
                    break
            if addr:
                break
    
    print("Resolved endpoint address:", addr)
    
    # Mostrar información adicional útil
    print("\n=== Información del cliente ===")
    print(f"Service binding: {port_obj.binding.name}")
    print(f"SOAP version: {port_obj.binding.transport}")