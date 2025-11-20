from pathlib import Path
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
import requests
import re

# ======================
# CONFIGURACIÓN
# ======================
DOCS_DIRS = [
    Path("/home/develop/workspace/baygroup/apps/aeat_module/docs"),
    Path("/home/develop/workspace/baygroup/apps/docs"),
]

LOCAL_XSD_MAP = {
    "RespuestaConsultaLR.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/RespuestaConsultaLR.xsd.sanitized.imports_rewritten"),
    "SuministroInformacion.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/SuministroInformacion.xsd.sanitized.imports_rewritten"),
    "SuministroLR.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/SuministroLR.xsd.sanitized.imports_rewritten"),
    "ConsultaLR.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/ConsultaLR.xsd.sanitized.imports_rewritten"),
    "RespuestaSuministro.xsd.sanitized.imports_rewritten": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/RespuestaSuministro.xsd.sanitized.imports_rewritten"),
    "xmldsig-core-schema.xsd.sanitized": Path("/home/develop/workspace/baygroup/apps/docs/xmldsig-core-schema.xsd.sanitized"),
    "SuministroInformacion.xsd": Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/SuministroInformacion.xsd"),
}

WSDL_PATH = Path("/home/develop/workspace/baygroup/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl")

# ======================
# HELPER: Find xmldsig
# ======================
def find_xmldsig_sanitized(docs_dirs):
    """Localizar xmldsig-core-schema.xsd.sanitized"""
    candidates = ["xmldsig-core-schema.xsd.sanitized", "xmldsig-core-schema.xsd"]
    for docs in docs_dirs:
        for name in candidates:
            p = docs / name
            if p.exists():
                return p.resolve()
    return None

XSD_SAN_PATH = find_xmldsig_sanitized(DOCS_DIRS)
print(f"xmldsig path: {XSD_SAN_PATH}")

# ======================
# CUSTOM TRANSPORT
# ======================
class LocalMappingTransport(Transport):
    def __init__(self, local_map=None, docs_dirs=None, xsd_san_path=None, *args, **kwargs):
        from pathlib import Path
        super().__init__(*args, **kwargs)
        self.local_map = {k: Path(v) if not isinstance(v, Path) else v for k, v in (local_map or {}).items()}
        self.docs_dirs = docs_dirs or []
        self.xsd_san_path = Path(xsd_san_path) if xsd_san_path and not isinstance(xsd_san_path, Path) else xsd_san_path

    def _collapse_file_scheme(self, s):
        import re
        from re import sub
        """Colapsar URIs file:// duplicados"""
        collapsed = re.sub(r'(file:/*)+', 'file:///', s)
        collapsed = re.sub(r'file://+', 'file:///', collapsed)
        return collapsed

    def _find_local_by_basename(self, basename):
        """Buscar fichero local por basename"""
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
        """Cargar XSD desde local, resolviendo placeholders"""
        import re
        from pathlib import Path as PathClass  # Asegúrate de tener este alias
        
        url_str = str(url)
        url_str = self._collapse_file_scheme(url_str)

        # Resolver placeholder $XSD_SAN
        if ("%24XSD_SAN" in url_str or "$XSD_SAN" in url_str) and self.xsd_san_path:
            print(f"  → Resolviendo $XSD_SAN a {self.xsd_san_path}")
            return self.xsd_san_path.read_bytes()

        # Extraer basename y buscar localmente
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
                print(f"  → Cargando local: {basename}")
                return local.read_bytes()

        # Intentar path directo file://
        if url_str.startswith("file://"):
            pth = PathClass(url_str.replace("file://", "", 1))  # ← CAMBIO AQUÍ
            if pth.exists():
                print(f"  → Cargando directo: {pth}")
                return pth.read_bytes()

        # Fallback: usar transport normal
        try:
            print(f"  → Intentando cargar remoto/fallback: {url_str}")
            return super().load(url_str)
        except Exception as e:
            print(f"  ✗ Error cargando {url_str}: {e}")
            if self.xsd_san_path:
                print(f"  → Usando xmldsig como fallback")
                return self.xsd_san_path.read_bytes()
            raise

# ======================
# CREAR CLIENTE
# ======================
WSDL = WSDL_PATH.resolve().as_uri()
print(f"WSDL URI: {WSDL}")

session = requests.Session()
session.cert = ("/etc/ssl/aeat/cert.pem", "/etc/ssl/aeat/key.pem")
session.verify = "/etc/ssl/aeat/ca-bundle.pem"

transport = LocalMappingTransport(
    local_map=LOCAL_XSD_MAP,
    docs_dirs=DOCS_DIRS,
    xsd_san_path=XSD_SAN_PATH,
    session=session,
    timeout=60
)

settings = Settings(strict=False, xml_huge_tree=True)
history = HistoryPlugin()

print("\nCargando WSDL...")
client = Client(wsdl=WSDL, transport=transport, settings=settings, plugins=[history])
print("✓ WSDL cargado correctamente")

# ======================
# INTROSPECCIÓN
# ======================
svc = client.wsdl.services.get("sfVerifactu")
port_obj = next(iter(svc.ports.values()))
op = port_obj.binding._operations['RegFactuSistemaFacturacion']

# Obtener tipo de RegistroFactura
body_type = op.input.body.type
print(f"\nBody type: {body_type}")

# Buscar RegistroFactura en los elementos del body
reg_factura_element = None
if hasattr(body_type, 'elements'):
    for item in body_type.elements:
        if isinstance(item, tuple):
            name, el = item
        else:
            el = item
            name = getattr(el, 'name', None)
        
        if name == 'RegistroFactura':
            reg_factura_element = el
            break

if not reg_factura_element:
    print("✗ No se encontró RegistroFactura en body.type.elements")
else:
    ptype = getattr(reg_factura_element, 'type', None)
    print(f"\nRegistroFactura type: {ptype}")
    print(f"maxOccurs: {getattr(reg_factura_element, 'max_occurs', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("ESTRUCTURA DE RegistroFactura:")
    print("=" * 60)
    
    def describe(t, indent=0, seen=None, max_depth=5):
        """Describe recursivamente la estructura de un tipo XSD"""
        if seen is None:
            seen = set()
        if indent > max_depth:
            print("  " * indent + "... (max depth)")
            return
        
        pad = "  " * indent
        key = getattr(t, "name", None) or str(t)
        
        if key in seen:
            print(pad + f"- [CYCLE] {key}")
            return
        seen.add(key)
        
        elems = getattr(t, "elements", None)
        if elems:
            try:
                elems_list = list(elems) if not isinstance(elems, list) else elems
            except Exception as e:
                print(pad + f"- Error listando elementos: {e}")
                return
            
            for item in elems_list:
                try:
                    if isinstance(item, tuple):
                        name, e = item
                    else:
                        e = item
                        name = getattr(e, 'name', None)
                    
                    if not name:
                        continue
                    
                    typ = getattr(e, 'type', None)
                    minO = getattr(e, 'min_occurs', 0)
                    maxO = getattr(e, 'max_occurs', 1)
                    
                    is_required = " [REQUIRED]" if minO > 0 else ""
                    is_array = " [ARRAY]" if maxO is None or (isinstance(maxO, int) and maxO > 1) else ""
                    
                    print(pad + f"- {name} (min={minO}, max={maxO}){is_required}{is_array}")
                    
                    # Recursión solo si tiene elementos
                    if typ is not None and getattr(typ, "elements", None):
                        describe(typ, indent + 1, seen.copy(), max_depth)
                except Exception as ex:
                    print(pad + f"- Error procesando elemento: {ex}")
        else:
            print(pad + f"- {key} (tipo simple, no hay subelementos)")
    
    describe(ptype, max_depth=3)

print("\n" + "=" * 60)
print("Introspección completada")
print("=" * 60)
