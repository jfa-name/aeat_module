import json
import os
from typing import Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter, Retry
import frappe

from .company_context import get_company_context
from .pkcs12_utils import pfx_to_pem_files

class VeriFactuAuthError(Exception):
    pass

class VeriFactuClient:
    """
    Cliente VERI*FACTU por Company.
    Implementa:
      - send_invoice(doc, payload) -> (vf_id, qr_url, response_json)
      - cancel_invoice(doc, payload) -> response_json
      - get_status(vf_id) -> response_json
    Usa configuración desde AEAT Company Settings (por company).
    """

    def __init__(self, company: str):
        self.company = company
        self.cs = frappe.get_doc("AEAT Company Settings", {"company": company})
        self.ctx = get_company_context(company)
        self.base_url = self.ctx.get("verifactu_base_url")
        if not self.base_url:
            raise VeriFactuAuthError("Base URL VERI*FACTU no configurada para la Company")

        self.path_send = self.cs.get("verifactu_api_path_send") or "/api/verifactu/v1/emitidas"
        self.path_cancel = self.cs.get("verifactu_api_path_cancel") or "/api/verifactu/v1/emitidas/anulacion"
        self.path_status = self.cs.get("verifactu_api_path_status") or "/api/verifactu/v1/estado"

        self.session = requests.Session()
        retries = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"])
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.headers.update({"Content-Type": "application/json"})

        self.verify = True
        if self.cs.get("verifactu_verify_tls") is not None:
            self.verify = bool(self.cs.get("verifactu_verify_tls"))
        if self.cs.get("verifactu_ca_bundle"):
            self.verify = self.cs.get("verifactu_ca_bundle")

        self._setup_auth()

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _log_tx(self, invoice: str, endpoint: str, method: str, payload: dict, response: Optional[requests.Response]):
        log = frappe.get_doc({
            "doctype": "AEAT Transmission Log",
            "company": self.company,
            "invoice": invoice,
            "method": method,
            "endpoint": endpoint,
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "status_code": response.status_code if response else None,
            "response_json": response.text if response else None
        })
        # extraer campos útiles si vienen en JSON
        try:
            if response is not None and response.headers.get("Content-Type", "").startswith("application/json"):
                rj = response.json()
                # campos habituales de AEAT: id/csv, estado, qrUrl, codigoError, descripcionError
                log.verifactu_id = rj.get("id") or rj.get("csv") or rj.get("identificador")
                log.status_text = rj.get("estado") or rj.get("status") or None
                log.error_code = rj.get("codigoError") or rj.get("error_code") or None
                log.error_message = rj.get("descripcionError") or rj.get("message") or None
        except Exception:
            pass
        log.insert(ignore_permissions=True)
        return log

    def _read_pfx_bytes(self, pfx_path: Optional[str], pfx_attach: Optional[str]) -> bytes:
        # prioridad: path en disco -> attach
        if pfx_path:
            p = pfx_path
            if not os.path.isabs(p):
                # soportar rutas relativas -> site base
                p = os.path.join(frappe.utils.get_bench_path(), p)
            if not os.path.exists(p):
                raise VeriFactuAuthError(f"mTLS PFX path not found: {p}")
            return open(p, "rb").read()
        if pfx_attach:
            file_doc = frappe.get_doc("File", {"file_url": pfx_attach})
            return open(file_doc.get_full_path(), "rb").read()
        raise VeriFactuAuthError("No PFX configured for mTLS")

    def _setup_auth(self):
        mode = (self.cs.get("verifactu_auth_mode") or "mTLS").strip()

        if mode == "mTLS":
            pfx_path = self.cs.get("mtls_client_pfx_path")
            pfx_file = self.cs.get("mtls_client_pfx_file")
            cert_path = self.cs.get("mtls_client_cert_path")
            key_path = self.cs.get("mtls_client_key_path")

            # leer password con get_password() si el campo es tipo Password
            try:
                pwd = self.cs.get_password("mtls_client_key_password") if hasattr(self.cs, "get_password") else self.cs.get("mtls_client_key_password")
            except Exception:
                pwd = self.cs.get("mtls_client_key_password")

            # fallback: usar signer_private_key_password si no hay mtls_client_key_password
            if not pwd:
                try:
                    pwd = self.cs.get_password("signer_private_key_password") if hasattr(self.cs, "get_password") else self.cs.get("signer_private_key_password")
                except Exception:
                    pwd = self.cs.get("signer_private_key_password")

            pwd_bytes = pwd.encode("utf-8") if isinstance(pwd, str) and pwd != "" else (pwd if isinstance(pwd, bytes) else None)

            if pfx_path or pfx_file:
                pfx_bytes = self._read_pfx_bytes(pfx_path, pfx_file)
                try:
                    cert_path_out, key_path_out = pfx_to_pem_files(pfx_bytes, pwd_bytes)
                except Exception as e:
                    frappe.log_error(frappe.get_traceback(), "AEAT VERI*FACTU: failed to convert PFX to PEM")
                    raise VeriFactuAuthError(f"Error loading PFX for mTLS: {e}")
                self.session.cert = (cert_path_out, key_path_out)
            else:
                if cert_path and key_path:
                    self.session.cert = (cert_path, key_path)
                else:
                    raise VeriFactuAuthError("Configura PFX o cert+key PEM para mTLS")

        elif mode == "OAuth2":
            token_url = self.cs.get("oauth_token_url")
            client_id = self.cs.get("oauth_client_id")
            try:
                client_secret = self.cs.get_password("oauth_client_secret") if hasattr(self.cs, "get_password") else self.cs.get("oauth_client_secret")
            except Exception:
                client_secret = self.cs.get("oauth_client_secret")
            scope = self.cs.get("oauth_scope")
            if not token_url or not client_id or not client_secret:
                raise VeriFactuAuthError("Faltan parámetros OAuth2 (token_url, client_id, client_secret)")
            data = {"grant_type": "client_credentials"}
            if scope:
                data["scope"] = scope
            resp = requests.post(token_url, data=data, auth=(client_id, client_secret), timeout=15, verify=self.verify)
            if resp.status_code != 200:
                raise VeriFactuAuthError(f"Error OAuth2 {resp.status_code}: {resp.text}")
            tok = resp.json()
            self.session.headers["Authorization"] = f"{tok.get('token_type','Bearer')} {tok['access_token']}"
        else:
            raise VeriFactuAuthError(f"Modo auth no soportado: {mode}")

    def send_invoice(self, doc: "Document", payload: Dict) -> Tuple[Optional[str], Optional[str], Dict]:
        """
        Envía registro de facturación (alta).
        Devuelve (verifactu_id/csv, qr_url, response_json_dict).
        """
        url = self._url(self.path_send)
        resp = self.session.post(url, json=payload, timeout=30, verify=self.verify)
        # registrar request/response
        self._log_tx(doc.name, url, "POST", payload, resp)
        resp.raise_for_status()
        rj = resp.json() if resp.text else {}
        vf_id = rj.get("id") or rj.get("csv")
        qr_url = rj.get("qrUrl") or rj.get("qr") or None
        return vf_id, qr_url, rj

    def cancel_invoice(self, doc: "Document", payload: Dict) -> Dict:
        url = self._url(self.path_cancel)
        resp = self.session.post(url, json=payload, timeout=30, verify=self.verify)
        self._log_tx(doc.name, url, "POST", payload, resp)
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    def get_status(self, vf_id: str) -> Dict:
        url = self._url(self.path_status)
        resp = self.session.get(url, params={"id": vf_id}, timeout=20, verify=self.verify)
        self._log_tx(vf_id, url, "GET", {"id": vf_id}, resp)
        resp.raise_for_status()
        return resp.json() if resp.text else {}