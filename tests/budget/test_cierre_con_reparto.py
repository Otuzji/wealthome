"""Cerrar es decidir el reparto.

El cierre ensena lo que hay (saldo de partida + ingresos - gastos del hogar),
propone el reparto de las reglas sobre lo real y deja cambiar cada importe. Lo
repartido sale (a la meta, a las mesadas) y lo que queda pasa al mes siguiente
como arrastre: el balance ya no cuenta dos veces el mismo dinero, y la mesada
decidida sustituye a la planeada sin ajuste al mes siguiente.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget import services
from apps.budget.engine.cascade import ALLOWANCE, FIXED, GOAL, REMAINDER, Asignacion
from apps.budget.models import (
    AllowanceLedger, BudgetMonth, GoalContribution, MonthlyAllocation, MonthlyClose,
)
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    AllocationRuleFactory, BudgetLineFactory, BudgetMonthFactory, CategoryFactory,
    GoalFactory, TransactionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def octubre(monkeypatch):
    """El octubre del piloto: 9,260.61 de ingreso, 7,486.51 gastados, una
    linea de 150 pagada a medias (quedan 100 sin pagar), y las reglas de la
    casa: 500 a la meta y el resto a la mesada de los dos."""
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: date(2026, 11, 1))
    admin = UserFactory(display_name="Otto")
    hogar = crear_hogar(admin, "Family Thompson", family_size=2)
    otto = hogar.active_memberships().get(user=admin)
    diana = MembershipFactory(household=hogar, user=UserFactory(display_name="Diana"))
    meta = GoalFactory(household=hogar, name="Fondo", target_amount=Decimal("100000.00"))
    AllocationRuleFactory(household=hogar, order=1, target_type=GOAL, target_goal=meta,
                          method=FIXED, amount=Decimal("500.00"))
    AllocationRuleFactory(household=hogar, order=2, target_type=ALLOWANCE, method=REMAINDER)

    mes = BudgetMonthFactory(household=hogar, year=2026, month=10)
    entra = CategoryFactory(household=hogar, slug="sueldo-x", kind="income")
    sale = CategoryFactory(household=hogar, slug="casa-x", kind="expense")
    BudgetLineFactory(household=hogar, budget_month=mes, category=entra, kind="income",
                      planned_amount=Decimal("9260.61"))
    parcial = BudgetLineFactory(household=hogar, budget_month=mes, category=sale,
                                kind="expense", planned_amount=Decimal("150.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=entra, member=otto,
                       amount=Decimal("9260.61"), date=date(2026, 10, 15))
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("50.00"), date=date(2026, 10, 20), budget_line=parcial)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=otto,
                       amount=Decimal("7436.51"), date=date(2026, 10, 20))
    # Lo planeado al empezar el mes, que el cierre va a sustituir.
    services.planificar_mes(hogar, mes, Decimal("2109.59"))
    return admin, hogar, mes, meta, otto, diana


def test_lo_disponible_suma_el_saldo_inicial_y_ensena_lo_no_pagado(octubre):
    _admin, _hogar, mes, *_ = octubre
    mes.opening_balance = Decimal("0.00")
    mes.save(update_fields=["opening_balance"])

    cifras = services.disponible_al_cierre(mes)

    assert cifras["ingresos"] == Decimal("9260.61")
    assert cifras["egresos"] == Decimal("7486.51")
    assert cifras["disponible"] == Decimal("1774.10")
    assert cifras["sin_pagar"] == Decimal("100.00")


def test_el_saldo_inicial_anotado_manda_sobre_el_arrastre_previo(octubre):
    _admin, hogar, mes, *_ = octubre
    septiembre = BudgetMonthFactory(household=hogar, year=2026, month=9)
    services.cerrar_mes(septiembre)   # sin movimientos: arrastre 0
    mes.opening_balance = Decimal("25.00")
    mes.save(update_fields=["opening_balance"])

    assert services.disponible_al_cierre(mes)["disponible"] == Decimal("1799.10")


def test_cerrar_con_el_reparto_decidido(octubre):
    """600 de mesada en vez de 1,274.10: el resto pasa a noviembre."""
    _admin, hogar, mes, meta, otto, diana = octubre
    reparto = [Asignacion(1, Decimal("500.00")),
               Asignacion(2, Decimal("300.00"), otto.pk),
               Asignacion(2, Decimal("300.00"), diana.pk)]

    cierre = services.cerrar_mes(mes, reparto)

    assert cierre.balance == Decimal("1774.10")
    assert cierre.arrastre == Decimal("674.10")
    aporte = GoalContribution.objects.for_household(hogar).get(goal=meta)
    assert aporte.amount == Decimal("500.00")
    libros = AllowanceLedger.objects.for_household(hogar).filter(budget_month=mes)
    assert sorted(l.granted for l in libros) == [Decimal("300.00"), Decimal("300.00")]
    # Ni ajuste ni fila de noviembre: lo que no se repartio va en el arrastre.
    assert not AllowanceLedger.objects.for_household(hogar).filter(
        budget_month__month=11).exists()
    reales = MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes)
    assert sum(r.actual_amount for r in reales) == Decimal("1100.00")


def test_el_cierre_automatico_reparte_lo_real_con_tope(octubre):
    _admin, hogar, mes, *_ = octubre

    cierre = services.cerrar_mes(mes)

    # 500 a la meta y 1,274.10 de mesada: nada pasa, nada se cuenta dos veces.
    assert cierre.arrastre == Decimal("0.00")
    libros = AllowanceLedger.objects.for_household(hogar).filter(budget_month=mes)
    assert sum(l.granted for l in libros) == Decimal("1274.10")


def test_no_se_reparte_mas_de_lo_que_hay(octubre):
    _admin, hogar, mes, *_ = octubre

    with pytest.raises(services.RepartoExcesivo):
        services.cerrar_mes(mes, [Asignacion(1, Decimal("2000.00"))])

    mes.refresh_from_db()
    assert not mes.esta_cerrado
    assert not MonthlyClose.objects.for_household(hogar).exists()


def test_el_arrastre_es_el_saldo_inicial_que_se_sugiere_en_noviembre(octubre):
    _admin, hogar, mes, _meta, otto, diana = octubre
    services.cerrar_mes(mes, [Asignacion(1, Decimal("500.00")),
                              Asignacion(2, Decimal("300.00"), otto.pk),
                              Asignacion(2, Decimal("300.00"), diana.pk)])
    from apps.budget import services_overview

    noviembre = services.obtener_mes(hogar, 2026, 11, date(2026, 11, 1))

    assert services_overview.sugerencia_saldo_inicial(noviembre) == Decimal("674.10")


# --- la pantalla -------------------------------------------------------------


def _url(mes):
    return reverse("budget:cerrar_mes", args=["household", mes.year, mes.month])


def test_la_pantalla_ensena_lo_que_hay_y_propone_el_reparto(client, octubre):
    admin, _hogar, mes, _meta, otto, diana = octubre
    client.force_login(admin)

    r = client.get(_url(mes))

    html = r.content.decode()
    assert r.status_code == 200
    assert "To split" in html and "1,774.10" in html
    assert "planned but not paid" in html and "$100.00" in html
    form = r.context["form"]
    assert form.fields["r1_0"].initial == Decimal("500.00")
    assert form.fields[f"r2_{otto.pk}"].initial == Decimal("637.05")
    assert form.fields[f"r2_{diana.pk}"].initial == Decimal("637.05")
    assert r.context["queda"] == Decimal("0.00")


def test_cerrar_desde_la_pantalla_con_otra_mesada(client, octubre):
    admin, hogar, mes, _meta, otto, diana = octubre
    client.force_login(admin)

    r = client.post(_url(mes), {"r1_0": "500.00", f"r2_{otto.pk}": "300.00",
                                f"r2_{diana.pk}": "300.00"})

    assert r.status_code == 302
    cierre = MonthlyClose.objects.for_household(hogar).get()
    assert cierre.arrastre == Decimal("674.10")


def test_la_pantalla_no_deja_repartir_de_mas(client, octubre):
    admin, hogar, mes, _meta, otto, diana = octubre
    client.force_login(admin)

    r = client.post(_url(mes), {"r1_0": "500.00", f"r2_{otto.pk}": "1000.00",
                                f"r2_{diana.pk}": "1000.00"})

    assert r.status_code == 200
    assert "You cannot split more than there is." in r.content.decode()
    assert BudgetMonth.objects.for_household(hogar).get(pk=mes.pk).status == "open"


def test_el_summary_ensena_lo_que_paso_al_mes_siguiente(client, octubre):
    admin, _hogar, mes, _meta, otto, diana = octubre
    services.cerrar_mes(mes, [Asignacion(1, Decimal("500.00")),
                              Asignacion(2, Decimal("300.00"), otto.pk),
                              Asignacion(2, Decimal("300.00"), diana.pk)])
    client.force_login(admin)

    html = client.get(reverse("budget:summary", args=["household"])).content.decode()

    assert "Carried over" in html and "674.10" in html
