import frappe

def get_company_context(company: str) -> dict:
    """Carga contexto por Company, con fallback a global AEAT Settings para TSA/firma."""
    cs = frappe.get_all("AEAT Company Settings", filters={"company": company}, limit=1)
    if not cs:
        # Sin configuración explícita para esta Company: AEAT/VERI*FACTU debe
        # quedar desactivado (antes devolvía enable_sif=True por defecto, lo
        # que intentaba sellar/firmar facturas de CUALQUIER company sin
        # configurar, fallando por falta de certificado).
        return {"jurisdiction": "Otra/No aplica", "enable_sif": False, "enable_verifactu": False}
    cs_doc = frappe.get_doc("AEAT Company Settings", cs[0].name)

    # Build endpoints
    base_url = cs_doc.verifactu_base_url_preprod if cs_doc.environment == "preprod" else cs_doc.verifactu_base_url_prod

    # TSA/firma (sellado SIF) es siempre configuración global (AEAT Settings):
    # AEAT Company Settings no tiene campos tsa_*/signer_* propios (solo
    # transporte VERI*FACTU: mTLS/OAuth2). El acceso previo a
    # `cs_doc.override_crypto` (campo inexistente en el DocType) lanzaba
    # AttributeError en TODA factura de una company con AEAT Company Settings
    # creado, y quedaba silenciado por el try/except de handle_sales_invoice_submit
    # devolviendo enable_sif=False/enable_verifactu=False pase lo que pase.
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
        # NOTA: antes exigía jurisdiction == "IVA (AEAT)", lo que bloqueaba
        # VERI*FACTU para companies que operan en Canarias/Ceuta/Melilla
        # (IGIC/IPSI) — el RD 1007/2023 aplica también a esos territorios
        # (el propio registro AEAT tiene un campo "Impuesto" con valores
        # 01=IVA/02=IPSI/03=IGIC precisamente para cubrirlos). El chequeo
        # real de "no aplica" es jurisdiction == "Otra/No aplica".
        enable_verifactu=(cs_doc.jurisdiction != "Otra/No aplica" and bool(cs_doc.enable_verifactu)),
        environment=cs_doc.environment,
        nif_emisor=cs_doc.nif_emisor,
        verifactu_base_url=base_url,
        series_table=cs_doc.series or [],
        crypto=crypto,
    )
