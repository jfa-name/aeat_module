# Copyright (c) 2025, Felipe Acosta and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class AEATCompanySettings(Document):
    def validate(self):
        # Unicidad por Company ya está marcada como unique en el campo
        if self.jurisdiction == "IVA (AEAT)" and self.enable_verifactu:
            if not self.nif_emisor:
                frappe.throw("NIF Emisor es obligatorio cuando VERI*FACTU está activo")
            # URLs por entorno
            if self.environment == "preprod" and not self.verifactu_base_url_preprod:
                frappe.throw("Base URL Preprod de VERI*FACTU es obligatoria")
            if self.environment == "prod" and not self.verifactu_base_url_prod:
                frappe.throw("Base URL Prod de VERI*FACTU es obligatoria")
        # Si se sobreescribe cripto/TSA, validar campos mínimos
        if self.override_crypto:
            if not self.tsa_url:
                frappe.throw("TSA URL (override) es obligatoria al activar override")