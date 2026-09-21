#!/usr/bin/env python3
"""
Recorre apps/docs y apps/aeat_module/docs y reescribe schemaLocation relativos
por file:// URIs apuntando a las versiones locales sanitizadas si existen.

Uso:
  /home/develop/workspace/baygroup/env/bin/python apps/aeat_module/scripts/fix_schema_locations_absolute.py
"""
from pathlib import Path
from lxml import etree
import re

ROOT = Path(__file__).resolve().parents[2]           # apps/aeat_module/
DOCS_DIRS = [ROOT.parent / "docs", ROOT / "docs"]    # apps/docs, apps/aeat_module/docs
CANDIDATE_SUFFIXES = [
    ".sanitized.imports_rewritten",
    ".sanitized.inlined.flattened2",
    ".sanitized.inlined.flattened",
    ".sanitized.inlined",
    ".sanitized",
    ".cleaned.imports_rewritten",
    ".cleaned.imports_rewritten",
    ".imports_rewritten",
    ""
]

def find_candidate(base_name):
    for docs in DOCS_DIRS:
        if not docs.exists():
            continue
        # try exact + suffixes
        for suff in CANDIDATE_SUFFIXES:
            p = docs / (base_name + suff)
            if p.exists():
                return p.resolve()
        # fallback: any file ending with base_name
        for p in docs.iterdir():
            if p.is_file() and p.name.endswith(base_name):
                return p.resolve()
    return None

def rewrite_file(path):
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()
    changed = False

    # find all elements with schemaLocation attribute
    for el in root.findall('.//*[@schemaLocation]'):
        sl = el.get('schemaLocation') or ""
        sl = sl.strip()
        if not sl:
            continue

        # placeholder $XSD_SAN -> try to replace with actual sanitized xmldsig path
        if "$XSD_SAN" in sl:
            # try to locate xmldsig sanitized file
            cand = find_candidate("xmldsig-core-schema.xsd.sanitized")
            if cand:
                new = cand.as_uri()
                el.set('schemaLocation', new)
                print(f"[{path.name}] Replaced placeholder $XSD_SAN -> {new}")
                changed = True
                continue
            else:
                print(f"[{path.name}] WARNING: placeholder $XSD_SAN found but no xmldsig candidate located.")
                continue

        # if already absolute (http(s) or file:// or startswith /), leave as is (but warn if remote)
        if sl.startswith("http://") or sl.startswith("https://"):
            print(f"[{path.name}] INFO: remote schemaLocation left as-is: {sl}")
            continue
        if sl.startswith("file://") or sl.startswith("/"):
            # check target exists (if file:// convert to path)
            if sl.startswith("file://"):
                testpath = Path(sl.replace("file://", "", 1))
            else:
                testpath = Path(sl)
            if not testpath.exists():
                # try to find candidate by basename
                cand = find_candidate(testpath.name)
                if cand:
                    el.set('schemaLocation', cand.as_uri())
                    print(f"[{path.name}] Fixed non-existing absolute path {sl} -> {cand.as_uri()}")
                    changed = True
                else:
                    print(f"[{path.name}] WARNING: absolute schemaLocation not found: {sl}")
            continue

        # otherwise it's relative (basename or relative path). Find local candidate by basename
        base = Path(sl).name
        cand = find_candidate(base)
        if cand:
            el.set('schemaLocation', cand.as_uri())
            print(f"[{path.name}] Replaced relative {sl} -> {cand.as_uri()}")
            changed = True
        else:
            print(f"[{path.name}] WARNING: no local candidate found for relative schemaLocation: {sl}")

    if changed:
        tree.write(str(path), pretty_print=True, xml_declaration=True, encoding="utf-8")
    return changed

def main():
    modified = []
    for docs in DOCS_DIRS:
        if not docs.exists():
            continue
        for f in docs.glob("*"):
            if f.suffix.lower() not in ('.xsd', '.wsdl', '.xml'):
                continue
            try:
                if rewrite_file(f):
                    modified.append(f)
            except Exception as e:
                print(f"ERROR rewriting {f}: {e}")
    if modified:
        print("Files modified:")
        for p in modified:
            print(" -", p)
    else:
        print("No files modified.")
    print("Done.")

if __name__ == '__main__':
    main()
