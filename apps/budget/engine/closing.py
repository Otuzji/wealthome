"""El cierre del mes y el arrastre del saldo (§4.4)."""

from dataclasses import dataclass
from decimal import Decimal

from .money import centavos

INGRESO = "income"
GASTO = "expense"


@dataclass(frozen=True)
class Renglon:
    categoria_id: int
    kind: str
    presupuestado: Decimal
    real: Decimal


@dataclass(frozen=True)
class Cierre:
    ingresos_presupuestados: Decimal
    ingresos_reales: Decimal
    egresos_presupuestados: Decimal
    egresos_reales: Decimal
    varianza_por_categoria: dict
    balance: Decimal
    arrastre: Decimal


def _total(renglones, kind, campo):
    return centavos(sum(getattr(r, campo) for r in renglones if r.kind == kind))


def cerrar(renglones, saldo_arrastrado):
    """La foto congelada de un mes.

    §4.4: balance = saldo arrastrado + ingresos reales − egresos reales, y ese
    balance es el arrastre del mes siguiente. El déficit se arrastra igual que
    el superávit: ocultarlo haría que un mes malo desapareciera del historial.
    """
    renglones = list(renglones)

    ingresos_reales = _total(renglones, INGRESO, "real")
    egresos_reales = _total(renglones, GASTO, "real")

    varianza = {}
    for renglon in renglones:
        acumulado = varianza.get(renglon.categoria_id, Decimal("0"))
        varianza[renglon.categoria_id] = acumulado + (renglon.real - renglon.presupuestado)
    varianza = {cat: centavos(v) for cat, v in varianza.items()}

    balance = centavos(centavos(saldo_arrastrado) + ingresos_reales - egresos_reales)

    return Cierre(
        ingresos_presupuestados=_total(renglones, INGRESO, "presupuestado"),
        ingresos_reales=ingresos_reales,
        egresos_presupuestados=_total(renglones, GASTO, "presupuestado"),
        egresos_reales=egresos_reales,
        varianza_por_categoria=varianza,
        balance=balance,
        arrastre=balance,
    )
