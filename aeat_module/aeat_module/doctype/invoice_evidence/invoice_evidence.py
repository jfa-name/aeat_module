import frappe
from frappe.model.document import Document

class InvoiceEvidence(Document):
    def validate(self):
        # Basic sanity checks
        if not self.invoice:
            frappe.throw("Invoice is required")
        # Ensure uniqueness for same event+invoice if needed
        existing = frappe.db.get_value("Invoice Evidence", {"invoice": self.invoice, "event": self.event})
        if existing and not self.name:
            # allow multiple by not enforcing; this is optional behaviour
            pass

    def on_trash(self):
        # retention policy: do not allow deletion in production unless system manager
        if frappe.session.user != "Administrator" and frappe.local.conf.get("protect_evidence", True):
            frappe.throw("Deleting evidence is not allowed")
