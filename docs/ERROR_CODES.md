# Mapeo de códigos AEAT

Incluye los códigos que has ido encontrando (ejemplos):
- 1105: FechaExpedicionFactura incorrecta — validación de formato/coherencia.
- 1251: IDVersion incorrecto — usar enumeración VersionType en XSD.
- 2000: Huella incorrecta — comprobar cadena de entrada y formato (SHA256 HEX).
- 2007: No debe informarse como primer registro — usar RegistroAnterior (encadenamiento).
- 3000: Registro duplicado — extraer IdPeticionRegistroDuplicado para consulta/encadenamiento.

Para cada código:
- Significado
- Acción recomendada (auto-fix posible? reintento? notificar al usuario)
- Documentación / link a fichero local donde está la especificación
