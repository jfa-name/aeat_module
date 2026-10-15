# -*- coding: utf-8 -*-
"""Tests unitarios puros para utils/qr.py (build_qr_url, sin red ni site)."""
import unittest

from aeat_module.aeat_module.utils.qr import QR_BASE_URL, build_qr_url


class TestBuildQrUrl(unittest.TestCase):
    def test_preprod_base_url(self):
        url = build_qr_url("preprod", "35429235X", "12345678/G33", "01-01-2024", "123.45")
        self.assertTrue(url.startswith(QR_BASE_URL["preprod"]))

    def test_prod_base_url(self):
        url = build_qr_url("prod", "35429235X", "12345678/G33", "01-01-2024", "123.45")
        self.assertTrue(url.startswith(QR_BASE_URL["prod"]))

    def test_unknown_environment_defaults_to_preprod(self):
        url = build_qr_url("not-a-real-env", "X", "Y", "Z", "1.00")
        self.assertTrue(url.startswith(QR_BASE_URL["preprod"]))

    def test_all_params_present_and_url_encoded(self):
        url = build_qr_url("preprod", "35429235X", "12345678/G 33", "01-01-2024", "123.45")
        self.assertIn("nif=35429235X", url)
        # El espacio y la barra en NumSerieFactura deben quedar URL-encoded, no literales.
        self.assertIn("numserie=12345678%2FG%2033", url)
        self.assertIn("fecha=01-01-2024", url)
        self.assertIn("importe=123.45", url)
        self.assertNotIn(" ", url)

    def test_missing_values_become_empty_params(self):
        url = build_qr_url("preprod", None, None, None, None)
        self.assertIn("nif=&", url)
        self.assertIn("numserie=&", url)
        self.assertIn("fecha=&", url)
        self.assertTrue(url.endswith("importe="))


if __name__ == "__main__":
    unittest.main()
