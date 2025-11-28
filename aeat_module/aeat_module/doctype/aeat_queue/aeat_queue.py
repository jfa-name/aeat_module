# AEAT Queue Python module (placeholder)
# - contains the DocType server logic: enqueue, mark in-progress, mark done/failed
# - CRUD functions for QueueItem: create_from_invoice(invoice_id), set_status(...)
# - remember: do not include keys or sensitive data in logs, only file paths.
import frappe
from frappe.model.document import Document
from frappe import _
from datetime import datetime

class AEATQueue(Document):
    """
    DocType para gestionar la cola de procesamiento de facturas para AEAT.
    Maneja el estado y seguimiento de facturas enviadas al servicio de sellado.
    """
    
    def validate(self):
        """Validación antes de guardar"""
        if not self.status:
            self.status = "Pending"
        
        if not self.created_at:
            self.created_at = frappe.utils.now()
    
    def before_submit(self):
        """No permitir submit si no está completado"""
        if self.status not in ["Completed", "Failed"]:
            frappe.throw(_("Cannot submit queue item that is not completed or failed"))


# CRUD Functions

def create_from_invoice(invoice_id):
    """
    Crea un nuevo item en la cola AEAT desde una factura.
    
    Args:
        invoice_id (str): ID de la Sales Invoice
    
    Returns:
        AEATQueue: Documento de cola creado
    """
    if not frappe.db.exists("Sales Invoice", invoice_id):
        frappe.throw(_("Sales Invoice {0} does not exist").format(invoice_id))
    
    # Verificar si ya existe un item en cola para esta factura
    existing = frappe.db.exists("AEAT Queue", {
        "sales_invoice": invoice_id,
        "status": ["in", ["Pending", "In Progress"]]
    })
    
    if existing:
        frappe.throw(_("An active queue item already exists for this invoice"))
    
    invoice = frappe.get_doc("Sales Invoice", invoice_id)
    
    # Crear el item de cola
    queue_item = frappe.get_doc({
        "doctype": "AEAT Queue",
        "sales_invoice": invoice_id,
        "company": invoice.company,
        "customer": invoice.customer,
        "status": "Pending",
        "created_at": frappe.utils.now(),
        "retry_count": 0
    })
    
    queue_item.insert(ignore_permissions=True)
    frappe.db.commit()
    
    frappe.logger().info(f"AEAT Queue item created for invoice {invoice_id}")
    
    return queue_item


def set_status(queue_id, status, error_message=None, seal_data=None):
    """
    Actualiza el estado de un item en la cola.
    
    Args:
        queue_id (str): ID del documento AEAT Queue
        status (str): Nuevo estado (Pending, In Progress, Completed, Failed)
        error_message (str): Mensaje de error si aplica
        seal_data (dict): Datos del sello si el proceso fue exitoso
    """
    valid_statuses = ["Pending", "In Progress", "Completed", "Failed"]
    
    if status not in valid_statuses:
        frappe.throw(_("Invalid status: {0}").format(status))
    
    if not frappe.db.exists("AEAT Queue", queue_id):
        frappe.throw(_("AEAT Queue {0} does not exist").format(queue_id))
    
    queue_item = frappe.get_doc("AEAT Queue", queue_id)
    
    # Actualizar estado
    queue_item.db_set("status", status, update_modified=False)
    
    # Actualizar timestamp según el estado
    if status == "In Progress":
        queue_item.db_set("started_at", frappe.utils.now(), update_modified=False)
    
    elif status == "Completed":
        queue_item.db_set("completed_at", frappe.utils.now(), update_modified=False)
        
        # Si hay datos del sello, actualizar la factura
        if seal_data and queue_item.sales_invoice:
            update_invoice_seal_data(queue_item.sales_invoice, seal_data)
    
    elif status == "Failed":
        queue_item.db_set("completed_at", frappe.utils.now(), update_modified=False)
        queue_item.db_set("retry_count", queue_item.retry_count + 1, update_modified=False)
        
        if error_message:
            # No incluir información sensible en logs
            safe_error = sanitize_error_message(error_message)
            queue_item.db_set("error_message", safe_error, update_modified=False)
            frappe.logger().error(f"AEAT Queue {queue_id} failed: {safe_error}")
    
    frappe.db.commit()
    
    frappe.logger().info(f"AEAT Queue {queue_id} status updated to {status}")


def enqueue_invoice(invoice_id):
    """
    Encola una factura para procesamiento AEAT.
    
    Args:
        invoice_id (str): ID de la Sales Invoice
    
    Returns:
        dict: Resultado de la operación
    """
    try:
        queue_item = create_from_invoice(invoice_id)
        
        # Encolar el trabajo de procesamiento
        frappe.enqueue(
            "aeat_module.aeat_module.doctype.aeat_queue.aeat_queue.process_queue_item",
            queue_id=queue_item.name,
            timeout=300,
            is_async=True
        )
        
        return {
            "success": True,
            "queue_id": queue_item.name,
            "message": _("Invoice enqueued for AEAT processing")
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "AEAT Enqueue Error")
        return {
            "success": False,
            "message": str(e)
        }


def process_queue_item(queue_id):
    """
    Procesa un item de la cola AEAT.
    Esta función será llamada de forma asíncrona.
    
    Args:
        queue_id (str): ID del documento AEAT Queue
    """
    try:
        # Marcar como en progreso
        set_status(queue_id, "In Progress")
        
        queue_item = frappe.get_doc("AEAT Queue", queue_id)
        
        if not queue_item.sales_invoice:
            raise Exception("No sales invoice linked to queue item")
        
        # Aquí se llamaría al servicio de sellado
        # Por ejemplo: seal_data = call_sealing_service(queue_item.sales_invoice)
        
        # Placeholder para resultado exitoso
        seal_data = {
            "seal_hash": "placeholder_hash",
            "seal_timestamp": frappe.utils.now(),
            "seal_signature": "placeholder_signature",
            "seal_status": "Sealed",
            "seal_evidence": "placeholder_evidence_path"
        }
        
        # Marcar como completado con los datos del sello
        set_status(queue_id, "Completed", seal_data=seal_data)
        
    except Exception as e:
        error_msg = str(e)
        set_status(queue_id, "Failed", error_message=error_msg)
        frappe.log_error(frappe.get_traceback(), f"AEAT Queue Processing Error - {queue_id}")


def mark_in_progress(queue_id):
    """
    Marca un item de cola como en progreso.
    
    Args:
        queue_id (str): ID del documento AEAT Queue
    """
    set_status(queue_id, "In Progress")


def mark_done(queue_id, seal_data):
    """
    Marca un item de cola como completado.
    
    Args:
        queue_id (str): ID del documento AEAT Queue
        seal_data (dict): Datos del sello obtenidos
    """
    set_status(queue_id, "Completed", seal_data=seal_data)


def mark_failed(queue_id, error_message):
    """
    Marca un item de cola como fallido.
    
    Args:
        queue_id (str): ID del documento AEAT Queue
        error_message (str): Mensaje de error
    """
    set_status(queue_id, "Failed", error_message=error_message)


# Helper Functions

def update_invoice_seal_data(invoice_id, seal_data):
    """
    Actualiza los datos del sello en la factura.
    
    Args:
        invoice_id (str): ID de la Sales Invoice
        seal_data (dict): Datos del sello
    """
    if not frappe.db.exists("Sales Invoice", invoice_id):
        frappe.logger().error(f"Sales Invoice {invoice_id} not found for seal update")
        return
    
    invoice = frappe.get_doc("Sales Invoice", invoice_id)
    
    # Verificar que existan los custom fields
    if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": "seal_hash"}):
        invoice.db_set("seal_hash", seal_data.get("seal_hash"), update_modified=False)
    
    if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": "seal_timestamp"}):
        invoice.db_set("seal_timestamp", seal_data.get("seal_timestamp"), update_modified=False)
    
    if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": "seal_signature"}):
        invoice.db_set("seal_signature", seal_data.get("seal_signature"), update_modified=False)
    
    if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": "seal_status"}):
        invoice.db_set("seal_status", seal_data.get("seal_status"), update_modified=False)
    
    if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": "seal_evidence"}):
        invoice.db_set("seal_evidence", seal_data.get("seal_evidence"), update_modified=False)
    
    frappe.db.commit()
    
    frappe.logger().info(f"Seal data updated for invoice {invoice_id}")


def sanitize_error_message(error_message):
    """
    Limpia el mensaje de error para evitar exponer información sensible.
    
    Args:
        error_message (str): Mensaje de error original
    
    Returns:
        str: Mensaje de error sanitizado
    """
    # Eliminar posibles paths completos, solo mantener nombres de archivo
    import re
    
    # Remover paths absolutos, mantener solo nombre de archivo
    sanitized = re.sub(r'/[\w/]+/([^/\s]+)', r'\1', error_message)
    
    # Remover posibles tokens o claves (patrones comunes)
    sanitized = re.sub(r'(key|token|secret|password)["\']?\s*[:=]\s*["\']?[\w-]+', r'\1=***', sanitized, flags=re.IGNORECASE)
    
    return sanitized[:500]  # Limitar longitud


@frappe.whitelist()
def retry_failed_item(queue_id):
    """
    Reintenta procesar un item fallido.
    
    Args:
        queue_id (str): ID del documento AEAT Queue
    
    Returns:
        dict: Resultado de la operación
    """
    if not frappe.db.exists("AEAT Queue", queue_id):
        frappe.throw(_("AEAT Queue {0} does not exist").format(queue_id))
    
    queue_item = frappe.get_doc("AEAT Queue", queue_id)
    
    if queue_item.status != "Failed":
        frappe.throw(_("Can only retry failed items"))
    
    # Resetear estado a Pending
    queue_item.db_set("status", "Pending", update_modified=False)
    queue_item.db_set("error_message", None, update_modified=False)
    frappe.db.commit()
    
    # Encolar nuevamente
    frappe.enqueue(
        "aeat_module.aeat_module.doctype.aeat_queue.aeat_queue.process_queue_item",
        queue_id=queue_item.name,
        timeout=300,
        is_async=True
    )
    
    return {
        "success": True,
        "message": _("Queue item re-enqueued for processing")
    }


@frappe.whitelist()
def get_queue_status(invoice_id):
    """
    Obtiene el estado de la cola para una factura específica.
    
    Args:
        invoice_id (str): ID de la Sales Invoice
    
    Returns:
        dict: Estado de la cola
    """
    queue_items = frappe.get_all(
        "AEAT Queue",
        filters={"sales_invoice": invoice_id},
        fields=["name", "status", "created_at", "completed_at", "error_message", "retry_count"],
        order_by="creation desc",
        limit=1
    )
    
    if not queue_items:
        return {
            "exists": False,
            "message": _("No queue item found for this invoice")
        }
    
    return {
        "exists": True,
        "queue_item": queue_items[0]
    }