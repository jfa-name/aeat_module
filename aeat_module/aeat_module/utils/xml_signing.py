# -*- coding: utf-8 -*-
"""
Firma XML (enveloped signature, XMLDSig) para los registros VERI*FACTU,
usando el paquete puro-Python `signxml` (backend `cryptography`).

Nota de diseño: las herramientas exploratorias de `scripts/` usaban
`python-xmlsec` (binding a libxmlsec1), pero requiere las cabeceras de
desarrollo del sistema (`libxmlsec1-dev`), que no están instalables sin
`sudo` en este entorno. `signxml` produce una firma XMLDSig enveloped
equivalente (RSA-SHA256, C14N) sin dependencias de sistema adicionales,
por lo que se adopta como implementación principal.
"""
from lxml import etree
from signxml import XMLSigner, methods, DigestAlgorithm

NSMAP_DS = {"ds": "http://www.w3.org/2000/09/xmldsig#"}


def sign_registro(root_element, target_id: str, private_key_pem: bytes, cert_pem: bytes) -> etree._Element:
    """Firma (enveloped) el elemento con atributo Id=target_id dentro de
    `root_element` (p.ej. RegistroAlta/RegistroAnulacion) y añade el nodo
    <ds:Signature> como último hijo de ese mismo elemento, tal y como
    exige el esquema de la AEAT.

    Devuelve el árbol raíz (mismo objeto `root_element` recibido) ya firmado.
    """
    target = root_element.find(f'.//*[@Id="{target_id}"]')
    if target is None:
        # el propio root_element es el nodo a firmar
        if root_element.get("Id") == target_id:
            target = root_element
        else:
            raise ValueError(f"No se encontró el elemento con Id='{target_id}' a firmar")

    # Placeholder de la firma dentro del nodo a firmar (enveloped)
    placeholder = etree.SubElement(target, "{http://www.w3.org/2000/09/xmldsig#}Signature", nsmap=NSMAP_DS)
    placeholder.set("Id", "placeholder")

    signer = XMLSigner(
        method=methods.enveloped,
        signature_algorithm="rsa-sha256",
        digest_algorithm=DigestAlgorithm.SHA256,
        c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#",
    )
    signed_root = signer.sign(
        root_element,
        key=private_key_pem,
        cert=cert_pem,
        reference_uri=f"#{target_id}",
        id_attribute="Id",
    )
    return signed_root
