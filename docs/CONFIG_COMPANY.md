# Configuración por Company (IVA vs IGIC/IPSI)

## Objetivo
Separar configuración y comportamiento por Company (ERPNext) para soportar:
- IVA (AEAT), IGIC (Canarias) e IPSI (Ceuta/Melilla): SIF + VERI*FACTU.
  El RD 1007/2023 y el propio registro VERI*FACTU (campo "Impuesto":
  01=IVA/02=IPSI/03=IGIC) aplican a los tres territorios, NO solo a IVA.
- "Foral"/"Otra/No aplica": sólo SIF (integridad/inmutabilidad), sin envío
  a AEAT vía VERI*FACTU.

## Doctypes
- AEAT Company Settings (uno por Company):
  - Jurisdicción: IVA (AEAT) | IGIC | IPSI | Foral | Otra/No aplica
    (solo informativa/por defecto; el desglose real Impuesto/ClaveRegimen
    por línea de factura lo decide `AEAT Tax Category`, ver más abajo).
  - Flags: Activar SIF, Activar VERI*FACTU (se desactiva SOLO si
    jurisdicción = "Otra/No aplica").
  - Entorno (preprod/prod) — determina el puerto SOAP que se usa del WSDL,
    NO hace falta configurar URLs manualmente (ver sección mTLS).
  - NIF Emisor.
  - Series (child AEAT Series State) con `last_hash` por cadena.
  - Sección "Autenticación VERI*FACTU": certificado mTLS (ver más abajo).
- AEAT Tax Category: una por cada tipo impositivo/exención (IVA 21%, IVA
  10%, IGIC 7%, exenciones...). Se enlaza desde "Item Tax Template" (o
  desde la cuenta contable si usas "Sales Taxes and Charges Template").
  Ver `utils/tax_breakdown.py` para el detalle del algoritmo de agrupación.
- AEAT Developer Settings (global): datos del desarrollador/software.
- AEAT Series State: child table para mantener `last_hash` por Company+Serie.

## ⚠️ Dos certificados/configuraciones DISTINTAS, no las confundas
1. **AEAT Settings (global) → TSA/Firma**: solo para el sellado interno SIF
   (`enable_sif`), inmutabilidad del propio ERP. El campo "TSA URL" es un
   servicio RFC3161 de sellado de tiempo (genérico, NO es una URL de la
   AEAT) y la clave/certificado de "Firma" solo firma el snapshot interno.
   Si no activas `enable_sif`, esta sección no se usa para nada.
2. **AEAT Company Settings → sección "Autenticación VERI*FACTU" (mTLS)**:
   el certificado REAL que exige la AEAT para autenticar las llamadas SOAP
   al servicio VERI*FACTU (`utils/verifactu_soap_client.py`). Es el que
   necesitas para que `enable_verifactu` funcione. Opciones:
   - `mTLS: PFX (Attach)` o `mTLS: PFX Path` → tu certificado digital
     `.p12`/`.pfx` (el mismo que usas para la Sede Electrónica de la AEAT).
   - `mTLS: Password Key` → contraseña del `.p12` (campo tipo Password).
   - Alternativa: `mTLS: Cert Path (PEM)` + `mTLS: Key Path (PEM)` si ya
     tienes el certificado separado en PEM.
   **No hace falta configurar ninguna URL/endpoint aquí**: el cliente SOAP
   elige automáticamente el puerto correcto del WSDL local según el
   `Entorno` (preprod → `prewww1.aeat.es`, prod → `www1.agenciatributaria.gob.es`).
   La URL `prewww2.aeat.es`/`www2.agenciatributaria.gob.es` que ves en el
   código es la del **QR** de la factura (servicio de cotejo), no la de
   envío; y `prewww10`/`www10` es la variante "Sello" (certificado de
   representante/colaborador social), que no se usa para un certificado
   personal de autónomo.

## Flujo en hooks
1. on_submit (Sales Invoice):
   - SIF: snapshot + hash + TSA + firma -> Invoice Evidence (solo si `enable_sif`).
   - Si VERI*FACTU=ON (cualquier jurisdicción salvo "Otra/No aplica"):
     - Huella oficial (`utils/verifactu_hash.py`) + QR (`utils/qr.py`).
     - Envío real por SOAP+mTLS (`utils/verifactu_soap_client.py`); si no
       hay certificado mTLS configurado, `verifactu_status` queda en
       `no_certificate` (no se bloquea la factura, solo no se envía).
     - Persistencia del `last_hash` en AEAT Company Settings.
2. on_cancel:
   - Evidence de cancelación.
   - Si VERI*FACTU activo: preparar cancelación (pendiente de cliente SOAP, Fase 3).
3. update_after_submit:
   - Evidence append-only.

## Pasos
- Crear registros de AEAT Company Settings por cada Company con jurisdicción
  y NIF emisor, y rellenar la sección "Autenticación VERI*FACTU" (mTLS) con
  el certificado real.
- Crear `AEAT Tax Category` y enlazarlas desde los Item Tax Template (o
  cuentas) usados por cada tipo impositivo de esa Company/territorio.
- Probar emisión por cada Company y validar en "Error Log"/`AEAT Transmission Log`.

