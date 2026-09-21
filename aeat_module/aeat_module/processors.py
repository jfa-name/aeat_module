# -*- coding: utf-8 -*-
"""
Processor glue that implements process_queue_item(queue_item_name).

This module is intentionally small and pluggable. It attempts to locate your
existing sign_and_send flow (script or module). If you already have a function
like `sign_and_send.process_queue_item(queue_item_name)` it will call it directly.
Otherwise, it returns an instructive error.

Implement your actual signing/sending logic inside a function that this module calls
(or adapt this module to start the sign_and_send script as a subprocess).
"""
import importlib
import traceback
import logging
import frappe
from frappe import _

LOG = logging.getLogger(__name__)


def process_queue_item(queue_item_name: str) -> dict:
    """
    Process an AEAT Queue Item.

    Returns a dict:
      { "ok": True, "meta": {...} } on success
      { "ok": False, "error": "message", "meta": {...} } on failure
    """
    # load queue item
    try:
        q = frappe.get_doc("AEAT Queue Item", queue_item_name)
    except Exception as e:
        LOG.exception("Could not load queue item %s", queue_item_name)
        return {"ok": False, "error": str(e)}

    # Try to import and call sign_and_send.process_queue_item
    # NOTE: "scripts/" lives at the app root (sibling of the "aeat_module" python
    # package), so it is NOT installed/importable as "aeat_module.scripts" in a
    # real bench. Pending Fase 2 (real SOAP client): move the sign_and_send logic
    # into "aeat_module/aeat_module/utils/" so it ships with the installed app.
    try:
        from aeat_module.scripts import sign_and_send
        
        if not hasattr(sign_and_send, 'process_queue_item'):
            msg = "sign_and_send.process_queue_item function not found"
            LOG.error(msg)
            return {"ok": False, "error": msg}
        
        LOG.info("Processor: calling sign_and_send.process_queue_item for %s", queue_item_name)
        
        result = sign_and_send.process_queue_item(queue_item_name)
        
        # Actualizar Queue Item con metadata
        if isinstance(result, dict) and result.get("meta"):
            meta = result["meta"]
            
            # Actualizar campos del Queue Item
            if meta.get("status"):
                q.status = meta["status"]
            if meta.get("sent_path"):
                q.last_sent_path = meta["sent_path"]
            if meta.get("received_path"):
                q.last_received_path = meta["received_path"]
            if meta.get("metadata"):
                q.metadata = meta["metadata"]
            if meta.get("response_code"):
                q.last_response_code = str(meta["response_code"])
            
            q.save(ignore_permissions=True)
            frappe.db.commit()
        
        return result
        
    except ImportError as e:
        msg = f"Could not import sign_and_send module: {e}"
        LOG.error(msg)
        return {"ok": False, "error": msg}
    except Exception as e:
        LOG.exception("Processor function raised")
        return {"ok": False, "error": f"{e}\n{traceback.format_exc()}"}
