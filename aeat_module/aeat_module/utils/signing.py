import base64
import pathlib
import frappe
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, ec, rsa, utils
from cryptography.hazmat.backends import default_backend


class KeyMaterial:
    def __init__(self, private_key, certificate_pem: Optional[bytes]):
        self.private_key = private_key
        self.certificate_pem = certificate_pem


def _read_bytes_from_path(path: str) -> bytes:
    return pathlib.Path(path).read_bytes()


def _read_bytes_from_attach(file_url: str) -> bytes:
    # Asume File private; usa File API para resolver a path local
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


def load_key_material() -> KeyMaterial:
    """Carga clave y (opcional) certificado según AEAT Settings."""
    s = frappe.get_single("AEAT Settings")

    if s.signer_key_source == "Path":
        key_bytes = _read_bytes_from_path(s.signer_private_key_path)
        cert_bytes = _read_bytes_from_path(s.signer_certificate_path) if s.signer_certificate_path else None
    elif s.signer_key_source == "File (Attach)":
        if not s.signer_private_key_file:
            frappe.throw("Debes adjuntar la clave privada en AEAT Settings")
        key_bytes = _read_bytes_from_attach(s.signer_private_key_file)
        cert_bytes = None  # opcional: un segundo attach para cert si lo prefieres
    elif s.signer_key_source == "Site Config":
        key_bytes = _read_bytes_from_site_config(s.site_config_key_name)
        cert_bytes = None
    else:
        frappe.throw("Origen de clave no soportado")

    password = s.signer_private_key_password.encode("utf-8") if s.signer_private_key_password else None

    # Detecta PEM vs PKCS#12
    private_key = None
    try:
        private_key = serialization.load_pem_private_key(key_bytes, password=password, backend=default_backend())
    except ValueError:
        # intentar PKCS#12 (PFX)
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12
            key, cert, _ = pkcs12.load_key_and_certificates(key_bytes, password)
            private_key = key
            if cert and not cert_bytes:
                cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
        except Exception as e:
            frappe.throw(f"No se pudo cargar la clave privada (PEM/PFX): {e}")

    return KeyMaterial(private_key=private_key, certificate_pem=cert_bytes)


def sign_bytes(data: bytes, hash_name: str = "sha256") -> Tuple[str, str]:
    """
    Firma los bytes con la clave configurada.
    Devuelve (signature_b64, alg_used).
    """
    km = load_key_material()
    algo = (hashes.SHA256() if hash_name == "sha256"
            else hashes.SHA384() if hash_name == "sha384"
            else hashes.SHA512())

    if isinstance(km.private_key, rsa.RSAPrivateKey):
        s = frappe.get_single("AEAT Settings")
        if s.signer_algorithm == "RSA-PSS":
            signature = km.private_key.sign(
                data,
                padding.PSS(mgf=padding.MGF1(algo), salt_length=padding.PSS.MAX_LENGTH),
                algo
            )
            alg_used = "RSA-PSS-" + hash_name
        else:
            # RSA-PKCS1v15 por defecto
            signature = km.private_key.sign(data, padding.PKCS1v15(), algo)
            alg_used = "RSA-PKCS1v15-" + hash_name
    elif isinstance(km.private_key, ec.EllipticCurvePrivateKey):
        signature = km.private_key.sign(data, ec.ECDSA(algo))
        alg_used = "ECDSA-" + hash_name
    else:
        frappe.throw("Tipo de clave no soportado (se espera RSA o ECDSA)")
        return "", ""

    return base64.b64encode(signature).decode("ascii"), alg_used
