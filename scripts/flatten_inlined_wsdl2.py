#!/usr/bin/env python3
"""
Flatten nested <xsd:schema> elements inside an inlined WSDL by moving the
children of nested <schema> nodes up to the nearest ancestor <schema> and
removing the nested wrapper.

This variant is defensive: it skips non-element nodes (comments, PIs),
sanitizes nsmap entries, and avoids passing invalid objects to lxml.

Usage:
  /home/develop/workspace/baygroup/env/bin/python apps/aeat_module/scripts/flatten_inlined_wsdl2.py \
    /home/develop/workspace/baygroup/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.inlined.wsdl
"""
import sys
from pathlib import Path
from lxml import etree
from copy import deepcopy

XSD_NS = "http://www.w3.org/2001/XMLSchema"
XSD_QNAME = f"{{{XSD_NS}}}schema"

def sanitize_nsmap(nsmap):
    """
    Return a sanitized nsmap dict containing only valid prefix->uri pairs,
    where prefix is None or str and uri is str.
    If any invalid entries are found, print them for diagnostics and skip.
    """
    if not nsmap:
        return {}
    cleaned = {}
    for p, u in nsmap.items():
        ok_prefix = (p is None) or isinstance(p, str)
        ok_uri = isinstance(u, str)
        if ok_prefix and ok_uri:
            cleaned[p] = u
        else:
            print("WARNING: skipping invalid nsmap entry:")
    return cleaned

def combined_nsmap(el):
    """
    Build a dict of namespaces in-scope for element `el` by walking ancestors
    and merging their nsmap (closest wins). Returns prefix->uri dict (strings only).
    """
    ns = {}
    cur = el
    ancestors = []
    while cur is not None:
        ancestors.append(cur)
        cur = cur.getparent()
    # walk from root to element so nearer ancestors override earlier ones
    for anc in reversed(ancestors):
        for p, u in (anc.nsmap or {}).items():
            if p not in ns:
                if (p is None or isinstance(p, str)) and isinstance(u, str):
                    ns[p] = u
                else:
                    print("WARNING: ignored invalid ns declaration on ancestor:", repr(p), "->", repr(u))
    return ns

def is_real_element(node):
    """Return True only for real element nodes (not comments, not PIs)."""
    return etree.iselement(node)

def clone_with_ns(el, inherited_ns=None):
    """
    Recursively clone `el` producing a new element where each element's nsmap
    contains inherited_ns merged with element's own nsmap so every node has
    explicit namespace declarations needed to resolve QNames later.

    If el is not an element, return None.
    """
    if not is_real_element(el):
        return None

    if inherited_ns is None:
        inherited_ns = {}

    # compute merged nsmap: inherited first, then el.nsmap overrides/extends
    merged = dict(inherited_ns)
    own = sanitize_nsmap(el.nsmap or {})
    merged.update(own)

    merged_clean = sanitize_nsmap(merged)

    # create new element with same tag and merged nsmap
    tag = el.tag
    if not isinstance(tag, str):
        # unexpected tag type (e.g., comment function) — skip cloning this node
        print("WARNING: skipping clone of node with non-string tag:", repr(tag))
        return None

    try:
        new = etree.Element(tag, nsmap=merged_clean)
    except Exception as exc:
        # last resort: try without nsmap and log the problem
        print("ERROR creating element with nsmap, falling back without nsmap for tag:", tag, "exception:", exc)
        new = etree.Element(tag)

    # copy attributes (they are strings, may contain qnames)
    for k, v in el.items():
        new.set(k, v)

    # copy text/tail
    if el.text:
        new.text = el.text
    if el.tail:
        new.tail = el.tail

    # recurse for child elements only
    for child in el:
        if is_real_element(child):
            new_child = clone_with_ns(child, merged_clean)
            if new_child is not None:
                new.append(new_child)
        else:
            # skip comments/PI but preserve tail text if any
            if child.tail:
                # append tail to previous child or to new.text if no children
                if len(new):
                    last = new[-1]
                    if last.tail:
                        last.tail += child.tail
                    else:
                        last.tail = child.tail
                else:
                    if new.text:
                        new.text += child.tail
                    else:
                        new.text = child.tail

    return new

def flatten_once(doc):
    """
    Find any <xsd:schema> that is a descendant of another <xsd:schema>;
    move its element children up into the nearest ancestor schema (the
    first ancestor which tag is xsd:schema), ensuring every moved node
    gets explicit ns declarations. Remove the nested schema wrapper.
    Return True if any change was made.
    """
    nested = doc.findall(f".//{XSD_QNAME}//{XSD_QNAME}")
    if not nested:
        return False

    changed = False
    for child_schema in nested:
        # find nearest ancestor schema
        parent = child_schema.getparent()
        while parent is not None and parent.tag != XSD_QNAME:
            parent = parent.getparent()
        if parent is None:
            continue

        parent_ns = combined_nsmap(parent)
        child_ns = sanitize_nsmap(child_schema.nsmap or {})

        # merge child namespaces into parent namespaces but keep parent values if conflict
        merged_parent_ns = dict(child_ns)
        merged_parent_ns.update(parent_ns)  # parent_ns overrides child_ns where same prefix
        merged_parent_ns_clean = sanitize_nsmap(merged_parent_ns)

        # create a replacement parent element with merged nsmap (sanitized)
        parent_tag = parent.tag
        if not isinstance(parent_tag, str):
            print("WARNING: parent has non-string tag, skipping:", repr(parent_tag))
            continue

        new_parent = etree.Element(parent_tag, nsmap=merged_parent_ns_clean)
        # copy attributes from old parent
        for k, v in parent.items():
            new_parent.set(k, v)
        # move existing children (elements) into new_parent
        for existing_child in [c for c in parent if is_real_element(c)]:
            new_parent.append(deepcopy(existing_child))
        # replace parent in the tree
        grandparent = parent.getparent()
        if grandparent is None:
            parent.getroottree()._setroot(new_parent)
        else:
            grandparent.replace(parent, new_parent)
        parent = new_parent

        # For each element child of child_schema, clone it with explicit ns and append to parent
        moved = 0
        for grand in [g for g in child_schema if is_real_element(g)]:
            inherited_ns = dict(parent.nsmap or {})
            cloned = clone_with_ns(grand, inherited_ns)
            if cloned is not None:
                parent.append(cloned)
                moved += 1

        # remove the nested schema element
        try:
            child_schema.getparent().remove(child_schema)
        except Exception:
            child_schema.clear()

        changed = True

    return changed

def main():
    if len(sys.argv) < 2:
        print("Usage: flatten_inlined_wsdl2.py path/to/inlined.wsdl")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print("File not found:", path)
        return 3

    doc = etree.parse(str(path))

    # iterate until no nested schema remain, safety cap
    changed = True
    it = 0
    while changed and it < 40:
        changed = flatten_once(doc)
        it += 1

    if it >= 40:
        print("Warning: reached 40 iterations. There may still be nested schemas.")

    # backup original (if not exists)
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        path.rename(bak)

    out_path = path.with_name(path.stem + ".flattened2.wsdl")
    doc.write(str(out_path), pretty_print=True, xml_declaration=True, encoding="utf-8")
    print("WSDL flattened written to:", out_path)
    print("Backup of original inlined file:", bak)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
