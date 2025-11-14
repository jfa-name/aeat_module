import base64
import pathlib
import frappe
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, ec, rsa
from cryptography.hazmat.backends import default_backend


class KeyMaterial:
    def __init__(self, private_key, certificate_pem: Optional[bytes]):
        self.private_key = private_key
        self.certificate_pem = certificate_pem


def _read_bytes_from_path(path: str) -> bytes:
    return pathlib.Path(path).read_bytes()


def _read_bytes_from_attach(file_url: str) -> bytes:
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    return pathlib.Path(file_doc.get_full_path()).read_bytes()


def _read_bytes_from_site_config(key_name: str) -> bytes:
    val = frappe.get_site_config().get(key_name)
    if not val:
        frappe.throw(f"No existe la clave '{key_name}' en site_config.json")
    # admite ruta o contenido PEM
    try:
        p = pathlib.Path(val)
        if p.exists():
            return p.read_bytes()
    except Exception:
        pass
    return val.encode("utf-8")


def _extract_from_company(company: str) -> dict:
    """Leer configuración crypto desde AEAT Company Settings (si existe)"""
    try:
        cs = frappe.get_doc("AEAT Company Settings", {"company": company})
    except Exception:
        return {}

    if not getattr(cs, "override_crypto", False):
        return {}

    # Para campos tipo Password use get_password para obtener el valor descifrado
    try:
        pwd = None
        if hasattr(cs, "get_password"):
            pwd = cs.get_password("signer_private_key_password")
    except Exception:
        pwd = None

    crypto = dict(
        signer_key_source=cs.signer_key_source,
        signer_private_key_path=cs.signer_private_key_path,
        signer_private_key_password=pwd or None,
        signer_private_key_file=cs.signer_private_key_file,
        site_config_key_name=cs.site_config_key_name,
        signer_certificate_path=cs.signer_certificate_path,
        signer_algorithm=cs.signer_algorithm or "RSA-PKCS1v15",
    )
    return crypto


def load_key_material(company: Optional[str] = None) -> KeyMaterial:
    """
    Carga clave y certificado.
    Si company se pasa, intenta primero cargar desde AEAT Company Settings (override).
    Si no hay override o company no tiene datos, cae en AEAT Settings (singleton).
    """
    # 1) Try company override if provided
    key_bytes = None
    cert_bytes = None
    password = None

    if company:
        crypto = _extract_from_company(company)
        if crypto:
            source = crypto.get("signer_key_source")
            try:
                if source == "Path" and crypto.get("signer_private_key_path"):
                    key_bytes = _read_bytes_from_path(crypto.get("signer_private_key_path"))
                    cert_bytes = _read_bytes_from_path(crypto.get("signer_certificate_path")) if crypto.get("signer_certificate_path") else None
                elif source == "File (Attach)" and crypto.get("signer_private_key_file"):
                    key_bytes = _read_bytes_from_attach(crypto.get("signer_private_key_file"))
                elif source == "Site Config" and crypto.get("site_config_key_name"):
                    key_bytes = _read_bytes_from_site_config(crypto.get("site_config_key_name"))
                password = crypto.get("signer_private_key_password")
            except Exception as e:
                # log and continue to global fallback
                frappe.log_error(frappe.get_traceback(), f"AEAT: company key load failed for {company}: {e}")

    # 2) Global fallback to AEAT Settings
    if not key_bytes:
        s = frappe.get_single("AEAT Settings")
        source = getattr(s, "signer_key_source", None)
        try:
            # obtener la contraseña descifrada desde el singleton si existe
            try:
                pwd_global = s.get_password("signer_private_key_password") if hasattr(s, "get_password") else None
            except Exception:
                pwd_global = getattr(s, "signer_private_key_password", None)

            if source == "Path" and s.signer_private_key_path:
                key_bytes = _read_bytes_from_path(s.signer_private_key_path)
                cert_bytes = _read_bytes_from_path(s.signer_certificate_path) if s.signer_certificate_path else None
            elif source == "File (Attach)" and s.signer_private_key_file:
                key_bytes = _read_bytes_from_attach(s.signer_private_key_file)
            elif source == "Site Config" and s.site_config_key_name:
                key_bytes = _read_bytes_from_site_config(s.site_config_key_name)
            password = pwd_global or None
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"AEAT: global key load failed: {e}")

    if not key_bytes:
        frappe.throw("No se encontró clave privada configurada (Company o AEAT Settings).")

    # Try PEM then PKCS12
    private_key = None
    try:
        private_key = serialization.load_pem_private_key(
            key_bytes,
            password=password.encode("utf-8") if password else None,
            backend=default_backend()
        )
    except Exception:
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12
            pwd = password.encode("utf-8") if password else None
            key, cert, _ = pkcs12.load_key_and_certificates(key_bytes, pwd)
            private_key = key
            if cert and not cert_bytes:
                cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "AEAT: failed loading key material")
            frappe.throw(f"No se pudo cargar la clave privada (PEM/PFX): {e}")

    return KeyMaterial(private_key=private_key, certificate_pem=cert_bytes)


def sign_bytes(data: bytes, hash_name: str = "sha256", company: Optional[str] = None) -> Tuple[str, str]:
    """
    Firma los bytes con la clave configurada.
    Pasa company si quieres usar la configuración de la AEAT Company Settings.
    Devuelve (signature_b64, alg_used).
    """
    km = load_key_material(company)
    algo = (hashes.SHA256() if hash_name == "sha256"
            else hashes.SHA384() if hash_name == "sha384"
            else hashes.SHA512())

    if isinstance(km.private_key, rsa.RSAPrivateKey):
        # Determina algoritmo preferido (se puede extraer de la config si se quiere)
        s = frappe.get_single("AEAT Settings")
        alg_pref = getattr(s, "signer_algorithm", "RSA-PKCS1v15")
        if alg_pref == "RSA-PSS":
            signature = km.private_key.sign(
                data,
                padding.PSS(mgf=padding.MGF1(algo), salt_length=padding.PSS.MAX_LENGTH),
                algo
            )
            alg_used = "RSA-PSS-" + hash_name
        else:
            signature = km.private_key.sign(data, padding.PKCS1v15(), algo)
            alg_used = "RSA-PKCS1v15-" + hash_name
    elif isinstance(km.private_key, ec.EllipticCurvePrivateKey):
        signature = km.private_key.sign(data, ec.ECDSA(algo))
        alg_used = "ECDSA-" + hash_name
    else:
        frappe.throw("Tipo de clave no soportado (se espera RSA o ECDSA)")
        return "", ""

    return base64.b64encode(signature).decode("ascii"), alg_used