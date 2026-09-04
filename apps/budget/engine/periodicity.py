"""Cuándo dispara una regla dentro de un mes concreto.

Decisión §2.2 del diseño del Plan 2: calendario real, no prorrateo. El
presupuesto tiene que predecir CUÁNDO sale el dinero, o el §4.4 —balance real
contra presupuestado— no significa nada.

Los valores de las periodicidades están en inglés como el resto del esquema.
Sus etiquetas traducibles viven en apps/budget/models/rules.py: este módulo no
importa django.utils, igual que no importa el ORM.
"""

import calendar
from datetime import date, timedelta

from .money import centavos

WEEKLY = "weekly"
BIWEEKLY = "biweekly"
SEMIMONTHLY = "semimonthly"
MONTHLY = "monthly"
BIMONTHLY = "bimonthly"
QUARTERLY = "quarterly"
SEMIANNUAL = "semiannual"
ANNUAL = "annual"

PERIODICIDADES = (
    WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY,
    BIMONTHLY, QUARTERLY, SEMIANNUAL, ANNUAL,
)

# Cada cuántos meses dispara una periodicidad de las que caen en su día del mes.
CADA_N_MESES = {
    MONTHLY: 1,
    BIMONTHLY: 2,
    QUARTERLY: 3,
    SEMIANNUAL: 6,
    ANNUAL: 12,
}

DIAS_ENTRE = {WEEKLY: 7, BIWEEKLY: 14}


def _dia_del_mes(anio, mes, dia):
    """El día pedido, recortado al último del mes si no existe.

    Una regla anclada el 31 dispara el 28 en febrero: nunca se salta un mes,
    porque el alquiler de febrero se paga en febrero.
    """
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(dia, ultimo))


def _dentro_de_vigencia(dia, ancla, hasta):
    return dia >= ancla and (hasta is None or dia <= hasta)


def ocurrencias(periodicidad, ancla, anio, mes, hasta=None):
    """Las fechas en que la regla dispara dentro de ese mes.

    `ancla` es effective_from y `hasta` es effective_to, que corta.
    """
    if periodicidad in DIAS_ENTRE:
        paso = timedelta(days=DIAS_ENTRE[periodicidad])
        primero = date(anio, mes, 1)
        ultimo = _dia_del_mes(anio, mes, 31)
        # Avanza desde el ancla en saltos del tamaño del paso.
        dia = ancla
        if dia < primero:
            saltos = (primero - dia).days // paso.days
            dia = dia + paso * saltos
            while dia < primero:
                dia += paso
        encontradas = []
        while dia <= ultimo:
            if _dentro_de_vigencia(dia, ancla, hasta):
                encontradas.append(dia)
            dia += paso
        return encontradas

    if periodicidad == SEMIMONTHLY:
        candidatas = [
            _dia_del_mes(anio, mes, ancla.day),
            _dia_del_mes(anio, mes, ancla.day + 15),
        ]
        # Un ancla el 16 daría 31 y 31: dos veces el mismo día no son dos pagos.
        vistas = []
        for dia in candidatas:
            if dia not in vistas and _dentro_de_vigencia(dia, ancla, hasta):
                vistas.append(dia)
        return vistas

    if periodicidad in CADA_N_MESES:
        distancia = (anio - ancla.year) * 12 + (mes - ancla.month)
        if distancia < 0 or distancia % CADA_N_MESES[periodicidad] != 0:
            return []
        dia = _dia_del_mes(anio, mes, ancla.day)
        return [dia] if _dentro_de_vigencia(dia, ancla, hasta) else []

    raise ValueError(f"Periodicidad desconocida: {periodicidad!r}")


def importe_del_mes(importe, periodicidad, ancla, anio, mes, hasta=None):
    """Lo que esa regla presupuesta para ese mes: importe x ocurrencias."""
    veces = len(ocurrencias(periodicidad, ancla, anio, mes, hasta))
    return centavos(importe * veces)
