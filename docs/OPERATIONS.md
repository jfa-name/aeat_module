# Operaciones y flujos operativos

- Flujo normal: Crear factura -> on_submit -> encolar -> worker procesa -> enviar -> Guardar resultado.
- Reintentos automatizados:
  - Huella incorrecta (2000): recalc huella y reintento 1 vez.
  - Fecha incorrecta (1105): normalizar a FechaHoraHusoGenRegistro.date() y reintento 1 vez.
  - Primer registro (2007): si RegistroDuplicado/IdPeticionRegistroDuplicado presente -> consultar -> insertar RegistroAnterior y reintentar 1 vez.
- Auditoría:
  - Guardar raw SOAP request/response por intento en /var/log/aeat/ o /tmp para debugging.
  - Guardar parsed response (JSON).
- Soporte:
  - Incluir checklist para pedir borrado en preprod a AEAT en caso de pruebas repetidas.
