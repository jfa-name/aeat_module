import frappe
from frappe.model.document import Document


class AEATTaxCategory(Document):
	def validate(self):
		has_calificacion = bool(self.calificacion_operacion)
		has_exenta = bool(self.operacion_exenta)
		if has_calificacion and has_exenta:
			frappe.throw("Calificaci\u00f3n Operaci\u00f3n y Operaci\u00f3n Exenta son excluyentes: rellena solo una de las dos.")
		if not has_calificacion and not has_exenta:
			frappe.throw("Debes rellenar Calificaci\u00f3n Operaci\u00f3n u Operaci\u00f3n Exenta (una de las dos, obligatoria).")
