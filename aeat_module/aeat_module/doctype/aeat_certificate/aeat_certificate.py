import frappe
from frappe.model.document import Document


class AEATCertificate(Document):
    def validate(self):
        if not self.cert_path and not self.key_path:
            frappe.throw("Cert Path o Key Path son obligatorios")
