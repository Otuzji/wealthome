"""Las dos formas de expresar una meta (§3.3).

Son la misma cosa vista al revés: el usuario da dos datos y la aplicación
deriva el tercero. Ambas formas deben existir, porque las familias piensan de
las dos maneras.
"""

import calendar
from datetime import date
from decimal import ROUND_CEILING, Decimal

from .money import DOS_DECIMALES, centavos

BY_TARGET_DATE = "by_target_date"
BY_MONTHLY_AMOUNT = "by_monthly_amount"
# El fondo abierto: sin objetivo ni fecha, solo un saldo al que se abona. No
# hay tercer dato que derivar; el aporte es el que el usuario fijo, si fijo.
OPEN_FUND = "open_fund"
MODOS_DE_META = (BY_TARGET_DATE, BY_MONTHLY_AMOUNT, OPEN_FUND)


def _meses_hasta(desde, hasta):
    """Cuántos aportes llegan EN o ANTES de la fecha target.

    Itera a través de las contribuciones clampeando el día: Feb 31 se vuelve
    Feb 28. Solo cuenta las contribuciones que llegan en o antes del target.
    """
    meses = 0
    while _sumar_meses(desde, meses) <= hasta:
        meses += 1
    # Garantiza al menos una contribución, incluso si el target es muy corto
    return max(meses, 1)


def _sumar_meses(origen, meses):
    total = origen.month - 1 + meses
    anio = origen.year + total // 12
    mes = total % 12 + 1
    return date(anio, mes, min(origen.day, calendar.monthrange(anio, mes)[1]))


def derivar(modo, objetivo, acumulado, desde, fecha_objetivo=None, aporte_mensual=None):
    """Devuelve (aporte mensual, fecha de llegada).

    El tercer dato nunca se guarda: se deriva al mostrarlo, o quedaría
    obsoleto en cuanto cambie el acumulado.
    """
    if modo not in MODOS_DE_META:
        raise ValueError(f"Modo de meta desconocido: {modo!r}")

    if modo == OPEN_FUND:
        aporte = centavos(aporte_mensual) if aporte_mensual else Decimal("0.00")
        return aporte, None

    falta = centavos(objetivo) - centavos(acumulado)
    if falta <= 0:
        return Decimal("0.00"), desde

    if modo == BY_TARGET_DATE:
        if fecha_objetivo is None:
            raise ValueError("Una meta by_target_date necesita `fecha_objetivo`.")
        if fecha_objetivo < desde:
            # No se divide entre cero meses ni se inventa un plazo: lo que
            # falta se pide ahora, que es la verdad.
            return falta, fecha_objetivo
        meses = _meses_hasta(desde, fecha_objetivo)
        # Hacia arriba: 333,33 tres veces deja un centavo sin ahorrar y la
        # meta no se alcanza en su fecha.
        aporte = (falta / meses).quantize(DOS_DECIMALES, rounding=ROUND_CEILING)
        return aporte, fecha_objetivo

    if modo == BY_MONTHLY_AMOUNT:
        if not aporte_mensual or centavos(aporte_mensual) <= 0:
            raise ValueError("Una meta by_monthly_amount necesita un aporte positivo.")
        aporte = centavos(aporte_mensual)
        meses = int((falta / aporte).to_integral_value(rounding=ROUND_CEILING))
        return aporte, _sumar_meses(desde, meses - 1)
