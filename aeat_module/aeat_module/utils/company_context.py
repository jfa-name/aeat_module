import frappe

def get_company_context(company: str) -> dict:
    """Carga contexto por Company, con fallback a global AEAT Settings para TSA/firma."""
    cs = frappe.get_all("AEAT Company Settings", filters={"company": company}, limit=1)
    if not cs:
        return {"jurisdiction": "Otra/No aplica", "enable_sif": True, "enable_verifactu": False}
    cs_doc = frappe.get_doc("AEAT Company Settings", cs[0].name)

    # Build endpoints
    base_url = cs_doc.verifactu_base_url_preprod if cs_doc.environment == "preprod" else cs_doc.verifactu_base_url_prod

    # Crypto/TSA: override o global
    crypto = {}
    if cs_doc.override_crypto:
        crypto = dict(
            tsa_url=cs_doc.tsa_url,
            tsa_username=cs_doc.tsa_username,
            tsa_password=cs_doc.tsa_password,
            tsa_policy_oid=cs_doc.tsa_policy_oid,
            tsa_hash_algo=cs_doc.tsa_hash_algo or "sha256",
            verify_tls=cs_doc.verify_tls,
            ca_bundle_path=cs_doc.ca_bundle_path,
            signer_key_source=cs_doc.signer_key_source,
            signer_private_key_path=cs_doc.signer_private_key_path,
            signer_private_key_password=cs_doc.signer_private_key_password,
            signer_private_key_file=cs_doc.signer_private_key_file,
            site_config_key_name=cs_doc.site_config_key_name,
            signer_certificate_path=cs_doc.signer_certificate_path,
            signer_algorithm=cs_doc.signer_algorithm or "RSA-PKCS1v15",
        )
    else:
        # toma de AEAT Settings global
        s = frappe.get_single("AEAT Settings")
        crypto = dict(
            tsa_url=s.tsa_url,
            tsa_username=s.tsa_username,
            tsa_password=s.tsa_password,
            tsa_policy_oid=s.tsa_policy_oid,
            tsa_hash_algo=s.tsa_hash_algo or "sha256",
            verify_tls=s.verify_tls,
            ca_bundle_path=s.ca_bundle_path,
            signer_key_source=s.signer_key_source,
            signer_private_key_path=s.signer_private_key_path,
            signer_private_key_password=s.signer_private_key_password,
            signer_private_key_file=s.signer_private_key_file,
            site_config_key_name=s.site_config_key_name,
            signer_certificate_path=s.signer_certificate_path,
            signer_algorithm=s.signer_algorithm or "RSA-PKCS1v15",
        )

    return dict(
        company=company,
        jurisdiction=cs_doc.jurisdiction,
        enable_sif=bool(cs_doc.enable_sif),
        enable_verifactu=(cs_doc.jurisdiction == "IVA (AEAT)" and bool(cs_doc.enable_verifactu)),
        environment=cs_doc.environment,
        nif_emisor=cs_doc.nif_emisor,
        verifactu_base_url=base_url,
        series_table=cs_doc.series or [],
        crypto=crypto,
    )
