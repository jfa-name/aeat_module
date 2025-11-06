import frappe
from frappe.model.document import Document

class AEATSettings(Document):
    def validate(self):
        # Validaciones básicas
        if not self.tsa_url:
            frappe.throw("TSA URL es obligatoria")
        if self.signer_key_source in ("Path", "Site Config") and not (self.signer_private_key_path or self.site_config_key_name):
            frappe.throw("Debes indicar la ruta de clave privada o la clave de site_config para la clave privada")
        if self.signer_key_source == "Path" and not self.signer_certificate_path:
            frappe.throw("Debes indicar la ruta del certificado público (PEM) cuando usas Path")

    @staticmethod
    def get_active():
        return frappe.get_single("AEAT Settings")
