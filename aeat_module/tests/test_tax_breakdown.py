# -*- coding: utf-8 -*-
"""Tests para utils/tax_breakdown.py usando `frappe._dict` como "filas"
falsas de child table (soporta tanto `row.campo` como `row.get(...)`, igual
que los documentos reales de Frappe).

`_resolve_meta` consulta `frappe.db.get_value` para `Account`/`Item Tax
Template`, así que estos tests necesitan un site Frappe real conectado a BD
(se ejecutan vía `bench run-tests`, no como unittest puro) — las cuentas
falsas usadas aquí ("IVA 10 TEST", etc.) no existen, por lo que la consulta
devuelve `None` y el código cae a la inferencia por tipo impositivo
(`DEFAULT_RATE_INFERENCE`), que es justo lo que se quiere validar.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from aeat_module.aeat_module.utils.tax_breakdown import AEATTaxBreakdownError, build_desglose


def _row(**kwargs):
    return frappe._dict(kwargs)


class TestBuildDesgloseMultiTipo(FrappeTestCase):
    def test_multi_rate_invoice_no_duplicated_base(self):
        """Caso real detectado en Fase 2b (FAC-BAY-2026-10140): 2 líneas, una
        al 10% y otra al 21%, cada una con su fila "de relleno" rate=0 en la
        fila de impuesto de el otro tipo. No debe duplicarse la base imponible
        agrupando por un falso grupo "0%"."""
        doc = frappe._dict(
            items=[_row(name="item-10", item_code="A"), _row(name="item-21", item_code="B")],
            taxes=[_row(name="tax-10", account_head="IVA 10 TEST"), _row(name="tax-21", account_head="IVA 21 TEST")],
            item_wise_tax_details=[
                # línea al 10%: fila real en tax-10, fila de relleno (0) en tax-21
                _row(item_row="item-10", tax_row="tax-10", rate=10.0, amount=97.13, taxable_amount=971.30),
                _row(item_row="item-10", tax_row="tax-21", rate=0.0, amount=0.0, taxable_amount=0.0),
                # línea al 21%: fila de relleno (0) en tax-10, fila real en tax-21
                _row(item_row="item-21", tax_row="tax-10", rate=0.0, amount=0.0, taxable_amount=0.0),
                _row(item_row="item-21", tax_row="tax-21", rate=21.0, amount=67.07, taxable_amount=319.40),
            ],
        )

        detalles = build_desglose(doc)

        self.assertEqual(len(detalles), 2)
        por_tipo = {d["TipoImpositivo"]: d for d in detalles}
        self.assertEqual(por_tipo["10.00"]["BaseImponibleOimporteNoSujeto"], "971.30")
        self.assertEqual(por_tipo["21.00"]["BaseImponibleOimporteNoSujeto"], "319.40")
        # Impuesto inferido correctamente (01 = IVA) vía DEFAULT_RATE_INFERENCE.
        self.assertTrue(all(d["Impuesto"] == "01" for d in detalles))

    def test_unclassified_zero_rate_raises(self):
        """El 0% nunca se infiere automáticamente: exige AEAT Tax Category
        explícita en Item Tax Template o Account. Sin ella, debe fallar
        (y no enviarse una factura con una exención no configurada)."""
        doc = frappe._dict(
            items=[_row(name="item-exenta", item_code="C")],
            taxes=[_row(name="tax-exenta", account_head="Exenta TEST")],
            item_wise_tax_details=[
                _row(item_row="item-exenta", tax_row="tax-exenta", rate=0.0, amount=0.0, taxable_amount=100.0),
            ],
        )
        with self.assertRaises(AEATTaxBreakdownError):
            build_desglose(doc)

    def test_single_rate_invoice(self):
        doc = frappe._dict(
            items=[_row(name="item-21", item_code="A")],
            taxes=[_row(name="tax-21", account_head="IVA 21 TEST")],
            item_wise_tax_details=[
                _row(item_row="item-21", tax_row="tax-21", rate=21.0, amount=21.0, taxable_amount=100.0),
            ],
        )
        detalles = build_desglose(doc)
        self.assertEqual(len(detalles), 1)
        self.assertEqual(detalles[0]["TipoImpositivo"], "21.00")
        self.assertEqual(detalles[0]["BaseImponibleOimporteNoSujeto"], "100.00")
        self.assertEqual(detalles[0]["CuotaRepercutida"], "21.00")
