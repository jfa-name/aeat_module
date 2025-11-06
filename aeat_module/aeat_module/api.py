import io, zipfile, json
import frappe
from frappe import _
from .utils.integrity import canonicalize_doc, hash_snapshot
from .utils.timestamp_client import TimestampClient
from .utils.signing import sign_bytes

def _make_snapshot_and_hash(doc):
    snap = canonicalize_doc(doc.as_dict())
    s = frappe.get_single("AEAT Settings")
    digest_b64 = hash_snapshot(snap, s.tsa_hash_algo or "sha256")
    return snap, digest_b64

@frappe.whitelist()
def handle_sales_invoice_submit(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)

    # Evitar doble sellado (idempotente)
    if doc.get("seal_status") == "signed" and doc.get("seal_hash"):
        return

    # 1) Snapshot y hash (base64 del digest)
    snap_bytes, digest_b64 = _make_snapshot_and_hash(doc)

    # 2) Timestamp TSA (RFC3161)
    tsa = TimestampClient()
    tsa_token = tsa.request_timestamp(snap_bytes)

    # 3) Firma con certificado (firma sobre los bytes de snapshot)
    signature_b64, alg = sign_bytes(snap_bytes, (frappe.get_single("AEAT Settings").tsa_hash_algo or "sha256"))

    # 4) Guardar evidencia
    ev = frappe.get_doc({
        "doctype": "Invoice Evidence",
        "invoice": doc.name,
        "snapshot_hash": digest_b64,
        "snapshot_file": frappe.attach_print(doc.doctype, doc.name, file_name=f"{doc.name}_snapshot.json", print_format=None, print_letterhead=False, html=json.dumps(json.loads(snap_bytes.decode()), ensure_ascii=False)),
        "tsa_token": frappe.as_json(tsa_token) if tsa_token else None,
        "signature": signature_b64,
        "event": "submit",
        "notes": f"Algoritmo firma: {alg}"
    })
    ev.insert(ignore_permissions=True)

    # 5) Actualizar la factura
    doc.db_set("seal_hash", digest_b64)
    doc.db_set("seal_timestamp", tsa_token.get("timestamp") if tsa_token else frappe.utils.now_datetime())
    doc.db_set("seal_signature", signature_b64)
    doc.db_set("seal_status", "signed")
    doc.db_set("seal_evidence", ev.name)

@frappe.whitelist()
def handle_sales_invoice_cancel(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)
    ev = frappe.get_doc({
        "doctype": "Invoice Evidence",
        "invoice": doc.name,
        "event": "cancel",
        "notes": f"Cancelado por {frappe.session.user}"
    })
    ev.insert(ignore_permissions=True)
    doc.db_set("seal_status", "voided")

@frappe.whitelist()
def handle_sales_invoice_update_after_submit(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)
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