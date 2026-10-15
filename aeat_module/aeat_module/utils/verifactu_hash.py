# -*- coding: utf-8 -*-
"""
Huella (hash) oficial VERI*FACTU, según:
"Detalle de las especificaciones técnicas para generación de la huella o hash
de los registros de facturación" (AEAT, v0.1.2, RD 1007/2023 art. 13).

Reglas clave de la especificación:
- Algoritmo: SHA-256 (único permitido a la fecha del documento).
- Entrada: concatenación "campo1=valor1&campo2=valor2&...&campoN=valorN" en el
  orden exacto indicado por la especificación (distinto para alta/anulación),
  codificada en UTF-8. Campos ausentes se informan como "campo=" (sin valor).
- Salida: hexadecimal en MAYÚSCULAS, 64 caracteres.
"""
import hashlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")


def format_importe(value) -> str:
    """Formatea un importe con 2 decimales y '.' como separador (p.ej. 123.45)."""
    return "{:.2f}".format(float(value or 0))


def format_fecha_expedicion(value) -> str:
    """Convierte una fecha a formato DD-MM-AAAA exigido por la especificación."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        value = datetime.strptime(value[:10], "%Y-%m-%d").date()
    if not isinstance(value, date):
        raise ValueError(f"Fecha de expedición no reconocida: {value!r}")
    return value.strftime("%d-%m-%Y")


def now_fecha_hora_huso() -> datetime:
    """Instante actual, con el huso horario de España (Europe/Madrid)."""
    return datetime.now(tz=MADRID_TZ)


def format_fecha_hora_huso(value: datetime) -> str:
    """Formatea datetime consciente de zona horaria como ISO8601 con offset
    (p.ej. 2024-01-01T19:20:30+01:00), tal y como exige FechaHoraHusoGenRegistro."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=MADRID_TZ)
    return value.isoformat(timespec="seconds")


def determine_tipo_factura(doc) -> str:
    """Determina el campo TipoFactura (Lista L2) a partir de la Sales Invoice.
    Por ahora solo distingue Factura completa (F1) de Rectificativa por
    sustitución (R1); el resto de subtipos rectificativos (R2-R5) y F2/F3
    requieren reglas de negocio adicionales (pendiente, ver docs/CONFIG.md).
    """
    if doc.get("is_return"):
        return "R1"
    return "F1"


def compute_huella_alta(
    nif_emisor: str,
    num_serie_factura: str,
    fecha_expedicion: str,
    tipo_factura: str,
    cuota_total: str,
    importe_total: str,
    huella_anterior: str | None,
    fecha_hora_gen_registro: str,
) -> str:
    """Huella para RegistroAlta (alta de factura). Devuelve hex mayúsculas (64 chars)."""
    parts = [
        f"IDEmisorFactura={nif_emisor or ''}",
        f"NumSerieFactura={num_serie_factura or ''}",
        f"FechaExpedicionFactura={fecha_expedicion or ''}",
        f"TipoFactura={tipo_factura or ''}",
        f"CuotaTotal={cuota_total or ''}",
        f"ImporteTotal={importe_total or ''}",
        f"Huella={huella_anterior or ''}",
        f"FechaHoraHusoGenRegistro={fecha_hora_gen_registro or ''}",
    ]
    return _sha256_hex_upper("&".join(parts))


def compute_huella_anulacion(
    nif_emisor_factura_anulada: str,
    num_serie_factura_anulada: str,
    fecha_expedicion_factura_anulada: str,
    huella_anterior: str | None,
    fecha_hora_gen_registro: str,
) -> str:
    """Huella para RegistroAnulacion (anulación de factura). Devuelve hex mayúsculas."""
    parts = [
        f"IDEmisorFacturaAnulada={nif_emisor_factura_anulada or ''}",
        f"NumSerieFacturaAnulada={num_serie_factura_anulada or ''}",
        f"FechaExpedicionFacturaAnulada={fecha_expedicion_factura_anulada or ''}",
        f"Huella={huella_anterior or ''}",
        f"FechaHoraHusoGenRegistro={fecha_hora_gen_registro or ''}",
    ]
    return _sha256_hex_upper("&".join(parts))


def _sha256_hex_upper(input_str: str) -> str:
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest().upper()
