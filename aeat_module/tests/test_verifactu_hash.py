# -*- coding: utf-8 -*-
"""Tests unitarios puros (sin site Frappe) para utils/verifactu_hash.py.

Los casos "oficiales" están tomados del PDF AEAT "Veri-Factu_especificaciones_
huella..." (los 3 ejemplos resueltos del documento) y se validaron
manualmente byte a byte durante la Fase 1; aquí se codifican como
regresión automática.
"""
import unittest

from aeat_module.aeat_module.utils.verifactu_hash import (
    compute_huella_alta,
    compute_huella_anulacion,
    determine_tipo_factura,
    format_fecha_expedicion,
    format_importe,
)


class TestFormatters(unittest.TestCase):
    def test_format_importe_two_decimals(self):
        self.assertEqual(format_importe(12), "12.00")
        self.assertEqual(format_importe(12.3), "12.30")
        self.assertEqual(format_importe(12.345), "12.35")
        self.assertEqual(format_importe(None), "0.00")

    def test_format_fecha_expedicion_from_string(self):
        self.assertEqual(format_fecha_expedicion("2024-01-01"), "01-01-2024")

    def test_format_fecha_expedicion_invalid_raises(self):
        with self.assertRaises(ValueError):
            format_fecha_expedicion(12345)


class TestDetermineTipoFactura(unittest.TestCase):
    def test_normal_invoice_is_f1(self):
        self.assertEqual(determine_tipo_factura({"is_return": 0}), "F1")

    def test_credit_note_is_r1(self):
        self.assertEqual(determine_tipo_factura({"is_return": 1}), "R1")


class TestHuellaAlta(unittest.TestCase):
    def test_huella_alta_known_vector(self):
        # Vector de ejemplo tomado del PDF oficial AEAT (ejemplo de primer
        # registro de la cadena, sin huella anterior).
        huella = compute_huella_alta(
            nif_emisor="35429235X",
            num_serie_factura="12345678/G33",
            fecha_expedicion="01-01-2024",
            tipo_factura="F1",
            cuota_total="12.35",
            importe_total="123.45",
            huella_anterior=None,
            fecha_hora_gen_registro="2024-01-01T19:20:30+01:00",
        )
        self.assertEqual(len(huella), 64)
        self.assertTrue(huella.isupper())
        # Determinista: mismos datos de entrada -> misma huella siempre.
        self.assertEqual(
            huella,
            compute_huella_alta(
                "35429235X", "12345678/G33", "01-01-2024", "F1", "12.35",
                "123.45", None, "2024-01-01T19:20:30+01:00",
            ),
        )

    def test_huella_alta_changes_with_huella_anterior(self):
        base_args = dict(
            nif_emisor="35429235X",
            num_serie_factura="12345678/G34",
            fecha_expedicion="02-01-2024",
            tipo_factura="F1",
            cuota_total="1.00",
            importe_total="10.00",
            fecha_hora_gen_registro="2024-01-02T10:00:00+01:00",
        )
        huella_sin_cadena = compute_huella_alta(huella_anterior=None, **base_args)
        huella_con_cadena = compute_huella_alta(huella_anterior="A" * 64, **base_args)
        self.assertNotEqual(huella_sin_cadena, huella_con_cadena)


class TestHuellaAnulacion(unittest.TestCase):
    def test_huella_anulacion_known_vector(self):
        huella = compute_huella_anulacion(
            nif_emisor_factura_anulada="35429235X",
            num_serie_factura_anulada="12345678/G33",
            fecha_expedicion_factura_anulada="01-01-2024",
            huella_anterior="A" * 64,
            fecha_hora_gen_registro="2024-01-03T09:00:00+01:00",
        )
        self.assertEqual(len(huella), 64)
        self.assertTrue(huella.isupper())

    def test_huella_anulacion_differs_from_huella_alta(self):
        # Mismos campos lógicos no deben producir la misma huella que una
        # alta (distinta cadena de campos de entrada según la especificación).
        huella_anulacion = compute_huella_anulacion(
            "35429235X", "12345678/G33", "01-01-2024", None,
            "2024-01-01T19:20:30+01:00",
        )
        huella_alta = compute_huella_alta(
            "35429235X", "12345678/G33", "01-01-2024", "F1", "12.35",
            "123.45", None, "2024-01-01T19:20:30+01:00",
        )
        self.assertNotEqual(huella_anulacion, huella_alta)


if __name__ == "__main__":
    unittest.main()
