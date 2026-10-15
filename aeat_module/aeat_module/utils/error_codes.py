# -*- coding: utf-8 -*-
"""
Mapeo de códigos de error/estado de VERI*FACTU, parseados de
`docs/Lista_codigos_de_error.md` (idéntico a
`AEAT Documentation/errores.properties.md`).

El fichero se organiza en secciones delimitadas por cabeceras
"********* Listado de códigos ... *********", que determinan el
"scope" del código:
  - "rechazo del envío completo"  -> scope="envio"       (afecta a todo el lote)
  - "rechazo de la factura"       -> scope="factura"      (solo ese registro)
  - "aceptación ... subsanados"   -> scope="aceptado_con_errores"
"""
import re
from functools import lru_cache

import frappe

_SECTION_SCOPE_KEYWORDS = [
    ("rechazo del envío completo", "envio"),
    ("rechazo de la factura", "factura"),
    ("aceptación", "aceptado_con_errores"),
]

# Códigos de la sección "envio" que son de naturaleza técnica/transitoria
# (caídas puntuales de servicio, BBDD, etc.) y por tanto reintentables.
# El resto de códigos son errores de validación de datos: reenviar el mismo
# XML no cambiará el resultado -> no reintentable.
_RETRYABLE_KEYWORDS = ("error técnico", "servicio no activo")


def _doc_path():
    # frappe.get_app_path() minúscula ("scrub") cualquier *joins que se le
    # pasen (salvo "public"), así que unimos la ruta nosotros mismos para
    # preservar el nombre real del fichero (Lista_codigos_de_error.md).
    import os
    return os.path.join(frappe.get_app_path("aeat_module"), "..", "docs", "Lista_codigos_de_error.md")


def _classify_scope(section_title: str) -> str:
    title = section_title.lower()
    for keyword, scope in _SECTION_SCOPE_KEYWORDS:
        if keyword in title:
            return scope
    return "desconocido"


@lru_cache(maxsize=1)
def _load_error_map() -> dict:
    path = _doc_path()
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return {}

    error_map = {}
    scope = "desconocido"
    line_re = re.compile(r"^\s*(\d{3,4})\s*=\s*(.+?)\s*$")
    for line in text.splitlines():
        if line.strip().startswith("*"):
            scope = _classify_scope(line)
            continue
        m = line_re.match(line)
        if not m:
            continue
        code, description = m.group(1), m.group(2)
        retryable = scope == "envio" and any(k in description.lower() for k in _RETRYABLE_KEYWORDS)
        error_map[code] = {"description": description, "scope": scope, "retryable": retryable}
    return error_map


def classify(code) -> dict:
    """Devuelve {"description", "scope", "retryable"} para un código AEAT.
    Códigos desconocidos se consideran no reintentables por seguridad."""
    code = str(code)
    info = _load_error_map().get(code)
    if info:
        return dict(info)
    return {"description": None, "scope": "desconocido", "retryable": False}


def classify_many(codes) -> list:
    return [dict(classify(c), code=str(c)) for c in codes]


def any_retryable(codes) -> bool:
    return any(classify(c)["retryable"] for c in codes)
