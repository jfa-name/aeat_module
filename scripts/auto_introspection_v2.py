#!/usr/bin/env python3
"""
Auto-introspección completa para RegFactuSistemaFacturacion.
Ejecutar completo en bench console (pegar todo en una celda).
"""
from pathlib import Path
from pprint import pprint
import re
import traceback
import requests

from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
from zeep.xsd import Element

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
CERT = ("/etc/ssl/aeat/cert.pem", "/etc/ssl/aeat/key.pem")
CA_BUNDLE = "/etc/ssl/aeat/ca-bundle.pem"

USE_PREPROD = True
HOST_MAP = {
    "www1.agenciatributaria.gob.es": "prewww1.aeat.es",
    "www2.agenciatributaria.gob.es": "prewww2.aeat.es",
    "www10.agenciatributaria.gob.es": "prewww10.aeat.es",
}
MAX_FILL_ITER = 15

# ======================
# HELPERS - Nivel módulo
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
        import re as re_module
        collapsed = re_module.sub(r'(file:/*)+', 'file:///', s)
        collapsed = re_module.sub(r'file://+', 'file:///', collapsed)
        return collapsed

    def _find_local_by_basename(self, basename):
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

def example_for_simple(xsd_type):
    """Devuelve ejemplo para tipo simple XSD"""
    try:
        py = getattr(xsd_type, "python_type", None)
        if py is not None:
            if py is bool:
                return False
            if py is int:
                return 0
            if py is float:
                return 0.0
            name = getattr(py, "__name__", "")
            if name == "date":
                return "2025-01-01"
            if name == "datetime":
                return "2025-01-01T00:00:00"
            return "example"
    except Exception:
        pass
    return "example"

def build_example_from_type(xsd_type, seen=None, depth=0):
    """Construye ejemplo recursivo para tipo XSD (incluye todos los elementos)"""
    if seen is None:
        seen = set()
    if depth > 10:
        return None
    
    key = getattr(xsd_type, "name", None) or str(xsd_type)
    if key in seen:
        return None
    seen.add(key)

    elements = getattr(xsd_type, "elements", None)
    if elements:
        out = {}
        try:
            elements_list = list(elements) if not isinstance(elements, list) else elements
        except Exception:
            return {}
        
        for item in elements_list:
            try:
                if isinstance(item, tuple):
                    name, el = item
                else:
                    el = item
                    name = getattr(el, "name", None)
                
                if not name:
                    continue
                
                maxo = getattr(el, "max_occurs", 1)
                etype = getattr(el, "type", None)
                
                if etype is None:
                    val = "example"
                else:
                    if getattr(etype, "elements", None):
                        # Recursión - usar la función global
                        val = build_example_from_type(etype, seen=seen.copy(), depth=depth+1)
                    else:
                        val = example_for_simple(etype)
                
                if maxo is None or (isinstance(maxo, int) and maxo > 1):
                    out[name] = [val] if val is not None else []
                else:
                    out[name] = val
            except Exception as e:
                print(f"  Warning: Error en elemento {getattr(item, 'name', '?')}: {e}")
                continue
        return out

    if isinstance(xsd_type, Element):
        return build_example_from_type(xsd_type.type, seen=seen, depth=depth)

    return example_for_simple(xsd_type)

def insert_by_path(payload, path_list, value):
    """
    Inserta `value` en `payload` siguiendo path_list.
    - Si encuentra valores primitivos en el camino que deben ser contenedores,
      los reemplaza por dicts (preservando el valor antiguo bajo '_value' si queremos).
    - Si encuentra listas, trabaja sobre el primer elemento.
    - path_list no debe contener el nombre de la operación (pero si lo hace, se lo quitamos).
    Devuelve True si se inserta correctamente.
    """
    if not path_list:
        return False

    # strip root operation name like 'RegFactuSistemaFacturacion' si aparece
    if len(path_list) > 0 and path_list[0].lower().startswith("reg"):
        path = path_list[1:]
    else:
        path = list(path_list)

    if not path:
        return False

    parent = None
    parent_key = None
    current = payload

    for i, key in enumerate(path):
        last = (i == len(path) - 1)

        # If current is a list, operate on its first element (create one if empty)
        if isinstance(current, list):
            if not current:
                current.append({})
            current = current[0]

        # If current is not a dict at this point, replace it with a dict
        # (preserve previous primitive value if you want under '_value'; here we overwrite)
        if not isinstance(current, dict):
            # try to replace in parent
            if parent is not None:
                if isinstance(parent, list):
                    if not parent:
                        parent.append({})
                    parent[0][parent_key] = {}
                    current = parent[0][parent_key]
                else:
                    parent[parent_key] = {}
                    current = parent[parent_key]
            else:
                # we're at the root and payload isn't a dict (unlikely), just bail
                return False

        if last:
            # set the final value
            current[key] = value
            return True

        # not last: ensure there is a container to descend into
        next_item = current.get(key)
        if next_item is None:
            # create dict container (could be array - but we can't know here)
            current[key] = {}
            parent = current
            parent_key = key
            current = current[key]
            continue

        # if next_item is primitive, replace with dict (preserve the primitive if desired)
        if not isinstance(next_item, (dict, list)):
            # preserve old value under a special key if you want:
            old = next_item
            current[key] = {}
            # optionally keep old: current[key]['_value'] = old
            parent = current
            parent_key = key
            current = current[key]
            continue

        # if next_item is list, descend into its first element (ensure not empty)
        if isinstance(next_item, list):
            if not next_item:
                next_item.append({})
            parent = current
            parent_key = key
            current = next_item[0]
            continue

        # else it's a dict: descend
        parent = current
        parent_key = key
        current = current[key]

    return False


def extract_missing_element_name(exc_text):
    """Parsea error 'Missing element NAME (PATH)'"""
    import re
    from re import search
    m = re.search(r"Missing element\s+([A-Za-z0-9_:.-]+)\s*\(([^)]+)\)", exc_text)
    if m:
        elem = m.group(1)
        fullpath = m.group(2)
        parts = fullpath.split('.')
        return elem, parts
    m2 = re.search(r"Missing element\s+([A-Za-z0-9_:.-]+)", exc_text)
    if m2:
        return m2.group(1), None
    return None

# ======================
# MAIN EXECUTION
# ======================
print("=" * 60)
print("Iniciando auto-introspección...")
print("=" * 60)

if not WSDL_PATH.exists():
    raise SystemExit(f"WSDL not found: {WSDL_PATH}")

wsdl_uri = WSDL_PATH.resolve().as_uri()
print(f"\nUsing WSDL: {wsdl_uri}")

session = requests.Session()
session.cert = CERT
session.verify = CA_BUNDLE

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
print("WSDL cargado. Servicios:", [s.name for s in client.wsdl.services.values()])

svc = client.wsdl.services.get("sfVerifactu")
if not svc:
    raise SystemExit("Service sfVerifactu not found")

port_obj = next(iter(svc.ports.values()))
binding_qname = port_obj.binding.name

# Extraer endpoint
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

print(f"Binding: {binding_qname}")
print(f"Endpoint: {address}")

if USE_PREPROD and address:
    for real_host, pre_host in HOST_MAP.items():
        if real_host in address:
            address = address.replace(real_host, pre_host)
            print(f"Usando preprod: {address}")
            break

op_name = "RegFactuSistemaFacturacion"
op = port_obj.binding._operations.get(op_name)
if not op:
    raise SystemExit(f"Operation {op_name} not found")

print(f"\nOperation signature: {op.input.signature()}")

# Construir payload inicial
print("\n" + "=" * 60)
print("Construyendo payload skeleton...")
print("=" * 60)

payload = {}
body_type = op.input.body.type
if body_type and hasattr(body_type, 'elements'):
    elements_list = list(body_type.elements)
    for item in elements_list:
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
        
        if maxo is None or (isinstance(maxo, int) and maxo > 1):
            if not isinstance(val, list):
                val = [val] if val else [{}]
        
        payload[name] = val

print("\nPayload inicial generado:")
pprint(payload, depth=3)

# Intentar crear mensaje con auto-relleno iterativo
print("\n" + "=" * 60)
print("Intentando generar XML con auto-relleno...")
print("=" * 60)

proxy = client.create_service(binding_qname, address)
attempts = 0

while attempts < MAX_FILL_ITER:
    attempts += 1
    try:
        xml_msg = client.create_message(proxy, op_name, **payload)
        from lxml import etree
        print(f"\n✓ Éxito en intento {attempts}!")
        print("\n" + "=" * 60)
        print("Preview XML (primeros 10000 chars):")
        print("=" * 60)
        pretty = etree.tostring(xml_msg, pretty_print=True, encoding="utf-8").decode()
        print(pretty[:10000])
        print("\n" + "=" * 60)
        print("Payload final:")
        print("=" * 60)
        pprint(payload, depth=4)
        print("\n✓ Introspección completada exitosamente!")
        break
    except Exception as e:
        txt = str(e)
        print(f"\n✗ Intento {attempts} falló: {e}")
        missing = extract_missing_element_name(txt)
        if not missing:
            print("No se pudo detectar elemento faltante. Abortando.")
            traceback.print_exc()
            break
        
        elem, path = missing
        print(f"  → Detectado elemento faltante: {elem}")
        print(f"  → Path: {path}")
        
        if path:
            path_keys = path[1:] if path[0].lower().startswith("reg") else path
            success = insert_by_path(payload, path_keys, "example")
            if success:
                print(f"  ✓ Insertado '{elem}' en {'.'.join(path_keys)}")
                continue
        
        # Fallback: insertar en Cabecera
        if "Cabecera" in payload and isinstance(payload["Cabecera"], dict):
            payload["Cabecera"][elem] = "example"
            print(f"  ✓ Insertado '{elem}' en Cabecera (fallback)")
            continue
        else:
            payload[elem] = "example"
            print(f"  ✓ Insertado '{elem}' en root (fallback)")
            continue
else:
    print(f"\n✗ Se alcanzó el límite de {MAX_FILL_ITER} intentos")
    print("\nPayload final (incompleto):")
    pprint(payload, depth=4)

print("\n" + "=" * 60)
print("Para usar el payload:")
print("=" * 60)
print(f"response = proxy.{op_name}(**payload)")