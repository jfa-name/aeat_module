import json
import frappe
from .utils.verifactu_client import VeriFactuClient
from .utils.company_context import get_company_context

def map_invoice_to_verifactu_payload(doc, vf_hash: str, prev_hash: str | None) -> dict:
    """
    Mapea Sales Invoice -> JSON VERI*FACTU.
    Debes ajustar los nombres/campos EXACTOS según el esquema oficial.
    Refiérete a verifactu-aeat.github.io (Esquemas de 'Registros de facturación emitidas').
    """
    # Ejemplo mínimo orientativo; sustituye claves por las del esquema oficial.
    payload = {
        "emisor": {
            "nif": frappe.get_cached_value("AEAT Company Settings", {"company": doc.company}, "nif_emisor"),
        },
        "factura": {
            "serie": doc.get("series") or doc.get("naming_series"),
            "numero": doc.get("name"),
            "fechaExpedicion": str(doc.get("posting_date")),
            "horaExpedicion": str(doc.get("posting_time") or ""),
            "huellaAnterior": prev_hash or "",
            "huella": vf_hash,
            "total": float(doc.get("grand_total") or 0),
            "divisa": doc.get("currency"),
            "cliente": {
                "nombre": doc.get("customer_name") or doc.get("customer"),
                "nif": doc.get("tax_id") or ""
            },
            "impuestos": [
                # Rellena desde doc.taxes con tipos y bases según IVA/IGIC/IPSI
            ],
            "rectificativa": bool(doc.get("is_return")),
            # ...
        },
        # "software": {...} opcional según guía (developer settings)
    }
    return payload

def submit_to_verifactu(doc, vf_hash: str, prev_hash: str | None):
    """
    Enrutador de envío: respeta Company Settings y actualiza campos al aceptar.
    Llamar desde tu on_submit actual cuando ctx.enable_verifactu sea True.
    """
    ctx = get_company_context(doc.company)
    if not ctx.get("enable_verifactu"):
        return

    client = VeriFactuClient(doc.company)
    payload = map_invoice_to_verifactu_payload(doc, vf_hash, prev_hash)
    vf_id, qr_url, resp = client.send_invoice(doc, payload)
    if vf_id:
        doc.db_set("verifactu_id", vf_id)
        doc.db_set("verifactu_qr_url", qr_url or "")
        doc.db_set("verifactu_status", resp.get("estado") or "accepted")

def cancel_in_verifactu(doc, reason_code: str, description: str = ""):
    """
    Envío de anulación/rectificación. Ajusta campos de payload conforme al esquema AEAT.
    """
    ctx = get_company_context(doc.company)
    if not ctx.get("enable_verifactu"):
        return

    client = VeriFactuClient(doc.company)
    payload = {
        # 'id' o referencias necesarias del documento que se anula/rectifica
        "id": doc.get("verifactu_id") or doc.name,
        "motivo": reason_code,
        "descripcion": description or f"Cancelación ERP {doc.name}"
    }
    resp = client.cancel_invoice(doc, payload)
    doc.db_set("verifactu_status", resp.get("estado") or "cancelled-pending")
