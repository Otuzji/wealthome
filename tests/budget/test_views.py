"""Las pantallas mínimas, y los permisos que las gobiernan.

Primer uso real de @requiere_permiso: hasta el lote de puertas estaba probado
y no lo llamaba ningún código de producción. Aquí queda ejercitado el
adolescente del §6.2 — registra sus gastos y no ve la hipoteca.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.models import ExpenseRule, IncomeSource
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_con_hogar():
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    return user, hogar


def _miembro(hogar, **permisos):
    base = dict(can_view_budget=False, can_edit_budget=False,
                can_add_transactions=False, can_view_reports=False)
    base.update(permisos)
    return MembershipFactory(household=hogar, role=Membership.MEMBER, **base)


# --- los permisos gobiernan de verdad ----------------------------------------


def test_configurar_exige_can_edit_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    sin_permiso = _miembro(hogar, can_add_transactions=True)
    client.force_login(sin_permiso.user)

    respuesta = client.get(reverse("budget:configurar"))

    assert respuesta.status_code == 403


def test_el_403_de_presupuesto_esta_traducido(client, admin_con_hogar):
    """No una página en blanco: la deuda que el lote de puertas cerró."""
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar).user)

    respuesta = client.get(reverse("budget:configurar"))

    assert "You do not have permission" in respuesta.content.decode()


def test_quien_tiene_el_permiso_entra(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_edit_budget=True).user)

    assert client.get(reverse("budget:configurar")).status_code == 200


def test_un_anonimo_va_al_login(client):
    respuesta = client.get(reverse("budget:configurar"))

    assert respuesta.status_code == 302


# --- los formularios no filtran datos de otras familias ----------------------


def test_el_desplegable_de_categorias_solo_trae_las_del_hogar(client, admin_con_hogar):
    """La fuga del <select> que el lote de puertas cerró, verificada en una
    pantalla real."""
    admin, hogar = admin_con_hogar
    CategoryFactory(household=hogar, name="Hipoteca Thompson", slug="mi-rent")
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    CategoryFactory(household=ajeno, name="Hipoteca García", slug="su-rent")
    client.force_login(admin)

    html = client.get(reverse("budget:gasto_nuevo")).content.decode()

    assert "Hipoteca Thompson" in html
    assert "Hipoteca García" not in html


def test_no_se_puede_crear_un_gasto_contra_una_categoria_ajena(client, admin_con_hogar):
    """El <select> filtrado es cosmético: lo que importa es que el POST con
    un id ajeno tampoco pase."""
    admin, hogar = admin_con_hogar
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    categoria_ajena = CategoryFactory(household=ajeno, slug="su-rent")
    client.force_login(admin)

    client.post(reverse("budget:gasto_nuevo"), {
        "category": categoria_ajena.pk, "name": "Intento",
        "amount": "100.00", "periodicity": "monthly",
        "effective_from": "2026-01-01", "scope": "household",
        "is_essential": "on",
    })

    assert not ExpenseRule.unscoped.filter(name="Intento").exists()


# --- crear las cosas ----------------------------------------------------------


def test_el_admin_crea_un_gasto_fijo(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent")
    client.force_login(admin)

    respuesta = client.post(reverse("budget:gasto_nuevo"), {
        "category": categoria.pk, "name": "Alquiler",
        "amount": "1800.00", "periodicity": "monthly",
        "effective_from": "2026-01-01", "scope": "household",
        "is_essential": "on",
    })

    assert respuesta.status_code == 302
    regla = ExpenseRule.objects.for_household(hogar).get(name="Alquiler")
    assert regla.amount == Decimal("1800.00")


def test_el_admin_crea_un_ingreso(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    membresia = hogar.active_memberships().first()
    client.force_login(admin)

    client.post(reverse("budget:ingreso_nuevo"), {
        "owner": membresia.pk, "name": "Sueldo", "source_type": "salary",
        "amount_type": "fixed", "amount": "3000.00",
        "periodicity": "monthly", "effective_from": "2026-01-01",
        "scope": "household",
    })

    assert IncomeSource.objects.for_household(hogar).filter(name="Sueldo").exists()


def test_la_pantalla_de_configuracion_lista_lo_creado(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent")
    from tests.factories_budget import ExpenseRuleFactory

    ExpenseRuleFactory(household=hogar, category=categoria, name="Alquiler")
    client.force_login(admin)

    html = client.get(reverse("budget:configurar")).content.decode()

    assert "Alquiler" in html


# --- registrar un gasto: la acción más frecuente ------------------------------


def test_registrar_exige_can_add_transactions(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    assert client.get(reverse("budget:registrar")).status_code == 403


def test_el_adolescente_registra_su_gasto_sin_ver_la_hipoteca(client, admin_con_hogar):
    """§6.2 completo, en dos afirmaciones."""
    _, hogar = admin_con_hogar
    adolescente = _miembro(hogar, can_add_transactions=True)
    client.force_login(adolescente.user)

    assert client.get(reverse("budget:registrar")).status_code == 200
    assert client.get(reverse("budget:mes", args=["household"])).status_code == 403


def test_registrar_un_gasto_lo_guarda_en_el_mes_corriente(client, admin_con_hogar):
    from apps.budget.models import Transaction

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    respuesta = client.post(reverse("budget:registrar"), {
        "category": categoria.pk, "amount": "45.50",
        "date": "2026-09-05", "payment_method": "debit", "scope": "household",
        "note": "Metro",
    })

    assert respuesta.status_code == 302
    tx = Transaction.objects.for_household(hogar).get()
    assert tx.amount == Decimal("45.50")
    assert tx.member == hogar.active_memberships().get(user=admin)


def test_el_gasto_se_registra_a_nombre_de_quien_lo_teclea(client, admin_con_hogar):
    """`member` no es un campo del formulario: sale de la petición. Si lo
    fuera, cualquiera podría registrar gastos a nombre de otro."""
    from apps.budget.forms import TransactionForm

    assert "member" not in TransactionForm.base_fields


# --- ver el mes ---------------------------------------------------------------


def test_el_mes_exige_can_view_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_add_transactions=True).user)

    assert client.get(reverse("budget:mes", args=["household"])).status_code == 403


def test_el_mes_muestra_lo_planeado_y_lo_real(client, admin_con_hogar):
    from tests.factories_budget import ExpenseRuleFactory

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent", name="Alquiler")
    ExpenseRuleFactory(household=hogar, category=categoria, name="Alquiler",
                       amount=Decimal("1800.00"))
    client.force_login(admin)

    html = client.get(reverse("budget:mes", args=["household"])).content.decode()

    assert "1,800.00" in html or "1 800,00" in html


def test_un_mes_futuro_se_puede_consultar_y_no_persiste(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth

    admin, hogar = admin_con_hogar
    client.force_login(admin)

    respuesta = client.get(reverse("budget:mes", args=["household", 2030, 5]))

    assert respuesta.status_code == 200
    assert not BudgetMonth.objects.for_household(hogar).filter(year=2030).exists()


# --- el comercio se teclea, no se elige --------------------------------------


def _gasto(categoria, **extra):
    datos = {"category": categoria.pk, "amount": "45.50", "date": "2026-09-05",
             "payment_method": "debit", "scope": "household"}
    datos.update(extra)
    return datos


def test_teclear_un_comercio_nuevo_lo_crea(client, admin_con_hogar):
    from apps.budget.models import Merchant

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    client.post(reverse("budget:registrar"),
                _gasto(categoria, merchant_name="WALMART #3421"))

    assert Merchant.objects.for_household(hogar).get().normalized_name == "WALMART"


def test_teclear_una_variante_reutiliza_el_comercio_que_ya_existe(client, admin_con_hogar):
    """Para lo que existe engine/merchants.py: WALMART #3421 y walmart son el
    mismo comercio, y sin esto la lista se llenaria de duplicados en un mes."""
    from apps.budget.models import Merchant

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    client.post(reverse("budget:registrar"),
                _gasto(categoria, merchant_name="WALMART #3421"))
    client.post(reverse("budget:registrar"),
                _gasto(categoria, merchant_name="walmart"))

    assert Merchant.objects.for_household(hogar).count() == 1


def test_un_gasto_sin_comercio_se_guarda_igual(client, admin_con_hogar):
    """No todo gasto tiene comercio: una transferencia, un reembolso."""
    from apps.budget.models import Transaction

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    client.post(reverse("budget:registrar"), _gasto(categoria, merchant_name=""))

    assert Transaction.objects.for_household(hogar).get().merchant is None


def test_el_comercio_de_otro_hogar_no_se_reutiliza(client, admin_con_hogar):
    """Dos familias que compran en el mismo Walmart tienen cada una su fila:
    fundirlas cruzaria el historial de gasto de dos hogares."""
    from apps.budget.models import Merchant
    from tests.factories_budget import MerchantFactory

    admin, hogar = admin_con_hogar
    ajeno = crear_hogar(UserFactory(), "Family Garcia", family_size=2)
    MerchantFactory(household=ajeno, name="Walmart")
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    client.post(reverse("budget:registrar"),
                _gasto(categoria, merchant_name="WALMART #3421"))

    assert Merchant.unscoped.count() == 2


# --- planificar el mes (§4.5.6) -----------------------------------------------


@pytest.fixture
def hogar_listo_para_planificar(admin_con_hogar):
    from apps.budget.engine.cascade import ALLOWANCE, FIXED, GOAL, REMAINDER
    from tests.factories_budget import (
        AllocationRuleFactory, ExpenseRuleFactory, GoalFactory, IncomeSourceFactory,
    )

    admin, hogar = admin_con_hogar
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


def test_planificar_muestra_el_sobrante_y_la_mesada(client, hogar_listo_para_planificar):
    """§13.5: la pareja ve su sobrante repartido y cada uno sabe su mesada."""
    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)

    html = client.get(reverse("budget:planificar", args=["household"])).content.decode()

    assert "1,200.00" in html or "1 200,00" in html   # el sobrante proyectado


def test_confirmar_la_planificacion_escribe_las_mesadas(client, hogar_listo_para_planificar):
    from apps.budget.models import AllowanceLedger

    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)

    respuesta = client.post(reverse("budget:planificar", args=["household"]))

    assert respuesta.status_code == 302
    assert AllowanceLedger.objects.for_household(hogar).exists()


def test_planificar_exige_can_edit_budget(client, hogar_listo_para_planificar):
    _, hogar = hogar_listo_para_planificar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    assert client.get(reverse("budget:planificar", args=["household"])).status_code == 403


# --- cerrar el mes ------------------------------------------------------------


def test_cerrar_el_mes_escribe_el_cierre(client, hogar_listo_para_planificar):
    from apps.budget.models import MonthlyClose

    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)
    client.post(reverse("budget:planificar", args=["household"]))

    respuesta = client.post(reverse("budget:cerrar", args=["household"]))

    assert respuesta.status_code == 302
    assert MonthlyClose.objects.for_household(hogar).exists()


def test_un_mes_cerrado_es_de_solo_lectura(client, hogar_listo_para_planificar):
    """§4.3: un mes cerrado no admite nada."""
    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)
    client.post(reverse("budget:planificar", args=["household"]))
    client.post(reverse("budget:cerrar", args=["household"]))

    respuesta = client.post(reverse("budget:cerrar", args=["household"]))

    assert respuesta.status_code in (302, 409)
    from apps.budget.models import MonthlyClose

    assert MonthlyClose.objects.for_household(hogar).count() == 1


# --- metas --------------------------------------------------------------------


def test_las_metas_muestran_su_dato_derivado(client, admin_con_hogar):
    from apps.budget.engine.goals import BY_TARGET_DATE
    from tests.factories_budget import GoalFactory

    admin, hogar = admin_con_hogar
    GoalFactory(household=hogar, name="Vacaciones",
                contribution_mode=BY_TARGET_DATE,
                target_amount=Decimal("7200.00"),
                target_date=date(2027, 6, 30))
    client.force_login(admin)

    html = client.get(reverse("budget:metas", args=["household"])).content.decode()

    assert "Vacaciones" in html


def test_aportar_a_una_meta_exige_can_edit_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    assert client.get(reverse("budget:aportar")).status_code == 403


# --- lo que encontró la revisión de la rama ----------------------------------


def test_un_mes_fuera_del_calendario_da_404_y_no_500(client, admin_con_hogar):
    """A esta URL se llega escribiéndola o con un enlace viejo.

    Un mes 13 reventaba en calendar.monthrange con un 500, y un mes 0 llegaba
    a crear la fila del BudgetMonth antes de reventar: solo la transacción la
    salvaba.
    """
    from apps.budget.models import BudgetMonth

    admin, hogar = admin_con_hogar
    client.force_login(admin)

    assert client.get("/budget/month/2026/13/").status_code == 404
    assert client.get("/budget/month/2026/0/").status_code == 404
    assert client.get("/budget/month/99999/5/").status_code == 404
    assert not BudgetMonth.objects.for_household(hogar).exists()


def test_registrar_en_un_mes_cerrado_avisa_en_vez_de_reventar(client, admin_con_hogar):
    """§4.3: un mes cerrado no admite escrituras, y decirlo es cosa del
    formulario, no de una página de error del servidor."""
    from django.utils import timezone

    from apps.budget import services
    from apps.budget.models import Transaction

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)
    hoy = timezone.localdate()
    services.cerrar_mes(services.obtener_mes(hogar, hoy.year, hoy.month))

    respuesta = client.post(reverse("budget:registrar"), _gasto(categoria))

    assert respuesta.status_code == 200
    assert respuesta.context["form"].errors
    assert not Transaction.objects.for_household(hogar).exists()


# --- el eje Hogar/Personal (Tarea 18) ----------------------------------------


def test_el_ambito_va_en_la_ruta():
    """§2.4: en la RUTA y no en un parametro de consulta ni en la sesion, porque
    el service worker de la tanda 6 cachea por URL."""
    assert reverse("budget:mes", args=["household"]).startswith("/budget/household/")
    assert reverse("budget:mes", args=["personal"]).startswith("/budget/personal/")


def test_un_ambito_inventado_da_404(client, admin_con_hogar):
    user, _hogar = admin_con_hogar
    client.force_login(user)
    assert client.get("/budget/marciano/month/").status_code == 404


def test_personal_solo_ensena_lo_del_miembro(client, admin_con_hogar):
    """§2.4: Hogar y Personal son la misma vista con un filtro, no dos vistas."""
    from tests.factories_budget import BudgetMonthFactory, TransactionFactory

    user, hogar = admin_con_hogar
    client.force_login(user)
    mia = hogar.memberships.get(user=user)
    otra = MembershipFactory(household=hogar)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=3)
    cat = CategoryFactory(household=hogar)

    TransactionFactory(household=hogar, budget_month=mes, category=cat,
                       member=mia, scope="personal", amount=Decimal("10.00"),
                       date=date(2026, 3, 2))
    TransactionFactory(household=hogar, budget_month=mes, category=cat,
                       member=otra, scope="personal", amount=Decimal("99.00"),
                       date=date(2026, 3, 3))

    respuesta = client.get(reverse("budget:mes", args=["personal", 2026, 3]))
    importes = [tx.amount for tx in respuesta.context["transacciones"]]

    assert Decimal("10.00") in importes
    assert Decimal("99.00") not in importes


def test_el_ambito_del_hogar_no_ensena_lo_personal_de_nadie(client, admin_con_hogar):
    """El otro lado del filtro, que el plan no pedia. Sin esta, `acotar` podria
    devolver el queryset sin filtrar en Hogar y nadie lo notaria: la prueba de
    arriba solo mira Personal.
    """
    from tests.factories_budget import BudgetMonthFactory, TransactionFactory

    user, hogar = admin_con_hogar
    client.force_login(user)
    mia = hogar.memberships.get(user=user)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=4)
    cat = CategoryFactory(household=hogar)

    TransactionFactory(household=hogar, budget_month=mes, category=cat,
                       member=mia, scope="personal", amount=Decimal("77.00"),
                       date=date(2026, 4, 2))
    TransactionFactory(household=hogar, budget_month=mes, category=cat,
                       member=mia, scope="household", amount=Decimal("55.00"),
                       date=date(2026, 4, 3))

    respuesta = client.get(reverse("budget:mes", args=["household", 2026, 4]))
    importes = [tx.amount for tx in respuesta.context["transacciones"]]

    assert Decimal("55.00") in importes
    assert Decimal("77.00") not in importes


def test_las_dos_pantallas_nuevas_resuelven_en_los_dos_ambitos(client, admin_con_hogar):
    """Overview y Balance estan vacias hasta las Tareas 19 y 20, pero sus rutas
    tienen que resolver ya: el menu de la Tarea 18 enlaza a Overview."""
    user, _hogar = admin_con_hogar
    client.force_login(user)
    for ambito in ("household", "personal"):
        assert client.get(reverse("budget:overview", args=[ambito])).status_code == 200
        assert client.get(reverse("budget:balance", args=[ambito])).status_code == 200


# --- el Overview (Tarea 19) ---------------------------------------------------


def test_el_overview_da_las_series_ya_serializadas(client, admin_con_hogar):
    import json

    from django.utils import timezone
    from tests.factories_budget import (
        BudgetLineFactory, BudgetMonthFactory, TransactionFactory,
    )

    user, hogar = admin_con_hogar
    client.force_login(user)
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    cat = CategoryFactory(household=hogar, slug="una-categoria-de-prueba")
    BudgetLineFactory(household=hogar, budget_month=mes, category=cat,
                      kind="expense", planned_amount=Decimal("400.00"))
    TransactionFactory(household=hogar, budget_month=mes, category=cat,
                       amount=Decimal("350.00"), date=date(hoy.year, hoy.month, 4))

    respuesta = client.get(reverse("budget:overview", args=["household"]))

    assert respuesta.status_code == 200
    series = respuesta.context["series_categorias"]
    # etiqueta() es un metodo, no una property: en plantilla Django lo llama
    # solo, en Python hay que llamarlo.
    assert cat.etiqueta() in series["etiquetas"]
    # Serializable de verdad: ni un Decimal suelto, que es lo que json_script
    # no sabe convertir.
    assert json.dumps(series)
    assert json.dumps(respuesta.context["series_balance"])


def test_el_overview_personal_no_cuenta_lo_del_hogar(client, admin_con_hogar):
    """Las series tambien pasan por el filtro de ambito, no solo las tablas."""
    from django.utils import timezone
    from tests.factories_budget import BudgetMonthFactory, TransactionFactory

    user, hogar = admin_con_hogar
    client.force_login(user)
    mia = hogar.memberships.get(user=user)
    hoy = timezone.localdate()
    mes = BudgetMonthFactory(household=hogar, year=hoy.year, month=hoy.month)
    cat = CategoryFactory(household=hogar, slug="una-categoria-de-prueba")
    TransactionFactory(household=hogar, budget_month=mes, category=cat, member=mia,
                       scope="household", amount=Decimal("500.00"),
                       date=date(hoy.year, hoy.month, 5))

    series = client.get(
        reverse("budget:overview", args=["personal"])
    ).context["series_categorias"]

    assert "500.00" not in series["real"]


# --- el Balance (Tarea 20) ----------------------------------------------------


def test_balance_ensena_la_varianza_por_categoria(client, admin_con_hogar):
    from apps.budget.models import MonthlyClose
    from tests.factories_budget import BudgetMonthFactory

    user, hogar = admin_con_hogar
    client.force_login(user)
    mes = BudgetMonthFactory(household=hogar, year=2026, month=2, status="closed")
    cat = CategoryFactory(household=hogar, slug="una-categoria-de-prueba")
    MonthlyClose.unscoped.create(
        household=hogar, budget_month=mes,
        ingresos_presupuestados=Decimal("3000.00"), ingresos_reales=Decimal("3000.00"),
        egresos_presupuestados=Decimal("400.00"), egresos_reales=Decimal("475.00"),
        varianza_por_categoria={str(cat.pk): "-75.00"},
        balance=Decimal("2525.00"), arrastre=Decimal("2525.00"),
    )

    respuesta = client.get(reverse("budget:balance", args=["household"]))

    assert respuesta.status_code == 200
    fila = respuesta.context["cierres"][0]
    assert fila["cierre"].balance == Decimal("2525.00")
    varianzas = {v["categoria"].pk: v["importe"] for v in fila["varianza"]}
    # Decimal reconstruido al leer, no el str que guarda el JSON (§1 del spec).
    assert varianzas[cat.pk] == Decimal("-75.00")
    assert isinstance(varianzas[cat.pk], Decimal)


def test_balance_exige_can_view_reports(client, admin_con_hogar):
    """El plan decia can_view_budget para esta vista. Balance ES un informe, y
    can_view_reports existe en el §6.2 para eso: con can_view_budget, un miembro
    al que se le nego ver informes los veria igual.
    """
    _user, hogar = admin_con_hogar
    solo_presupuesto = _miembro(hogar, can_view_budget=True, can_view_reports=False)
    client.force_login(solo_presupuesto.user)

    assert client.get(reverse("budget:balance", args=["household"])).status_code == 403


def test_balance_sin_cierres_lo_dice_y_no_revienta(client, admin_con_hogar):
    user, _hogar = admin_con_hogar
    client.force_login(user)

    respuesta = client.get(reverse("budget:balance", args=["household"]))

    assert respuesta.status_code == 200
    assert respuesta.context["cierres"] == []
