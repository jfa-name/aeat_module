import io, zipfile, json
import frappe
from frappe import _
from .utils.integrity import canonicalize_doc, hash_snapshot
from .utils.timestamp_client import TimestampClient
from .utils.signing import sign_bytes
from .utils.company_context import get_company_context

def _make_snapshot_and_hash(doc, hash_algo: str):
    snap = canonicalize_doc(doc.as_dict())
    digest_b64 = hash_snapshot(snap, hash_algo)
    return snap, digest_b64

def _compute_verifactu_chain_hash(doc, prev_hash_b64: str | None) -> str:
    """
    Placeholder: calcula la 'huella' VERI*FACTU encadenada por serie.
    Debe implementarse según el esquema AEAT: campos + huellaAnterior -> SHA-256 b64.
    """
    base_string = json.dumps({
        "serie": doc.get("series") or doc.get("naming_series"),
        "numero": doc.get("name"),
        "fecha": str(doc.get("posting_date")),
        "hora": str(doc.get("posting_time") or ""),
        "emisor": doc.get("company"),
        "cliente": doc.get("customer"),
        "total": float(doc.get("grand_total") or 0),
        "prev": prev_hash_b64 or ""
    }, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hash_snapshot(base_string, "sha256")

def _is_aeat_enabled_for_company(company: str) -> bool:
    """
    Verifica si el módulo AEAT está habilitado para la Company dada.
    Retorna False si no existe configuración o si enabled=0.
    """
    if not company:
        return False
    
    try:
        settings = frappe.get_doc("AEAT Company Settings", {"company": company})
        return bool(settings.get("enabled"))
    except frappe.DoesNotExistError:
        # No hay configuración para esta Company
        return False
    except Exception as e:
        frappe.log_error(f"Error verificando AEAT enabled para {company}: {str(e)}")
        return False

@frappe.whitelist()
def handle_sales_invoice_submit(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)

    # Verificar si AEAT está habilitado para esta Company
    if not _is_aeat_enabled_for_company(doc.company):
        frappe.logger().debug(f"AEAT Module deshabilitado para Company: {doc.company}")
        return

    ctx = get_company_context(doc.company)
    
    # 1) SIF siempre si enable_sif
    if ctx["enable_sif"]:
        snap_bytes, digest_b64 = _make_snapshot_and_hash(doc, ctx["crypto"]["tsa_hash_algo"])
        tsa = TimestampClient()
        tsa_token = tsa.request_timestamp(snap_bytes)
        signature_b64, alg = sign_bytes(snap_bytes, ctx["crypto"]["tsa_hash_algo"])
        ev = frappe.get_doc({
            "doctype": "Invoice Evidence",
            "invoice": doc.name,
            "snapshot_hash": digest_b64,
            "snapshot_file": frappe.attach_print(doc.doctype, doc.name, file_name=f"{doc.name}_snapshot.json", print_format=None, print_letterhead=False, html=json.dumps(json.loads(snap_bytes.decode()), ensure_ascii=False)),
            "tsa_token": frappe.as_json(tsa_token) if tsa_token else None,
            "signature": signature_b64,
            "event": "submit",
            "notes": f"SIF OK; Firma {alg}"
        })
        ev.insert(ignore_permissions=True)
        # actualizar campos sello si no lo estaban
        if not doc.get("seal_status"):
            doc.db_set("seal_hash", digest_b64)
            doc.db_set("seal_timestamp", tsa_token.get("timestamp") if tsa_token else frappe.utils.now_datetime())
            doc.db_set("seal_signature", signature_b64)
            doc.db_set("seal_status", "signed")
            doc.db_set("seal_evidence", ev.name)

    # 2) Si jurisdicción IVA y VERI*FACTU activo -> encadenado + envío
    if ctx["enable_verifactu"]:
        series_code = doc.get("series") or doc.get("naming_series") or ""
        # obtener prev_hash de AEAT Company Settings.series
        prev_hash = None
        settings = frappe.get_doc("AEAT Company Settings", {"company": doc.company})
        for row in settings.series or []:
            if row.series_code == series_code:
                prev_hash = row.last_hash
                break
        vf_hash = _compute_verifactu_chain_hash(doc, prev_hash)
        # Guardar en factura
        doc.db_set("verifactu_prev_hash", prev_hash)
        doc.db_set("verifactu_hash", vf_hash)
        # TODO: llamar a cliente VERI*FACTU para enviar registro y recibir id/CSV/QR
        # vf_id, vf_qr, status = verifactu_client.send(doc, vf_hash, prev_hash, ctx)
        # doc.db_set("verifactu_id", vf_id); doc.db_set("verifactu_qr_url", vf_qr); doc.db_set("verifactu_status", status)
        # Actualizar state en settings
        for row in settings.series or []:
            if row.series_code == series_code:
                row.last_hash = vf_hash
                row.last_number = (row.last_number or 0) + 1
                row.last_sent_at = frappe.utils.now_datetime()
                break
        settings.save(ignore_permissions=True)

@frappe.whitelist()
def handle_sales_invoice_cancel(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)
    
    # Verificar si AEAT está habilitado para esta Company
    if not _is_aeat_enabled_for_company(doc.company):
        frappe.logger().debug(f"AEAT Module deshabilitado para Company: {doc.company}")
        return
    
    ctx = get_company_context(doc.company)
    ev = frappe.get_doc({
        "doctype": "Invoice Evidence",
        "invoice": doc.name,
        "event": "cancel",
        "notes": f"Cancelado por {frappe.session.user}"
    })
    ev.insert(ignore_permissions=True)
    doc.db_set("seal_status", "voided")
    # Si VERI*FACTU activo, aquí deberías invocar verifactu_client.cancel(...)
    if ctx["enable_verifactu"]:
        doc.db_set("verifactu_status", "pending_cancel")

@frappe.whitelist()
def handle_sales_invoice_update_after_submit(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)
    
    # Verificar si AEAT está habilitado para esta Company
    if not _is_aeat_enabled_for_company(doc.company):
        frappe.logger().debug(f"AEAT Module deshabilitado para Company: {doc.company}")
        return
    
    ev = frappe.get_doc({
        "doctype": "Invoice Evidence",
        "invoice": doc.name,
        "event": "update_after_submit",
        "notes": f"Actualizado tras submit por {frappe.session.user}"
    })
    ev.insert(ignore_permissions=True)

@frappe.whitelist(allow_guest=False)
def export_aeat_package(invoice_names):
    if isinstance(invoice_names, str):
        invoice_names = [n.strip() for n in invoice_names.split(",") if n.strip()]
    mem = io.BytesIO()
    z = zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED)
    for name in invoice_names:
        doc = frappe.get_doc("Sales Invoice", name)
        
        # Solo exportar si AEAT está habilitado para la Company
        if not _is_aeat_enabled_for_company(doc.company):
            continue
            
        snap = canonicalize_doc(doc.as_dict())
        z.writestr(f"{name}.json", snap.decode() if isinstance(snap, (bytes, bytearray)) else snap)
        if doc.get("seal_evidence"):
            ev = frappe.get_doc("Invoice Evidence", doc.seal_evidence)
            z.writestr(f"{name}.evidence.json", frappe.as_json(ev.as_dict(), indent=2))
    z.close()
    mem.seek(0)
    frappe.local.response.filename = f"aeat_package_{frappe.utils.nowdate()}.zip"
    frappe.local.response.filecontent = mem.read()
    frappe.local.response.type = "download"