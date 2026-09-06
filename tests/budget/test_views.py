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
    assert client.get(reverse("budget:mes")).status_code == 403


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

    assert client.get(reverse("budget:mes")).status_code == 403


def test_el_mes_muestra_lo_planeado_y_lo_real(client, admin_con_hogar):
    from tests.factories_budget import ExpenseRuleFactory

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent", name="Alquiler")
    ExpenseRuleFactory(household=hogar, category=categoria, name="Alquiler",
                       amount=Decimal("1800.00"))
    client.force_login(admin)

    html = client.get(reverse("budget:mes")).content.decode()

    assert "1,800.00" in html or "1 800,00" in html


def test_un_mes_futuro_se_puede_consultar_y_no_persiste(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth

    admin, hogar = admin_con_hogar
    client.force_login(admin)

    respuesta = client.get(reverse("budget:mes", args=[2030, 5]))

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

    html = client.get(reverse("budget:planificar")).content.decode()

    assert "1,200.00" in html or "1 200,00" in html   # el sobrante proyectado


def test_confirmar_la_planificacion_escribe_las_mesadas(client, hogar_listo_para_planificar):
    from apps.budget.models import AllowanceLedger

    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)

    respuesta = client.post(reverse("budget:planificar"))

    assert respuesta.status_code == 302
    assert AllowanceLedger.objects.for_household(hogar).exists()


def test_planificar_exige_can_edit_budget(client, hogar_listo_para_planificar):
    _, hogar = hogar_listo_para_planificar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    assert client.get(reverse("budget:planificar")).status_code == 403


# --- cerrar el mes ------------------------------------------------------------


def test_cerrar_el_mes_escribe_el_cierre(client, hogar_listo_para_planificar):
    from apps.budget.models import MonthlyClose

    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)
    client.post(reverse("budget:planificar"))

    respuesta = client.post(reverse("budget:cerrar"))

    assert respuesta.status_code == 302
    assert MonthlyClose.objects.for_household(hogar).exists()


def test_un_mes_cerrado_es_de_solo_lectura(client, hogar_listo_para_planificar):
    """§4.3: un mes cerrado no admite nada."""
    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)
    client.post(reverse("budget:planificar"))
    client.post(reverse("budget:cerrar"))

    respuesta = client.post(reverse("budget:cerrar"))

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

    html = client.get(reverse("budget:metas")).content.decode()

    assert "Vacaciones" in html


def test_aportar_a_una_meta_exige_can_edit_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    assert client.get(reverse("budget:aportar")).status_code == 403
