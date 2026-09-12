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
CONSULTAS_MES = 17
CONSULTAS_METAS = 10


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
        respuesta = client.get(reverse("budget:mes", args=[mes.year, mes.month]))
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
        respuesta = client.get(reverse("budget:metas"))
    assert respuesta.status_code == 200
