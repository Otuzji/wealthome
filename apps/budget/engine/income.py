"""Los cinco modos de ingreso variable del §4.1.

La regla que gobierna todo el motor: el presupuesto siempre usa la cifra
conservadora. Un hogar que presupuesta el mejor mes de un ingreso variable se
endeuda en el peor. El optimismo va en la proyección; nunca en el plan.
"""

from decimal import Decimal

from .money import centavos

FIXED = "fixed"
ESTIMATED = "estimated"
RANGE = "range"
ROLLING_AVERAGE = "rolling_average"
IRREGULAR = "irregular"

MODOS = (FIXED, ESTIMATED, RANGE, ROLLING_AVERAGE, IRREGULAR)

MESES_DE_LA_MEDIA = 6
MESES_MINIMOS_PARA_MEDIA = 3


def cifra_conservadora(amount_type, *, amount=None, amount_min=None,
                       amount_max=None, historial=()):
    """Lo que este ingreso presupuesta para un mes.

    Devuelve None solo en `rolling_average` sin historia suficiente: significa
    "aún no hay datos", y la interfaz lo dice con todas sus letras en vez de
    inventar un número.
    """
    if amount_type in (FIXED, ESTIMATED):
        if amount is None:
            raise ValueError(f"Un ingreso {amount_type} necesita `amount`.")
        return centavos(amount)

    if amount_type == RANGE:
        if amount_min is None:
            raise ValueError("Un ingreso `range` necesita `amount_min`.")
        # El mínimo, no el promedio y desde luego no el máximo: lo que exceda
        # aparece como superávit al cierre.
        return centavos(amount_min)

    if amount_type == IRREGULAR:
        return centavos(0)

    if amount_type == ROLLING_AVERAGE:
        meses = list(historial)[-MESES_DE_LA_MEDIA:]
        if len(meses) < MESES_MINIMOS_PARA_MEDIA:
            return None
        return centavos(sum(meses) / Decimal(len(meses)))

    raise ValueError(f"Modo de ingreso desconocido: {amount_type!r}")
