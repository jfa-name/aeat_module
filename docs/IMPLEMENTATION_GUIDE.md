Implementación - pasos operativos (guía para desarrollador/operador)

1) Requisitos del sistema:
   - python packages: zeep, lxml, xmlsec, requests
   - libs del sistema: libxml2, libxmlsec1, libxmlsec1-openssl
   - openssl
   - acceso a: cert.pem, key.pem (o .p12) y ca-bundle.pem

2) Crear DocTypes:
   - AEAT Settings: endpoint, env (preprod/prod), retry policy, timeout, log level.
   - AEAT Certificate: referencia/alias a certificado (no almacenar claves en texto plano).
   - AEAT Queue Item: invoice_id, status, attempt_count, last_error, last_sent_path, last_received_path.

3) Hooks:
   - on_submit Sales Invoice -> crear AEAT Queue Item y encolar.
   - Scheduler: periodic worker runner, o use background worker.

4) Worker flow:
   - Pop queue item.
   - Build payload (mapear campos Sale Invoice -> payload AEAT).
   - create_message preview (zeep).
   - Calcular huella (según especificación AEAT: cadena de campos o c14n según TipoHuella).
   - Insertar Huella/TipoHuella.
   - Firmar (xmlsec).
   - Enviar por requests (mTLS) o con Zeep transport si no firmas el XML.
   - Guardar /tmp/aeat_last_sent.xml y /tmp/aeat_last_received.xml y actualizar estado del Queue Item.
   - Si AEAT devuelve código que exige reintento/autocorrección (1105, 1251, 2007, 3000...), manejar lógicas de reintento o reencadenamiento automático (consulta + reenvío).

5) Seguridad:
   - claves en carpeta con permisos restringidos.
   - rotación y backup de certificados.
   - no registrar claves en logs.

6) Deploy:
   - Asegurar xmlsec en servidores (apt install ...).
   - Crear job/worker en bench background.
   - Añadir variables en ENV para rutas.
