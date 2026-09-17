# AEAT Module — Files to create and next steps (summary, no code)

Este documento enumera los archivos y recursos que conviene añadir al módulo "AEAT Module" de ERPNext para cubrir todo el flujo que tienes ya probado: detectar facturas en ERPNext, transformar al esquema AEAT, calcular huella, firmar, enviar (mTLS + XML‑DSIG), gestionar reintentos y guardar trazabilidad. No incluyo código; sólo nombres de archivos, su propósito, y pasos previos/depencias.

Resumen del flujo
- Detectar facturas emitidas en ERPNext (DocType: Sales Invoice u otro personalizado).
- Construir payload conforme a SuministroInformacion.xsd / RegFactuSistemaFacturacion.
- Calcular huella según regla AEAT (cadena de campos -> SHA256 HEX).
- Insertar huella en payload, generar XML (zeep.create_message), firmar con xmlsec (ds:Signature) y enviar por mTLS.
- Analizar respuesta AEAT; en errores manejables (1105, 1251, 2000, 2007, 3000...) aplicar correcciones o reintentos automáticos (ej. consultar RegistroDuplicado y encadenar).
- Guardar trazabilidad: last_sent, last_received, parsed response, logs.
- Exponer UI para estado y reintentos manuales.

Archivos (estructura propuesta)
- apps/aeat_module/
  - __init__.py
    - Módulo: registra package.
  - hooks.py
    - Hook de ERPNext: registrar eventos (on_submit, on_cancel) sobre Sales Invoice o hook scheduler/task.
  - hooks_data.json (opcional)
    - Lista de hooks y scheduler jobs documentada.
  - settings/aeat_settings.py (o DocType `AEAT Settings`)
    - Clase o DocType para guardar configuración (paths a cert/key, ca-bundle, endpoint, modo preprod/prod, retries, NIF del presentador).
  - docs/README.md (documentación de integrador)
    - Explica flujo, configuración, how-to, y ejemplo de despliegue.
  - services/client.py
    - Clase wrapper para crear el zeep Client con LocalMappingTransport, HistoryPlugin y gestionar endpoint/resuelve WSDL.
  - services/transformer.py
    - Funciones para mapear Sales Invoice -> payload dict esperado por Zeep (nombres exactos del XSD).
  - services/huella.py
    - Implementación del algoritmo AEAT: construir la cadena de entrada (los campos en orden), formateos (decimales, fecha), y calcular SHA256 hex uppercase.
  - services/signer.py
    - Encapsula xmlsec signing: registro de Id, template ds:Signature, firma con PEM o PKCS12, fallback a xmlsec1 CLI.
  - services/sender.py
    - Lógica de mTLS send: preparar headers, usar requests session con session.cert y session.verify, captura de errores TLS y reintentos bajos.
  - services/error_mapper.py
    - Mapea códigos AEAT (1105, 1251, 2000, 2007, 3000...) a mensajes de usuario y acciones automáticas (normalizar fecha, cambiar IDVersion, recalc huella, encadenar).
  - services/consulta.py
    - Lógica para ConsultaFactuSistemaFacturacion (resolver firma de operación, preparar request, parsear respuesta) — usado para recuperar registro anterior cuando sea necesario.
  - tasks.py
    - Funciones encolables (background jobs) para procesar lotes de facturas; integrable con frappe.enqueue.
  - api.py (o controllers.py)
    - Endpoints REST/JSON para iniciar envío manual, ver estado, forzar reintento, descargar last_sent/received.
  - doctype/AEAT Settings/aeat_settings.json (DocType)
    - Definición del DocType que almacenará la configuración de la integración (cert path, key path, ca bundle, preprod flag, default system info).
  - doctype/AEAT Log/aeat_log.json (DocType)
    - Definición de DocType para almacenar trazas por factura (referencia a invoice, timestamp, status, last_sent file ref, last_received file ref, code).
  - cron/aeat_scheduler.py
    - Tareas programadas: enviar pendientes, renovar data, limpiar logs antiguos.
  - workers/worker_integration.py
    - Si usas worker separado para firma/envío para no bloquear request.
  - tests/
    - test_transformer.py (unit)
    - test_huella.py (unit)
    - test_signer_integration.py (integration, requires test key/cert)
    - test_end_to_end_preprod.mocked.py (integration with mocked AEAT)
  - migrations/README.md (si hace falta)
    - Parches o fixtures para registrar DocTypes en sitios nuevos.
  - config/example.yml
    - Ejemplo de valores: CERT, KEY, CA_BUNDLE, USE_PREPROD, TIMEOUTS, MAX_RETRIES.
  - scripts/sign_and_send.py
    - Script CLI (tu versión ya existente). Útil como referencia y para pruebas ad‑hoc fuera de ERPNext.
  - docs/Lista_codigos_de_error.md
    - Mapa de códigos AEAT -> explicación y acciones recomendadas.
  - docs/XSD_notes.md
    - Lista de los XSD locales usados, versiones y observaciones (p. ej. VersionType enumerations).
  - templates/admin/aeat_status.html (opcional)
    - Página de administración para visualizar estados y reintentos.
  - utils/files.py
    - Helper para guardar archivos en filesystem o File doc, rutas /tmp -> storage, rotación y permisos.

Cambios en el modelo de datos / Doctypes
- DocType: AEAT Settings
  - Campos: certificate_path, key_path, ca_bundle_path, endpoint, preprod_flag, obligado_nif_por_defecto, tipo_huella_default, max_retries, notify_emails.
- DocType: AEAT Log / AEAT Transmission
  - Campos: linked_invoice (Link to Sales Invoice), status, aeat_code, aeat_message, sent_file (File/Attachment), received_file (File/Attachment), raw_response, attempt_number, timestamp, details JSON.
- (Opcional) DocType: AEAT Queue
  - Si no quieres usar frappe queue, una tabla para pendientes.

Integración en ERPNext
- Hooks para:
  - on_submit (Sales Invoice) -> enqueue job to sign_and_send (nonblocking)
  - on_cancel -> send cancellation/rectification flows
  - Scheduled job -> retry failed up to N times
- UI:
  - Button "Enviar a AEAT" en la vista de invoice (llama API endpoint que encola job)
  - Panel "AEAT Status" mostrando AEAT Log entries for the invoice.

Dependencias / prerequisitos (sistema)
- Python packages (requirements.txt):
  - zeep
  - lxml
  - xmlsec (binding)
  - requests
- System packages:
  - libxml2-dev, libxmlsec1-dev, libxmlsec1-openssl (para python-xmlsec)
  - openssl (para manejo de certificados)
- Certificates:
  - Certificado PEM (cert.pem) y clave (key.pem) con permisos adecuados
  - CA bundle (merged) que incluya la cadena intermedia requerida por AEAT
  - (Opcional) almacenar certificado/clave en un lugar seguro (Vault) y el módulo leerlos con permisos de sistema
- AEAT:
  - Registro/alta en preprod/prod con NIF del obligado y perfil correcto
  - Solicitar limpieza en preprod si necesitas empezar desde cero (opcional)
  - Confirmar algoritmo de huella y TipoHuella code con AEAT (documentación)

Operativa y seguridad
- No guardar claves privadas en el repo. Usar rutas configuradas y restringir permisos (600).
- Registrar trazas en DB/File, pero no exponer llaves.
- Logs: //tmp/aeat_last_sent.xml //tmp/aeat_last_received.xml (para debugging), y también guardar permanentemente en AEAT Log Doctype o storage.
- Reintentos: limitar (p.ej. 3) y alertas por email si fallido repetido.

Testing & QA
- Unit tests para transformer (campo names / types), huella builder, signer (mock key).
- Integration tests (in CI) that mock AEAT responses (use recorded responses) to assert error handling (1105, 1251, 2000, 2007, 3000).
- Manual acceptance in preprod AEAT: test sending single invoice, duplicate handling, encadenamiento.

Despliegue
- Añadir `requirements.txt` y playbook (ansible / shell) para instalar system deps y pip packages.
- Registrar DocTypes en aplicación y activar hooks.
- Probar con una cuenta de preprod (usar cert/key de test).
- Hacer smoke tests: send invoice -> expect Parsed response saved -> check AEAT Log.

Checklist por empresa/copañía
- [ ] Registrar y comprobar que el certificado que usas es válido/aceptado en preprod (ya lo hiciste).
- [ ] CA bundle merge (ya resuelto).
- [ ] Verificar que el NIF del ObligadoEmision coincide con el sujeto del certificado (AEAT valida esto).
- [ ] Confirmar con AEAT el formato final de TipoHuella (¿"01" o "1"?) y el algoritmo (SHA256 HEX vs base64). Ya detectaste que AEAT usa SHA256 HEX.
- [ ] Decidir estrategia para borrar/limpiar preprod si quieres empezar desde cero (opcional).
- [ ] Instalar libxmlsec y python-xmlsec en los servidores donde se ejecute (worker/bench).

Operaciones y UX para el módulo en ERPNext
- Pantalla de configuración (AEAT Settings).
- Botón manual "Enviar a AEAT" en Sales Invoice; background job que hace el envío.
- Página de logs/estado por factura y global.
- Notificaciones automáticas si AEAT devuelve errores críticos (ej. 4112, certificados no coinciden).

Siguientes pasos recomendados (prioritarios)
1. Crear los DocTypes (AEAT Settings, AEAT Log) y `hooks.py` para registrar evento on_submit.  
2. Implementar los servicios en `services/*` (transformer, huella, signer, sender, consulta, error_mapper).  
3. Añadir jobs background (tasks.py) y endpoints API para triggers manuales y status.  
4. Escribir tests unit e integración mockeando AEAT.  
5. Desplegar en entorno de staging / preprod y probar con un flujo completo (ya tienes el script CLI para pruebas ad‑hoc).  

