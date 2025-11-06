import base64
import frappe
from typing import Optional, Dict

try:
    from rfc3161_client import RFC3161TimestampClient
    HAS_RFC3161 = True
except Exception:
    HAS_RFC3161 = False

import requests


class TimestampClient:
    """
    Cliente TSA.
    - Modo RFC3161 (preferente) con rfc3161-client.
    - Fallback POST binario (si el TSA admite contrato no estándar).
    """

    def __init__(self):
        self.s = frappe.get_single("AEAT Settings")

    def _verify_arg(self):
        if not self.s.verify_tls:
            return False
        if self.s.ca_bundle_path:
            return self.s.ca_bundle_path
        return True

    def request_timestamp(self, snapshot_bytes: bytes) -> Optional[Dict]:
        algo = (self.s.tsa_hash_algo or "sha256").lower()
        verify = self._verify_arg()

        # Preferente: RFC3161
        if HAS_RFC3161:
            try:
                client = RFC3161TimestampClient(
                    tsa_url=self.s.tsa_url,
                    hashname=algo,
                    username=self.s.tsa_username or None,
                    password=self.s.tsa_password or None,
                    verify=verify,
                    timeout=15,
                    policy_oid=self.s.tsa_policy_oid or None
                )
                tsr_bytes = client.timestamp(data=snapshot_bytes)
                return {
                    "timestamp": frappe.utils.now_datetime(),  # el TSR tiene el time-stamp internamente
                    "tsa_response_der_b64": base64.b64encode(tsr_bytes).decode("ascii"),
                    "mode": "rfc3161"
                }
            except Exception:
                frappe.log_error(frappe.get_traceback(), "RFC3161 TSA request failed")

        # Fallback: POST directo (no estándar; depende del TSA)
        try:
            auth = None
            if self.s.tsa_username and self.s.tsa_password:
                auth = (self.s.tsa_username, self.s.tsa_password)
            r = requests.post(self.s.tsa_url, data=snapshot_bytes, auth=auth, timeout=15, verify=verify)
            r.raise_for_status()
            return {
                "timestamp": r.headers.get("Date") or frappe.utils.now_datetime(),
                "tsa_response_raw_b64": base64.b64encode(r.content).decode("ascii"),
                "mode": "raw-post"
            }
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Raw TSA request failed")
            return None