"""`reabrir_mes`: deshacer un cierre hecho con la regla vieja para volver a
cerrarlo con el reparto decidido."""

from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from apps.budget import services
from apps.budget.models import (
    AllowanceLedger, GoalContribution, MonthlyAllocation, MonthlyClose,
)
from tests.budget.test_cierre_con_reparto import octubre  # noqa: F401

pytestmark = pytest.mark.django_db


def _cerrado_a_la_antigua(hogar, mes, otto):
    """Un cierre con lo que dejaba la regla vieja: aporte a la meta y un ajuste
    negativo en la mesada del mes siguiente."""
    services.cerrar_mes(mes)
    noviembre = services._fila_del_mes_siguiente(mes)
    libro = services.mesada_de_por_id(hogar, otto.pk, noviembre)
    libro.adjustment = Decimal("-335.49")
    libro.save(update_fields=["adjustment"])
    return libro


def test_sin_aplicar_no_toca_nada(octubre):
    _admin, hogar, mes, _meta, otto, _diana = octubre
    _cerrado_a_la_antigua(hogar, mes, otto)

    call_command("reabrir_mes", hogar=hogar.pk, anio=2026, mes=10)

    mes.refresh_from_db()
    assert mes.esta_cerrado
    assert MonthlyClose.objects.for_household(hogar).exists()


def test_reabre_y_deshace_lo_que_escribio_el_cierre(octubre):
    _admin, hogar, mes, meta, otto, _diana = octubre
    libro = _cerrado_a_la_antigua(hogar, mes, otto)

    call_command("reabrir_mes", hogar=hogar.pk, anio=2026, mes=10,
                 saldo_inicial="0", aplicar=True)

    mes.refresh_from_db()
    libro.refresh_from_db()
    assert not mes.esta_cerrado and mes.closed_at is None
    assert mes.opening_balance == Decimal("0.00")
    assert not MonthlyClose.objects.for_household(hogar).exists()
    assert not GoalContribution.objects.for_household(hogar).filter(goal=meta).exists()
    assert libro.adjustment == Decimal("0.00")
    assert all(r.actual_amount is None
               for r in MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes))

    # Y se vuelve a cerrar con la regla nueva.
    cierre = services.cerrar_mes(mes)
    assert cierre.balance == Decimal("1774.10")


def test_no_reabre_si_hay_un_mes_posterior_cerrado(octubre):
    _admin, hogar, mes, _meta, otto, _diana = octubre
    _cerrado_a_la_antigua(hogar, mes, otto)
    services.cerrar_mes(services._fila_del_mes_siguiente(mes))

    with pytest.raises(CommandError):
        call_command("reabrir_mes", hogar=hogar.pk, anio=2026, mes=10, aplicar=True)
