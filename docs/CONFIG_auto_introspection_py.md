## Documentation for run script in 'bench console'
## Output example when running auto-introspection script 'auto_introspection_py.py' with WSDL "/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl":
============================================================
Iniciando auto-introspección...
============================================================

Using WSDL: file:///path/to/your/frappe-bench/apps/aeat_module/docs/PreSistemaFacturacion.wsdl.sanitized.rewritten.localized.wsdl
WSDL cargado. Servicios: ['sfVerifactu', 'sfRequerimiento']
Binding: {https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SistemaFacturacion.wsdl}sfVerifactu
Endpoint: https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP
Usando preprod: https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP

Operation signature: Cabecera: ns1:CabeceraType, RegistroFactura: ns3:RegistroFacturaType[]

============================================================
Construyendo payload skeleton...
============================================================
  Warning: Error en elemento ?: name 'build_example_from_type' is not defined
  Warning: Error en elemento ?: name 'build_example_from_type' is not defined
  Warning: Error en elemento ?: name 'build_example_from_type' is not defined
  Warning: Error en elemento ?: name 'build_example_from_type' is not defined
  Warning: Error en elemento ?: name 'build_example_from_type' is not defined
  Warning: Error en elemento ?: name 'build_example_from_type' is not defined

Payload inicial generado:
{'Cabecera': {}, 'RegistroFactura': [{}]}

============================================================
Intentando generar XML con auto-relleno...
============================================================

✗ Intento 1 falló: Missing element ObligadoEmision (RegFactuSistemaFacturacion.Cabecera.ObligadoEmision)
  → Detectado elemento faltante: ObligadoEmision
  → Path: ['RegFactuSistemaFacturacion', 'Cabecera', 'ObligadoEmision']
  ✓ Insertado 'ObligadoEmision' en Cabecera.ObligadoEmision

✗ Intento 2 falló: Missing element NIF (RegFactuSistemaFacturacion.Cabecera.ObligadoEmision.NIF)
  → Detectado elemento faltante: NIF
  → Path: ['RegFactuSistemaFacturacion', 'Cabecera', 'ObligadoEmision', 'NIF']
  ✓ Insertado 'NIF' en Cabecera.ObligadoEmision.NIF

✗ Intento 3 falló: Missing element NombreRazon (RegFactuSistemaFacturacion.Cabecera.ObligadoEmision.NombreRazon)
  → Detectado elemento faltante: NombreRazon
  → Path: ['RegFactuSistemaFacturacion', 'Cabecera', 'ObligadoEmision', 'NombreRazon']
  ✓ Insertado 'NombreRazon' en Cabecera.ObligadoEmision.NombreRazon

✓ Éxito en intento 4!

============================================================
Preview XML (primeros 10000 chars):
============================================================
<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">
  <soap-env:Body>
    <ns0:RegFactuSistemaFacturacion xmlns:ns0="https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd">
      <ns0:Cabecera>
        <ns1:ObligadoEmision xmlns:ns1="https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd">
          <ns1:NombreRazon>example</ns1:NombreRazon>
          <ns1:NIF>example</ns1:NIF>
        </ns1:ObligadoEmision>
      </ns0:Cabecera>
      <ns0:RegistroFactura/>
    </ns0:RegFactuSistemaFacturacion>
  </soap-env:Body>
</soap-env:Envelope>


============================================================
Payload final:
============================================================
{'Cabecera': {'ObligadoEmision': {'NIF': 'example', 'NombreRazon': 'example'}},
 'RegistroFactura': [{}]}

✓ Introspección completada exitosamente!

============================================================
Para usar el payload:
============================================================
response = proxy.RegFactuSistemaFacturacion(**payload)

============================================================
Ejemplo completo de invocación:
============================================================
proxy = client.create_service(binding_qname, address)

try:
    resp = proxy.RegFactuSistemaFacturacion(**payload)
    print("Respuesta (obj):", resp)
except Exception as e:
    print("Error durante la invocación:", e)

if history.last_sent:
    sent = history.last_sent["envelope"].decode("utf-8")
    print("=== Último XML enviado (truncado) ===")
    print(sent[:10000])
    open("/tmp/aeat_last_sent.xml", "w").write(sent)
if history.last_received:
    recv = history.last_received["envelope"].decode("utf-8")
    print("=== Último XML recibido (truncado) ===")
    print(recv[:10000])
    open("/tmp/aeat_last_received.xml", "w").write(recv)