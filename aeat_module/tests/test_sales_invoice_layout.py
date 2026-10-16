import json
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.model.meta import Meta

from aeat_module.aeat_module.utils.sales_invoice_layout import (
    get_sales_invoice_field_order,
    sync_sales_invoice_layout,
)


APP_PATH = Path(__file__).resolve().parents[1]
LAYOUT_MODULE = "aeat_module.aeat_module.utils.sales_invoice_layout"


class TestSalesInvoiceLayout(unittest.TestCase):
    def test_export_filter_matches_all_fixtures_without_duplicates(self):
        hooks = runpy.run_path(str(APP_PATH / "hooks.py"))
        fixture_files = list((APP_PATH / "fixtures").glob("*.json"))
        self.assertEqual([path.name for path in fixture_files], ["custom_field.json"])
        fields = json.loads(fixture_files[0].read_text())
        names = [field["name"] for field in fields]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(hooks["fixtures"]), 1)
        self.assertEqual(set(hooks["fixtures"][0]["filters"][0][2]), set(names))

    def test_frappe_places_entire_aeat_tab_after_standard_fields(self):
        invoice_path = APP_PATH.parents[1] / "erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.json"
        invoice = json.loads(invoice_path.read_text())
        standard = {field["fieldname"]: frappe._dict(field) for field in invoice["fields"]}
        fields = [standard[fieldname] for fieldname in invoice["field_order"]]
        custom = json.loads((APP_PATH / "fixtures/custom_field.json").read_text())
        fields += [frappe._dict(field, is_custom_field=True) for field in custom if field["dt"] == "Sales Invoice"]
        meta = SimpleNamespace(fields=fields, _fields={field.fieldname: field for field in fields})
        meta._update_fields_based_on_order = lambda order: Meta._update_fields_based_on_order(meta, order)
        Meta.sort_fields(meta)
        self.assertEqual(
            [field.fieldname for field in meta.fields],
            invoice["field_order"] + get_sales_invoice_field_order(),
        )

    @patch(f"{LAYOUT_MODULE}.frappe")
    def test_no_property_setter_is_created_for_uncustomized_sites(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        sync_sales_invoice_layout()
        mock_frappe.get_doc.assert_not_called()

    @patch(f"{LAYOUT_MODULE}.frappe")
    def test_existing_order_preserves_other_fields_and_is_idempotent(self, mock_frappe):
        original = ["customer", "seal_hash", "custom_other_app", "grand_total", "verifactu_hash"]
        setter = SimpleNamespace(name="Sales Invoice-main-field_order", value=json.dumps(original))
        mock_frappe.db.get_value.return_value = setter
        doc = mock_frappe.get_doc.return_value
        sync_sales_invoice_layout()
        expected = ["customer", "custom_other_app", "grand_total"] + get_sales_invoice_field_order()
        self.assertEqual(json.loads(doc.value), expected)
        doc.save.assert_called_once_with(ignore_permissions=True)
        mock_frappe.clear_cache.assert_called_once_with(doctype="Sales Invoice")
        setter.value = doc.value
        mock_frappe.get_doc.reset_mock()
        sync_sales_invoice_layout()
        mock_frappe.get_doc.assert_not_called()