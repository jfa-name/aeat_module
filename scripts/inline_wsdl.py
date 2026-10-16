#!/usr/bin/env python3
"""
Inlinear XSDs importados dentro del WSDL principal para evitar que zeep
intente descargar imports remotos que contienen DTD/ENTITY.

Salida: <orig>.inlined.wsdl en el mismo directorio docs/.
Uso:
  /path/to/your/frappe-bench/env/bin/python apps/aeat_module/scripts/inline_wsdl.py
"""
import os
from pathlib import Path
from lxml import etree
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[2]  # apps/aeat_module/
DOCS = ROOT / "docs"
WSDL_CANDIDATES = [
    "PreSistemaFacturacion.wsdl.sanitized.imports_rewritten",
    "PreSistemaFacturacion.wsdl.sanitized",
    "PreSistemaFacturacion.wsdl.cleaned.imports_rewritten",
    "PreSistemaFacturacion.wsdl.cleaned",
    "PreSistemaFacturacion.wsdl",
]

XSD_CANDIDATE_SUFFIXES = [
    ".sanitized.imports_rewritten",
    ".sanitized",
    ".cleaned.imports_rewritten",
    ".cleaned",
    ""
]

XSD_NS = "http://www.w3.org/2001/XMLSchema"
WSDL_NS = "http://schemas.xmlsoap.org/wsdl/"

def find_wsdl_path():
    for name in WSDL_CANDIDATES:
        p = DOCS / name
        if p.exists():
            return p
    # fallback: any file starting with PreSistemaFacturacion
    for p in DOCS.iterdir():
        if p.is_file() and p.name.startswith("PreSistemaFacturacion") and p.suffix in (".wsdl", ".xml"):
            return p
    raise SystemExit(f"No encontré el WSDL PreSistemaFacturacion en {DOCS}")

def resolve_xsd_file(schemaLocation):
    basename = os.path.basename(schemaLocation)
    # probar varias variantes locales
    for suff in XSD_CANDIDATE_SUFFIXES:
        candidate = DOCS / (basename + suff)
        if candidate.exists():
            return candidate
    candidate = DOCS / basename
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"No encontré XSD local para schemaLocation '{schemaLocation}' (busqué en {DOCS})")

def inject_imported_xsd_children(target_schema_el, schemaLocation):
    """
    Parsear el XSD en schemaLocation y copiar sus hijos (element, complexType, etc.)
    dentro del elemento target_schema_el. Evita insertar un <schema> dentro de otro.
    Devuelve (True, mensaje) si se inyectó, (False, mensaje) si no.
    """
    try:
        xsd_file = resolve_xsd_file(schemaLocation)
    except FileNotFoundError:
        return False, f"XSD no encontrado localmente para {schemaLocation}"
    try:
        imported_doc = etree.parse(str(xsd_file))
        imported_root = imported_doc.getroot()
    except Exception as e:
        return False, f"Error parseando {xsd_file}: {e}"

    # localizar el elemento schema adecuado dentro del archivo importado
    try:
        localname = etree.QName(imported_root.tag).localname
    except Exception:
        localname = None

    if localname != "schema":
        # si el root no es schema, buscar el primer schema debajo del documento
        found = imported_root.find(f".//{{{XSD_NS}}}schema")
        if found is not None:
            imported_root = found

    appended = 0
    # recorrer los hijos del imported_root y copiar los apropiados
    for child in imported_root:
        if not isinstance(child, etree._Element):
            continue
        try:
            child_local = etree.QName(child.tag).localname
        except Exception:
            continue
        if child_local == "schema":
            # si por alguna razón hay un <schema> dentro del import, no lo anexamos;
            # en su lugar, añadimos sus hijos (evitar nested schema)
            for nested in [n for n in child if isinstance(n, etree._Element)]:
                target_schema_el.append(deepcopy(nested))
                appended += 1
        else:
            # copia normal de tipos/element/attribute/annotations/etc.
            target_schema_el.append(deepcopy(child))
            appended += 1

    return True, f"Injectados {appended} nodos desde {xsd_file.name}"

def inline_wsdl(wsdl_path: Path):
    tree = etree.parse(str(wsdl_path))
    root = tree.getroot()

    # localizar wsdl:types
    types_el = root.find(f".//{{{WSDL_NS}}}types")
    if types_el is None:
        print("No encontré elemento wsdl:types en el WSDL. Abortando.")
        return 1

    # Procesar cada xsd:schema dentro de types
    for schema_el in [c for c in list(types_el) if isinstance(c, etree._Element) and etree.QName(c.tag).localname == "schema"]:
        # Recolectar imports/includes dentro de este schema (solo elementos)
        imports = [i for i in schema_el.findall(f".//{{{XSD_NS}}}import") if isinstance(i, etree._Element)]
        includes = [i for i in schema_el.findall(f".//{{{XSD_NS}}}include") if isinstance(i, etree._Element)]

        # Procesar imports: inyectar el contenido y eliminar la import si se resolvió
        for imp in imports:
            sl = imp.get("schemaLocation")
            if not sl:
                continue
            ok, msg = inject_imported_xsd_children(schema_el, sl)
            if ok:
                parent = imp.getparent()
                if parent is not None:
                    parent.remove(imp)
            else:
                print("WARNING:", msg)

        # Procesar includes de forma análoga (si existen)
        for inc in includes:
            sl = inc.get("schemaLocation")
            if not sl:
                continue
            ok, msg = inject_imported_xsd_children(schema_el, sl)
            if ok:
                parent = inc.getparent()
                if parent is not None:
                    parent.remove(inc)
            else:
                print("WARNING:", msg)

    # También procesar imports a nivel WSDL (fuera de wsdl:types) si quedan
    top_level_imports = [i for i in tree.findall(f".//{{{XSD_NS}}}import") if isinstance(i, etree._Element)]
    for imp in top_level_imports:
        sl = imp.get("schemaLocation")
        if not sl:
            continue
        # intentar encontrar un schema en types donde inyectar; si no hay, crear uno nuevo
        existing_schema = types_el.find(f".//{{{XSD_NS}}}schema")
        if existing_schema is not None:
            target_schema = existing_schema
        else:
            target_schema = etree.Element(f"{{{XSD_NS}}}schema")
            types_el.append(target_schema)

        ok, msg = inject_imported_xsd_children(target_schema, sl)
        if ok:
            parent = imp.getparent()
            if parent is not None:
                parent.remove(imp)
        else:
            print("WARNING:", msg)

    out_name = wsdl_path.with_name(wsdl_path.stem + ".inlined.wsdl")
    tree.write(str(out_name), pretty_print=True, xml_declaration=True, encoding="utf-8")
    print("WSDL inlined escrito en:", out_name)
    return 0

def main():
    wsdl_path = find_wsdl_path()
    print("WSDL a inlinear:", wsdl_path)
    return inline_wsdl(wsdl_path)

if __name__ == "__main__":
    raise SystemExit(main())
