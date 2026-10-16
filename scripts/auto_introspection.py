#!/usr/bin/env python3
"""
Introspección automática para operación RegFactuSistemaFacturacion usando Zeep.

- Usa un Transport local (LocalMappingTransport) que sirve XSD locales y
  detecta/soluciona placeholders como $XSD_SAN / %24XSD_SAN.
- Introspección recursiva para generar un payload-esqueleto con valores
  de ejemplo para todos los elementos obligatorios (minOccurs > 0).
- Permite apuntar al endpoint de preproducción (prewwwX...) si se desea.

Cortar/pegar entero en bench --site your-site console y ejecutarlo en una celda.
Ajusta paths, certificados y la variable PREPROD (ver más abajo).
"""
from pathlib import Path
from pprint import pprint
import re
import traceback
import requests

from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
from zeep.xsd import ComplexType, Element

# -----------------------
# Configuración - Ajusta si hace falta
# -----------------------
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

WSDLPATH = Path("/path/to/your/frappe-bench/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl")
USE_PREPROD = True
HOST_MAP = {
    "www1.agenciatributaria.gob.es": "prewww1.aeat.es",
    "www2.agenciatributaria.gob.es": "prewww2.aeat.es",
    "www10.agenciatributaria.gob.es": "prewww10.aeat.es",
}

CERT = ("/etc/ssl/aeat/cert.pem", "/etc/ssl/aeat/key.pem")
VERIFY = "/etc/ssl/aeat/ca-bundle.pem"

# -----------------------
# Helper: find_xmldsig_sanitized function
# -----------------------
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

# -----------------------
# Helper: LocalMappingTransport
# -----------------------
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
        import re as re_module
        import traceback as tb_module
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

        m = re_module.match(r'^https?://(/.+)$', url_str)
        if m:
            p = PathClass(m.group(1))
            if p.exists():
                return p.read_bytes()

        if url_str.startswith("file://"):
            pth = PathClass(url_str.replace("file://", "", 1))
            if pth.exists():
                return pth.read_bytes()

        try:
            return super().load(url_str)
        except Exception as e:
            tb_module.print_exc()
            if self.xsd_san_path:
                return self.xsd_san_path.read_bytes()
            raise

# -----------------------
# Crear cliente con transport local
# -----------------------
wsdl_path = WSDLPATH
if not wsdl_path.exists():
    raise SystemExit(f"WSDL not found: {wsdl_path}")
wsdl_uri = wsdl_path.resolve().as_uri()
print("Using WSDL URI:", wsdl_uri)

session = requests.Session()
session.cert = CERT
session.verify = VERIFY

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

# -----------------------
# Select service/port and optionally override endpoint to preprod
# -----------------------
service_name = "sfVerifactu"
svc = client.wsdl.services.get(service_name)
if not svc:
    raise SystemExit("Service sfVerifactu not found")

port_obj = next(iter(svc.ports.values()))
binding_qname = port_obj.binding.name

address = None
if hasattr(port_obj, 'binding_options') and 'address' in port_obj.binding_options:
    address = port_obj.binding_options['address']
else:
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

print("Binding QName:", binding_qname)
print("Resolved endpoint address (from WSDL):", address)

if USE_PREPROD and address:
    for real_host, pre_host in HOST_MAP.items():
        if real_host in address:
            pre_addr = address.replace(real_host, pre_host)
            print("Using preprod endpoint override:", pre_addr)
            address = pre_addr
            break

# -----------------------
# Introspección y creación de payload esqueleto
# -----------------------
op_name = "RegFactuSistemaFacturacion"
op = port_obj.binding._operations[op_name]
print("Operation signature:", op.input.signature())

# -----------------------
# Funciones helper para introspección (definir ANTES de usar)
# -----------------------
def example_for_simple(xsd_type):
    """Return a best-effort example value for a simple xsd type using python_type when available."""
    try:
        py = getattr(xsd_type, "python_type", None)
        if py is not None:
            if py is bool:
                return False
            if py is int:
                return 0
            if py is float:
                return 0.0
            if py.__name__ == "date":
                return "2025-01-01"
            if py.__name__ == "datetime":
                return "2025-01-01T00:00:00"
            return "example"
    except Exception:
        pass
    return "example"

def build_example_from_type(xsd_type, seen=None, depth=0):
    """Return an example (primitive or dict/list) for a given xsd type."""
    if seen is None:
        seen = set()
    if depth > 10:  # Límite de profundidad
        return None
        
    key = getattr(xsd_type, "name", None) or str(xsd_type)
    if key in seen:
        return None
    seen.add(key)

    # Manejar elementos con tipo complejo
    elements = getattr(xsd_type, "elements", None)
    if elements:
        out = {}
        # elements puede ser una lista o generador
        try:
            elements_list = list(elements) if not isinstance(elements, list) else elements
        except Exception:
            return {}
        
        for item in elements_list:
            # item puede ser una tupla (name, element) o directamente un Element
            try:
                if isinstance(item, tuple):
                    name, el = item
                else:
                    el = item
                    name = getattr(el, "name", None)
                
                if not name:
                    continue
                    
                mino = getattr(el, "min_occurs", 0)
                maxo = getattr(el, "max_occurs", 1)
                etype = getattr(el, "type", None)
                
                # Solo incluir elementos obligatorios (min_occurs > 0) o muy comunes
                if mino == 0 and name not in ['IDFactura', 'NombreRazon', 'NIF', 'FechaExpedicion']:
                    continue
                
                if etype is None:
                    val = "example"
                else:
                    if getattr(etype, "elements", None):
                        # Llamada recursiva - usar globals() para asegurar que la función está en scope
                        val = build_example_from_type(etype, seen=seen.copy(), depth=depth+1)
                    else:
                        val = example_for_simple(etype)
                
                if maxo is None or maxo > 1:
                    out[name] = [val] if val is not None else []
                else:
                    out[name] = val
            except Exception as e:
                print(f"  Warning: Error processing element {getattr(item, 'name', '?')}: {e}")
                continue
                
        return out

    if isinstance(xsd_type, Element):
        return build_example_from_type(xsd_type.type, seen=seen, depth=depth)

    return example_for_simple(xsd_type)

# -----------------------
# Build payload
# -----------------------
payload = {}
try:
    body_type = op.input.body.type
    if body_type and hasattr(body_type, 'elements'):
        elements_list = list(body_type.elements)
        
        for item in elements_list:
            # Manejar tanto tuplas como objetos Element directos
            if isinstance(item, tuple):
                name, el = item
            else:
                el = item
                name = getattr(el, "name", None)
            
            if not name:
                continue
            
            etype = getattr(el, "type", None)
            maxo = getattr(el, "max_occurs", 1)
            
            if etype is None:
                val = {}
            else:
                val = build_example_from_type(etype)
            
            # Si es RegistroFactura (maxOccurs > 1), forzar array
            if maxo is None or maxo > 1:
                if not isinstance(val, list):
                    val = [val] if val else [{}]
            
            payload[name] = val
    else:
        print("WARNING: No body.type.elements found, using fallback")
        payload = {
            'Cabecera': {},
            'RegistroFactura': [{}]
        }
except Exception as e:
    print(f"Error building payload: {e}")
    traceback.print_exc()
    payload = {
        'Cabecera': {},
        'RegistroFactura': [{}]
    }

print("\nGenerated payload skeleton (example):")
pprint(payload, depth=4, width=120)

# -----------------------
# Mostrar estructura esperada sin intentar serializar
# -----------------------
print("\n=== Estructura de tipos detectada ===")
try:
    for param_name, param_value in payload.items():
        print(f"\n{param_name}:")
        if isinstance(param_value, dict):
            items = list(param_value.items())
            print(f"  Campos detectados: {len(items)}")
            for k, v in items[:10]:  # Mostrar primeros 10
                v_type = type(v).__name__
                if isinstance(v, dict):
                    v_type = f"dict ({len(v)} campos)"
                elif isinstance(v, list):
                    v_type = f"list ({len(v)} items)"
                print(f"  - {k}: {v_type}")
            if len(items) > 10:
                print(f"  ... y {len(items) - 10} campos más")
        elif isinstance(param_value, list) and param_value:
            print(f"  [array] con {len(param_value)} elemento(s)")
            if isinstance(param_value[0], dict):
                items = list(param_value[0].items())
                print(f"  Campos en elemento[0]: {len(items)}")
                for k, v in items[:10]:
                    v_type = type(v).__name__
                    if isinstance(v, dict):
                        v_type = f"dict ({len(v)} campos)"
                    elif isinstance(v, list):
                        v_type = f"list ({len(v)} items)"
                    print(f"    - {k}: {v_type}")
                if len(items) > 10:
                    print(f"    ... y {len(items) - 10} campos más")
except Exception as e:
    print(f"Error mostrando estructura: {e}")

print("\n=== Introspection complete ===")
print("\nCampos obligatorios detectados en payload:")
print("Para Cabecera:", list(payload.get('Cabecera', {}).keys()) if payload.get('Cabecera') else "ninguno detectado")
if payload.get('RegistroFactura') and isinstance(payload['RegistroFactura'], list) and payload['RegistroFactura']:
    print("Para RegistroFactura:", list(payload['RegistroFactura'][0].keys())[:20] if payload['RegistroFactura'][0] else "ninguno detectado")

print("\nEjemplo de uso:")
print(f"  proxy = client.create_service(binding_qname, address)")
print(f"  response = proxy.{op_name}(**payload)")