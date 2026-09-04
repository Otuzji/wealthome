"""El libro mayor de la mesada (§3.3, §4.5.4).

Cada mes es una fila y el saldo se deriva sumando, no un campo que se
sobrescribe. Así "¿por qué tengo $145 este mes?" siempre tiene respuesta.
"""

from decimal import Decimal

from .money import centavos


def saldo(carried_in, granted, adjustment, spent):
    """Lo que este miembro tiene disponible este mes."""
    return centavos(
        centavos(carried_in) + centavos(granted) + centavos(adjustment) - centavos(spent)
    )


def carried_out(saldo_del_mes, rollover):
    """Lo que viaja al mes siguiente al cerrar.

    §4.5.4: con la acumulación activada (por defecto) el saldo no gastado se
    acumula — guardar $100 durante tres meses para comprar algo de $300 es lo
    que hace que se sienta dinero propio y no una asignación que caduca. Con
    la opción desactivada, lo no gastado vuelve al hogar.

    Un saldo NEGATIVO viaja siempre, con acumulación o sin ella: una deuda no
    se perdona por apagar una opción, o desactivarla sería una forma de gastar
    gratis.
    """
    saldo_del_mes = centavos(saldo_del_mes)
    if saldo_del_mes < 0:
        return saldo_del_mes
    return saldo_del_mes if rollover else Decimal("0.00")
