import frappe


CUSTOM_FIELDS = [
    {
        "dt": "Sales Invoice",
        "fieldname": "seal_hash",
        "label": "Seal Hash",
        "fieldtype": "Data",
        "insert_after": "grand_total",
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "seal_timestamp",
        "label": "Seal Timestamp",
        "fieldtype": "Datetime",
        "insert_after": "seal_hash",
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "seal_signature",
        "label": "Seal Signature",
        "fieldtype": "Text",
        "insert_after": "seal_timestamp",
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "seal_status",
        "label": "Seal Status",
        "fieldtype": "Select",
        "options": "\nsigned\nsign_error\nsign_failed\nerror",
        "insert_after": "seal_signature",
        "read_only": 1,
        "no_copy": 1,
        "in_list_view": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "seal_evidence",
        "label": "Seal Evidence",
        "fieldtype": "Link",
        "options": "Invoice Evidence",
        "insert_after": "seal_status",
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "verifactu_prev_hash",
        "label": "VERI*FACTU Prev Hash",
        "fieldtype": "Text",
        "insert_after": "seal_evidence",
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "verifactu_hash",
        "label": "VERI*FACTU Hash",
        "fieldtype": "Text",
        "insert_after": "verifactu_prev_hash",
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "verifactu_id",
        "label": "VERI*FACTU Id/CSV",
        "fieldtype": "Data",
        "insert_after": "verifactu_hash",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "verifactu_qr_url",
        "label": "VERI*FACTU QR URL",
        "fieldtype": "Text",
        "insert_after": "verifactu_id",
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
    },
    {
        "dt": "Sales Invoice",
        "fieldname": "verifactu_status",
        "label": "VERI*FACTU Status",
        "fieldtype": "Select",
        "options": "\naccepted\nsubmit_error\nsend_error\ncancelled-pending",
        "insert_after": "verifactu_qr_url",
        "read_only": 1,
        "no_copy": 1,
        "in_list_view": 1,
    },
]


def execute():
    """
    Install Custom Fields on Sales Invoice for AEAT SIF + VERI*FACTU (Frappe v16).
    Idempotent: skips fields that already exist as Custom Field records.
    Uses Frappe's Custom Field API instead of raw SQL ALTER TABLE.
    """
    for cf in CUSTOM_FIELDS:
        fieldname = cf["fieldname"]
        dt = cf["dt"]

        if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
            # Already installed (either by this patch or by a previous v14 patch + migrate)
            continue

        doc = frappe.get_doc({"doctype": "Custom Field", **cf})
        doc.flags.ignore_permissions = True
        doc.insert()
