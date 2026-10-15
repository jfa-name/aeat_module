import frappe
from .utils.verifactu_soap_client import VeriFactuSoapClient, VeriFactuSoapError
from .utils.verifactu_hash import format_fecha_expedicion, format_importe
from .utils.company_context import get_company_context


def submit_to_verifactu(doc, vf_hash: str, prev_hash: str | None):
    """
    Envía el RegistroAlta a AEAT por SOAP (Fase 2: VeriFactuSoapClient con
    mTLS + firma XMLDSig). Requiere certificado real configurado en
    AEAT Company Settings; si no lo hay, se registra el motivo en
    verifactu_status en vez de fallar de forma silenciosa/ambigua.
    """
    ctx = get_company_context(doc.company)
    if not ctx.get("enable_verifactu"):
        return

    try:
        client = VeriFactuSoapClient(doc.company, ctx)
    except VeriFactuSoapError as e:
        frappe.log_error(message=f"VERIFACTU SOAP client no disponible para {doc.name}: {e}", title="AEAT Debug")
        doc.db_set("verifactu_status", "no_certificate")
        return

    result = client.send_alta(
        doc,
        vf_hash=vf_hash,
        prev_hash=prev_hash,
        tipo_factura=doc.get("verifactu_invoice_type"),
        fecha_expedicion=format_fecha_expedicion(doc.posting_date),
        cuota_total=format_importe(doc.total_taxes_and_charges),
        importe_total=format_importe(doc.grand_total),
        fecha_hora_gen=doc.get("verifactu_generation_datetime"),
    )

    if result.get("ok"):
        doc.db_set("verifactu_status", "accepted")
    else:
        codes = result.get("codigos_error") or []
        doc.db_set("verifactu_status", "retry_pending" if result.get("retryable") else "submit_error")
        if codes:
            frappe.log_error(
                message=f"VERIFACTU rechazado para {doc.name}: {codes}",
                title="AEAT Debug",
            )


def cancel_in_verifactu(doc):
    """
    Envía el RegistroAnulacion a AEAT por SOAP. Requiere que
    `api.py::handle_sales_invoice_cancel` haya calculado y persistido ya
    `verifactu_cancel_hash`/`verifactu_cancel_prev_hash`/
    `verifactu_cancel_generation_datetime` sobre `doc` (mismo patrón que
    `submit_to_verifactu` con la huella de alta).
    """
    ctx = get_company_context(doc.company)
    if not ctx.get("enable_verifactu"):
        return

    try:
        client = VeriFactuSoapClient(doc.company, ctx)
    except VeriFactuSoapError as e:
        frappe.log_error(message=f"VERIFACTU SOAP client no disponible para anulación {doc.name}: {e}", title="AEAT Debug")
        doc.db_set("verifactu_status", "no_certificate")
        return

    result = client.send_anulacion(
        doc,
        vf_hash=doc.get("verifactu_cancel_hash"),
        prev_hash=doc.get("verifactu_cancel_prev_hash"),
        fecha_expedicion=format_fecha_expedicion(doc.posting_date),
        fecha_hora_gen=doc.get("verifactu_cancel_generation_datetime"),
    )

    if result.get("ok"):
        doc.db_set("verifactu_status", "cancelled")
    else:
        codes = result.get("codigos_error") or []
        doc.db_set("verifactu_status", "retry_pending" if result.get("retryable") else "submit_error")
        if codes:
            frappe.log_error(
                message=f"VERIFACTU anulación rechazada para {doc.name}: {codes}",
                title="AEAT Debug",
            )
