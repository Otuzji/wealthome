"""El reparto en cascada del sobrante (§4.5).

La función que distingue al producto. Nace de un ritual real: una pareja se
sienta cada mes, estima el ingreso variable, agrega los gastos excepcionales,
y reparte lo que sobra entre el ahorro y una mesada personal para cada uno.
Casi ninguna aplicación de presupuesto lo modela, porque todas asumen que el
sobrante "se queda ahí".
"""

from dataclasses import dataclass
from decimal import Decimal

from .money import centavos, repartir_proporcional

GOAL = "goal"
ALLOWANCE = "allowance"
CATEGORY = "category"
DESTINOS = (GOAL, ALLOWANCE, CATEGORY)

FIXED = "fixed"
PERCENTAGE = "percentage"
REMAINDER = "remainder"
METODOS = (FIXED, PERCENTAGE, REMAINDER)


@dataclass(frozen=True)
class ReglaReparto:
    orden: int
    destino: str
    metodo: str
    importe: Decimal | None = None
    porcentaje: Decimal | None = None
    destino_id: int | None = None
    miembros: tuple = ()
    pesos: tuple | None = None


@dataclass(frozen=True)
class Asignacion:
    orden: int
    importe: Decimal
    miembro_id: int | None = None


def _bruto(regla, sobrante, disponible):
    if regla.metodo == FIXED:
        return regla.importe or Decimal("0")
    if regla.metodo == PERCENTAGE:
        return sobrante * (regla.porcentaje or Decimal("0"))
    if regla.metodo == REMAINDER:
        return disponible
    raise ValueError(f"Método de reparto desconocido: {regla.metodo!r}")


def _asignaciones_de(regla, importe):
    """Una asignación, o una por miembro si el destino es la mesada."""
    if regla.destino != ALLOWANCE:
        return [Asignacion(regla.orden, importe, None)]

    if not regla.miembros:
        return []
    pesos = regla.pesos or tuple(Decimal("1") for _ in regla.miembros)
    partes = repartir_proporcional(importe, pesos)
    return [
        Asignacion(regla.orden, parte, miembro)
        for miembro, parte in zip(regla.miembros, partes)
    ]


def repartir(sobrante, reglas):
    """Cómo cae el sobrante por las reglas, ordenadas por prioridad.

    La suma nunca excede el sobrante. Lo que las reglas no agoten se queda sin
    asignar a propósito y se arrastra en el balance (§2.7).
    """
    sobrante = centavos(sobrante)
    if sobrante <= 0:
        return []

    disponible = sobrante
    asignaciones = []

    for regla in sorted(reglas, key=lambda r: r.orden):
        if disponible <= 0:
            break
        importe = min(centavos(_bruto(regla, sobrante, disponible)), disponible)
        if importe <= 0:
            continue
        nuevas = _asignaciones_de(regla, importe)
        if not nuevas:
            # Una mesada sin miembros no consume sobrante: cae a la siguiente.
            continue
        asignaciones.extend(nuevas)
        disponible -= importe

    return asignaciones
