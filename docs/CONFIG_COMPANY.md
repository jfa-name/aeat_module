# Configuración por Company (IVA vs IGIC/IPSI)

## Objetivo
Cada Company (ERPNext) debe soportar:
- IVA/IGIC/IPSI (AEAT): VERI*FACTU.
- Firma digital + sellado temporal (TSA) por Company.

## Custom Fieldnames
- En Company, añadir:
  - Jurisdicción (AEAT): aeat_jurisdiction (Select): IVA | IGIC | IPSI | Foral | Otra
  - NIF Emisor
  - Series (child AEAT Series State) con `last_hash` por cadena
  - Override Firma/TSA por Company (si no, usa AEAT Settings global)
  - Flags: 
   - Activar SIF: aeat_enable_sif (Check)
   - Activar VERI*FACTU: aeat_enable_verifactu (Check)
  - Entorno: aeat_verifactu_environment (Select): Preprod | Prod
  - URL VERI*FACTU (preprod): aeat_verifactu_url_preprod (Data)
  - URL VERI*FACTU (prod): aeat_verifactu_url_prod (Data)
  - aeat_nif_emitter (Data)

## Doctypes
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

## Pasos
- Añadir configuración a cada Company.
- Rellenar jurisdicción, series y NIF emisor (si IVA).
- Override de firma/TSA por Company.
- Probar emisión por cada Company y validar que el flujo decide correctamente.
