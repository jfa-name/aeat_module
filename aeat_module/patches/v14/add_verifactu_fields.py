import frappe

def execute():
    """Añade campos VERI*FACTU a Sales Invoice si no existen."""
    table = "tabSales Invoice"
    columns = {
        "verifactu_prev_hash": "TEXT",
        "verifactu_hash": "TEXT",
        "verifactu_id": "VARCHAR(140)",
        "verifactu_qr_url": "TEXT",
        "verifactu_status": "VARCHAR(20)"
    }
    for col, sqltype in columns.items():
        if not frappe.db.has_column(table, col):
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {sqltype}")
    frappe.db.commit()
