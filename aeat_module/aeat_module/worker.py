# -*- coding: utf-8 -*-
"""
Simple AEAT Queue worker.

Usage:
 - As bench worker: `bench worker` will run queued jobs (if enqueued via frappe.enqueue)
 - Or run this module using python in bench console (not recommended for production)
 - Recommended: start this as a separate long-running process (supervisord/systemd) that
   imports this module and calls `run_worker(...)`

Behavior:
 - Poll "AEAT Queue Item" for Pending items
 - Try to claim (lock) an item using aeat_queue.claim_queue_item
 - Call processors.process_queue_item(queue_item_name) which performs the actual
   sign/send logic (this function should be implemented to call your sign_and_send flow).
 - On success, mark_queue_item_done; on failure, mark_queue_item_failed.

Note: processors.process_queue_item is intentionally decoupled so you can implement
the heavy logic (payload building, signing, sending) in a separate module.
"""
import time
import logging
import socket
import os

import frappe

from aeat_module.aeat_module.doctype.aeat_queue.aeat_queue import (
    get_pending_queue_item,
    claim_queue_item,
    mark_queue_item_done,
    mark_queue_item_failed,
    release_queue_item,
)

LOG = logging.getLogger(__name__)

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def run_worker(poll_interval: int = 5, lock_ttl_seconds: int = 300):
    """
    Run forever, polling for new AEAT Queue Items.
    """
    LOG.info("AEAT worker starting with id %s", WORKER_ID)
    try:
        while True:
            try:
                pending = get_pending_queue_item()
                if not pending:
                    time.sleep(poll_interval)
                    continue
                queue_item_name = pending.get("name")
                # try to claim
                claimed = claim_queue_item(queue_item_name, worker_id=WORKER_ID, lock_ttl_seconds=lock_ttl_seconds)
                if not claimed:
                    # someone else took it
                    continue
                LOG.info("AEAT worker %s claimed %s", WORKER_ID, queue_item_name)
                # call processor
                try:
                    # dynamic import to avoid circular deps
                    from aeat_module.aeat_module import processors
                    result_meta = processors.process_queue_item(queue_item_name)
                    # processors should return a dict with at least {"ok": True/False, "meta": {...}}
                    if isinstance(result_meta, dict) and result_meta.get("ok"):
                        mark_queue_item_done(queue_item_name, result_meta.get("meta"))
                    else:
                        err = None
                        meta = None
                        if isinstance(result_meta, dict):
                            err = result_meta.get("error") or "Processor returned not ok"
                            meta = result_meta.get("meta")
                        else:
                            err = "Processor returned non-dict result"
                        mark_queue_item_failed(queue_item_name, str(err), transient=True)
                except Exception as e:
                    LOG.exception("AEAT worker processing failed for %s", queue_item_name)
                    mark_queue_item_failed(queue_item_name, str(e), transient=True)
                finally:
                    # make sure lock cleared if still present
                    try:
                        release_queue_item(queue_item_name, expected_worker_id=WORKER_ID)
                    except Exception:
                        LOG.exception("Error releasing lock for %s", queue_item_name)
            except Exception:
                LOG.exception("Unhandled exception in AEAT worker loop")
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        LOG.info("AEAT worker interrupted and exiting")


def drain_pending_queue(max_items: int = 20) -> dict:
    """Procesa hasta `max_items` AEAT Queue Item pendientes y retorna.
    A diferencia de `run_worker` (bucle infinito para un proceso demonio
    separado), esta función está pensada para invocarse periódicamente desde
    el scheduler de Frappe (`scheduler_events` en hooks.py), que ya corre
    dentro del propio bench sin necesitar un proceso adicional."""
    from aeat_module.aeat_module import processors

    processed = 0
    ok_count = 0
    for _ in range(max_items):
        pending = get_pending_queue_item()
        if not pending:
            break
        queue_item_name = pending.get("name")
        if not claim_queue_item(queue_item_name, worker_id=WORKER_ID):
            continue
        processed += 1
        try:
            result = processors.process_queue_item(queue_item_name)
            if isinstance(result, dict) and result.get("ok"):
                ok_count += 1
                mark_queue_item_done(queue_item_name, result.get("meta"))
            else:
                err = result.get("error") if isinstance(result, dict) else "Processor returned non-dict result"
                mark_queue_item_failed(queue_item_name, str(err), transient=True)
        except Exception as e:
            LOG.exception("AEAT drain_pending_queue: error processing %s", queue_item_name)
            mark_queue_item_failed(queue_item_name, str(e), transient=True)
        finally:
            try:
                release_queue_item(queue_item_name, expected_worker_id=WORKER_ID)
            except Exception:
                LOG.exception("Error releasing lock for %s", queue_item_name)

    LOG.info("AEAT drain_pending_queue: processed=%s ok=%s", processed, ok_count)
    return {"processed": processed, "ok": ok_count}
