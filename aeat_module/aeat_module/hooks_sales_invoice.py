# -*- coding: utf-8 -*-
"""
Hooks for Sales Invoice to enqueue AEAT Queue Items on submit.
"""
import frappe
from frappe import _

def on_submit(doc, method=None):
    """
    Called when Sales Invoice is submitted.
    Creates AEAT Queue Item if company has verifactu enabled.
    """
    try:
        # Check if company has AEAT enabled
        company_settings = frappe.get_doc("AEAT Company Settings", {"company": doc.company})
        
        if not company_settings.get("enable_verifactu"):
            return
        
        # Create Queue Item
        from aeat_module.aeat_module.doctype.aeat_queue.aeat_queue import create_queue_item_from_invoice
        
        queue_item_name = create_queue_item_from_invoice(
            invoice_doctype="Sales Invoice",
            invoice_name=doc.name,
            company=doc.company,
            queue_name="verifactu",
            priority=0
        )
        
        frappe.msgprint(
            _("Factura encolada para envío a AEAT: {0}").format(queue_item_name),
            alert=True,
            indicator="blue"
        )
        
        frappe.logger().info(f"AEAT: Enqueued {doc.name} as {queue_item_name}")
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"AEAT: Failed to enqueue {doc.name}")
        # No fallar la factura si falla el encolado
        frappe.msgprint(
            _("Error al encolar factura para AEAT: {0}").format(str(e)),
            alert=True,
            indicator="red"
        )