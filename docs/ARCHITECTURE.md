# Arquitectura del módulo AEAT Module

Resumen de alto nivel:
- Detectar facturas emitidas (Sales Invoice) y poner en cola para envío a AEAT.
- Worker en background que:
  - construye payload (create_message),
  - calcula huella según especificación AEAT,
  - firma XML (xmlsec / PKCS12),
  - envía por mTLS al endpoint AEAT,
  - guarda last_sent/last_received y mapea códigos de respuesta.
- Ficheros de configuración y DocTypes:
  - AEAT Settings (cert paths, CA bundle, endpoint preprod/prod, modo).
  - AEAT Certificate (almacén o referencia al key/cert).
  - AEAT Queue (estado, retries, logs).
- Integración con UI de ERPNext para monitorizar estado y reprocesar.

Implementar:
- DocTypes y formularios para configuración.
- Colas y worker (bench worker o celery/redis según prefieras).
- Mecanismo seguro para almacenar claves (no en texto plano en el repo).
- Tests integrados y pipelines CI.
