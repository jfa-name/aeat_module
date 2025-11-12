import traceback
import frappe
import json
from .utils.integrity import canonicalize_doc, hash_snapshot
from .utils.timestamp_client import TimestampClient
from .utils.signing import sign_bytes
from .utils.company_context import get_company_context
from .utils.integrity import canonicalize_doc, hash_snapshot

def _compute_verifactu_chain_hash(doc, prev_hash_b64: str | None) -> str:
    """
    Calcula la 'huella' encadenada VERI*FACTU para una factura.
    WARNING: Ajusta exactamente la lista de campos y su normalización
    según la especificación AEAT. Esta función usa un enfoque genérico:
    - crea un objeto con los campos relevantes en un orden determinista,
    - incluye la huella anterior (prev_hash_b64) tal cual (o "" si none),
    - aplica SHA-256 y devuelve Base64.
    Modifica el conjunto de campos y las normalizaciones (fechas, decimales)
    para cumplir estrictamente la especificación oficial.
    """
    # Campos básicos: adapta la selección y nombres exactos a la especificación AEAT
    invoice_data = {
        "serie": (doc.get("series") or doc.get("naming_series") or ""),
        "numero": doc.get("name") or "",
        "fecha": str(doc.get("posting_date") or ""),
        "hora": str(doc.get("posting_time") or ""),
        "nif_emisor": doc.get("company_tax_id") or doc.get("company") or "",
        "nif_receptor": doc.get("tax_id") or "",
        "total": format(doc.get("grand_total") or 0, "f"),
        "moneda": doc.get("currency") or "",
        "prev_huella": prev_hash_b64 or ""
    }

    # Si necesitas incluir impuestos desglosados, líneas, etc. agrégalos aquí.
    # Asegúrate de normalizar decimales y fechas EXACTAMENTE como exige AEAT.

    # Serializar de forma determinista (sin espacios)
    base_string = json.dumps(invoice_data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    # Usa sha256 para la huella encadenada (ajusta si AEAT exige otro)
    return hash_snapshot(base_string, "sha256")

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

        # 2) VERI*FACTU (si activado)
        if ctx.get("enable_verifactu"):
            # Aquí calcula verifactu_prev_hash, verifactu_hash y llama al cliente VERI*FACTU
            # (mantén tu lógica existente; añade logs y captura de excepciones)
            try:
                # ejemplo: prev_hash lookup y compute
                series_code = doc.get("series") or doc.get("naming_series") or ""
                settings = frappe.get_doc("AEAT Company Settings", {"company": doc.company})
                prev_hash = None
                for row in settings.series or []:
                    if row.series_code == series_code:
                        prev_hash = row.last_hash
                        break
                # calcula vf_hash (usa tu función)
                vf_hash = _compute_verifactu_chain_hash(doc, prev_hash)
                doc.db_set("verifactu_prev_hash", prev_hash)
                doc.db_set("verifactu_hash", vf_hash)
                try:
                    from .api_verifactu import submit_to_verifactu
                    submit_to_verifactu(doc, vf_hash, prev_hash)
                except Exception as e:
                    frappe.log_error(message=f"VERIFACTU submission failed for {doc.name}: {e}\n{traceback.format_exc()}", title="AEAT Debug")
                    frappe.db.set_value("Sales Invoice", doc.name, "verifactu_status", "submit_error")
                frappe.db.set_value("Sales Invoice", doc.name, "verifactu_prev_hash", prev_hash)
                frappe.db.set_value("Sales Invoice", doc.name, "verifactu_hash", vf_hash)
                # TODO: enviar a AEAT (client), guardar verifactu_id, verifactu_qr_url, verifactu_status
            except Exception as e:
                frappe.log_error(message=f"VERIFACTU send failed for {doc.name}: {e}\n{traceback.format_exc()}", title="AEAT Debug")
                frappe.db.set_value("Sales Invoice", doc.name, "verifactu_status", "send_error")

    except Exception as exc:
        # Log general unexpected error
        frappe.log_error(message=f"AEAT handler unexpected error for {doc.name}: {exc}\n{traceback.format_exc()}", title="AEAT Debug")
        # opcional: marcar la factura como error
        frappe.db.set_value("Sales Invoice", doc.name, "seal_status", "error")
        raise