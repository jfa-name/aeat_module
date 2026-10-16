# Configuración AEAT/TSA

Este módulo soporta:
- Sellado temporal RFC3161 (TSA) con `rfc3161-client`.
- Firma digital con `cryptography` (RSA/ECDSA).

## 1) Dependencias

En el app (aeat_module), añade en `requirements.txt`:
```
cryptography>=41.0.0
requests>=2.31.0
rfc3161-client>=0.1.0
```

Ejecuta:
```
bench pip install -r apps/aeat_module/requirements.txt
bench migrate
```

## 2) AEAT Settings (Config > AEAT Settings)

Campos principales:
- TSA URL: endpoint RFC3161 (ejemplos públicos: consulta con tu TSA/FNMT; no se incluyen aquí por seguridad).
- Usuario/Password: si el TSA requiere Basic Auth.
- Policy OID: OID de política del TSA (si aplica).
- Hash: sha256/384/512.
- TLS: verifica certificados; opcional `ca_bundle_path`.

Firma:
- Origen clave: Path | File (Attach) | Site Config.
- Si usas Path: apunta a PEM/PFX de la clave privada y al PEM del certificado.
- Password: contraseña de la clave (si aplica).
- Algoritmo: RSA-PKCS1v15 (por defecto), RSA-PSS o ECDSA.

## 3) Site Config (opcional)

Puedes almacenar rutas o contenido de la clave/certificado:
```json
{
  "aeat_tsa_url": "https://tsa.example.com",
  "my_signer_key": "/home/frappe/keys/signer.pfx"
}
```
En AEAT Settings pon `Origen Clave = Site Config` y `Nombre clave = my_signer_key`.

## 4) Pruebas

- Crea y envía una Sales Invoice; al hacer submit se generará:
  - hash, timestamp TSA (TSR DER en base64) y firma (base64),
  - doctype "Invoice Evidence" vinculado.
- Revisa el log si falla (Desk > Error Logs).

## 5) Producción

- Protege el fichero de clave privada (permisos en el SO).
- No subas claves al repositorio.
- Considera HSM o servicio de firma remota en producción.

## 6) Distribución del formulario Sales Invoice

Los campos del módulo se agrupan en una pestaña `AEAT`, al final de Sales
Invoice, con secciones de sellado, VERI*FACTU y anulación. Los nombres y
propiedades de los campos de datos existentes se conservan.

La fuente única es `aeat_module/fixtures/custom_field.json`, que también
incluye las categorías fiscales de Account e Item Tax Template. No mantener
otros JSON con los mismos Custom Fields: Frappe importa todos los JSON de
fixtures, aunque no estén enumerados en `hooks.py`.

Para modificar la distribución desde código, editar `insert_after` en ese
archivo. Los campos de Sales Invoice forman una cadena desde `aeat_tab`;
la pestaña se inserta después de `connections_tab`. Si se añaden campos o
separadores, incluir sus nombres en el filtro de fixtures de `hooks.py`.

Después de desplegar el código, ejecutar en cada sitio:

```bash
bench --site NOMBRE_DEL_SITIO migrate
bench --site NOMBRE_DEL_SITIO clear-cache
```

El hook `after_migrate` adapta un `Property Setter field_order` existente:
conserva el orden relativo de los demás campos y mueve el bloque AEAT al
final. No crea un orden global en sitios sin esa personalización. Esta
distribución se vuelve a aplicar en cada migración.

También se puede diseñar en Customize Form y exportar posteriormente con
`bench --site NOMBRE_DEL_SITIO export-fixtures --app aeat_module`. Hacerlo
solo después de aplicar esta migración; exportar antes podría sustituir
el diseño del código por la distribución antigua de la base de datos.
