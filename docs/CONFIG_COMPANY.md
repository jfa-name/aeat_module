# Configuración por Company (IVA vs IGIC/IPSI)

## Objetivo
Separar configuración y comportamiento por Company (ERPNext) para soportar:
- IVA (AEAT): SIF + VERI*FACTU (opcional).
- IGIC/IPSI: sólo SIF (integridad/inmutabilidad). No se envía a AEAT.

## Doctypes
- AEAT Company Settings (uno por Company):
  - Jurisdicción: IVA (AEAT) | IGIC | IPSI | Foral | Otra
  - Flags: Activar SIF, Activar VERI*FACTU (sólo si IVA)
  - Entorno + URLs VERI*FACTU (preprod/prod)
  - NIF Emisor
  - Series (child AEAT Series State) con `last_hash` por cadena
  - Override Firma/TSA por Company (si no, usa AEAT Settings global)
- AEAT Developer Settings (global): datos del desarrollador/software.
- AEAT Series State: child table para mantener `last_hash` por Company+Serie.

## Flujo en hooks
1. on_submit (Sales Invoice):
   - SIF: snapshot + hash + TSA + firma -> Invoice Evidence.
   - Si Jurisdicción=IVA y VERI*FACTU=ON:
     - Cálculo `verifactu_prev_hash` desde AEAT Company Settings.series
     - Cálculo `verifactu_hash` (encadenado por serie)
     - (Luego) Envío a VERI*FACTU y guardado de `verifactu_id`, `verifactu_qr_url`, `verifactu_status`
     - Persistencia del `last_hash` en AEAT Company Settings
2. on_cancel:
   - Evidence de cancelación.
   - Si VERI*FACTU activo: preparar cancelación (pendiente de cliente).
3. update_after_submit:
   - Evidence append-only.

## IGIC/IPSI
- Mantener SIF siempre.
- No activar VERI*FACTU.
- El encadenado puede mantenerse internamente (opcional) pero no se envía a AEAT.

## Pasos
- Crear registros de AEAT Company Settings por cada Company.
- Rellenar jurisdicción, series y NIF emisor (si IVA).
- (Opcional) Override de firma/TSA por Company.
- Probar emisión por cada Company y validar que el flujo decide correctamente.
