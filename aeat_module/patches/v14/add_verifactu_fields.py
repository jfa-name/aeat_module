import frappe

def execute():
    """Añade campos VERI*FACTU a Sales Invoice si no existen."""
    doctype = "Sales Invoice"        # <-- DocType name (no 'tab' prefix)
    table = "tabSales Invoice"       # <-- physical table name for raw SQL

    columns = {
        "verifactu_prev_hash": "TEXT",
        "verifactu_hash": "TEXT",
        "verifactu_id": "VARCHAR(140)",
        "verifactu_qr_url": "TEXT",
        "verifactu_status": "VARCHAR(20)"
    }
    try:
        for col, sqltype in columns.items():
            if not frappe.db.has_column(doctype, col):
                frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {sqltype}")
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AEAT Patch: add_verifactu_fields")
        raise