## Ejemplo de Payload para Alta de Factura, ejecutar en 'bench console'

```python
def normalize_nif(s):
    s = str(s).strip()
    import re
    m = re.match(r'^([A-Za-z])\s*(\d{7,8})$', s)
    if m:
        return m.group(2).zfill(8) + m.group(1).upper()
    s = s.replace(" ", "").upper()
    return s

print("normalize:", normalize_nif("G12345678"), "->", normalize_nif("G12345678"))

payload = {
    "Cabecera": {
        "ObligadoEmision": {
            "NIF": normalize_nif("35429235X"),
            "NombreRazon": "Juan Ejemplo García"
        }
    },
    "RegistroFactura": [
        {
            "RegistroAlta": {
                "IDVersion": "1.1",
                "IDFactura": "F-0001",
                "NombreRazonEmisor": "Juan Ejemplo García",
                "TipoFactura": "01",
                "FechaOperacion": "2025-11-18",
                "ImporteTotal": "100.00",
                "Desglose": {
                    "BaseImponible": "82.64",
                    "CuotaTotal": "17.36"
                },
                "Destinatarios": {
                    "IDDestinatario": [
                        {
                            "NIF": normalize_nif("42059159A"),
                            "NombreRazon": "Flora Hernández García"
                        }
                    ]
                },
                "Lineas": {
                    "Linea": [
                        {
                            "NumeroLinea": 1,
                            "Descripcion": "Servicio X",
                            "Cantidad": "1",
                            "PrecioUnitario": "100.00",
                            "Importe": "100.00"
                        }
                    ]
                }
            }
        }
    ]
}

