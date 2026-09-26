"""Mover al mes siguiente un gasto que no estaba planificado.

Solo eso: un gasto registrado como "Something not planned" cuya partida
puntual sigue siendo suya. Lo planificado —los ingresos y los gastos del
plan— no se mueve: eso se corrige en Plan the month, que edita el mes entero.

El mes siguiente se materializa si el hogar no habia llegado a el, como ya
hace el asistente de planificacion.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.budget import services, services_posponer
from apps.budget.models import BudgetLine, BudgetMonth, MesCerrado, Transaction
from tests.budget.test_registrar_contra_el_plan import hogar_con_plan  # noqa: F401
from tests.factories_budget import BudgetLineFactory, CategoryFactory, TransactionFactory

pytestmark = pytest.mark.django_db


def _mes_siguiente_de(mes):
    anio, numero = services.mes_siguiente(mes.year, mes.month)
    return BudgetMonth.objects.for_household(mes.household).filter(year=anio, month=numero).first()


def _miembro(hogar):
    return hogar.active_memberships().first()


def _registro(hogar, mes, **extra):
    datos = dict(household=hogar, budget_month=mes, member=_miembro(hogar),
                 amount=Decimal("38.20"), date=timezone.localdate())
    datos.update(extra)
    return TransactionFactory(**datos)


def _gasto_suelto(hogar, mes, amount=Decimal("38.20"), kind="expense", slug="farmacia"):
    """Lo que deja "Something not planned": el registro y su partida puntual
    ya pagada, que es solo suya."""
    categoria = CategoryFactory(household=hogar, slug=slug, kind=kind)
    puntual = BudgetLineFactory(household=hogar, budget_month=mes, is_exceptional=True,
                                category=categoria, kind=kind, note="Antibiotico",
                                planned_amount=amount)
    return _registro(hogar, mes, budget_line=puntual, category=categoria, amount=amount)


# --- que se puede mover -----------------------------------------------------


def test_un_gasto_no_planeado_se_puede_mover(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan

    assert _gasto_suelto(hogar, mes).se_puede_posponer is True


def test_un_pago_contra_el_plan_no_se_puede_mover(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    alquiler = mes.lineas.get(kind="expense")
    tx = _registro(hogar, mes, budget_line=alquiler, category=alquiler.category,
                   amount=Decimal("1750.00"))

    assert tx.se_puede_posponer is False


def test_un_ingreso_suelto_no_se_puede_mover(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan

    extra = _gasto_suelto(hogar, mes, kind="income", slug="bono")

    assert extra.se_puede_posponer is False


def test_una_puntual_con_otro_pago_no_se_puede_mover(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    tx = _gasto_suelto(hogar, mes, amount=Decimal("20.00"))
    _registro(hogar, mes, budget_line=tx.budget_line, category=tx.category,
              amount=Decimal("18.20"))

    assert tx.se_puede_posponer is False


def test_un_registro_sin_partida_no_se_puede_mover(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    tx = _registro(hogar, mes, category=CategoryFactory(household=hogar, slug="farmacia"))

    assert tx.se_puede_posponer is False


# --- mover ------------------------------------------------------------------


def test_el_registro_y_su_partida_cambian_de_mes(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    hoy = timezone.localdate()
    tx = _gasto_suelto(hogar, mes)
    puntual = tx.budget_line

    services_posponer.posponer_registro(tx)

    tx.refresh_from_db()
    puntual.refresh_from_db()
    siguiente = _mes_siguiente_de(mes)
    assert siguiente is not None and siguiente.status == BudgetMonth.OPEN
    assert tx.budget_month_id == siguiente.pk
    assert tx.date == hoy   # la fecha se conserva: ese dia salio el dinero
    assert puntual.budget_month_id == siguiente.pk
    assert puntual.estado == BudgetLine.PAGADA


def test_el_mes_siguiente_se_materializa_con_sus_propias_reglas(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    tx = _gasto_suelto(hogar, mes)

    services_posponer.posponer_registro(tx)

    siguiente = _mes_siguiente_de(mes)
    assert siguiente.lineas.filter(is_exceptional=False, kind="expense").exists()
    assert siguiente.lineas.filter(is_exceptional=False, kind="income").exists()


def test_lo_planificado_no_se_mueve_ni_abre_el_mes_siguiente(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    alquiler = mes.lineas.get(kind="expense")
    tx = _registro(hogar, mes, budget_line=alquiler, category=alquiler.category,
                   amount=Decimal("1750.00"))

    with pytest.raises(services_posponer.NoEsUnGastoSuelto):
        services_posponer.posponer_registro(tx)

    assert Transaction.objects.for_household(hogar).get(pk=tx.pk).budget_month_id == mes.pk
    assert _mes_siguiente_de(mes) is None


def test_un_registro_de_un_mes_cerrado_no_se_mueve(hogar_con_plan):
    admin, hogar, mes = hogar_con_plan
    tx = _gasto_suelto(hogar, mes)
    mes.status = BudgetMonth.CLOSED
    mes.save(update_fields=["status"])

    with pytest.raises(MesCerrado):
        services_posponer.posponer_registro(tx)

    assert Transaction.objects.for_household(hogar).get(pk=tx.pk).budget_month_id == mes.pk
    assert _mes_siguiente_de(mes) is None
