# -*- coding: utf-8 -*-
"""
Transport de zeep que resuelve WSDL/XSD localmente (docs/*.sanitized...),
para poder cargar el esquema de VERI*FACTU sin depender de la disponibilidad
de red hacia los servidores de la AEAT. Portado y simplificado desde el
prototipo exploratorio `scripts/sign_and_send.py` (rama fix/sf-wsdl-local-xsd).
"""
import re
from pathlib import Path

from zeep.transports import Transport


class LocalWsdlTransport(Transport):
    """Intercepta las peticiones de zeep para cargar WSDL/XSD por nombre de
    fichero desde un directorio local, en vez de resolver la URL remota
    original embebida en los documentos (p.ej. agenciatributaria.gob.es)."""

    def __init__(self, docs_dir, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.docs_dir = Path(docs_dir)
        # Placeholder literal "$XSD_SAN" dejado en PreSuministroInformacion.xsd/
        # SuministroInformacion.xsd (rama fix/sf-wsdl-local-xsd) apuntando al
        # schema xmldsig saneado; no es una URL real, hay que interceptarlo.
        self.xsd_san_path = self.docs_dir / "xmldsig-core-schema.xsd.sanitized"

    def _collapse_file_scheme(self, s: str) -> str:
        collapsed = re.sub(r"(file:/*)+", "file:///", s)
        return re.sub(r"file://+", "file:///", collapsed)

    def _find_local_by_basename(self, basename: str):
        cand = self.docs_dir / basename
        if cand.exists():
            return cand.resolve()
        for f in self.docs_dir.iterdir():
            if f.is_file() and f.name.endswith(basename):
                return f.resolve()
        return None

    def load(self, url):
        url_str = self._collapse_file_scheme(str(url))

        if ("XSD_SAN" in url_str) and self.xsd_san_path.exists():
            return self.xsd_san_path.read_bytes()

        if url_str.startswith("file://"):
            basename = Path(url_str.replace("file://", "", 1)).name
        else:
            basename = Path(url_str).name

        local = self._find_local_by_basename(basename)
        if local:
            return local.read_bytes()

        # Fallback: comportamiento estándar de zeep (red / file:// directo)
        return super().load(url)
