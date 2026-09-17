# -*- coding: utf-8 -*-
"""
Patch: add_sales_invoice_seal_fields.py

This patch creates the Sales Invoice custom fields used for the AEAT seal/manifest:
 - aeat_seal_hash (Data)
 - aeat_seal_timestamp (Datetime)
 - aeat_seal_signature (Text)
 - aeat_seal_status (Select)
 - aeat_seal_evidence (Text)

It uses frappe's create_custom_fields helper to ensure fields are created as proper
Custom Field records (so they integrate with export_to_files and fixtures).
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    try:
        custom_fields = {
            "Sales Invoice": [
                {
                    "fieldname": "aeat_seal_hash",
                    "label": "AEAT Seal Hash",
                    "fieldtype": "Data",
                    "insert_after": "grand_total",
                    "description": "Hash/huella calculada para la factura (AEAT)"
                },
                {
                    "fieldname": "aeat_seal_timestamp",
                    "label": "AEAT Seal Timestamp",
                    "fieldtype": "Datetime",
                    "insert_after": "aeat_seal_hash",
                    "description": "Timestamp (fecha/hora) del sellado"
                },
                {
                    "fieldname": "aeat_seal_signature",
                    "label": "AEAT Seal Signature",
                    "fieldtype": "Text",
                    "insert_after": "aeat_seal_timestamp",
                    "description": "XML-DSIG Signature o contenido relacionado"
                },
                {
                    "fieldname": "aeat_seal_status",
                    "label": "AEAT Seal Status",
                    "fieldtype": "Select",
                    "options": "Pending\nSigned\nSent\nAccepted\nAcceptedWithErrors\nFailed",
                    "insert_after": "aeat_seal_signature",
                    "description": "Estado del proceso de sellado/expedición"
                },
                {
                    "fieldname": "aeat_seal_evidence",
                    "label": "AEAT Seal Evidence",
                    "fieldtype": "Text",
                    "insert_after": "aeat_seal_status",
                    "description": "Evidencias y metadatos (JSON) del sellado/envío"
                }
            ]
        }

        # Create the custom fields (idempotent)
        create_custom_fields(custom_fields)
        frappe.db.commit()
        frappe.enqueue(method=frappe.clear_cache)  # clear caches asynchronously
        frappe.logger().info("AEAT: Sales Invoice seal custom fields ensured")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AEAT Patch: add_sales_invoice_seal_fields")
        raise