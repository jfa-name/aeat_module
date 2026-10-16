# -*- coding: utf-8 -*-
"""
Comprobación de seguridad para usar antes de un despliegue a producción:
VERI*FACTU no debe quedar activo para ninguna company que no tenga
certificado mTLS configurado.

No modifica nada; solo informa por stdout y, si detecta una situación
insegura, lanza una excepción para que un script de despliegue (con
`set -e`) se detenga y el humano revise antes de continuar.

Para restringir además compañías concretas que deban permanecer
desactivadas aunque tuvieran certificado (p.ej. mientras se confirma algo
operativamente), añade sus nombres a `site_config.json`:

    "aeat_deploy_check_blocked_companies": ["Mi Empresa S.L."]
"""
import frappe


def _has_cert_configured(cs_doc) -> bool:
    return bool(
        cs_doc.get("mtls_client_pfx_file")
        or cs_doc.get("mtls_client_pfx_path")
        or (cs_doc.get("mtls_client_cert_path") and cs_doc.get("mtls_client_key_path"))
    )


def check_no_live_verifactu_without_cert():
    blocked_companies = frappe.conf.get("aeat_deploy_check_blocked_companies") or []
    rows = frappe.get_all(
        "AEAT Company Settings",
        fields=["name", "company", "enable_verifactu", "environment"],
    )
    if not rows:
        print("No hay ninguna 'AEAT Company Settings' configurada todavía. OK (nada activo).")
        return

    problems = []
    for row in rows:
        cs_doc = frappe.get_doc("AEAT Company Settings", row.name)
        has_cert = _has_cert_configured(cs_doc)
        status = "ACTIVO" if row.enable_verifactu else "desactivado"
        print(f"- {row.company}: enable_verifactu={status}, entorno={row.environment}, certificado configurado={has_cert}")

        if row.enable_verifactu and row.company in blocked_companies:
            problems.append(
                f"{row.company} tiene enable_verifactu=1 pero está en "
                "'aeat_deploy_check_blocked_companies' (site_config.json). "
                "Quita la entrada ahí si ya se confirmó que puede activarse."
            )
        elif row.enable_verifactu and not has_cert:
            problems.append(
                f"{row.company} tiene enable_verifactu=1 pero NO tiene ningún certificado "
                "mTLS configurado (fallará en cada factura con verifactu_status=no_certificate)."
            )

    if problems:
        raise RuntimeError("Despliegue detenido por seguridad:\n- " + "\n- ".join(problems))


    print("\nOK: ninguna company insegura (activa sin certificado) detectada.")
