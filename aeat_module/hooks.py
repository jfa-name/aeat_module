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
        "filters": [["name", "in", ["Sales Invoice-" + fieldname for fieldname in [
            "aeat_tab", "aeat_seal_section", "aeat_verifactu_section", "aeat_cancel_section",
            "seal_hash", "seal_timestamp", "seal_signature", "seal_status", "seal_evidence",
            "verifactu_prev_hash", "verifactu_hash", "verifactu_id", "verifactu_qr_url", "verifactu_status",
            "verifactu_invoice_type", "verifactu_generation_datetime", "verifactu_qr_image",
            "verifactu_cancel_hash", "verifactu_cancel_prev_hash", "verifactu_cancel_generation_datetime"
        ]] + ["Account-aeat_tax_category", "Item Tax Template-aeat_tax_category"]]]
    }
]

after_migrate = "aeat_module.aeat_module.utils.sales_invoice_layout.sync_sales_invoice_layout"

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

# Fase 3: drena periódicamente AEAT Queue Item pendientes (altas/anulaciones)
# sin necesitar un proceso worker.py separado (bench worker/schedule están
# deshabilitados en este entorno de bajo RAM, ver FRAPPE_LOW_RAM_OPTIMIZATION).
scheduler_events = {
    "cron": {
        "*/5 * * * *": ["aeat_module.aeat_module.worker.drain_pending_queue"],
    }
}

patches = [
    # v14 patches: kept for reference; already executed on pre-v16 installs.
    # "aeat_module.patches.v14.add_sales_invoice_seal_fields",
    # "aeat_module.patches.v14.add_verifactu_fields",

    # NOTA: este listado bajo hooks.py "patches" NO es leído por Frappe (el
    # patch runner usa <app>/patches.txt, que está vacío) — es código muerto
    # heredado de la Fase 0. Los Custom Fields de Sales Invoice se instalan
    # realmente vía fixtures/custom_field.json (sync_fixtures).
    # v16: install Custom Fields via Frappe API (idempotent)
    "aeat_module.patches.v16.install_sales_invoice_custom_fields",
]
