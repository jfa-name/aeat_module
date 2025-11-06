import requests
import frappe
import base64

class TimestampClient:
    """
    Minimal TSA client. Configure TSA_URL in Site Config or Single Doc.
    request_timestamp(snapshot_bytes) -> {"timestamp": ..., "tsa_response": ...} or None
    """

    def __init__(self):
        self.tsa_url = frappe.get_site_config().get("aeat_tsa_url") or frappe.db.get_single_value("AEAT Settings", "tsa_url") or None

    def request_timestamp(self, snapshot_bytes):
        if not self.tsa_url:
            return None
        try:
            # POST raw snapshot to TSA; this is a placeholder contract.
            r = requests.post(self.tsa_url, data=snapshot_bytes, timeout=10)
            r.raise_for_status()
            # return token and server time
            return {"timestamp": r.headers.get("Date"), "tsa_response": base64.b64encode(r.content).decode("ascii")}
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "AEAT TSA request failed")
            return None
