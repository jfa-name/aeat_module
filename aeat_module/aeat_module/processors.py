# -*- coding: utf-8 -*-
"""
Dispatcher que implementa `process_queue_item(queue_item_name)` para el
worker de AEAT Queue. Delega en `api_verifactu.py` (single source of truth
de la lógica de envío SOAP) para no duplicarla; este módulo solo traduce
entre el AEAT Queue Item y el resultado que espera `worker.py`.
"""
import logging
import traceback

import frappe

from aeat_module.aeat_module import api_verifactu
from aeat_module.aeat_module.utils.company_context import get_company_context

LOG = logging.getLogger(__name__)

_OK_STATUSES = {"accepted", "cancelled"}
_RETRYABLE_STATUSES = {"retry_pending"}


def process_queue_item(queue_item_name: str) -> dict:
    """
    Procesa un AEAT Queue Item (Alta o Anulacion).

    Returns a dict:
      { "ok": True, "meta": {...} } on success
      { "ok": False, "error": "message", "meta": {...} } on failure
    """
    try:
        q = frappe.get_doc("AEAT Queue Item", queue_item_name)
    except Exception as e:
        LOG.exception("Could not load queue item %s", queue_item_name)
        return {"ok": False, "error": str(e)}

    try:
        doc = frappe.get_doc(q.invoice_type, q.invoice)
        ctx = get_company_context(doc.company)
        if not ctx.get("enable_verifactu"):
            return {"ok": False, "error": "enable_verifactu desactivado para esta Company"}

        if q.operation == "Anulacion":
            api_verifactu.cancel_in_verifactu(doc)
        else:
            api_verifactu.submit_to_verifactu(doc, doc.get("verifactu_hash"), doc.get("verifactu_prev_hash"))

        final_status = frappe.db.get_value(q.invoice_type, q.invoice, "verifactu_status")
        ok = final_status in _OK_STATUSES
        retryable = final_status in _RETRYABLE_STATUSES

        return {
            "ok": ok,
            "error": None if ok else f"verifactu_status={final_status}",
            "meta": {"status": "Accepted" if ok else ("Pending" if retryable else "Failed")},
        }
    except Exception as e:
        LOG.exception("Processor function raised for %s", queue_item_name)
        return {"ok": False, "error": f"{e}\n{traceback.format_exc()}"}


