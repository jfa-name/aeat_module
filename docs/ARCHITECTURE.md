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
  - AEAT Settings (TSA/firma para el sellado interno SIF, solo).
  - AEAT Company Settings (certificado mTLS real por Company, sección
    "Autenticación VERI*FACTU" — único lugar donde se configura el
    certificado usado para hablar con la AEAT; se eliminó el DocType
    "AEAT Certificate" por duplicar este almacenamiento sin estar
    conectado a ningún flujo real, ver Fase 4).
  - AEAT Queue / AEAT Queue Item (estado, reintentos, logs).
- Integración con UI de ERPNext para monitorizar estado y reprocesar.

Implementar:
- DocTypes y formularios para configuración.
- Colas y worker (bench worker o celery/redis según prefieras).
- Mecanismo seguro para almacenar claves (no en texto plano en el repo).
- Tests integrados y pipelines CI.
