import json
import hashlib
import base64
import frappe
from collections import OrderedDict

def canonicalize_doc(doc_dict):
    """
    Deterministic JSON canonicalization:
    - sort keys, remove non-essential volatile fields (modified, idx, _server)
    - returns bytes (utf-8)
    """
    def _clean(d):
        if isinstance(d, dict):
            o = OrderedDict()
            for k in sorted(d.keys()):
                if k in ("modified", "modified_by", "creation", "owner", "__last_sync_on"):
                    continue
                v = d[k]
                o[k] = _clean(v)
            return o
        elif isinstance(d, list):
            return [_clean(v) for v in d]
        else:
            return d

    cleaned = _clean(doc_dict)
    # Use separators to avoid spaces
    s = json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)
    return s.encode("utf-8")

def hash_snapshot(snapshot_bytes):
    h = hashlib.sha256(snapshot_bytes).digest()
    return base64.b64encode(h).decode("ascii")

def sign_hash(hash_b64):
    """
    Placeholder signing: in production call HSM or external signer.
    Here we store a pseudo-signature (hash prefixed). Replace integration later.
    """
    # simple deterministic "signature" for PoC:
    return "SIG:" + hash_b64
