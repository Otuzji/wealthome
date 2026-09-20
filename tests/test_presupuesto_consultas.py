"""Presupuestos de consultas.

No prueban comportamiento: prueban que una pantalla no se vuelva cara sin que
nadie se entere. Los numeros son un tope acordado, no una medida sagrada; si
una tarea futura los sube con razon, se suben aqui a proposito y en su commit.
"""

import pytest
from datetime import date
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import (
    BudgetMonthFactory, CategoryFactory, GoalFactory, TransactionFactory,
)

# Historia de estos dos numeros, porque explica por que estan donde estan:
#
# La Tarea 8 subio el del mes de 17 a 18, porque la guardia del §5.2 hizo que
# `obtener_mes` preguntara `hogar.puede_escribir` y eso buscaba la fila de
# Subscription. Quedo apuntado que un select_related en `membresia_actual` la
# dejaria en cero para TODA vista, y se dejo para quien tocara esa funcion.
#
# La Tarea 14 lo hizo necesario: el menu pregunta `puede_escribir` en CADA
# render, asi que la consulta dejo de ser de una pantalla y paso a ser de todas
# — el tope de metas se fue a 11. En vez de subir dos topes se hizo el
# select_related, y ahora la suscripcion viaja con el hogar: el del mes VUELVE
# a 17, y el de metas se queda en 10 con el menu ya contado.
#
# La tarjeta Cash Float (2026-09-19) lo subio de 17 a 21: services.cash_float()
# lee los miembros activos (dos veces: la suya y la de _reglas_del_motor), las
# reglas de reparto y el hogar del mes. Cuatro consultas fijas; ninguna crece
# con las transacciones, que es lo que esta prueba vigila con 50 sembradas.
CONSULTAS_MES = 21
# BAJADO de 10 a 6 en la Tarea 21, y la historia importa porque es un N+1 que
# habia sobrevivido a la tarea que vino a quitar los N+1.
#
# La Tarea 4 fijo este tope en 10 con CINCO metas, y solo comprobo que no creciera
# con las TRANSACCIONES. Con veinte metas eran 26 consultas: Goal.acumulado()
# usaba .aggregate(), que va siempre a la base y no mira el prefetch, o sea una
# consulta por meta. Ahora acumulado() suma en Python cuando las aportaciones
# vienen prefetched, y el numero NO crece con las metas: 6 con cinco y 6 con
# veinte. Medido las dos veces.
#
# SUBIDO de 6 a 8 con la tarjeta nueva: resumen() lee las reglas de reparto
# (para decir que alimenta cada meta) y el mes de hoy (para "This month"), una
# consulta cada una y ninguna crece con las metas. Medido con cinco y con
# veinte: test_resumen_no_hace_una_consulta_por_meta lo vigila.
CONSULTAS_METAS = 8
# El Summary junta los cierres, el reparto de cada mes, lo planeado y lo real
# por categoria y las categorias en cinco consultas agregadas, mas el ahorro:
# el tope no crece ni con los meses cerrados ni con los movimientos. Medido con
# tres meses y cincuenta movimientos por mes.
CONSULTAS_SUMMARY = 10


@pytest.fixture
def hogar_con_movimiento(db):
    # `crear_hogar` (y no `HouseholdFactory()` a secas) porque siembra el
    # árbol de categorías: sin una categoría de ingreso, `obtener_mes`
    # revienta con LookupError en cuanto intenta materializar el mes. Y el
    # mes se ancla a "hoy" (no a una fecha fija) para que `cerrar_vencidos`
    # no encuentre meses atrasados que cerrar en cadena cuando pase el
    # tiempo: eso metería consultas de cierre ajenas al presupuesto que
    # esta prueba vigila.
    hoy = timezone.localdate()
    user = UserFactory()
    hogar = crear_hogar(user, "Hogar de prueba", family_size=4)
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    categoria = CategoryFactory(household=hogar)
    for _i in range(50):
        TransactionFactory(
            household=hogar, budget_month=mes, category=categoria,
            amount=Decimal("10.00"), date=date(hoy.year, hoy.month, 5),
        )
    return hogar, user, mes


@pytest.mark.django_db
def test_la_pantalla_del_mes_no_hace_una_consulta_por_transaccion(
    client, django_assert_num_queries, hogar_con_movimiento
):
    _hogar, user, mes = hogar_con_movimiento
    client.force_login(user)
    with django_assert_num_queries(CONSULTAS_MES):
        respuesta = client.get(reverse("budget:mes", args=["household", mes.year, mes.month]))
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_metas_no_calcula_el_acumulado_dos_veces(
    client, django_assert_num_queries, hogar_con_movimiento
):
    hogar, user, _mes = hogar_con_movimiento
    for _i in range(5):
        GoalFactory(household=hogar)
    client.force_login(user)
    with django_assert_num_queries(CONSULTAS_METAS):
        respuesta = client.get(reverse("budget:metas", args=["household"]))
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_el_summary_no_hace_una_consulta_por_mes_ni_por_movimiento(
    client, django_assert_num_queries, hogar_con_movimiento
):
    from apps.budget.models import BudgetMonth
    from tests.factories_budget import MonthlyCloseFactory

    hogar, user, mes = hogar_con_movimiento
    categoria = CategoryFactory(household=hogar)
    for numero in (1, 2, 3):
        cerrado = BudgetMonthFactory(household=hogar, year=mes.year - 1, month=numero)
        for _i in range(50):
            TransactionFactory(household=hogar, budget_month=cerrado, category=categoria,
                               amount=Decimal("10.00"), date=date(mes.year - 1, numero, 5))
        MonthlyCloseFactory(household=hogar, budget_month=cerrado)
        cerrado.status = BudgetMonth.CLOSED
        cerrado.save(update_fields=["status"])
    client.force_login(user)
    with django_assert_num_queries(CONSULTAS_SUMMARY):
        respuesta = client.get(reverse("budget:summary", args=["household"]))
    assert respuesta.status_code == 200
