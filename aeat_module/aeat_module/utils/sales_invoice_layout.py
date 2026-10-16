import json
from pathlib import Path

import frappe


def get_sales_invoice_field_order():
    fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "custom_field.json"
    fields = {
        field["fieldname"]: field
        for field in json.loads(fixture_path.read_text())
        if field["dt"] == "Sales Invoice"
    }
    order = []
    previous = fields["aeat_tab"]["insert_after"]
    while fields:
        fieldname = next(
            fieldname for fieldname, field in fields.items() if field["insert_after"] == previous
        )
        order.append(fieldname)
        fields.pop(fieldname)
        previous = fieldname
    return order


def sync_sales_invoice_layout():
    setter = frappe.db.get_value(
        "Property Setter",
        {"doc_type": "Sales Invoice", "doctype_or_field": "DocType", "property": "field_order"},
        ["name", "value"],
        as_dict=True,
    )
    if not setter:
        return

    aeat_order = get_sales_invoice_field_order()
    current_order = json.loads(setter.value)
    new_order = [fieldname for fieldname in current_order if fieldname not in aeat_order] + aeat_order
    if new_order == current_order:
        return

    doc = frappe.get_doc("Property Setter", setter.name)
    doc.value = json.dumps(new_order)
    doc.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Sales Invoice")