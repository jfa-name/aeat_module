from zeep import Client, Settings
from zeep.transports import Transport
import requests
import logging

# Opcional: logging para ver el XML que se envía/recibe
logging.basicConfig(level=logging.INFO)
logging.getLogger('zeep.transports').setLevel(logging.DEBUG)
logging.getLogger('zeep.client').setLevel(logging.DEBUG)

wsdl_path = "docs/PreSistemaFacturacion.wsdl"  # o URL si lo apuntas a remoto
cert_path = "/etc/ssl/aeat/cert.pem"
key_path = "/etc/ssl/aeat/key.pem"
ca_bundle = "/etc/ssl/aeat/ca-bundle.pem"  # o True

session = requests.Session()
session.cert = (cert_path, key_path)
session.verify = ca_bundle  # o True

transport = Transport(session=session, timeout=60)
settings = Settings(strict=False, xml_huge_tree=True)
client = Client(wsdl=wsdl_path, transport=transport, settings=settings)

# inspeccionar servicios/operaciones:
print(client.wsdl.services)      # ver servicios
for svc in client.wsdl.services.values():
    for port in svc.ports.values():
        print("Service:", svc.name, "Port:", port.name, "Binding:", port.binding.name)
        print("Address:", port.binding.options.get("address"))

# crear message (si map_invoice produce dict compatible puedes usar create_message)
# ejemplo: suponiendo operacion SuministroLR y tipo de entrada 'suministro' 
service = client.create_service('{http://www2.agenciatributaria.gob.es/}SuministroInformacionPort', 'https://prewww1.aeat.es/.../ServiceEndpoint')
# payload must match WSDL/XSD structure; build dict or lxml Element
payload = {
    # rellena con la estructura exacta del XSD
}
response = service.SuministroLR(payload)
print(response)
