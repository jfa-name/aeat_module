#!/usr/bin/env python3
"""
Fix remaining $XSD_SAN / %24XSD_SAN placeholders and normalize file:// repetitions
in .wsdl/.xsd/.xml files under apps/*.

Usage:
  /home/develop/workspace/baygroup/env/bin/python apps/aeat_module/scripts/fix_remaining_xsd_placeholder.py

What it does:
- Finds the local sanitized xmldsig file (xmldsig-core-schema.xsd.sanitized) under apps/docs or apps/aeat_module/docs.
- Builds its file:// URI using Path.as_uri().
- Replaces occurrences of $XSD_SAN and %24XSD_SAN with that URI.
- Collapses duplicate file:// prefixes (e.g. file:///file:///... -> file:///...).
- Optionally replaces obvious bad constructs like file:/home/... (single slash) and ensures file:///absolute/path.
- Writes files back and prints changed files and examples of replacements.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]  # apps/aeat_module/
DOC_DIRS = [ROOT.parent / "docs", ROOT / "docs"]  # apps/docs, apps/aeat_module/docs
TARGET_NAMES = [
    "xmldsig-core-schema.xsd.sanitized",
    "xmldsig-core-schema.xsd",
]

# file types to process
EXTS = {".xsd", ".wsdl", ".xml"}

def find_xsd_sanitized():
    for docs in DOC_DIRS:
        if not docs.exists():
            continue
        for name in TARGET_NAMES:
            p = docs / name
            if p.exists():
                return p.resolve()
    return None

def normalize_file_uri(uri_text):
    """
    Normalize common problems:
    - collapse repeated 'file://' sequences
    - ensure 'file:///<abs_path>' format (use as_uri on Path if possible)
    - decode any %24XSD_SAN remnants are handled separately
    """
    # collapse repeated file:// occurrences (e.g. file:///file:///... -> file:///...)
    # We will replace any sequence of file:/...file:/... into one file:// + remainder
    # Simpler: replace 'file://file://' with 'file://' repeatedly
    new = uri_text
    while 'file://file://' in new or 'file:///file:///' in new:
        new = new.replace('file://file://', 'file://')
        new = new.replace('file:///file:///', 'file:///')
    # If it contains "file:/" but not "file://", try to correct common mistakes:
    # Replace file:////home/... -> file:///home/...
    new = re.sub(r'file:(//+)', lambda m: 'file:///' if len(m.group(1)) >= 2 else 'file:///', new)
    return new

def process_file(p: Path, xsd_uri: str):
    text = p.read_text(encoding='utf-8', errors='surrogateescape')
    orig = text
    changed = False
    # 1) Replace placeholder patterns
    # Replace literal $XSD_SAN and URL-encoded %24XSD_SAN with xsd_uri
    if '$XSD_SAN' in text or '%24XSD_SAN' in text:
        text = text.replace('$XSD_SAN', xsd_uri)
        text = text.replace('%24XSD_SAN', xsd_uri)
        changed = True

    # 2) Collapse repeated file:// occurrences (which can occur due to earlier substitutions)
    if 'file://file://' in text or 'file:///file:///' in text:
        text = normalize_file_uri(text)
        changed = True

    # 3) Some files might contain "file:///home/develop/.../file:///home/..." due to previous substitutions
    # Normalize any occurrences of multiple 'file://' segments separated by path parts:
    # Use a regex to find file://...file://... and replace by the last file://... (more robust)
    def collapse_match(m):
        s = m.group(0)
        # take the last 'file://' occurrence and everything after it
        last = s.rfind('file://')
        return s[last:]
    text_before = text
    text = re.sub(r'(file://[^"\'>\s]+){2,}', collapse_match, text)
    if text != text_before:
        changed = True

    # 4) Ensure schemaLocation attributes that are absolute file paths are proper file:// URIs.
    # Find schemaLocation="..." occurrences and normalize if they start with '/home' (absolute path without scheme)
    def repl_schema_location(m):
        val = m.group(1)
        if val.startswith('/'):
            # absolute path: convert to file:// URI via Path.as_uri
            try:
                pth = Path(val)
                if pth.exists():
                    return f'schemaLocation="{pth.resolve().as_uri()}"'
                else:
                    # try to normalize duplicates inside val
                    new_val = normalize_file_uri(val)
                    return f'schemaLocation="{new_val}"'
            except Exception:
                return f'schemaLocation="{val}"'
        return f'schemaLocation="{val}"'
    text2 = re.sub(r'schemaLocation="([^"]+)"', repl_schema_location, text)
    if text2 != text:
        text = text2
        changed = True

    # 5) Final pass: collapse any remaining 'file:///file:///' or 'file://file://'
    final = normalize_file_uri(text)
    if final != text:
        text = final
        changed = True

    if changed and text != orig:
        # Backup original file (first time only)
        backup = p.with_suffix(p.suffix + '.bak')
        if not backup.exists():
            backup.write_bytes(orig.encode('utf-8', 'surrogateescape'))
        p.write_text(text, encoding='utf-8', errors='surrogateescape')
        print(f"[FIXED] {p}")
        # print a short preview where replacements occurred
        for line in text.splitlines():
            if xsd_uri in line or '$XSD_SAN' in line or '%24XSD_SAN' in line:
                print("  >>>", line.strip()[:240])
        return True
    return False

def main():
    xsd_path = find_xsd_sanitized()
    if not xsd_path:
        print("ERROR: no encontré xmldsig-core-schema.xsd.sanitized en los directorios docs.")
        print("Busca manualmente y coloca el fichero en apps/docs o apps/aeat_module/docs.")
        return 2
    xsd_uri = xsd_path.resolve().as_uri()
    print("Usando XSD sanitizado URI:", xsd_uri)

    modified = []
    for docs in DOC_DIRS:
        if not docs.exists():
            continue
        for f in docs.rglob("*"):
            if f.is_file() and f.suffix.lower() in EXTS:
                try:
                    if process_file(f, xsd_uri):
                        modified.append(f)
                except Exception as exc:
                    print(f"ERROR procesando {f}: {exc}")

    if modified:
        print("\nFicheros modificados:")
        for m in modified:
            print(" -", m)
    else:
        print("No se modificó ningún fichero (no se encontraron placeholders).")
    print("Terminado.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
