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

## 2) Configurar cada Company (Config > Company > AEAT Settings)

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
