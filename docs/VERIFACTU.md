# VERI*FACTU — Endpoints y autenticación

Este módulo soporta dos modos de autenticación por Company:
- mTLS (certificado cliente): el más habitual para entornos tributarios.
- OAuth2 Client Credentials (si tu entorno/tarjeta de pruebas lo usa).

Configura por Company en “AEAT Company Settings”:
- Entorno y Base URL (preprod/prod) conforme al portal de AEAT: https://verifactu-aeat.github.io/
- Paths concretos de las operaciones (alta, anulación, estado). En esta plantilla:
  - `verifactu_api_path_send`          → Envío (alta) de registro
  - `verifactu_api_path_cancel`        → Anulación/rectificación
  - `verifactu_api_path_status`        → Consulta de estado

Autenticación:
- mTLS:
  - Certificado cliente y clave en PEM (o PFX adjunto/ruta). Si usas PFX, el cliente convertirá a PEM temporalmente.
  - Opcional: password de la clave. Recomendación: generar PEM sin pass para el proceso (protege con permisos de SO).
- OAuth2:
  - Token URL, Client ID/Secret y scope.
- TLS:
  - Verificación del servidor activada por defecto (recomendado). Puedes indicar un CA bundle propio si AEAT publica uno específico.

Uso desde hooks:
- En on_submit de Sales Invoice, calcula `verifactu_prev_hash` y `verifactu_hash` y llama:
  ```python
  from aeat_module.aeat_module.api_verifactu import submit_to_verifactu
  submit_to_verifactu(doc, vf_hash, prev_hash)
  ```
- En cancelación:
  ```python
  from aeat_module.aeat_module.api_verifactu import cancel_in_verifactu
  cancel_in_verifactu(doc, reason_code="ANU", description="Anulación ERP")
  ```

Bitácora:
- Cada llamada se guarda en “AEAT Transmission Log” con payload/response para auditoría.

IMPORTANTE
- Ajusta el mapeo `map_invoice_to_verifactu_payload` con el esquema oficial (nombres y estructura).
- Valida en el Portal de Pruebas Externas:
  https://sede.agenciatributaria.gob.es/Sede/iva/suministro-inmediato-informacion/informacion-tecnica/portal-pruebas-externas.html
