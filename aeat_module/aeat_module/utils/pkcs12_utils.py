import tempfile
import pathlib
from typing import Tuple, Optional

from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives.serialization import pkcs12
import frappe


def pfx_to_pem_files(pfx_bytes: bytes, password: Optional[bytes]) -> Tuple[str, str]:
    """
    Convierte un .pfx/.p12 a archivos PEM temporales (cert.pem, key.pem).
    - password: bytes or None
    Devuelve rutas (cert_path, key_path).
    El llamador debe eliminar los ficheros temporales si lo requiere.
    """
    try:
        private_key, cert, _additional = pkcs12.load_key_and_certificates(pfx_bytes, password)
    except Exception as e:
        # Mejora del mensaje de error para debugging
        frappe.log_error(frappe.get_traceback(), "AEAT pfx_to_pem_files: failed to load PKCS12")
        raise

    if not private_key or not cert:
        raise ValueError("El PFX no contiene clave y/o certificado")

    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
    cert_pem = cert.public_bytes(Encoding.PEM)

    cert_fd = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    key_fd = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    cert_fd.write(cert_pem)
    key_fd.write(key_pem)
    cert_fd.flush()
    key_fd.flush()
    cert_fd.close()
    key_fd.close()
    return cert_fd.name, key_fd.name