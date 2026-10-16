#!/usr/bin/env python3
# Crear proxy con LocalMappingTransport (pegar en bench console en una sola celda)
from pathlib import Path
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
import requests
import re
import traceback

# ------------------------
# Configuración
# ------------------------
DOCS_DIRS = [
    Path("/path/to/your/frappe-bench/apps/aeat_module/docs"),
    Path("/path/to/your/frappe-bench/apps/docs"),
]

LOCAL_XSD_MAP = {
    "RespuestaConsultaLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/RespuestaConsultaLR.xsd.sanitized.imports_rewritten"),
    "SuministroInformacion.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/SuministroInformacion.xsd.sanitized.imports_rewritten"),
    "SuministroLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/SuministroLR.xsd.sanitized.imports_rewritten"),
    "ConsultaLR.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/ConsultaLR.xsd.sanitized.imports_rewritten"),
    "RespuestaSuministro.xsd.sanitized.imports_rewritten": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/RespuestaSuministro.xsd.sanitized.imports_rewritten"),
    "xmldsig-core-schema.xsd.sanitized": Path("/path/to/your/frappe-bench/apps/docs/xmldsig-core-schema.xsd.sanitized"),
    "SuministroInformacion.xsd": Path("/path/to/your/frappe-bench/apps/aeat_module/docs/SuministroInformacion.xsd"),
}

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

# ------------------------
# Transport personalizado
# ------------------------
class LocalMappingTransport(Transport):
    def __init__(self, local_map=None, docs_dirs=None, xsd_san_path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from pathlib import Path as PathClass
        self.local_map = {k: PathClass(v) if not isinstance(v, PathClass) else v for k, v in (local_map or {}).items()}
        self.docs_dirs = docs_dirs or []
        if xsd_san_path:
            self.xsd_san_path = PathClass(xsd_san_path) if not isinstance(xsd_san_path, PathClass) else xsd_san_path
        else:
            self.xsd_san_path = find_xmldsig_sanitized(self.docs_dirs) if self.docs_dirs else None

    def _collapse_file_scheme(self, s):
        """Colapsar URIs file:// duplicados y malformados"""
        import re as re_module
        collapsed = re_module.sub(r'(file:/*)+', 'file:///', s)
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
        
        # 1) Normalizar URIs file:// duplicados o malformados
        url_str = self._collapse_file_scheme(url_str)
        
        # 2) Detectar placeholders $XSD_SAN o %24XSD_SAN y servir xmldsig sanitizado
        if ("$XSD_SAN" in url_str or "%24XSD_SAN" in url_str) and self.xsd_san_path:
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
            if local and local.exists():
                return local.read_bytes()
        
        # 5) Corregir patrones como https:///home/... -> file:///home/...
        m = re_module.match(r'^https?://(/.+)$', url_str)
        if m:
            p = PathClass(m.group(1))
            if p.exists():
                return p.read_bytes()
        
        # 6) Si es file:// absoluto, intentar abrir
        if url_str.startswith("file://"):
            pth = PathClass(url_str.replace("file://", "", 1))
            if pth.exists():
                return pth.read_bytes()
        
        # 7) Fallback: delegar
        try:
            return super().load(url_str)
        except Exception as e:
            tb_module.print_exc()
            raise

# ------------------------
# Crear cliente con transport personalizado
# ------------------------
wsdl_path = Path("/path/to/your/frappe-bench/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl")
wsdl_uri = wsdl_path.resolve().as_uri()

session = requests.Session()
session.cert = ("/etc/ssl/aeat/cert.pem", "/etc/ssl/aeat/key.pem")
session.verify = "/etc/ssl/aeat/ca-bundle.pem"

# USAR LocalMappingTransport en lugar de Transport básico
transport = LocalMappingTransport(
    local_map=LOCAL_XSD_MAP,
    docs_dirs=DOCS_DIRS,
    xsd_san_path=XSD_SAN_PATH,
    session=session,
    timeout=60
)

settings = Settings(strict=False, xml_huge_tree=True)
history = HistoryPlugin()

print(f"Loading WSDL: {wsdl_uri}")
client = Client(wsdl=wsdl_uri, transport=transport, settings=settings, plugins=[history])

# ------------------------
# Extraer información del servicio
# ------------------------
svc = client.wsdl.services.get("sfVerifactu")
if not svc:
    print("ERROR: Service 'sfVerifactu' no encontrado")
    print("Services disponibles:", list(client.wsdl.services.keys()))
else:
    port_obj = next(iter(svc.ports.values()))
    binding_qname = port_obj.binding.name
    
    # Extraer endpoint address
    address = None
    if hasattr(port_obj, 'binding_options') and 'address' in port_obj.binding_options:
        address = port_obj.binding_options['address']
    else:
        # Buscar en las definiciones del WSDL
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
    
    print("\n=== Información del Servicio ===")
    print(f"Service: {svc.name}")
    print(f"Port: {port_obj.name}")
    print(f"Binding QName: {binding_qname}")
    print(f"Endpoint address: {address}")
    print(f"SOAP version: {port_obj.binding.transport}")
    
    print("\n=== Operaciones disponibles ===")
    for opname, op in port_obj.binding._operations.items():
        print(f"- {opname}")
    
    print("\n=== Cliente listo para usar ===")
    print("Ejemplo de uso:")
    print("  service = client.bind('sfVerifactu', 'SistemaVerifactu')")
    print("  # O usar directamente: client.service.RegFactuSistemaFacturacion(...)")