app_name = "aeat_module"
app_title = "Aeat Module"
app_publisher = "soporte@jfa.name"
app_description = "AEAT VERI*FACTU support: snapshot, hash, timestamp & export"
app_email = "soporte@jfa.name"
app_license = "MIT"

# Register doctype client JS to add buttons in Sales Invoice form
doctype_js = {
    "Sales Invoice": "public/js/sales_invoice_seal.js"
}

# Register doc events for Sales Invoice
doc_events = {
    "Sales Invoice": {
        "on_submit": "aeat_module.api.handle_sales_invoice_submit",
        "on_cancel": "aeat_module.api.handle_sales_invoice_cancel",
        "on_update_after_submit": "aeat_module.api.handle_sales_invoice_update_after_submit",
    }
}

# Patches (migration scripts)
patches = [
    "aeat_module.patches.v14.add_sales_invoice_seal_fields"
]

# Whitelisted methods (export API)
override_whitelisted_methods = {
    # optional: expose an export endpoint
    "aeat_module.api.export_aeat_package": "aeat_module.api.export_aeat_package"
}