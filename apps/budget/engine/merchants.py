"""Normalización de nombres de comercio (§3.3).

Unifica las variantes del MISMO nombre —mayúsculas, acentos, puntuación,
número de sucursal— para que `WALMART #3421` y `walmart` sean el mismo
comercio. Es la base de las consultas tipo "¿cuánto gastamos en Walmart este
año?" que llegan en la Fase 2.

Lo que NO hace, y conviene saberlo: no funde nombres distintos.
"Walmart Supercentre" sigue siendo otro comercio. Fundirlos exige una acción
del usuario, que llega con los reportes de la Fase 2 — el ejemplo del §3.3
promete más de lo que la normalización sola puede dar. Añadir heurísticas de
sufijos aquí fundiría comercios de verdad distintos, que es un error peor.
"""

import re
import unicodedata

_SUCURSAL = re.compile(r"#\s*\d+")
_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]+")


def normalizar(nombre):
    if not nombre:
        return ""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c)
    )
    sin_sucursal = _SUCURSAL.sub(" ", sin_acentos.upper())
    return _NO_ALFANUMERICO.sub(" ", sin_sucursal).strip()
