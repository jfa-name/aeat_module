import frappe

def execute():
    """
    Add fields to Sales Invoice table:
    - seal_hash (Data)
    - seal_timestamp (Datetime)
    - seal_signature (Text)
    - seal_status (Data)
    - seal_evidence (Link to Invoice Evidence)
    """
    doctype = "Sales Invoice"         # <-- use DocType name (no 'tab' prefix)
    table = "tabSales Invoice"        # <-- physical table name for raw SQL

    try:
        # Use doctype when calling frappe.db.has_column
        if not frappe.db.has_column(doctype, "seal_hash"):
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `seal_hash` TEXT")
        if not frappe.db.has_column(doctype, "seal_timestamp"):
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `seal_timestamp` DATETIME")
        if not frappe.db.has_column(doctype, "seal_signature"):
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `seal_signature` TEXT")
        if not frappe.db.has_column(doctype, "seal_status"):
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `seal_status` VARCHAR(20)")
        if not frappe.db.has_column(doctype, "seal_evidence"):
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `seal_evidence` VARCHAR(140)")
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AEAT Patch: add_sales_invoice_seal_fields")
        raise