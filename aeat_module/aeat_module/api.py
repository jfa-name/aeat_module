import frappe
from frappe import _
from .utils.integrity import canonicalize_doc, hash_snapshot, sign_hash
from .utils.timestamp_client import TimestampClient

TSA = TimestampClient()

def _make_snapshot(doc):
    """Return canonicalized snapshot bytes and metadata dict"""
    snap = canonicalize_doc(doc.as_dict())
    h = hash_snapshot(snap)
    return snap, h

@frappe.whitelist()
def handle_sales_invoice_submit(doc, method=None):
    """
    Called by hook on Sales Invoice.on_submit
    - create snapshot
    - request timestamp (TSA) or sign locally
    - create Invoice Evidence and link to Sales Invoice
    """
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)

    # do not double-seal
    if doc.get("seal_status") == "signed":
        return

    # 1) snapshot + hash
    snap_bytes, h = _make_snapshot(doc)

    # 2) request timestamp (TSA) and sign (or both)
    tsa_token = TSA.request_timestamp(snap_bytes)  # may return None if not configured

    # 3) local signature placeholder (could be HSM or remote)
    signature = sign_hash(h)

    # 4) create evidence doc
    ev = frappe.get_doc({
        "doctype": "Invoice Evidence",
        "invoice": doc.name,
        "snapshot_hash": h,
        "snapshot_file": frappe.attach_print(doc.doctype, doc.name, file_name=f"{doc.name}_snapshot.json"),
        "tsa_token": tsa_token,
        "signature": signature,
        "created_by": frappe.session.user
    })
    ev.insert(ignore_permissions=True)
    # 5) set link fields on Sales Invoice
    doc.db_set("seal_hash", h)
    doc.db_set("seal_timestamp", tsa_token.get("timestamp") if tsa_token else frappe.utils.now_datetime())
    doc.db_set("seal_signature", signature)
    doc.db_set("seal_status", "signed")
    doc.db_set("seal_evidence", ev.name)

@frappe.whitelist()
def handle_sales_invoice_cancel(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)
    # record cancellation as new evidence
    ev = frappe.get_doc({
        "doctype": "Invoice Evidence",
        "invoice": doc.name,
        "event": "cancel",
        "notes": f"Invoice cancelled by {frappe.session.user}"
    })
    ev.insert(ignore_permissions=True)
    doc.db_set("seal_status", "voided")

@frappe.whitelist()
def handle_sales_invoice_update_after_submit(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)
    # Create evidence entry for any post-submit changes (append-only)
    ev = frappe.get_doc({
        "doctype": "Invoice Evidence",
        "invoice": doc.name,
        "event": "update_after_submit",
        "notes": f"Updated after submit by {frappe.session.user}"
    })
    ev.insert(ignore_permissions=True)

@frappe.whitelist(allow_guest=False)
def export_aeat_package(invoice_names):
    """
    invoice_names: comma separated or list
    Return a zip/JSON package ready for AEAT (minimal example)
    """
    import json, io, zipfile
    if isinstance(invoice_names, str):
        invoice_names = [n.strip() for n in invoice_names.split(",") if n.strip()]

    mem = io.BytesIO()
    z = zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED)
    for name in invoice_names:
        doc = frappe.get_doc("Sales Invoice", name)
        snap = canonicalize_doc(doc.as_dict())
        z.writestr(f"{name}.json", snap.decode() if isinstance(snap, bytes) else snap)
        # include evidence if exists
        if doc.get("seal_evidence"):
            ev = frappe.get_doc("Invoice Evidence", doc.seal_evidence)
            z.writestr(f"{name}.evidence.txt", frappe.as_json(ev.as_dict()))
    z.close()
    mem.seek(0)
    frappe.local.response.filename = f"aeat_package_{frappe.utils.nowdate()}.zip"
    frappe.local.response.filecontent = mem.read()
    frappe.local.response.type = "download"
