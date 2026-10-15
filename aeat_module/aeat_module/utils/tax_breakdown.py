# -*- coding: utf-8 -*-
"""
Desglose de impuestos (Desglose/DetalleDesglose) para el RegistroAlta de
VERI*FACTU, soportando facturas multi-tipo (varios tipos de IVA/IGIC/exentos
en la misma factura) y ambas formas de configurar impuestos en Frappe/ERPNext:

  - "Item Tax Template" (plantilla de impuestos de artículo, por línea)
  - "Sales Taxes and Charges Template" (plantilla de impuestos de ventas,
    aplicada de forma uniforme a toda la factura)

Fuente de datos: `Sales Invoice.item_wise_tax_details` (child table nativa
de Frappe/ERPNext v16 con `item_row`, `tax_row`, `rate`, `amount`,
`taxable_amount` YA calculados correctamente por el motor de impuestos,
independientemente de si el tipo viene del Item Tax Template o de la
Sales Taxes and Charges Template) — evita duplicar esa lógica de cálculo.

Clasificación AEAT (Impuesto/ClaveRegimen/CalificacionOperacion/
OperacionExenta) por línea, con prioridad:
  1. `Item Tax Template.aeat_tax_category` (más específico, por artículo)
  2. `Account.aeat_tax_category` (cabecera de impuesto de la Sales Taxes
     and Charges Template)
  3. Inferencia por tipo impositivo para los casos inequívocos de este
     proyecto (ver `DEFAULT_RATE_INFERENCE`); el 0% NUNCA se infiere
     (puede ser IVA exento, IGIC exento, o distintos motivos de exención)
     y exige configurar una `AEAT Tax Category` explícita.
"""
from collections import OrderedDict

import frappe

# tipo impositivo (%) -> (impuesto, clave_regimen, calificacion_operacion, operacion_exenta)
# Inferencia únicamente para los tipos inequívocos declarados por el negocio:
# IVA general/reducido en Península y Baleares, IGIC general en Canarias.
DEFAULT_RATE_INFERENCE = {
    21.0: ("01", "01", "S1", None),
    10.0: ("01", "01", "S1", None),
    4.0: ("01", "01", "S1", None),
    7.0: ("03", "01", "S1", None),
}


class AEATTaxBreakdownError(Exception):
    pass


def _split_impuesto_code(value: str) -> str:
    """'01 - IVA' -> '01'."""
    return (value or "").split(" - ")[0].strip()


def _category_meta(category_name: str) -> dict:
    cat = frappe.get_cached_doc("AEAT Tax Category", category_name)
    return {
        "impuesto": _split_impuesto_code(cat.impuesto),
        "clave_regimen": cat.clave_regimen or "01",
        "calificacion_operacion": (cat.calificacion_operacion or "").split(" - ")[0].strip() or None,
        "operacion_exenta": (cat.operacion_exenta or "").split(" - ")[0].strip() or None,
    }


def _infer_meta_from_rate(rate: float, context: str) -> dict:
    key = round(float(rate or 0), 2)
    inferred = DEFAULT_RATE_INFERENCE.get(key)
    if not inferred:
        raise AEATTaxBreakdownError(
            f"No hay 'AEAT Tax Category' configurada para el tipo impositivo {key}% "
            f"({context}) y no se puede inferir automáticamente (obligatorio para "
            "tipos 0%/exentos, o tipos no contemplados en DEFAULT_RATE_INFERENCE). "
            "Configura el campo 'AEAT Tax Category' en el Item Tax Template o en "
            "la cuenta contable de la plantilla de impuestos."
        )
    impuesto, clave_regimen, calificacion, exenta = inferred
    return {
        "impuesto": impuesto,
        "clave_regimen": clave_regimen,
        "calificacion_operacion": calificacion,
        "operacion_exenta": exenta,
    }


def _resolve_meta(item_row, tax_row, rate: float) -> dict:
    category_name = None
    if item_row and item_row.get("item_tax_template"):
        category_name = frappe.db.get_value("Item Tax Template", item_row.item_tax_template, "aeat_tax_category")
    if not category_name and tax_row and tax_row.get("account_head"):
        category_name = frappe.db.get_value("Account", tax_row.account_head, "aeat_tax_category")

    if category_name:
        return _category_meta(category_name)

    context = f"item={item_row.get('item_code') if item_row else '?'}"
    return _infer_meta_from_rate(rate, context)


def _fmt_amount(value) -> str:
    return "{:.2f}".format(float(value or 0))


def build_desglose(doc) -> list:
    """Devuelve la lista de bloques DetalleDesglose (uno por combinación
    distinta de Impuesto/ClaveRegimen/Calificación/Exención/TipoImpositivo
    presente en la factura)."""
    details = doc.get("item_wise_tax_details") or []

    if not details:
        return _fallback_single_block(doc)

    items_by_name = {d.name: d for d in (doc.get("items") or [])}
    taxes_by_name = {d.name: d for d in (doc.get("taxes") or [])}

    # Frappe/ERPNext genera una fila item_wise_tax_details por CADA
    # combinación (línea de factura, fila de impuesto), incluso cuando esa
    # línea no está sujeta a esa fila de impuesto en concreto (rate=0,
    # amount=0 "de relleno" para el cálculo acumulativo). Si se agrupara
    # directamente por tipo, esas filas de relleno inflarían un falso grupo
    # "0%" duplicando la base imponible. Por eso se agrupa primero por
    # línea de factura y se descartan las filas de relleno cuando esa línea
    # sí tiene una fila "real" (importe o tipo distinto de 0) en otra fila
    # de impuesto.
    rows_by_item = OrderedDict()
    for row in details:
        rows_by_item.setdefault(row.item_row, []).append(row)

    groups = OrderedDict()
    for item_name, rows in rows_by_item.items():
        item_row = items_by_name.get(item_name)
        real_rows = [r for r in rows if float(r.amount or 0) != 0 or float(r.rate or 0) != 0]
        # Línea realmente exenta en todas las filas de impuesto: se queda
        # con una sola (evita duplicar la base si hay >1 fila de impuesto).
        chosen_rows = real_rows or rows[:1]

        for row in chosen_rows:
            tax_row = taxes_by_name.get(row.tax_row)
            rate = float(row.rate or 0)
            meta = _resolve_meta(item_row, tax_row, rate)
            key = (meta["impuesto"], meta["clave_regimen"], meta["calificacion_operacion"], meta["operacion_exenta"], round(rate, 2))
            g = groups.setdefault(key, {"meta": meta, "rate": rate, "base": 0.0, "cuota": 0.0})
            g["base"] += float(row.taxable_amount or 0)
            g["cuota"] += float(row.amount or 0)

    return [_to_detalle_desglose(g) for g in groups.values()]


def _fallback_single_block(doc) -> list:
    """Sin `item_wise_tax_details` disponible (p.ej. factura sin impuestos,
    o generada antes de que el campo existiera): un único bloque con el
    tipo de la primera línea de impuestos, o 0% si no hay impuestos."""
    taxes = doc.get("taxes") or []
    rate = float(taxes[0].rate) if taxes else 0.0
    meta = _resolve_meta(None, taxes[0] if taxes else None, rate)
    base = float(doc.get("net_total") or 0)
    cuota = float(doc.get("total_taxes_and_charges") or 0)
    return [_to_detalle_desglose({"meta": meta, "rate": rate, "base": base, "cuota": cuota})]


def _to_detalle_desglose(g: dict) -> dict:
    meta = g["meta"]
    detalle = {
        "Impuesto": meta["impuesto"],
        "ClaveRegimen": meta["clave_regimen"],
        "BaseImponibleOimporteNoSujeto": _fmt_amount(g["base"]),
    }
    if meta["operacion_exenta"]:
        detalle["OperacionExenta"] = meta["operacion_exenta"]
    else:
        detalle["CalificacionOperacion"] = meta["calificacion_operacion"] or "S1"
        detalle["TipoImpositivo"] = _fmt_amount(g["rate"])
        detalle["CuotaRepercutida"] = _fmt_amount(g["cuota"])
    return detalle
