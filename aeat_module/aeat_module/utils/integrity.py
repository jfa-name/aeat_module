import json
import hashlib
import base64
from collections import OrderedDict

def canonicalize_doc(doc_dict):
    """
    JSON determinista:
    - ordena claves
    - excluye campos volátiles
    - devuelve bytes UTF-8
    """
    volatile = {"modified", "modified_by", "creation", "owner", "__last_sync_on", "idx", "_user_tags", "_comments"}
    def _clean(d):
        if isinstance(d, dict):
            o = OrderedDict()
            for k in sorted(d.keys()):
                if k in volatile:
                    continue
                o[k] = _clean(d[k])
            return o
        if isinstance(d, list):
            return [_clean(x) for x in d]
        return d

    cleaned = _clean(doc_dict)
    s = json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)
    return s.encode("utf-8")

def hash_snapshot(snapshot_bytes, algo: str = "sha256"):
    if algo == "sha256":
        h = hashlib.sha256(snapshot_bytes).digest()
    elif algo == "sha384":
        h = hashlib.sha384(snapshot_bytes).digest()
    else:
        h = hashlib.sha512(snapshot_bytes).digest()
    return base64.b64encode(h).decode("ascii")