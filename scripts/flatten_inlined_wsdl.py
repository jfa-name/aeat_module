#!/usr/bin/env python3
"""
Flatten nested <xsd:schema> elements inside a WSDL inlined file.

Usage (from repo root):
  /home/develop/workspace/baygroup/env/bin/python apps/aeat_module/scripts/flatten_inlined_wsdl.py \
    /home/develop/workspace/baygroup/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.inlined.wsdl

It writes a new file with suffix ".flattened.wsdl" in the same directory.
"""
import sys
from pathlib import Path
from lxml import etree
from copy import deepcopy

XSD_NS = "http://www.w3.org/2001/XMLSchema"

def copy_ns_decls(src_el, dst_el):
    """Copy xmlns:prefix declarations from src_el to dst_el (if missing)."""
    # src_el.nsmap is a dict prefix->uri (prefix may be None for default ns)
    for prefix, uri in (src_el.nsmap or {}).items():
        if prefix is None:
            attr = "xmlns"
        else:
            attr = f"xmlns:{prefix}"
        # If not already declared on destination, set it as attribute
        if dst_el.get(attr) is None:
            dst_el.set(attr, uri)

def flatten_schemas(wsdl_path: Path):
    if not wsdl_path.exists():
        raise SystemExit(f"File not found: {wsdl_path}")
    doc = etree.parse(str(wsdl_path))
    root = doc.getroot()

    # Find all schema elements
    schemas = doc.findall(f".//{{{XSD_NS}}}schema")
    flattened_any = False
    for parent_schema in schemas:
        # need to iterate over a snapshot list since we may modify children
        for child in list(parent_schema):
            # only consider element nodes
            if not isinstance(child, etree._Element):
                continue
            # detect nested schema elements (child.tag may include namespace)
            try:
                if etree.QName(child.tag).localname == "schema":
                    # 1) copy namespace declarations from nested schema to parent
                    copy_ns_decls(child, parent_schema)
                    # 2) move grandchildren (only element children) up to parent_schema
                    moved = 0
                    for grand in [g for g in child if isinstance(g, etree._Element)]:
                        parent_schema.append(deepcopy(grand))
                        moved += 1
                    # 3) remove the nested schema element
                    parent_schema.remove(child)
                    flattened_any = True
                    # continue scanning this parent for more nested schemas
            except Exception:
                # ignore malformed tag names
                continue

    if not flattened_any:
        print("No nested <schema> elements found or nothing to flatten.")
    # write output
    out_path = wsdl_path.with_name(wsdl_path.stem + ".flattened.wsdl")
    # backup original (optional)
    backup = wsdl_path.with_suffix(wsdl_path.suffix + ".bak")
    if not backup.exists():
        wsdl_path.replace(backup)  # atomically move original to backup
        # and write the modified doc to original path, then rename to flattened later
        # But to keep behavior simpler, write flattened directly
        # restore original from backup path for safety
        wsdl_path = backup
        # parse again from backup
        doc = etree.parse(str(backup))
        root = doc.getroot()
    # Actually use original filename from argv for reading/writing
    # Reparse input file to ensure consistent state
    doc2 = etree.parse(str(sys.argv[1]))
    # perform flattening again on doc2 (safer path)
    # We'll use the modifications we applied above (we already computed flattened_any)
    # But to avoid complexity, simply write the modified tree we created earlier:
    # (we used 'doc' originally and possibly replaced wsdl_path -> backup; use 'doc')
    # Write out the modified tree (root) to out_path
    try:
        doc.write(str(out_path), pretty_print=True, xml_declaration=True, encoding="utf-8")
    except Exception as e:
        # fallback: write root string
        out_path.write_bytes(etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="utf-8"))
    print("WSDL flattened written to:", out_path)
    print("Original (backup) kept as:", backup if backup.exists() else "(original kept)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: flatten_inlined_wsdl.py path/to/PreSistemaFacturacion.wsdl.sanitized.inlined.wsdl")
        raise SystemExit(1)
    wsdl_file = Path(sys.argv[1])
    flatten_schemas(wsdl_file)
