# -*- coding: utf-8 -*-
"""
Código QR VERI*FACTU, según "Detalle de las especificaciones técnicas del
código QR de la factura y de la URL del servicio de cotejo..." (AEAT).

- URL con 4 parámetros obligatorios: nif, numserie, fecha (DD-MM-AAAA),
  importe. Solo contempla el caso "Sistema que emite facturas verificables"
  (VERI*FACTU), que es el único soportado por este módulo.
- Nivel de corrección de errores M (medio), tamaño impreso entre 30x30 y
  40x40 mm (según ISO/IEC 18004:2015) — el tamaño físico se controla desde
  el Print Format, no desde la imagen generada aquí.
"""
from urllib.parse import quote

import frappe

QR_BASE_URL = {
    "preprod": "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR",
    "prod": "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR",
}


def build_qr_url(environment: str, nif: str, num_serie: str, fecha: str, importe: str) -> str:
    """Construye la URL de cotejo/QR con URL-encoding de los valores (UTF-8)."""
    base = QR_BASE_URL.get(environment, QR_BASE_URL["preprod"])
    params = [
        ("nif", nif or ""),
        ("numserie", num_serie or ""),
        ("fecha", fecha or ""),
        ("importe", importe or ""),
    ]
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
    return f"{base}?{query}"


def generate_qr_png_bytes(url: str) -> bytes:
    """Genera el PNG del código QR (nivel de corrección M) para la URL dada.

    Requiere el paquete opcional 'qrcode[pil]'. Se importa de forma perezosa
    para no exigir la dependencia a instalaciones que aún no usan VERI*FACTU.
    """
    try:
        import qrcode
    except ImportError as e:
        raise RuntimeError(
            "El paquete 'qrcode' no está instalado. Añade 'qrcode[pil]' a las "
            "dependencias de aeat_module e instálalo en el entorno del bench."
        ) from e

    import io

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_qr_attachment(doc, png_bytes: bytes, filename: str) -> str:
    """Guarda el PNG como archivo adjunto de la Sales Invoice y devuelve su file_url."""
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": filename,
        "attached_to_doctype": doc.doctype,
        "attached_to_name": doc.name,
        "attached_to_field": "verifactu_qr_image",
        "content": png_bytes,
        "is_private": 0,
    })
    file_doc.flags.ignore_permissions = True
    file_doc.save(ignore_permissions=True)
    return file_doc.file_url
