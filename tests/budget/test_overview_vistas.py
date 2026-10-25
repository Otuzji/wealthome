"""La pantalla Overview: el mes de un vistazo, solo lectura.

Sus cifras salen de las mismas funciones que This month; aqui se comprueba que
las dos pantallas cuadran, que el ambito personal no filtra lo de otro miembro
y que los casos de borde (sin presupuesto, mes cerrado, hogar sin escritura)
se ensenan sin escribir nada.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget.models import BudgetMonth
from tests.budget.test_cash_float import mes_con_dinero  # noqa: F401
from tests.budget.test_views import _miembro, admin_con_hogar  # noqa: F401
from tests.factories_budget import (
    BudgetLineFactory, BudgetMonthFactory, CategoryFactory, ExpenseRuleFactory,
    IncomeSourceFactory, MonthlyCloseFactory, TransactionFactory,
)

pytestmark = pytest.mark.django_db


def test_el_overview_del_hogar_cuadra_con_this_month(client, mes_con_dinero):
    r = client.get(reverse("budget:overview", args=["household"]))
    m = client.get(reverse("budget:mes", args=["household"]))

    assert r.status_code == 200
    assert r.context["real"] == m.context["totales"]
    assert r.context["forecast"]["ingresos"] == m.context["totales"]["ingresos_esperado"]
    assert r.context["forecast"]["egresos"] == m.context["totales"]["egresos_esperado"]
    assert r.context["alerta"] is not None
    html = r.content.decode()
    assert 'id="overview-alerta"' in html and "No upcoming income planned" in html


def test_sin_presupuesto_invita_a_crearlo(client, admin_con_hogar):
    user, _hogar = admin_con_hogar
    client.force_login(user)

    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.context["sin_presupuesto"] is True
    assert reverse("budget:configurar") in r.content.decode()


def test_sin_presupuesto_y_sin_permiso_pide_al_dueno(client, admin_con_hogar):
    _user, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    assert r.context["sin_presupuesto"] is True
    assert "Ask the household owner to set up the budget." in html
    assert reverse("budget:configurar") not in html


def test_personal_no_tiene_alerta_y_ensena_la_mesada(client, mes_con_dinero):
    r = client.get(reverse("budget:overview", args=["personal"]))

    assert r.context["alerta"] is None and "mesada" in r.context["forecast"]


def test_personal_no_cuenta_lo_de_otro_miembro(client, mes_con_dinero):
    user, hogar, mes, otto, diana = mes_con_dinero
    sale = mes.lineas.filter(kind="expense").first().category
    # Diana: una linea personal de 500 y un gasto personal de 999.
    BudgetLineFactory(household=hogar, budget_month=mes, category=sale, kind="expense",
                      planned_amount=Decimal("500.00"), scope="personal", owner=diana)
    TransactionFactory(household=hogar, budget_month=mes, category=sale, member=diana,
                       scope="personal", amount=Decimal("999.00"), date=timezone.localdate())

    r = client.get(reverse("budget:overview", args=["personal"]))   # sesion de Otto

    assert r.context["real"]["egresos_real"] == Decimal("0.00")
    assert r.context["forecast"]["egresos"] == Decimal("0.00")
    h = client.get(reverse("budget:overview", args=["household"]))
    # Lo del hogar: 500 pagados del alquiler + 500 sueltos, sin los 999 de Diana.
    assert h.context["real"]["egresos_real"] == Decimal("1000.00")


def test_un_exceso_se_ensena_con_su_enlace_al_mes(client, mes_con_dinero):
    _user, hogar, mes, otto, _diana = mes_con_dinero
    cafe = CategoryFactory(household=hogar, slug="cafe", kind="expense")
    linea = BudgetLineFactory(household=hogar, budget_month=mes, category=cafe,
                              kind="expense", planned_amount=Decimal("100.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=cafe, member=otto,
                       amount=Decimal("120.00"), date=timezone.localdate(), budget_line=linea)

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    # El gasto suelto del fixture (500 sin partida) tambien es exceso: lo no
    # planeado cuenta; aqui solo se mira la categoria de la linea.
    assert [d.diferencia for d in r.context["desvios"] if d.categoria == cafe] == [Decimal("20.00")]
    assert "over plan" in html and "$20.00" in html
    assert reverse("budget:mes", args=["household"]) + "?orden=categoria" in html


def test_lo_gastado_de_menos_solo_se_ensena_con_el_mes_cerrado(client, mes_con_dinero):
    _user, hogar, mes, otto, _diana = mes_con_dinero
    cafe = CategoryFactory(household=hogar, slug="cafe-de-menos", kind="expense")
    linea = BudgetLineFactory(household=hogar, budget_month=mes, category=cafe,
                              kind="expense", planned_amount=Decimal("100.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=cafe, member=otto,
                       amount=Decimal("60.00"), date=timezone.localdate(), budget_line=linea)

    abierto = client.get(reverse("budget:overview", args=["household"]))
    BudgetMonth.objects.for_household(hogar).filter(pk=mes.pk).update(status="closed")
    cerrado = client.get(reverse("budget:overview", args=["household"]))

    assert cafe not in [d.categoria for d in abierto.context["desvios"]]
    assert [d.diferencia for d in cerrado.context["desvios"] if d.categoria == cafe] == [Decimal("-40.00")]


def test_un_mes_cerrado_se_ensena_sin_alerta(client, mes_con_dinero):
    _user, hogar, mes, _otto, _diana = mes_con_dinero
    BudgetMonth.objects.for_household(hogar).filter(pk=mes.pk).update(status="closed")

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    assert r.context["cerrado"] is True and r.context["alerta"] is None
    assert "is closed." in html
    anio, numero = (mes.year + 1, 1) if mes.month == 12 else (mes.year, mes.month + 1)
    assert reverse("budget:planificar_mes", args=["household", anio, numero, 1]) in html


def test_un_hogar_sin_escritura_ve_la_proyeccion(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    IncomeSourceFactory(household=hogar, owner=hogar.active_memberships().get(user=user),
                        effective_from=timezone.localdate().replace(day=1))
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.status_code == 200 and r.context["es_proyeccion"] is True
    assert r.context["sin_presupuesto"] is False
    assert r.context["alerta"] is None
    assert r.context["forecast"]["ingresos"] == Decimal("3000.00")
    assert not BudgetMonth.objects.for_household(hogar).exists()


def test_la_proyeccion_del_hogar_no_cuenta_las_reglas_personales_de_otro(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    otto = hogar.active_memberships().get(user=user)
    diana = _miembro(hogar, can_view_budget=True)
    desde = timezone.localdate().replace(day=1)
    IncomeSourceFactory(household=hogar, owner=otto, effective_from=desde)
    ExpenseRuleFactory(household=hogar, amount=Decimal("400.00"), effective_from=desde)
    # Las de Diana: personales, no son del hogar.
    IncomeSourceFactory(household=hogar, owner=diana, scope="personal",
                        amount=Decimal("777.00"), effective_from=desde)
    ExpenseRuleFactory(household=hogar, owner=diana, scope="personal",
                       amount=Decimal("123.00"), effective_from=desde)
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()
    client.force_login(user)

    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.context["es_proyeccion"] is True
    assert r.context["forecast"]["ingresos"] == Decimal("3000.00")
    assert r.context["forecast"]["egresos"] == Decimal("400.00")
    assert r.context["forecast"]["sobrante"] == Decimal("2600.00")
    assert r.context["real"]["ingresos"] == Decimal("3000.00")
    assert r.context["real"]["egresos"] == Decimal("400.00")


def test_un_ambito_inventado_es_404(client, admin_con_hogar):
    user, _hogar = admin_con_hogar
    client.force_login(user)

    assert client.get("/budget/inventado/").status_code == 404


# --- el saldo inicial se escribe en la propia alerta ---------------------------


def _guardar_saldo(client, importe, htmx=True):
    cabeceras = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    return client.post(reverse("budget:saldo_inicial"), {"opening_balance": importe}, **cabeceras)


def test_guardar_el_saldo_inicial_recalcula_la_alerta(client, mes_con_dinero):
    _user, _hogar, mes, _otto, _diana = mes_con_dinero
    real_del_mes = client.get(reverse("budget:mes", args=["household"])).context["totales"]["sobrante_real"]

    r = _guardar_saldo(client, "1500.00")

    mes.refresh_from_db()
    assert mes.opening_balance == Decimal("1500.00")
    assert r.status_code == 200
    assert r.context["alerta"]["en_mano"] == Decimal("1500.00") + real_del_mes
    assert r.context["alerta"]["falta_saldo"] is False
    html = r.content.decode()
    assert 'id="overview-alerta"' in html and "<html" not in html


def test_cero_es_un_saldo_y_deja_de_pedirlo(client, mes_con_dinero):
    _user, _hogar, mes, _otto, _diana = mes_con_dinero

    r = _guardar_saldo(client, "0.00")

    mes.refresh_from_db()
    assert mes.opening_balance == Decimal("0.00")
    assert r.context["alerta"]["falta_saldo"] is False
    assert "Add this month's opening balance" not in r.content.decode()


def test_un_saldo_negativo_se_admite(client, mes_con_dinero):
    _user, _hogar, mes, _otto, _diana = mes_con_dinero

    _guardar_saldo(client, "-250.00")

    mes.refresh_from_db()
    assert mes.opening_balance == Decimal("-250.00")


def test_un_saldo_ilegible_no_se_guarda_y_se_dice(client, mes_con_dinero):
    _user, _hogar, mes, _otto, _diana = mes_con_dinero

    for malo in ("", "abc"):
        r = _guardar_saldo(client, malo)
        assert r.status_code == 200 and r.context["form"].errors
        assert 'id="overview-alerta"' in r.content.decode()

    mes.refresh_from_db()
    assert mes.opening_balance is None


def test_sin_htmx_vuelve_al_overview(client, mes_con_dinero):
    _user, _hogar, mes, _otto, _diana = mes_con_dinero

    r = _guardar_saldo(client, "10.00", htmx=False)

    assert r.status_code == 302 and r.url == reverse("budget:overview", args=["household"])
    mes.refresh_from_db()
    assert mes.opening_balance == Decimal("10.00")


def test_con_saldo_guardado_se_ofrece_editarlo(client, mes_con_dinero):
    _user, _hogar, mes, _otto, _diana = mes_con_dinero
    mes.opening_balance = Decimal("1500.00")
    mes.save(update_fields=["opening_balance"])

    html = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert 'name="opening_balance"' in html and 'value="1500.00"' in html
    assert "Edit" in html


def test_la_sugerencia_no_se_guarda_sola(client, mes_con_dinero):
    _user, hogar, mes, _otto, _diana = mes_con_dinero
    anio, numero = (mes.year - 1, 12) if mes.month == 1 else (mes.year, mes.month - 1)
    anterior = BudgetMonthFactory(household=hogar, year=anio, month=numero)
    MonthlyCloseFactory(household=hogar, budget_month=anterior, arrastre=Decimal("640.00"))
    # Cerrado de verdad: un mes pasado abierto lo cierra la propia peticion.
    BudgetMonth.objects.for_household(hogar).filter(pk=anterior.pk).update(status="closed")

    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.context["sugerencia_saldo"] == Decimal("640.00")
    html = r.content.decode()
    assert 'value="640.00"' in html and "Suggested from last month's close." in html
    mes.refresh_from_db()
    assert mes.opening_balance is None


def test_sin_can_edit_budget_no_hay_campo_y_el_post_es_403(client, mes_con_dinero):
    _user, hogar, mes, _otto, _diana = mes_con_dinero
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    html = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert 'name="opening_balance"' not in html
    assert _guardar_saldo(client, "1.00").status_code == 403
    mes.refresh_from_db()
    assert mes.opening_balance is None


def test_un_hogar_sin_escritura_no_ofrece_el_campo_ni_lo_acepta(client, mes_con_dinero):
    _user, hogar, mes, _otto, _diana = mes_con_dinero
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    r = client.get(reverse("budget:overview", args=["household"]))

    # La fila del mes ya existia: la alerta se ensena, pero sin formulario.
    assert r.context["alerta"] is not None
    assert 'name="opening_balance"' not in r.content.decode()
    assert _guardar_saldo(client, "1.00").status_code == 403
    mes.refresh_from_db()
    assert mes.opening_balance is None


def test_en_un_mes_cerrado_no_se_guarda(client, mes_con_dinero):
    _user, hogar, mes, _otto, _diana = mes_con_dinero
    BudgetMonth.objects.for_household(hogar).filter(pk=mes.pk).update(status="closed")

    r = _guardar_saldo(client, "1.00")

    mes.refresh_from_db()
    assert mes.opening_balance is None
    assert r.status_code == 200 and r["HX-Redirect"] == reverse("budget:overview", args=["household"])


def test_el_saldo_inicial_no_toca_la_tarjeta_cash_float(client, mes_con_dinero):
    antes = client.get(reverse("budget:mes", args=["household"])).context["cash_float"]

    _guardar_saldo(client, "5000.00")

    despues = client.get(reverse("budget:mes", args=["household"])).context["cash_float"]
    assert despues == antes


# --- lo que un hogar sin escritura o un miembro de solo lectura no puede usar ---


def _caducar(hogar):
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()


def test_un_hogar_caducado_sin_presupuesto_no_ofrece_configurarlo(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    _caducar(hogar)
    client.force_login(user)

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    assert r.context["sin_presupuesto"] is True
    # El cajon de la navegacion enlaza "Budget setup": se mira el boton de esta pantalla.
    assert "Set up the budget" not in html


def test_un_hogar_caducado_no_ofrece_planear_el_mes_siguiente(client, mes_con_dinero):
    _user, hogar, mes, _otto, _diana = mes_con_dinero
    BudgetMonth.objects.for_household(hogar).filter(pk=mes.pk).update(status="closed")
    _caducar(hogar)

    html = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert "is closed." in html
    assert "Plan next month" not in html
    anio, numero = (mes.year + 1, 1) if mes.month == 12 else (mes.year, mes.month + 1)
    assert reverse("budget:planificar_mes", args=["household", anio, numero, 1]) not in html


def test_un_hogar_caducado_no_ofrece_montar_un_ingreso(client, mes_con_dinero):
    _user, hogar, _mes, _otto, _diana = mes_con_dinero
    _caducar(hogar)

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    assert r.context["alerta"]["sin_ingreso"] is True
    assert "No upcoming income planned" in html
    assert "Set up an income" not in html


def test_con_escritura_si_se_ofrece_montar_un_ingreso(client, mes_con_dinero):
    html = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert "Set up an income" in html and reverse("budget:configurar") in html


def test_el_forecast_personal_ensena_lo_planeado_de_ingresos_y_gastos(client, mes_con_dinero):
    _user, hogar, mes, otto, _diana = mes_con_dinero
    entra = mes.lineas.filter(kind="income").first().category
    sale = mes.lineas.filter(kind="expense").first().category
    BudgetLineFactory(household=hogar, budget_month=mes, category=entra, kind="income",
                      planned_amount=Decimal("611.00"), scope="personal", owner=otto)
    BudgetLineFactory(household=hogar, budget_month=mes, category=sale, kind="expense",
                      planned_amount=Decimal("321.00"), scope="personal", owner=otto)

    r = client.get(reverse("budget:overview", args=["personal"]))
    html = r.content.decode()
    # La tarjeta Real tambien nombra lo planeado: se mira solo la del Forecast.
    forecast = html.split("overview__forecast", 1)[1].split("overview__real", 1)[0]

    assert r.context["forecast"]["ingresos"] == Decimal("611.00")
    assert r.context["forecast"]["egresos"] == Decimal("321.00")
    assert "$611.00" in forecast and "$321.00" in forecast


def test_quien_no_puede_fijar_el_saldo_ve_a_quien_pedirselo(client, mes_con_dinero):
    _user, hogar, _mes, _otto, _diana = mes_con_dinero
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    r = client.get(reverse("budget:overview", args=["household"]))
    html = r.content.decode()

    assert r.context["alerta"]["falta_saldo"] is True
    assert "Ask the household owner to add this month's opening balance." in html
    assert "Add this month's opening balance for an accurate check" not in html


def test_un_hogar_sin_escritura_tampoco_pide_el_saldo_a_quien_no_puede_darlo(client, mes_con_dinero):
    _user, hogar, _mes, _otto, _diana = mes_con_dinero
    _caducar(hogar)

    html = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert "Ask the household owner to add this month's opening balance." in html
    assert "Add this month's opening balance for an accurate check" not in html


def test_quien_puede_fijar_el_saldo_ve_la_invitacion_a_anotarlo(client, mes_con_dinero):
    html = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert "Add this month's opening balance for an accurate check" in html
    assert "Ask the household owner to add" not in html


def _sin_espacios(html):
    """El html con el espacio en blanco colapsado: para asertar sobre un
    parrafo concreto (clase + texto) y no sobre algo suelto de la pagina."""
    return " ".join(html.split()).replace("> ", ">").replace(" <", "<")


def _mes_con_gasto_pasado_de_largo(hogar):
    """Una partida pagada de mas y otra a medias: lo pendiente es 60, aunque
    entre las dos lo planificado menos lo pagado de 10."""
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    sale = CategoryFactory(household=hogar, slug="tarjetas-sale", kind="expense")
    miembro = hogar.active_memberships().first()
    for importe in ("150.00", "40.00"):
        linea = BudgetLineFactory(household=hogar, budget_month=mes, category=sale,
                                  kind="expense", planned_amount=Decimal("100.00"))
        TransactionFactory(household=hogar, budget_month=mes, category=sale, member=miembro,
                           budget_line=linea, amount=Decimal(importe), date=hoy)
    return hoy


def test_las_tarjetas_ensenan_pendiente_esperado_y_desvio(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)
    hoy = _mes_con_gasto_pasado_de_largo(hogar)

    mes = client.get(reverse("budget:mes", args=["household", hoy.year, hoy.month]))
    overview = client.get(reverse("budget:overview", args=["household"]))

    for respuesta in (mes, overview):
        totales = respuesta.context["totales" if respuesta is mes else "real"]
        assert totales["egresos_pendiente"] == Decimal("60.00")
        assert totales["egresos_esperado"] == Decimal("250.00")
        assert totales["egresos_desvio"] == Decimal("50.00")
        html = respuesta.content.decode()
        assert "Pending" in html and "60.00" in html
        assert "Expected" in html and "250.00" in html
        # El parrafo concreto del desvio: gasto de mas, en rojo.
        assert 'campo__ayuda importe--mal">+$50.00 over plan' in _sin_espacios(html)


def test_un_desvio_de_cero_no_dice_nada(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    sale = CategoryFactory(household=hogar, slug="tarjetas-justo", kind="expense")
    BudgetLineFactory(household=hogar, budget_month=mes, category=sale,
                      kind="expense", planned_amount=Decimal("100.00"))

    html = client.get(reverse("budget:mes", args=["household", hoy.year, hoy.month])).content.decode()

    assert "Pending" in html and "Expected" in html
    assert "over plan" not in html and "under plan" not in html


def test_los_ingresos_por_encima_del_plan_van_en_verde(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    entra = CategoryFactory(household=hogar, slug="tarjetas-entra", kind="income")
    linea = BudgetLineFactory(household=hogar, budget_month=mes, category=entra,
                              kind="income", planned_amount=Decimal("100.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=entra,
                       member=hogar.active_memberships().first(), budget_line=linea,
                       amount=Decimal("130.00"), date=hoy)

    html = client.get(reverse("budget:mes", args=["household", hoy.year, hoy.month])).content.decode()

    assert "30.00 over plan" in html
    assert 'class="campo__ayuda importe--ingreso"' in html


def _mes_cerrado_con_la_mitad_pagada(hogar):
    """Un gasto planeado de 100 con 60 pagados y un ingreso planeado de 100 con
    60 cobrados; el mes se cierra con eso. Lo que faltaba ya no se espera."""
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    sale = CategoryFactory(household=hogar, slug="cierre-sale", kind="expense")
    entra = CategoryFactory(household=hogar, slug="cierre-entra", kind="income")
    miembro = hogar.active_memberships().first()
    for categoria, kind in ((sale, "expense"), (entra, "income")):
        linea = BudgetLineFactory(household=hogar, budget_month=mes, category=categoria,
                                  kind=kind, planned_amount=Decimal("100.00"))
        TransactionFactory(household=hogar, budget_month=mes, category=categoria, member=miembro,
                           budget_line=linea, amount=Decimal("60.00"), date=hoy)
    BudgetMonth.objects.for_household(hogar).filter(pk=mes.pk).update(status="closed")
    return hoy


def test_un_mes_cerrado_no_espera_nada_y_ensena_lo_de_menos(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)
    hoy = _mes_cerrado_con_la_mitad_pagada(hogar)

    mes = client.get(reverse("budget:mes", args=["household", hoy.year, hoy.month]))
    overview = client.get(reverse("budget:overview", args=["household"]))

    for respuesta in (mes, overview):
        totales = respuesta.context["totales" if respuesta is mes else "real"]
        assert totales["egresos_pendiente"] == Decimal("0.00")
        assert totales["ingresos_pendiente"] == Decimal("0.00")
        assert totales["egresos_esperado"] == Decimal("60.00")
        assert totales["egresos_desvio"] == Decimal("-40.00")
        assert totales["ingresos_desvio"] == Decimal("-40.00")
        html = _sin_espacios(respuesta.content.decode())
        # Gastar de menos es bueno (verde); cobrar de menos es malo (rojo).
        assert html.count('campo__ayuda importe--ingreso">−$40.00 under plan') == 1
        assert html.count('campo__ayuda importe--mal">−$40.00 under plan') == 1
        # El mes ya no debe nada: no hay fila de pendiente.
        assert ">Pending $" not in html


def test_un_mes_abierto_con_un_pago_parcial_no_dice_que_gasta_de_menos(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    sale = CategoryFactory(household=hogar, slug="parcial-sale", kind="expense")
    linea = BudgetLineFactory(household=hogar, budget_month=mes, category=sale,
                              kind="expense", planned_amount=Decimal("100.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=sale,
                       member=hogar.active_memberships().first(), budget_line=linea,
                       amount=Decimal("60.00"), date=hoy)

    for nombre, args in (("budget:mes", ["household", hoy.year, hoy.month]),
                         ("budget:overview", ["household"])):
        html = _sin_espacios(client.get(reverse(nombre, args=args)).content.decode())
        assert ">Pending $40.00<" in html
        assert "under plan" not in html


def test_la_alerta_dice_cuanto_de_lo_pendiente_es_del_mes_siguiente(client, admin_con_hogar):
    user, hogar = admin_con_hogar
    client.force_login(user)
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    anio, numero = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
    siguiente = BudgetMonthFactory(household=hogar, year=anio, month=numero)
    entra = CategoryFactory(household=hogar, slug="sig-entra", kind="income")
    sale = CategoryFactory(household=hogar, slug="sig-sale", kind="expense")
    BudgetLineFactory(household=hogar, budget_month=mes, category=sale, kind="expense",
                      planned_amount=Decimal("100.00"))
    BudgetLineFactory(household=hogar, budget_month=siguiente, category=entra, kind="income",
                      planned_amount=Decimal("3000.00"), due_date=date(anio, numero, 14))
    BudgetLineFactory(household=hogar, budget_month=siguiente, category=sale, kind="expense",
                      planned_amount=Decimal("250.00"), due_date=date(anio, numero, 2))

    r = client.get(reverse("budget:overview", args=["household"]))
    html = _sin_espacios(r.content.decode())

    assert r.context["alerta"]["del_siguiente"] == Decimal("250.00")
    assert r.context["alerta"]["pendiente"] == Decimal("350.00")
    fecha = f"{date(anio, numero, 14):%b} 14"
    assert f"Includes $250.00 due before {fecha}" in html


def test_la_alerta_no_menciona_el_mes_siguiente_si_no_aporta_nada(client, mes_con_dinero):
    r = client.get(reverse("budget:overview", args=["household"]))

    assert r.context["alerta"]["del_siguiente"] == Decimal("0.00")
    assert "due before" not in r.content.decode()
