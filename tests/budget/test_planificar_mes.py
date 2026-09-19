"""Planificar el mes de verdad: cualquier mes no cerrado, y con sus lineas editables.

El asistente del §4.5.6 pintaba la proyeccion de las reglas en los pasos 1 y 2
—solo lectura— y solo para el mes corriente. Dos consecuencias: no se podia
planificar un mes futuro, y una partida excepcional anadida en el paso 2 ni
siquiera entraba en el sobrante del paso 3, porque el paso 3 volvia a leer las
reglas. Aqui el asistente trabaja sobre las `BudgetLine` del mes: se edita el
mes, no el setup (§2.3: "editar un mes concreto: tocas sus filas").
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget import services
from apps.budget.engine.cascade import ALLOWANCE, FIXED, GOAL, REMAINDER
from apps.budget.models import (
    AllowanceLedger,
    BudgetLine,
    Category,
    BudgetMonth,
    MonthlyAllocation,
)
from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import (
    AllocationRuleFactory,
    BudgetMonthFactory,
    CategoryFactory,
    ExpenseRuleFactory,
    GoalFactory,
    IncomeSourceFactory,
)

pytestmark = pytest.mark.django_db


def _sumar_meses(fecha, n):
    indice = fecha.year * 12 + (fecha.month - 1) + n
    return indice // 12, indice % 12 + 1


@pytest.fixture
def hogar_listo():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    membresia = hogar.active_memberships().first()
    IncomeSourceFactory(household=hogar, owner=membresia, amount=Decimal("3000.00"))
    ExpenseRuleFactory(household=hogar, amount=Decimal("1800.00"),
                       category=CategoryFactory(household=hogar, slug="mi-rent"))
    meta = GoalFactory(household=hogar, target_amount=Decimal("10000.00"))
    AllocationRuleFactory(household=hogar, order=1, target_type=GOAL,
                          target_goal=meta, method=FIXED, amount=Decimal("600.00"))
    AllocationRuleFactory(household=hogar, order=2, target_type=ALLOWANCE,
                          method=REMAINDER, target_goal=None)
    return admin, hogar


def _paso(anio, numero, paso):
    return reverse("budget:planificar_mes", args=["household", anio, numero, paso])


# --- un mes futuro ------------------------------------------------------------


def test_planificar_un_mes_futuro_lo_materializa(client, hogar_listo):
    """Al entrar al asistente de un mes que aun no existe, nacen sus filas, igual
    que le pasa al mes corriente al abrirlo. Desde ahi es independiente del setup."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    anio, numero = _sumar_meses(timezone.localdate(), 2)

    respuesta = client.get(_paso(anio, numero, 1))

    assert respuesta.status_code == 200
    mes = BudgetMonth.objects.for_household(hogar).get(year=anio, month=numero)
    assert mes.status == BudgetMonth.OPEN
    assert mes.lineas.count() == 2


def test_la_ruta_sin_fecha_es_el_mes_corriente(client, hogar_listo):
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()

    respuesta = client.get(reverse("budget:planificar_paso", args=["household", 1]))

    assert respuesta.status_code == 200
    assert BudgetMonth.objects.for_household(hogar).filter(
        year=hoy.year, month=hoy.month
    ).exists()


def test_un_mes_pasado_que_no_se_vivio_no_se_planifica(client, hogar_listo):
    """Fabricar un mes pasado escribe historial inventado (ver obtener_mes)."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    anio, numero = _sumar_meses(timezone.localdate(), -3)

    assert client.get(_paso(anio, numero, 1)).status_code == 404
    assert not BudgetMonth.objects.for_household(hogar).exists()


def test_un_mes_cerrado_no_se_planifica(client, hogar_listo):
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month, status="closed")

    respuesta = client.get(_paso(hoy.year, hoy.month, 2))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("budget:mes", args=["household", hoy.year, hoy.month])


def test_un_mes_fuera_del_calendario_es_404(client, hogar_listo):
    admin, _ = hogar_listo
    client.force_login(admin)

    assert client.get(_paso(2026, 13, 1)).status_code == 404


# --- las lineas se editan en el asistente ------------------------------------


def test_el_paso_2_corrige_el_importe_de_un_gasto_del_mes(client, hogar_listo):
    """Se edita el MES, no el setup: la regla sigue diciendo 1.800."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    linea = mes.lineas.get(kind="expense")

    respuesta = client.post(_paso(hoy.year, hoy.month, 2), {f"linea-{linea.pk}": "1950.00"})

    assert respuesta.status_code == 302
    assert respuesta.url == _paso(hoy.year, hoy.month, 3)
    linea.refresh_from_db()
    assert linea.planned_amount == Decimal("1950.00")
    assert linea.source_expense_rule.amount == Decimal("1800.00")


def test_el_paso_1_corrige_un_ingreso_del_mes(client, hogar_listo):
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    linea = mes.lineas.get(kind="income")

    client.post(_paso(hoy.year, hoy.month, 1), {f"linea-{linea.pk}": "3200.00"})

    linea.refresh_from_db()
    assert linea.planned_amount == Decimal("3200.00")


def test_un_importe_invalido_no_avanza(client, hogar_listo):
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    linea = mes.lineas.get(kind="expense")

    respuesta = client.post(_paso(hoy.year, hoy.month, 2), {f"linea-{linea.pk}": "-5"})

    assert respuesta.status_code == 200
    linea.refresh_from_db()
    assert linea.planned_amount == Decimal("1800.00")


def test_un_campo_en_blanco_conserva_el_importe_y_avanza(client, hogar_listo):
    """Borrar el campo no es poner cero: es no tocar esa linea. Y "Next" sin
    cambiar nada tiene que avanzar, como antes de que los pasos guardaran."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    linea = mes.lineas.get(kind="expense")

    respuesta = client.post(_paso(hoy.year, hoy.month, 2), {f"linea-{linea.pk}": ""})

    assert respuesta.status_code == 302
    linea.refresh_from_db()
    assert linea.planned_amount == Decimal("1800.00")


def test_los_pasos_pintan_las_lineas_del_mes_y_no_las_reglas(client, hogar_listo):
    """Tras corregir el alquiler del mes, el paso 2 tiene que ensenar 1.950, no 1.800."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    linea = mes.lineas.get(kind="expense")
    linea.planned_amount = Decimal("1950.00")
    linea.save()

    html = client.get(_paso(hoy.year, hoy.month, 2)).content.decode()

    assert "1950.00" in html
    assert f'name="linea-{linea.pk}"' in html


def test_una_partida_excepcional_entra_en_el_sobrante(client, hogar_listo):
    """El fallo de origen: el paso 3 volvia a las reglas y el extra no contaba."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    categoria = CategoryFactory(household=hogar, slug="campamento", kind="expense")

    client.post(reverse("budget:linea_nueva_del_mes", args=["household", hoy.year, hoy.month]), {
        "category": categoria.pk, "kind": "expense",
        "planned_amount": "200.00", "scope": "household", "note": "Campamento",
    })
    html = client.get(_paso(hoy.year, hoy.month, 3)).content.decode()

    assert "1,000.00" in html or "1 000,00" in html   # 3000 - 1800 - 200


def test_la_partida_excepcional_se_anade_al_mes_que_se_planifica(client, hogar_listo):
    admin, hogar = hogar_listo
    client.force_login(admin)
    anio, numero = _sumar_meses(timezone.localdate(), 1)
    categoria = CategoryFactory(household=hogar, slug="viaje", kind="expense")

    respuesta = client.post(reverse("budget:linea_nueva_del_mes", args=["household", anio, numero]), {
        "category": categoria.pk, "kind": "expense",
        "planned_amount": "900.00", "scope": "household", "note": "Viaje",
    })

    assert respuesta.status_code == 302
    assert respuesta.url == _paso(anio, numero, 2)
    linea = BudgetLine.objects.for_household(hogar).get(note="Viaje")
    assert (linea.budget_month.year, linea.budget_month.month) == (anio, numero)


def test_una_partida_excepcional_se_puede_quitar(client, hogar_listo):
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    categoria = CategoryFactory(household=hogar, slug="viaje", kind="expense")
    extra = BudgetLine(household=hogar, budget_month=mes, category=categoria,
                       kind="expense", planned_amount=Decimal("900.00"), is_exceptional=True)
    extra.save()
    fija = mes.lineas.get(kind="expense", is_exceptional=False)

    respuesta = client.post(reverse("budget:linea_quitar", args=["household", extra.pk]))

    assert respuesta.status_code == 302
    assert not BudgetLine.objects.for_household(hogar).filter(pk=extra.pk).exists()
    # Una linea que viene de una regla no se quita: se pone a cero.
    assert client.post(reverse("budget:linea_quitar", args=["household", fija.pk])).status_code == 404
    assert BudgetLine.objects.for_household(hogar).filter(pk=fija.pk).exists()


# --- confirmar de nuevo ----------------------------------------------------------


def test_reconfirmar_reescribe_el_reparto_sin_duplicar(client, hogar_listo):
    """Hasta el cierre, el plan se puede rehacer: cambiar un gasto y volver a
    confirmar deja UN reparto con la mesada nueva, no dos."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    client.post(_paso(hoy.year, hoy.month, 3))
    mes = BudgetMonth.objects.for_household(hogar).get(year=hoy.year, month=hoy.month)
    membresia = hogar.active_memberships().first()
    assert AllowanceLedger.objects.for_household(hogar).get(
        member=membresia, budget_month=mes
    ).granted == Decimal("600.00")   # 3000 - 1800 - 600 de ahorro

    linea = mes.lineas.get(kind="expense")
    client.post(_paso(hoy.year, hoy.month, 2), {f"linea-{linea.pk}": "2000.00"})
    client.post(_paso(hoy.year, hoy.month, 3))

    assert MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes).count() == 2
    assert AllowanceLedger.objects.for_household(hogar).get(
        member=membresia, budget_month=mes
    ).granted == Decimal("400.00")


def test_se_puede_anadir_un_ingreso_excepcional_desde_el_paso_1(client, hogar_listo):
    """Un aguinaldo o una devolucion de impuestos: entra una vez y no es una regla."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    ruta = reverse("budget:linea_nueva_del_mes_de", args=["household", hoy.year, hoy.month, "income"])
    assert ruta in client.get(_paso(hoy.year, hoy.month, 1)).content.decode()

    html = client.get(ruta).content.decode()
    assert 'name="kind"' not in html                      # el tipo lo fija la ruta
    assert "Salary" in html and "Rent" not in html        # solo categorias de ingreso
    assert "One-off income" in html

    categoria = Category.objects.for_household(hogar).get(slug="salary")
    respuesta = client.post(ruta, {
        "category": categoria.pk, "planned_amount": "1200.00",
        "scope": "household", "note": "Aguinaldo",
    })

    assert respuesta.status_code == 302
    assert respuesta.url == _paso(hoy.year, hoy.month, 1)
    linea = BudgetLine.objects.for_household(hogar).get(note="Aguinaldo")
    assert linea.kind == "income" and linea.is_exceptional


def test_la_tarjeta_planned_tiene_cuatro_bloques_con_su_total(client, hogar_listo):
    """Income, One-off income, Expenses, One-off expenses, cada uno con su total."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    BudgetLine(household=hogar, budget_month=mes, kind="expense", is_exceptional=True,
               category=CategoryFactory(household=hogar, slug="viaje", kind="expense"),
               planned_amount=Decimal("900.00"), note="Viaje a Quebec").save()
    BudgetLine(household=hogar, budget_month=mes, kind="income", is_exceptional=True,
               category=Category.objects.for_household(hogar).get(slug="salary"),
               planned_amount=Decimal("1200.00"), note="Aguinaldo").save()
    fijo = mes.lineas.get(kind="expense", is_exceptional=False)
    ingreso = mes.lineas.get(kind="income", is_exceptional=False)

    html = client.get(reverse("budget:mes", args=["household", hoy.year, hoy.month])).content.decode()

    assert (html.index(ingreso.nombre) < html.index("Aguinaldo")
            < html.index(fijo.nombre) < html.index("Viaje a Quebec"))
    for titulo in ("One-off income", "Expenses", "One-off expenses"):
        assert titulo in html
    # Los cuatro totales, en orden: 3000 · 1200 · 1800 · 900.
    totales = [html.index(cifra, html.index("Planned")) for cifra in
               ("3,000.00", "1,200.00", "1,800.00", "900.00")]
    assert totales == sorted(totales)
    assert html.count('class="tabla__total"') == 4


def test_la_tarjeta_planned_muestra_categoria_estado_y_vencimiento(client, hogar_listo):
    from apps.budget.models import Transaction

    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    fijo = mes.lineas.get(kind="expense", is_exceptional=False)
    Transaction(household=hogar, budget_month=mes, budget_line=fijo, category=fijo.category,
                amount=Decimal("1000.00"), date=hoy,
                member=hogar.active_memberships().first()).save()

    html = client.get(reverse("budget:mes", args=["household", hoy.year, hoy.month])).content.decode()

    for cabecera in ("Category", "Name", "Planned", "Status", "Due date"):
        assert f"<th>{cabecera}</th>" in html or f'<th class="numero">{cabecera}</th>' in html
    assert fijo.category.etiqueta() in html
    assert "Partial" in html and "800.00" in html          # lo que falta
    assert fijo.due_date.strftime("%b") in html            # la fecha, pintada


# --- volver a copiar el setup ------------------------------------------------------


def _refresh(anio, numero, paso):
    return reverse("budget:planificar_refrescar", args=["household", anio, numero, paso])


def test_refrescar_vuelve_a_copiar_las_reglas_y_respeta_lo_excepcional(hogar_listo):
    """Un mes ya copiado no sigue al setup. Refrescar lo pone al dia: importes
    de las reglas vigentes, reglas nuevas anadidas, reglas borradas quitadas —
    y las partidas excepcionales tal cual estaban."""
    from apps.budget.models import ExpenseRule

    _, hogar = hogar_listo
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    ingreso = mes.lineas.get(kind="income")
    gasto = mes.lineas.get(kind="expense")
    extra = BudgetLine(household=hogar, budget_month=mes, kind="expense",
                       category=CategoryFactory(household=hogar, slug="viaje", kind="expense"),
                       planned_amount=Decimal("900.00"), is_exceptional=True, note="Viaje")
    extra.save()
    # El setup cambia despues de copiar el mes:
    regla_ingreso = ingreso.source_income
    regla_ingreso.amount = Decimal("3500.00")
    regla_ingreso.save()
    gasto.source_expense_rule.delete()
    nueva = ExpenseRuleFactory(household=hogar, name="Internet", amount=Decimal("60.00"),
                               category=CategoryFactory(household=hogar, slug="net", kind="expense"),
                               effective_from=hoy.replace(day=1))

    services.refrescar_desde_las_reglas(hogar, mes)

    ingreso.refresh_from_db()
    assert ingreso.planned_amount == Decimal("3500.00")
    assert not BudgetLine.objects.for_household(hogar).filter(pk=gasto.pk).exists()
    assert mes.lineas.get(source_expense_rule=nueva).planned_amount == Decimal("60.00")
    extra.refresh_from_db()
    assert extra.planned_amount == Decimal("900.00")
    assert mes.lineas.count() == 3


def test_refrescar_desde_el_paso_vuelve_al_mismo_paso(client, hogar_listo):
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    linea = mes.lineas.get(kind="expense")
    linea.planned_amount = Decimal("9999.00")
    linea.save()

    respuesta = client.post(_refresh(hoy.year, hoy.month, 2))

    assert respuesta.status_code == 302
    assert respuesta.url == _paso(hoy.year, hoy.month, 2)
    linea.refresh_from_db()
    assert linea.planned_amount == Decimal("1800.00")
    assert client.get(_refresh(hoy.year, hoy.month, 2)).status_code == 405


def test_refrescar_un_mes_cerrado_no_toca_nada(client, hogar_listo):
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    linea = mes.lineas.get(kind="expense")
    linea.planned_amount = Decimal("9999.00")
    linea.save()
    mes.status = "closed"
    mes.save(update_fields=["status"])

    respuesta = client.post(_refresh(hoy.year, hoy.month, 2))

    assert respuesta.status_code == 302
    linea.refresh_from_db()
    assert linea.planned_amount == Decimal("9999.00")


def test_los_pasos_ofrecen_refrescar(client, hogar_listo):
    admin, _ = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()

    assert _refresh(hoy.year, hoy.month, 1) in client.get(_paso(hoy.year, hoy.month, 1)).content.decode()
    assert _refresh(hoy.year, hoy.month, 2) in client.get(_paso(hoy.year, hoy.month, 2)).content.decode()


# --- llegar hasta ahi ----------------------------------------------------------


def test_la_pantalla_del_mes_enlaza_al_anterior_al_siguiente_y_a_planificarlo(client, hogar_listo):
    admin, _ = hogar_listo
    client.force_login(admin)
    anio, numero = _sumar_meses(timezone.localdate(), 1)
    anterior = _sumar_meses(timezone.localdate(), 0)
    siguiente = _sumar_meses(timezone.localdate(), 2)

    html = client.get(reverse("budget:mes", args=["household", anio, numero])).content.decode()

    assert reverse("budget:mes", args=["household", *anterior]) in html
    assert reverse("budget:mes", args=["household", *siguiente]) in html
    assert _paso(anio, numero, 1) in html


def test_la_tarjeta_planned_separa_ingresos_de_gastos_y_los_nombra(client, hogar_listo):
    """Ingresos arriba, gastos abajo, cada uno con el NOMBRE de su regla (no la
    categoria) y con su color: verde lo que entra, naranja lo que sale."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    ingreso = mes.lineas.get(kind="income")
    gasto = mes.lineas.get(kind="expense")

    html = client.get(reverse("budget:mes", args=["household", hoy.year, hoy.month])).content.decode()

    assert ingreso.nombre in html and gasto.nombre in html
    assert html.index(ingreso.nombre) < html.index(gasto.nombre)
    assert 'class="numero importe--ingreso"' in html
    assert 'class="numero importe--egreso"' in html


# --- cerrar el mes que se ve, no "hoy" ----------------------------------------


def test_cerrar_desde_un_mes_cierra_ese_mes(client, hogar_listo):
    """Con paginacion entre meses, `cerrar` no puede seguir tomando "hoy": desde
    la pantalla de agosto se cierra agosto."""
    from apps.budget.models import MonthlyClose

    admin, hogar = hogar_listo
    client.force_login(admin)
    hoy = timezone.localdate()
    anio, numero = _sumar_meses(hoy, -1)
    pasado = BudgetMonthFactory(household=hogar, year=anio, month=numero, status="open")
    services.obtener_mes(hogar, hoy.year, hoy.month)   # el corriente, abierto

    respuesta = client.post(reverse("budget:cerrar_mes", args=["household", anio, numero]))

    assert respuesta.status_code == 302
    pasado.refresh_from_db()
    assert pasado.esta_cerrado
    assert MonthlyClose.objects.for_household(hogar).count() == 1
    assert not BudgetMonth.objects.for_household(hogar).get(
        year=hoy.year, month=hoy.month
    ).esta_cerrado


def test_un_mes_futuro_no_se_cierra(client, hogar_listo):
    """Cerrar un mes que no ha empezado congelaria un balance sin movimientos."""
    admin, hogar = hogar_listo
    client.force_login(admin)
    anio, numero = _sumar_meses(timezone.localdate(), 1)
    client.get(_paso(anio, numero, 1))   # lo materializa

    respuesta = client.post(reverse("budget:cerrar_mes", args=["household", anio, numero]))

    assert respuesta.status_code == 404
    assert not BudgetMonth.objects.for_household(hogar).get(year=anio, month=numero).esta_cerrado
    html = client.get(reverse("budget:mes", args=["household", anio, numero])).content.decode()
    assert reverse("budget:cerrar_mes", args=["household", anio, numero]) not in html
