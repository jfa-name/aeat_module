#!/usr/bin/env python3
"""
Inlinear las XSD importadas dentro del WSDL principal para que zeep no intente
descargar imports remotos que provocan EntitiesForbidden.

Salida: <orig>-inlined.wsdl en el mismo directorio docs/.
Uso: desde la raíz del repo:
  /home/develop/workspace/baygroup/env/bin/python apps/aeat_module/scripts/inline_wsdl.py
"""
import os
from pathlib import Path
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]  # apps/aeat_module/
DOCS = ROOT / "docs"
WSDL_NAMES = [
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

def find_wsdl_path():
    for name in WSDL_NAMES:
        p = DOCS / name
        if p.exists():
            return p
    # fallback: try any file starting with PreSistemaFacturacion in docs
    for p in DOCS.iterdir():
        if p.is_file() and p.name.startswith("PreSistemaFacturacion") and p.suffix in (".wsdl", ".xml"):
            return p
    raise SystemExit("No encontré el WSDL PreSistemaFacturacion en {}".format(DOCS))

def resolve_xsd_file(schemaLocation):
    # schemaLocation puede ser un URL o un basename; buscamos variantes locales
    basename = os.path.basename(schemaLocation)
    # probar con varios sufijos
    for suff in XSD_CANDIDATE_SUFFIXES:
        candidate = DOCS / (basename + suff)
        if candidate.exists():
            return candidate
    # si no lo encontramos, probar basename tal cual (ya incluido), o raise
    candidate = DOCS / basename
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"No encontré XSD local para schemaLocation '{schemaLocation}' (busqué en {DOCS})")

def inline_xsd_recursive(xsd_path, visited):
    """
    Devuelve una lista de xsd:schema Element (copias) con imports inlineados recursivamente.
    visited es set para evitar ciclos.
    """
    xsd_path = Path(xsd_path)
    key = str(xsd_path.resolve())
    if key in visited:
        return []  # ya procesado
    visited.add(key)

    doc = etree.parse(str(xsd_path))
    root = doc.getroot()

    # obtener el elemento schema adecuado
    try:
        root_tag_local = etree.QName(root.tag).localname
    except Exception:
        root_tag_local = None

    if root_tag_local != 'schema':
        found = root.find('.//{http://www.w3.org/2001/XMLSchema}schema')
        if found is not None:
            root = found

    # Crear una copia limpia del schema (nuevo elemento con mismos atributos)
    schema_copy = etree.Element(root.tag, nsmap=root.nsmap)
    for k, v in root.items():
        schema_copy.set(k, v)

    # recorrer solo ELEMENT children y reemplazar imports por su contenido (recursivamente)
    for child in root:
        # ignorar no-element nodes (comentarios, PIs, etc.)
        if not isinstance(child, etree._Element):
            continue
        try:
            tag_local = etree.QName(child.tag).localname
        except Exception:
            # si por alguna razón no es un tag válido, saltarlo
            continue

        if tag_local in ("import", "include"):
            schemaLocation = child.get("schemaLocation")
            if not schemaLocation:
                # mantener la import si no hay schemaLocation (no podemos resolverla)
                schema_copy.append(child)
                continue
            try:
                xsd_file = resolve_xsd_file(schemaLocation)
            except FileNotFoundError as e:
                print(f"WARNING: no pude resolver import '{schemaLocation}' desde {xsd_path}: {e}")
                # conservar la import original para no perder información
                schema_copy.append(child)
                continue
            # inlinear el contenido del XSD importado (recursivo)
            imported_schemas = inline_xsd_recursive(xsd_file, visited)
            if imported_schemas:
                for s in imported_schemas:
                    schema_copy.append(s)
            else:
                # si no retornó nada, intentar añadir el fichero importado como schema raw
                try:
                    imported_doc = etree.parse(str(xsd_file))
                    imported_root = imported_doc.getroot()
                    # añadir solo elementos (evitar comments)
                    for sub in [c for c in imported_root if isinstance(c, etree._Element)]:
                        schema_copy.append(sub)
                except Exception as e:
                    print(f"WARNING: no pude parsear/inlinear {xsd_file}: {e}")
                    schema_copy.append(child)
        else:
            # copiar el elemento tal cual (clon profundo)
            schema_copy.append(child)

    return [schema_copy]

def main():
    wsdl_path = find_wsdl_path()
    print("WSDL a inlinear:", wsdl_path)
    tree = etree.parse(str(wsdl_path))
    root = tree.getroot()

    # localizar wsdl:types
    types_el = root.find('.//{http://schemas.xmlsoap.org/wsdl/}types')
    if types_el is None:
        print("No encontré elemento wsdl:types en el WSDL. Abortando.")
        return 1

    new_schemas = []
    visited = set()

    # procesar xsd:schema dentro de types y sus imports
    for child in list(types_el):
        if not isinstance(child, etree._Element):
            continue
        try:
            if etree.QName(child.tag).localname == "schema":
                # procesar imports del schema actual
                for imp in [i for i in child.findall('.//{http://www.w3.org/2001/XMLSchema}import') if isinstance(i, etree._Element)]:
                    sl = imp.get("schemaLocation")
                    if sl:
                        try:
                            xsd_file = resolve_xsd_file(sl)
                            imported = inline_xsd_recursive(xsd_file, visited)
                            for s in imported:
                                new_schemas.append(s)
                        except FileNotFoundError:
                            print("WARNING: import no resuelto:", sl)
                # añadir el schema original (sin modificaciones)
                new_schemas.append(child)
        except Exception:
            continue

    # procesar imports declarados en todo el WSDL (por si quedan)
    for imp in [i for i in tree.findall('.//{http://www.w3.org/2001/XMLSchema}import') if isinstance(i, etree._Element)]:
        sl = imp.get("schemaLocation")
        if sl:
            try:
                xsd_file = resolve_xsd_file(sl)
                imported = inline_xsd_recursive(xsd_file, visited)
                for s in imported:
                    if s not in new_schemas:
                        new_schemas.append(s)
            except FileNotFoundError:
                print("WARNING: import no resuelto en WSDL:", sl)

    if not new_schemas:
        print("No se generaron schemas inlineados — puede que las referencias estén ya inlineadas.")
    else:
        # eliminar schemas existentes en types_el
        for child in list(types_el):
            if not isinstance(child, etree._Element):
                continue
            try:
                if etree.QName(child.tag).localname == "schema":
                    types_el.remove(child)
            except Exception:
                continue
        # insertar los schemas inlineados en types_el
        for s in new_schemas:
            types_el.append(s)

    # escribir WSDL resultante
    out_name = wsdl_path.with_name(wsdl_path.stem + ".inlined.wsdl")
    tree.write(str(out_name), pretty_print=True, xml_declaration=True, encoding="utf-8")
    print("WSDL inlined escrito en:", out_name)
    print("Comprueba el archivo y luego carga con zeep apuntando a ese WSDL.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
