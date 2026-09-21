# -*- coding: utf-8 -*-
"""
Server-side helpers for AEAT Queue / AEAT Queue Item DocTypes.

Provides:
- create_queue_item_from_invoice(invoice_doctype, invoice_name, company)
- claim_queue_item(queue_item_name, worker_id, lock_ttl_seconds)
- release_queue_item(queue_item_name, worker_id)
- mark_queue_item_done(queue_item_name, result_meta)
- mark_queue_item_failed(queue_item_name, error_message, transient=True)
- get_pending_queue_item(queue_name=None)
- simple helper to increment attempts and set status

These functions are intended to be used by a worker process (aeat_module.worker)
or by on_submit hooks that enqueue invoices for processing.
"""
from __future__ import annotations

import json
import socket
import os
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, now


class AEATQueue(Document):
    """Definición de una cola lógica de procesamiento AEAT (p.ej. 'verifactu')."""
    pass


def create_queue_item_from_invoice(invoice_doctype: str, invoice_name: str, company: str, queue_name: str = "verifactu", priority: int = 0) -> str:
    """
    Create an AEAT Queue Item referencing an invoice.
    Returns the name (primary key) of the created AEAT Queue Item.
    Idempotent behavior: if there is already a Pending/Processing item for this invoice, returns existing.
    """
    existing = frappe.get_all("AEAT Queue Item",
                              filters=[
                                  ["invoice_type", "=", invoice_doctype],
                                  ["invoice", "=", invoice_name],
                                  ["company", "=", company],
                                  ["status", "in", ["Pending", "Processing"]]
                              ],
                              fields=["name", "status"],
                              limit=1)
    if existing:
        return existing[0].get("name")

    doc = frappe.get_doc({
        "doctype": "AEAT Queue Item",
        "invoice_type": invoice_doctype,
        "invoice": invoice_name,
        "company": company,
        "status": "Pending",
        "priority": priority,
        "attempts": 0,
        "created_by": frappe.session.user if frappe.session else "Administrator",
        "created_at": now()
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger().info(f"AEAT: created queue item {doc.name} for {invoice_doctype}/{invoice_name}")
    return doc.name


def get_pending_queue_item(queue_name: str = None):
    """
    Return one pending item (dict) ordered by priority desc, created_at asc.
    Does NOT lock the item. Use claim_queue_item to claim/lock it.
    """
    filters = [["status", "=", "Pending"]]
    if queue_name:
        filters.append(["queue_name", "=", queue_name])
    res = frappe.get_all("AEAT Queue Item",
                         filters=filters,
                         fields=["name", "invoice_type", "invoice", "company", "priority", "attempts", "created_at"],
                         order_by="priority desc, creation asc",
                         limit=1)
    return res[0] if res else None


def claim_queue_item(queue_item_name: str, worker_id: str = None, lock_ttl_seconds: int = 300) -> bool:
    """
    Try to claim a queue item for processing. Returns True if claim succeeded.
    Claiming sets locked_by and lock_timestamp and status to 'Processing'.
    If item already locked and lock_timestamp is recent (< lock_ttl_seconds), claim fails.
    If lock_timestamp is older than ttl, steal the lock.
    """
    worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    now_dt = now_datetime()
    item = frappe.get_doc("AEAT Queue Item", queue_item_name)

    # If already locked by this worker, return True
    if item.locked_by == worker_id:
        return True

    # If no lock, claim it
    if not item.locked_by:
        item.locked_by = worker_id
        item.lock_timestamp = now_dt
        item.status = "Processing"
        item.attempts = (item.attempts or 0) + 1
        item.save(ignore_permissions=True)
        frappe.db.commit()
        return True

    # If locked, check TTL
    try:
        lock_ts = item.lock_timestamp
        if not lock_ts:
            # corrupt state: take it
            item.locked_by = worker_id
            item.lock_timestamp = now_dt
            item.status = "Processing"
            item.attempts = (item.attempts or 0) + 1
            item.save(ignore_permissions=True)
            frappe.db.commit()
            return True
        # compare
        if isinstance(lock_ts, str):
            lock_dt = frappe.utils.parse_datetime(lock_ts)
        else:
            lock_dt = lock_ts
        if now_dt - lock_dt > timedelta(seconds=lock_ttl_seconds):
            # steal lock
            item.locked_by = worker_id
            item.lock_timestamp = now_dt
            item.status = "Processing"
            item.attempts = (item.attempts or 0) + 1
            item.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger().warning(f"AEAT: worker {worker_id} stole lock on {queue_item_name}")
            return True
    except Exception:
        # On any parsing issue, attempt to claim
        item.locked_by = worker_id
        item.lock_timestamp = now_dt
        item.status = "Processing"
        item.attempts = (item.attempts or 0) + 1
        item.save(ignore_permissions=True)
        frappe.db.commit()
        return True

    # otherwise cannot claim
    return False


def release_queue_item(queue_item_name: str, expected_worker_id: str = None) -> None:
    """
    Release a previously claimed queue item. Only releases if locked_by matches expected_worker_id (if provided)
    """
    item = frappe.get_doc("AEAT Queue Item", queue_item_name)
    if expected_worker_id and item.locked_by != expected_worker_id:
        # do not release another worker's lock
        frappe.logger().warning(f"AEAT: release_queue_item called by {expected_worker_id} but locked_by={item.locked_by}")
        return
    item.locked_by = None
    item.lock_timestamp = None
    if item.status == "Processing":
        item.status = "Pending"
    item.save(ignore_permissions=True)
    frappe.db.commit()


def mark_queue_item_done(queue_item_name: str, result_meta: dict | None = None) -> None:
    """
    Mark queue item as Sent/Accepted depending on meta. Writes metadata and clears lock.
    """
    item = frappe.get_doc("AEAT Queue Item", queue_item_name)
    item.locked_by = None
    item.lock_timestamp = None
    
    # Actualizar metadata
    if result_meta:
        if result_meta.get("status"):
            item.status = result_meta["status"]
        if result_meta.get("sent_path"):
            item.last_sent_path = result_meta["sent_path"]
        if result_meta.get("received_path"):
            item.last_received_path = result_meta["received_path"]
        if result_meta.get("metadata"):
            item.metadata = result_meta["metadata"]
        if result_meta.get("response_code"):
            item.last_response_code = str(result_meta["response_code"])
        if result_meta.get("response_text"):
            # Guardar primeros 1000 caracteres
            item.last_error = result_meta["response_text"][:1000]
    
    item.last_error = None if item.status in ["Accepted", "Sent"] else item.last_error
    item.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger().info(f"AEAT: queue item {queue_item_name} marked done ({item.status})")


def mark_queue_item_failed(queue_item_name: str, error_message: str, transient: bool = True) -> None:
    """
    Mark as Failed and optionally set status to Pending for retry according to attempts.
    If transient is True and attempts < allowed, set back to Pending, else Failed.
    """
    item = frappe.get_doc("AEAT Queue Item", queue_item_name)
    item.locked_by = None
    item.lock_timestamp = None
    item.last_error = error_message
    # attempts already incremented when claimed
    max_retries = 3
    if hasattr(item, "attempts"):
        attempts = int(item.attempts or 0)
    else:
        attempts = 1
    if transient and attempts < max_retries:
        item.status = "Pending"
    else:
        item.status = "Failed"
    item.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger().warning(f"AEAT: queue item {queue_item_name} marked {item.status} after error: {error_message}")


def get_queue_item(queue_item_name: str):
    """Return AEAT Queue Item doc (fresh)"""
    return frappe.get_doc("AEAT Queue Item", queue_item_name)
