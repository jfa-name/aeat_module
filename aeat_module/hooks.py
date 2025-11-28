app_name = "aeat_module"
app_title = "Aeat Module"
app_publisher = "Felipe Acosta"
app_description = "AEAT VERI*FACTU support: snapshot, hash, timestamp & export"
app_version = "0.3.0"
app_email = "soporte@jfa.name"
app_license = "MIT"

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

fixtures = [
    {
    "doctype": "Custom Field",
        "filters": [
            [
                "name",
                "in",
                [
                    "Company.aeat_nif_emitter",
                    "Company.aeat_environment",
                    "Company.aeat_series",
                    "Company.aeat_signer_certificate",
                    "Company.aeat_signer_key_source",
                    "Company.aeat_signer_key_path",
                    "Company.aeat_signer_key_file",
                    "Company.aeat_signer_key_password",
                    "Company.aeat_tsa_url",
                    "Company.aeat_tsa_username",
                    "Company.aeat_tsa_password",
                    "Company.aeat_tsa_policy_oid",
                    "Company.aeat_tsa_hash_algo",
                    "Company.aeat_verify_tls",
                    "Company.aeat_ca_bundle_path",
                    "Sales Invoice.aeat_seal_hash",
                    "Sales Invoice.aeat_seal_timestamp",
                    "Sales Invoice.aeat_seal_signature",
                    "Sales Invoice.aeat_seal_status",
                    "Sales Invoice.aeat_seal_evidence",
                ],
            ]
        ],
    }
]
