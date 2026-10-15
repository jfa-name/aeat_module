# Copyright (c) 2025, Felipe Acosta and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from aeat_module.aeat_module.utils.file_security import secure_attached_file

class AEATCompanySettings(Document):
	def on_update(self):
		secure_attached_file(self.mtls_client_pfx_file)
