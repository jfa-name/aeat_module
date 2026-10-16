#!/usr/bin/env python3
"""
Reescribe schemaLocation para apuntar a ficheros locales sanitizados (file:// URIs).
Busca en apps/docs y apps/aeat_module/docs y produce <orig>.rewritten.wsdl.

Uso:
  /path/to/your/frappe-bench/env/bin/python apps/aeat_module/scripts/rewrite_schema_locations.py
"""
import os
from pathlib import Path
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]  # apps/aeat_module/
DOCS_CANDIDATES = [ROOT.parent / "docs", ROOT / "docs"]  # apps/docs, apps/aeat_module/docs

# Sufijos probados por orden para encontrar la versión local más adecuada
CANDIDATE_SUFFIXES = [
    ".sanitized.imports_rewritten",
    ".sanitized.inlined.flattened2",
    ".sanitized.inlined.flattened",
    ".sanitized.inlined",
    ".sanitized",
    ".cleaned.imports_rewritten",
    ".cleaned",
    ".imports_rewritten",
    ""
]

WSDL_CANDIDATES = [
    "PreSistemaFacturacion.wsdl.sanitized.imports_rewritten",
    "PreSistemaFacturacion.wsdl.sanitized",
    "PreSistemaFacturacion.wsdl.cleaned.imports_rewritten",
    "PreSistemaFacturacion.wsdl.cleaned",
    "PreSistemaFacturacion.wsdl",
]

def find_wsdl():
    # prioriza ficheros en apps/aeat_module/docs, si no los encuentra, mira apps/docs
    for docs_dir in DOCS_CANDIDATES:
        for name in WSDL_CANDIDATES:
            p = docs_dir / name
            if p.exists():
                return p
    # fallback: buscar cualquier PreSistemaFacturacion* en los docs candidatas
    for docs_dir in DOCS_CANDIDATES:
        if docs_dir.exists():
            for p in docs_dir.iterdir():
                if p.is_file() and p.name.startswith("PreSistemaFacturacion"):
                    return p
    raise SystemExit(f"No encontré PreSistemaFacturacion.* en {DOCS_CANDIDATES}")

def find_local_candidate(schema_location):
    if not schema_location:
        return None
    base = os.path.basename(schema_location)
    # caso especial: xmldsig, normalizar a fichero sanitizado si existe
    if "xmldsig-core" in base or "xmldsig" in schema_location:
        for docs_dir in DOCS_CANDIDATES:
            for nm in ("xmldsig-core-schema.xsd.sanitized", "xmldsig-core-schema.xsd"):
                cand = docs_dir / nm
                if cand.exists():
                    return cand.resolve()
    # general: probar basename + sufijos en ambos docs dirs
    for docs_dir in DOCS_CANDIDATES:
        for suff in CANDIDATE_SUFFIXES:
            cand = docs_dir / (base + suff)
            if cand.exists():
                return cand.resolve()
    # buscar por cualquier fichero que termine en base en ambos candidate dirs
    for docs_dir in DOCS_CANDIDATES:
        if docs_dir.exists():
            for p in docs_dir.iterdir():
                if p.is_file() and p.name.endswith(base):
                    return p.resolve()
    return None

def rewrite_schema_locations(wsdl_path: Path):
    print("Reescribiendo schemaLocation en:", wsdl_path)
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(wsdl_path), parser)
    root = tree.getroot()

    changed = False
    for el in root.findall(".//*[@schemaLocation]"):
        sl = el.get("schemaLocation")
        local = find_local_candidate(sl)
        if local:
            file_uri = local.as_uri()  # genera file:///abs/path de forma correcta
            if sl != file_uri:
                print(f"  {el.tag} {sl} -> {file_uri}")
                el.set("schemaLocation", file_uri)
                changed = True
        else:
            # si ya era file:// o /abs/path, dejarlo; si no, advertir
            if sl and (sl.startswith("file://") or sl.startswith("/")):
                # dejar como está, pero avisar si no existe local
                if sl.startswith("file://"):
                    path_candidate = Path(sl.replace("file://", "", 1))
                else:
                    path_candidate = Path(sl)
                if not path_candidate.exists():
                    print("WARNING: schemaLocation local apunta a fichero inexistente:", sl)
                continue
            print("WARNING: no local candidate found for schemaLocation:", sl)

    out_path = wsdl_path.with_name(wsdl_path.stem + ".rewritten.wsdl")
    tree.write(str(out_path), pretty_print=True, xml_declaration=True, encoding="utf-8")
    print("WSDL reescrito guardado en:", out_path)
    return out_path

def main():
    wsdl = find_wsdl()
    out = rewrite_schema_locations(wsdl)
    print("Hecho. Comprueba referencias remotas con: grep -R --line-number -n \"schemaLocation=\\\"http\" apps || true")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
