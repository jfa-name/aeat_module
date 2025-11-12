import json
import hashlib
import base64
from collections import OrderedDict
from datetime import date, datetime, time
from decimal import Decimal

# Lista de campos volátiles que no deben formar parte del snapshot
VOLATILE_FIELDS = {
    "modified", "modified_by", "creation", "owner", "__last_sync_on", "idx",
    "_user_tags", "_comments"
}


def _normalize_value(v):
    """Normalize non-JSON-native types into JSON-serializable primitives."""
    if v is None:
        return None
    if isinstance(v, (str, bool, int, float)):
        return v
    if isinstance(v, Decimal):
        # Use plain string with full decimal digits (no exponent)
        # You may want to quantize depending on AEAT spec (e.g. 2 decimals)
        return format(v, "f")
    if isinstance(v, (datetime, date, time)):
        # ISO 8601 representation (deterministic)
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return base64.b64encode(bytes(v)).decode("ascii")
    # Fallback: try to convert to str (last resort)
    try:
        return str(v)
    except Exception:
        return None


def canonicalize_doc(doc_dict):
    """
    Deterministic JSON canonicalization:
    - sorts dictionary keys
    - removes volatile fields (modified, owner, etc.)
    - normalizes dates, decimals, bytes to deterministic strings
    - returns bytes (utf-8)
    """
    def _clean(obj):
        if isinstance(obj, dict):
            o = OrderedDict()
            for k in sorted(obj.keys()):
                if k in VOLATILE_FIELDS:
                    continue
                v = obj[k]
                cleaned_v = _clean(v)
                # Only include keys with non-None values? Keep None to preserve schema.
                o[k] = cleaned_v
            return o
        if isinstance(obj, list):
            # Keep list order; clean each element
            return [_clean(v) for v in obj]
        # Primitive / non-container -> normalize
        return _normalize_value(obj)

    cleaned = _clean(doc_dict)
    # Ensure separators without spaces for deterministic output
    s = json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)
    return s.encode("utf-8")


def hash_snapshot(snapshot_bytes, algo: str = "sha256"):
    """
    Compute Base64-encoded digest using selected algorithm.
    """
    if algo == "sha256":
        h = hashlib.sha256(snapshot_bytes).digest()
    elif algo == "sha384":
        h = hashlib.sha384(snapshot_bytes).digest()
    elif algo == "sha512":
        h = hashlib.sha512(snapshot_bytes).digest()
    else:
        # default to sha256 if unknown
        h = hashlib.sha256(snapshot_bytes).digest()
    return base64.b64encode(h).decode("ascii")