#!/usr/bin/env python3
"""
Limpia WSDL/XSD en apps/aeat_module/docs:
- elimina DOCTYPE y declaraciones <!ENTITY ...>
- reemplaza &dsig; por la URI literal
- reescribe schemaLocation/href con los basenames locales si existen
Es seguro ejecutarlo en el servidor (no necesita librerías externas).
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # apps/aeat_module/
DOCS_DIR = ROOT / "docs"

def clean_file(path_in: Path, path_out: Path):
    text = path_in.read_text(encoding="utf-8")
    text = re.sub(r"(?is)<!DOCTYPE[^>]*?>", "", text)
    text = re.sub(r"(?is)<!ENTITY\s+[^>]+?>", "", text)
    text = text.replace("&dsig;", "http://www.w3.org/2000/09/xmldsig#")
    path_out.write_text(text, encoding="utf-8")
    return path_out

def rewrite_imports(wsdl_clean_path: Path):
    text = wsdl_clean_path.read_text(encoding="utf-8")
    def repl(match):
        orig = match.group(0)
        url = match.group(1)
        basename = os.path.basename(url.split("?")[0])
        cleaned_candidate = DOCS_DIR / (basename + ".cleaned")
        local_candidate = DOCS_DIR / basename
        if cleaned_candidate.exists():
            new = orig.replace(url, basename + ".cleaned")
        elif local_candidate.exists():
            new = orig.replace(url, basename)
        else:
            new = orig.replace(url, basename)
        return new
    text2 = re.sub(r'schemaLocation\s*=\s*"(https?://[^"]+)"', repl, text, flags=re.IGNORECASE)
    text2 = re.sub(r'href\s*=\s*"(https?://[^"]+)"', repl, text2, flags=re.IGNORECASE)
    outp = wsdl_clean_path.with_suffix(wsdl_clean_path.suffix + ".imports_rewritten")
    outp.write_text(text2, encoding="utf-8")
    return outp

def main():
    if not DOCS_DIR.exists():
        print("ERROR: no existe el directorio docs:", DOCS_DIR)
        return 1

    cleaned_map = {}
    for p in sorted(DOCS_DIR.iterdir()):
        if p.suffix.lower() in (".wsdl", ".xsd"):
            out = p.with_name(p.name + ".cleaned")
            clean_file(p, out)
            cleaned_map[p.name] = out
            print("Limpio:", p.name, "->", out.name)

    # localizar WSDL principal (usa PreSistemaFacturacion.*)
    candidates = [
        DOCS_DIR / "PreSistemaFacturacion.wsdl.cleaned",
        DOCS_DIR / "PreSistemaFacturacion.cleaned.wsdl",
        DOCS_DIR / "PreSistemaFacturacion.wsdl"
    ]
    main_wsdl = None
    for c in candidates:
        if c.exists():
            main_wsdl = c
            break
    if not main_wsdl:
        print("ERROR: no pude encontrar PreSistemaFacturacion.wsdl limpio. Revisa docs/")
        return 2

    wsdl_rewritten = rewrite_imports(main_wsdl)
    print("WSDL imports reescritos a:", wsdl_rewritten.name)

    # Reescribir imports para cada XSD limpio si existen
    for original, cleaned_path in cleaned_map.items():
        if cleaned_path.suffix.lower().startswith(".xsd") or cleaned_path.name.endswith(".xsd.cleaned"):
            rewritten = rewrite_imports(Path(cleaned_path))
            print("Rewrites en:", Path(cleaned_path).name, "->", Path(rewritten).name)

    print("Script terminado. Archivos generados en:", DOCS_DIR)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
