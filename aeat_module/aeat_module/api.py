import json
import traceback
import frappe
from .utils.integrity import canonicalize_doc, hash_snapshot
from .utils.timestamp_client import TimestampClient
from .utils.signing import sign_bytes
from .utils.company_context import get_company_context
from .utils.verifactu_hash import (
    compute_huella_alta,
    compute_huella_anulacion,
    determine_tipo_factura,
    format_fecha_expedicion,
    format_fecha_hora_huso,
    format_importe,
    now_fecha_hora_huso,
)
from .utils.qr import build_qr_url, generate_qr_png_bytes, save_qr_attachment
from .doctype.aeat_queue.aeat_queue import create_queue_item_from_invoice


def _get_or_create_series_row(settings, series_code: str):
    """Devuelve la fila de AEAT Series State para `series_code`, creándola si no existe."""
    for row in settings.series or []:
        if row.series_code == series_code:
            return row
    row = settings.append("series", {"series_code": series_code, "active": 1})
    return row


def _advance_verifactu_chain(doc, ctx, tipo_factura, fecha_expedicion, cuota_total, importe_total):
    """Calcula la huella oficial (RegistroAlta), avanza la cadena de la serie en
    AEAT Company Settings y genera el QR. Devuelve (vf_hash, prev_hash)."""
    series_code = doc.get("series") or doc.get("naming_series") or ""
    settings = frappe.get_doc("AEAT Company Settings", {"company": doc.company})
    row = _get_or_create_series_row(settings, series_code)
    prev_hash = row.last_hash or None

    nif_emisor = ctx.get("nif_emisor") or doc.get("company_tax_id") or ""
    num_serie_factura = doc.name
    fecha_hora_gen = now_fecha_hora_huso()
    fecha_hora_gen_str = format_fecha_hora_huso(fecha_hora_gen)

    vf_hash = compute_huella_alta(
        nif_emisor=nif_emisor,
        num_serie_factura=num_serie_factura,
        fecha_expedicion=fecha_expedicion,
        tipo_factura=tipo_factura,
        cuota_total=cuota_total,
        importe_total=importe_total,
        huella_anterior=prev_hash,
        fecha_hora_gen_registro=fecha_hora_gen_str,
    )

    # Avanzar el encadenamiento de la serie para la siguiente factura
    row.last_hash = vf_hash
    row.last_number = (row.last_number or 0) + 1
    row.last_sent_at = frappe.utils.now_datetime()
    settings.save(ignore_permissions=True)

    doc.db_set("verifactu_invoice_type", tipo_factura)
    doc.db_set("verifactu_generation_datetime", fecha_hora_gen_str)
    doc.db_set("verifactu_prev_hash", prev_hash)
    doc.db_set("verifactu_hash", vf_hash)

    # QR: URL siempre calculable localmente; la imagen es best-effort (depende
    # del paquete opcional 'qrcode').
    qr_url = build_qr_url(
        environment=ctx.get("environment") or "preprod",
        nif=nif_emisor,
        num_serie=num_serie_factura,
        fecha=fecha_expedicion,
        importe=importe_total,
    )
    doc.db_set("verifactu_qr_url", qr_url)
    try:
        png_bytes = generate_qr_png_bytes(qr_url)
        file_url = save_qr_attachment(doc, png_bytes, f"{doc.name}-verifactu-qr.png")
        doc.db_set("verifactu_qr_image", file_url)
    except Exception as e:
        frappe.log_error(message=f"VERIFACTU QR generation failed for {doc.name}: {e}", title="AEAT Debug")

    return vf_hash, prev_hash


def _advance_verifactu_cancel_chain(doc, ctx, fecha_expedicion, fecha_hora_gen_str):
    """Calcula la huella oficial del RegistroAnulacion y avanza la misma
    cadena de serie usada para las altas (la anulación es el siguiente
    registro de la cadena). Devuelve (vf_cancel_hash, prev_hash)."""
    series_code = doc.get("series") or doc.get("naming_series") or ""
    settings = frappe.get_doc("AEAT Company Settings", {"company": doc.company})
    row = _get_or_create_series_row(settings, series_code)
    prev_hash = row.last_hash or None

    nif_emisor = ctx.get("nif_emisor") or doc.get("company_tax_id") or ""

    vf_cancel_hash = compute_huella_anulacion(
        nif_emisor_factura_anulada=nif_emisor,
        num_serie_factura_anulada=doc.name,
        fecha_expedicion_factura_anulada=fecha_expedicion,
        huella_anterior=prev_hash,
        fecha_hora_gen_registro=fecha_hora_gen_str,
    )

    row.last_hash = vf_cancel_hash
    row.last_number = (row.last_number or 0) + 1
    row.last_sent_at = frappe.utils.now_datetime()
    settings.save(ignore_permissions=True)

    doc.db_set("verifactu_cancel_prev_hash", prev_hash)
    doc.db_set("verifactu_cancel_hash", vf_cancel_hash)
    doc.db_set("verifactu_cancel_generation_datetime", fecha_hora_gen_str)

    return vf_cancel_hash, prev_hash

def handle_sales_invoice_submit(doc, method=None):
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)

    # debug: registrar invocación y contexto
    try:
        ctx = get_company_context(doc.company)
    except Exception:
        ctx = {"enable_sif": False, "enable_verifactu": False}
    frappe.log_error(message=f"AEAT handler invoked for {doc.name} company={doc.company} enable_sif={ctx.get('enable_sif')} enable_verifactu={ctx.get('enable_verifactu')}", title="AEAT Debug")

    # Evitar doble sellado
    if doc.get("seal_status") == "signed":
        frappe.log_error(message=f"AEAT handler: already signed {doc.name}", title="AEAT Debug")
        return

    try:
        # 1) SIF: snapshot + hash
        if ctx.get("enable_sif"):
            snap = canonicalize_doc(doc.as_dict())
            hash_algo = ctx.get("crypto", {}).get("tsa_hash_algo") or "sha256"
            digest_b64 = hash_snapshot(snap, hash_algo)

            # TSA (si configurado)
            tsa = TimestampClient()
            try:
                tsa_token = tsa.request_timestamp(snap)
            except Exception as e:
                tsa_token = None
                frappe.log_error(message=f"TSA request failed for {doc.name}: {e}", title="AEAT Debug")

            # Firma: PASAR company para que load_key_material use la configuración por Company
            try:
                signature_b64, alg = sign_bytes(snap, hash_algo, company=doc.company)
            except Exception as e:
                signature_b64, alg = None, None
                frappe.log_error(message=f"Signing failed for {doc.name}: {e}\n{traceback.format_exc()}", title="AEAT Debug")
                # opcional: marcar estado de error en la factura
                frappe.db.set_value("Sales Invoice", doc.name, "seal_status", "sign_error")

            # Crear Invoice Evidence (al menos con lo disponible)
            ev = frappe.get_doc({
                "doctype": "Invoice Evidence",
                "invoice": doc.name,
                "snapshot_hash": digest_b64,
                "snapshot_file": None,
                "tsa_token": frappe.as_json(tsa_token) if tsa_token else None,
                "signature": signature_b64,
                "event": "submit",
                "notes": f"Algorithm: {alg}" if alg else "signature missing"
            })
            ev.insert(ignore_permissions=True)

            # actualizar la factura (si hubo signature)
            if signature_b64:
                frappe.db.set_value("Sales Invoice", doc.name, "seal_hash", digest_b64)
                # frappe.db.set_value("Sales Invoice", doc.name, "seal_timestamp", tsa_token.get("timestamp") if tsa_token else frappe.utils.now_datetime())
                ts_val = None
                if tsa_token:
                    ts_val = tsa_token.get("timestamp")
                
                if isinstance(ts_val, str):
                    try:
                        ts_parsed = frappe.utils.parse_datetime(ts_val)
                    except Exception:
                        ts_parsed = frappe.utils.now_datetime()
                else:
                    ts_parsed = ts_val or frappe.utils.now_datetime()
                
                doc.db_set("seal_timestamp", ts_parsed)
                frappe.db.set_value("Sales Invoice", doc.name, "seal_signature", signature_b64)
                frappe.db.set_value("Sales Invoice", doc.name, "seal_status", "signed")
                frappe.db.set_value("Sales Invoice", doc.name, "seal_evidence", ev.name)
            else:
                # Guardar evidence si no se firmó y avisar
                frappe.db.set_value("Sales Invoice", doc.name, "seal_status", "sign_failed")
                frappe.db.set_value("Sales Invoice", doc.name, "seal_evidence", ev.name)

        # 2) VERI*FACTU (si activado): huella oficial (RD 1007/2023), QR y envío
        if ctx.get("enable_verifactu"):
            try:
                tipo_factura = determine_tipo_factura(doc)
                fecha_expedicion = format_fecha_expedicion(doc.posting_date)
                cuota_total = format_importe(doc.total_taxes_and_charges)
                importe_total = format_importe(doc.grand_total)

                vf_hash, prev_hash = _advance_verifactu_chain(
                    doc, ctx, tipo_factura, fecha_expedicion, cuota_total, importe_total
                )

                try:
                    create_queue_item_from_invoice("Sales Invoice", doc.name, doc.company, operation="Alta")
                    doc.db_set("verifactu_status", "queued")
                except Exception as e:
                    frappe.log_error(message=f"VERIFACTU enqueue failed for {doc.name}: {e}\n{traceback.format_exc()}", title="AEAT Debug")
                    frappe.db.set_value("Sales Invoice", doc.name, "verifactu_status", "submit_error")
            except Exception as e:
                frappe.log_error(message=f"VERIFACTU send failed for {doc.name}: {e}\n{traceback.format_exc()}", title="AEAT Debug")
                frappe.db.set_value("Sales Invoice", doc.name, "verifactu_status", "send_error")

    except Exception as exc:
        # Log general unexpected error
        frappe.log_error(message=f"AEAT handler unexpected error for {doc.name}: {exc}\n{traceback.format_exc()}", title="AEAT Debug")
        # opcional: marcar la factura como error
        frappe.db.set_value("Sales Invoice", doc.name, "seal_status", "error")
        raise


def handle_sales_invoice_cancel(doc, method=None):
    """Calcula la huella oficial del RegistroAnulacion (Fase 3) y encola su
    envío a AEAT vía AEAT Queue, igual que `handle_sales_invoice_submit` con
    el RegistroAlta."""
    if isinstance(doc, str):
        doc = frappe.get_doc("Sales Invoice", doc)

    try:
        ctx = get_company_context(doc.company)
    except Exception:
        ctx = {"enable_sif": False, "enable_verifactu": False}

    if ctx.get("enable_sif"):
        frappe.get_doc({
            "doctype": "Invoice Evidence",
            "invoice": doc.name,
            "event": "cancel",
            "notes": "Sales Invoice cancelled in ERP",
        }).insert(ignore_permissions=True)

    if ctx.get("enable_verifactu"):
        try:
            fecha_expedicion = format_fecha_expedicion(doc.posting_date)
            fecha_hora_gen_str = format_fecha_hora_huso(now_fecha_hora_huso())
            _advance_verifactu_cancel_chain(doc, ctx, fecha_expedicion, fecha_hora_gen_str)
            create_queue_item_from_invoice("Sales Invoice", doc.name, doc.company, operation="Anulacion")
            doc.db_set("verifactu_status", "cancel_queued")
        except Exception as e:
            frappe.log_error(message=f"VERIFACTU anulación failed for {doc.name}: {e}\n{traceback.format_exc()}", title="AEAT Debug")
            frappe.db.set_value("Sales Invoice", doc.name, "verifactu_status", "submit_error")


def handle_sales_invoice_update_after_submit(doc, method=None):
    """Registrado en hooks.py (on_update_after_submit) pero antes no existía.
    No-op por ahora: los campos AEAT/VERI*FACTU se escriben vía db_set en el
    propio submit y no requieren acción adicional aquí."""
    pass


@frappe.whitelist()
def export_aeat_package(invoice_names):
    """Referenciado desde public/js/sales_invoice_seal.js (botón 'Ver evidencia/
    validar sello') pero no existía -> AttributeError al pulsarlo. Exporta como
    JSON descargable las evidencias SIF (Invoice Evidence) y los datos
    VERI*FACTU (huella, QR) de una o varias Sales Invoice."""
    if isinstance(invoice_names, str):
        try:
            names = json.loads(invoice_names)
            if not isinstance(names, list):
                names = [invoice_names]
        except ValueError:
            names = [invoice_names]
    else:
        names = invoice_names

    package = []
    for name in names:
        doc = frappe.get_doc("Sales Invoice", name)
        evidences = frappe.get_all(
            "Invoice Evidence",
            filters={"invoice": name},
            fields=["name", "event", "snapshot_hash", "tsa_token", "signature", "notes", "creation"],
            order_by="creation asc",
        )
        package.append({
            "invoice": name,
            "seal_status": doc.get("seal_status"),
            "seal_hash": doc.get("seal_hash"),
            "seal_timestamp": str(doc.get("seal_timestamp") or ""),
            "verifactu_status": doc.get("verifactu_status"),
            "verifactu_invoice_type": doc.get("verifactu_invoice_type"),
            "verifactu_prev_hash": doc.get("verifactu_prev_hash"),
            "verifactu_hash": doc.get("verifactu_hash"),
            "verifactu_generation_datetime": doc.get("verifactu_generation_datetime"),
            "verifactu_qr_url": doc.get("verifactu_qr_url"),
            "evidences": evidences,
        })

    result = package[0] if len(package) == 1 else package
    frappe.response["filename"] = f"aeat-package-{names[0]}.json"
    frappe.response["filecontent"] = frappe.as_json(result, indent=2)
    frappe.response["type"] = "download"