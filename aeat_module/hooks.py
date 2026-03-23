app_name = "aeat_module"
app_title = "Aeat Module"
app_publisher = "Felipe Acosta"
app_description = "AEAT VERI*FACTU support: snapshot, hash, timestamp & export"
app_version = "0.3.0"
app_email = "soporte@jfa.name"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [["dt", "=", "Sales Invoice"], ["fieldname", "in", [
            "seal_hash", "seal_timestamp", "seal_signature", "seal_status", "seal_evidence",
            "verifactu_prev_hash", "verifactu_hash", "verifactu_id", "verifactu_qr_url", "verifactu_status"
        ]]]
    }
]

doctype_js = {
    "Sales Invoice": "public/js/sales_invoice_seal.js"
}

doc_events = {
    "Sales Invoice": {
        "on_submit": "aeat_module.aeat_module.api.handle_sales_invoice_submit",
        "on_cancel": "aeat_module.aeat_module.api.handle_sales_invoice_cancel",
        "on_update_after_submit": "aeat_module.aeat_module.api.handle_sales_invoice_update_after_submit",
    }
}

patches = [
    # v14 patches: kept for reference; already executed on pre-v16 installs.
    # "aeat_module.patches.v14.add_sales_invoice_seal_fields",
    # "aeat_module.patches.v14.add_verifactu_fields",

    # v16: install Custom Fields via Frappe API (idempotent)
    "aeat_module.patches.v16.install_sales_invoice_custom_fields",
]