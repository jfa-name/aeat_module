# -*- coding: utf-8 -*-
"""
Patch: add_verifactu_fields.py

Creates the VERI*FACTU related custom fields on Sales Invoice:
 - verifactu_prev_hash (Text)
 - verifactu_hash (Text)
 - verifactu_id (Data)
 - verifactu_qr_url (Text)
 - verifactu_status (Select)

Implemented via create_custom_fields so that fields are proper Custom Field docs
(compatible with export_to_files and fixtures).
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    try:
        custom_fields = {
            "Sales Invoice": [
                {
                    "fieldname": "verifactu_prev_hash",
                    "label": "VERI*FACTU Previous Hash",
                    "fieldtype": "Text",
                    "insert_after": "aeat_seal_evidence",
                    "description": "Previous hash used for encadenamiento"
                },
                {
                    "fieldname": "verifactu_hash",
                    "label": "VERI*FACTU Hash",
                    "fieldtype": "Text",
                    "insert_after": "verifactu_prev_hash",
                    "description": "Hash computed for this invoice (VERI*FACTU)"
                },
                {
                    "fieldname": "verifactu_id",
                    "label": "VERI*FACTU Id",
                    "fieldtype": "Data",
                    "insert_after": "verifactu_hash",
                    "description": "Identifier returned by AEAT (IdPeticionRegistro, etc.)"
                },
                {
                    "fieldname": "verifactu_qr_url",
                    "label": "VERI*FACTU QR URL",
                    "fieldtype": "Text",
                    "insert_after": "verifactu_id",
                    "description": "URL to the QR or verification page"
                },
                {
                    "fieldname": "verifactu_status",
                    "label": "VERI*FACTU Status",
                    "fieldtype": "Select",
                    "options": "NotSent\nPending\nAccepted\nAcceptedWithErrors\nFailed\nDuplicate",
                    "insert_after": "verifactu_qr_url",
                    "description": "Status returned by AEAT or internal workflow"
                }
            ]
        }

        create_custom_fields(custom_fields)
        frappe.db.commit()
        frappe.enqueue(method=frappe.clear_cache)
        frappe.logger().info("AEAT: VERI*FACTU custom fields ensured")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AEAT Patch: add_verifactu_fields")
        raise