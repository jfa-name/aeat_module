Implementación - pasos operativos (guía para desarrollador/operador)

1) Requisitos del sistema:
   - python packages: zeep, lxml, signxml, requests (ver pyproject.toml;
     no se usa python-xmlsec, requiere libxmlsec1-dev vía sudo apt)
   - openssl (para inspeccionar/convertir certificados .p12 manualmente)
   - acceso al certificado digital real (.p12/.pfx, o cert.pem+key.pem)

2) DocTypes relevantes:
   - AEAT Company Settings: jurisdicción, entorno (preprod/prod), NIF
     emisor, series, y sección "Autenticación VERI*FACTU" (certificado
     mTLS real: PFX o cert+key PEM — único lugar donde se configura).
   - AEAT Queue Item: invoice, operation (Alta/Anulacion), status,
     attempts, last_error, last_sent_path, last_received_path.

3) Hooks:
   - on_submit Sales Invoice -> calcula huella/QR y crea AEAT Queue Item
     (operation="Alta").
   - on_cancel Sales Invoice -> calcula huella de anulación y crea AEAT
     Queue Item (operation="Anulacion").
   - scheduler_events (cron cada 5 min) -> worker.drain_pending_queue()
     procesa los pendientes sin necesitar un proceso worker.py separado.

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
