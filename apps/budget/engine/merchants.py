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
# Ligaduras francesas que NFKD no descompone
_LIGADURAS = {"Œ": "OE", "œ": "OE", "Æ": "AE", "æ": "AE"}


def normalizar(nombre):
    if not nombre or not nombre.strip():
        return ""
    # Sustituye ligaduras antes de NFKD
    sin_ligaduras = nombre
    for ligadura, reemplazo in _LIGADURAS.items():
        sin_ligaduras = sin_ligaduras.replace(ligadura, reemplazo)
    # Quita acentos
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", sin_ligaduras) if not unicodedata.combining(c)
    )
    # Quita sucursales
    sin_sucursal = _SUCURSAL.sub(" ", sin_acentos.upper())
    # Quita no-alfanuméricos y colapsa espacios
    resultado = _NO_ALFANUMERICO.sub(" ", sin_sucursal).strip()
    # Si la normalización lo deja vacío, cae atrás a mayúsculas con espacios
    # colapsados, pero solo si no era originalmente vacío
    if resultado:
        return resultado
    # Cae atrás al nombre original en mayúsculas con espacios colapsados
    return " ".join(nombre.upper().split())
