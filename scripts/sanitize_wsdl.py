#!/usr/bin/env python3
"""
Sanitiza WSDL/XSD en apps/aeat_module/docs para que zeep/lxml no fallen con EntitiesForbidden.
- elimina DOCTYPE con internal DTD subset: <!DOCTYPE ... [ ... ]>
- elimina cualquier declaración <!ENTITY ...>
- reemplaza &dsig; por la URI http://www.w3.org/2000/09/xmldsig#
- reescribe schemaLocation/href que apunten a URLs remotas para usar archivos locales donde existan
Genera archivos .sanitized and .sanitized.imports_rewritten
"""
import re
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"

def sanitize_text(text: str) -> str:
    # 1) Remove DOCTYPE with internal subset: <!DOCTYPE name [ ... ]>
    text = re.sub(r'(?is)<!DOCTYPE[^>]*\[[\s\S]*?\]>', '', text)
    # 2) Remove any remaining DOCTYPE without internal subset
    text = re.sub(r'(?is)<!DOCTYPE[^>]*?>', '', text)
    # 3) Remove ENTITY declarations
    text = re.sub(r'(?is)<!ENTITY\s+[^>]+?>', '', text)
    # 4) Replace common entity references used by these WS/XSD
    text = text.replace("&dsig;", "http://www.w3.org/2000/09/xmldsig#")
    return text

def rewrite_imports(text: str) -> str:
    def repl(match):
        orig = match.group(0)
        url = match.group(1)
        basename = os.path.basename(url.split("?")[0])
        cleaned_candidate = DOCS_DIR / (basename + ".sanitized")
        local_candidate = DOCS_DIR / basename
        if cleaned_candidate.exists():
            return orig.replace(url, basename + ".sanitized")
        elif local_candidate.exists():
            return orig.replace(url, basename)
        else:
            return orig.replace(url, basename)
    text2 = re.sub(r'schemaLocation\s*=\s*"(https?://[^"]+)"', repl, text, flags=re.IGNORECASE)
    text2 = re.sub(r'href\s*=\s*"(https?://[^"]+)"', repl, text2, flags=re.IGNORECASE)
    return text2

def main():
    if not DOCS_DIR.exists():
        print("ERROR: no existe", DOCS_DIR)
        return 1

    created = []
    for p in sorted(DOCS_DIR.iterdir()):
        if p.suffix.lower() in (".wsdl", ".xsd"):
            txt = p.read_text(encoding="utf-8")
            sanitized = sanitize_text(txt)
            out = p.with_name(p.name + ".sanitized")
            out.write_text(sanitized, encoding="utf-8")
            print("Sanitizado:", p.name, "->", out.name)
            created.append(out)

    # rewrite imports for main WSDL candidate(s)
    main_candidates = [
        DOCS_DIR / "PreSistemaFacturacion.wsdl.sanitized",
        DOCS_DIR / "PreSistemaFacturacion.sanitized.wsdl",
        DOCS_DIR / "PreSistemaFacturacion.wsdl"
    ]
    main_wsdl = None
    for c in main_candidates:
        if c.exists():
            main_wsdl = c
            break
    if not main_wsdl:
        print("WARNING: no pude encontrar el WSDL principal entre:", [str(c) for c in main_candidates])
        # still try to rewrite imports for every sanitized file
        for f in created:
            txt = f.read_text(encoding="utf-8")
            rewritten = rewrite_imports(txt)
            out = f.with_suffix(f.suffix + ".imports_rewritten")
            out.write_text(rewritten, encoding="utf-8")
            print("Imports reescritos para:", f.name, "->", out.name)
        return 0

    wsdl_text = main_wsdl.read_text(encoding="utf-8")
    wsdl_rewritten_text = rewrite_imports(wsdl_text)
    wsdl_out = main_wsdl.with_suffix(main_wsdl.suffix + ".imports_rewritten")
    wsdl_out.write_text(wsdl_rewritten_text, encoding="utf-8")
    print("WSDL imports reescritos en:", wsdl_out.name)

    # rewrite imports for each sanitized XSD too
    for p in created:
        txt = p.read_text(encoding="utf-8")
        rewritten = rewrite_imports(txt)
        out = p.with_suffix(p.suffix + ".imports_rewritten")
        out.write_text(rewritten, encoding="utf-8")
        print("Imports reescritos para:", p.name, "->", out.name)

    print("Sanitización completada. Comprueba los archivos *.sanitized y *.imports_rewritten en", DOCS_DIR)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
