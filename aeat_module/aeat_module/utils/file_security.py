# -*- coding: utf-8 -*-
"""
Red de seguridad: certificados/claves subidos vía Attach (p.ej.
AEAT Company Settings.mtls_client_pfx_file, AEAT Settings.signer_private_key_file)
pueden acabar con permisos de fichero demasiado abiertos (p.ej. 0644/0664 según
el umask del sistema al guardarlos), dejando la clave privada legible por otros
usuarios del servidor. Esta función los restringe a solo-propietario (0600).
"""
import os
from pathlib import Path

import frappe


def secure_attached_file(file_url: str) -> None:
    if not file_url:
        return
    try:
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        path = Path(file_doc.get_full_path())
        if path.exists():
            os.chmod(path, 0o600)
    except Exception:
        # Best-effort: no bloquear el guardado del documento por esto.
        frappe.log_error(frappe.get_traceback(), "AEAT: secure_attached_file failed")
