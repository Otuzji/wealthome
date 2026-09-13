"""Siembra un hogar de demostracion en la base de DESARROLLO.

Para qué existe: la base de desarrollo nace vacía, y una aplicación de
presupuesto vacía no se puede juzgar. Con esto, las nueve pantallas tienen algo
que enseñar — incluido el mes cerrado que Balance necesita para tener varianza, y
el ajuste de mesada que hace visible la explicación del §4.5.3.

    .venv/Scripts/python.exe scripts/sembrar_demo.py

Idempotente: si el correo ya existe, borra ese hogar entero y lo vuelve a
sembrar. Para dejar la base como estaba:

    .venv/Scripts/python.exe scripts/sembrar_demo.py --borrar

NO se usa en pruebas. Es una herramienta de desarrollo, y no toca nada que no
sea el hogar de demostración.
"""

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.budget import services  # noqa: E402
from apps.budget.engine import cascade as motor_cascade  # noqa: E402
from apps.budget.engine import income as motor_income  # noqa: E402
from apps.budget.engine.periodicity import MONTHLY  # noqa: E402
from apps.budget.models import (  # noqa: E402
    AllocationRule,
    AllowanceLedger,
    Category,
    ExpenseRule,
    Goal,
    GoalContribution,
    IncomeSource,
    Transaction,
)
from apps.households.models import Household, Membership  # noqa: E402
from apps.households.services import crear_hogar  # noqa: E402

CORREO_ADMIN = "demo@wealthome.test"
CORREO_PAREJA = "pareja@wealthome.test"
CORREO_HIJO = "hijo@wealthome.test"
CLAVE = "wealthome-demo-2026"
NOMBRE_HOGAR = "Hogar de demostracion"


def _categoria(hogar, slug):
    return Category.objects.for_household(hogar).get(slug=slug)


def _primer_slug(hogar, kind, *preferidos):
    """La primera categoria que exista de las preferidas, o cualquiera del tipo.

    El arbol sembrado puede cambiar entre planes; esto evita que el sembrador se
    rompa por un slug renombrado.
    """
    for slug in preferidos:
        fila = Category.objects.for_household(hogar).filter(slug=slug).first()
        if fila is not None:
            return fila
    return Category.objects.for_household(hogar).filter(kind=kind).first()


def borrar():
    """Borra el hogar de demostracion y sus usuarios. Nada mas."""
    hogares = Household.objects.filter(name=NOMBRE_HOGAR)
    n = hogares.count()
    for hogar in hogares:
        hogar.delete()          # CASCADE se lleva todo lo del hogar
    User.objects.filter(email__in=[CORREO_ADMIN, CORREO_PAREJA, CORREO_HIJO]).delete()
    print(f"borrados {n} hogar(es) de demostracion y sus usuarios")


@transaction.atomic
def sembrar():
    hoy = timezone.localdate()

    admin = User.objects.create_user(
        email=CORREO_ADMIN, password=CLAVE, display_name="Ana"
    )
    hogar = crear_hogar(admin, NOMBRE_HOGAR, family_size=3)
    membresia_admin = hogar.memberships.get(user=admin)

    # --- los otros dos miembros, con los perfiles del §6.2 ------------------
    pareja_user = User.objects.create_user(
        email=CORREO_PAREJA, password=CLAVE, display_name="Beto"
    )
    pareja = Membership.objects.create(
        user=pareja_user, household=hogar, role=Membership.MEMBER,
        can_view_budget=True, can_edit_budget=True,
        can_add_transactions=True, can_view_reports=True,
    )
    # El adolescente: registra sus gastos y no ve la hipoteca.
    hijo_user = User.objects.create_user(
        email=CORREO_HIJO, password=CLAVE, display_name="Carla"
    )
    Membership.objects.create(
        user=hijo_user, household=hogar, role=Membership.MEMBER,
        can_view_budget=False, can_edit_budget=False,
        can_add_transactions=True, can_view_reports=False,
    )

    # --- ingresos ----------------------------------------------------------
    cat_ingreso = _primer_slug(hogar, "income", "salary", "income")
    IncomeSource.unscoped.create(
        household=hogar, owner=membresia_admin, name="Sueldo de Ana",
        source_type="salary", amount_type=motor_income.FIXED,
        amount=Decimal("3200.00"), periodicity=MONTHLY,
        effective_from=date(hoy.year - 1, 1, 1),
    )
    IncomeSource.unscoped.create(
        household=hogar, owner=pareja, name="Sueldo de Beto",
        source_type="salary", amount_type=motor_income.FIXED,
        amount=Decimal("2400.00"), periodicity=MONTHLY,
        effective_from=date(hoy.year - 1, 1, 1),
    )

    # --- gastos fijos ------------------------------------------------------
    fijos = [
        ("Alquiler", "rent", Decimal("1750.00")),
        ("Supermercado", "groceries", Decimal("850.00")),
        ("Electricidad", "utilities", Decimal("180.00")),
        ("Transporte", "transport", Decimal("220.00")),
    ]
    for nombre, slug, importe in fijos:
        categoria = _primer_slug(hogar, "expense", slug)
        if categoria is None:
            continue
        ExpenseRule.unscoped.create(
            household=hogar, category=categoria, name=nombre, amount=importe,
            periodicity=MONTHLY, effective_from=date(hoy.year - 1, 1, 1),
        )

    # --- una meta de ahorro, ya empezada -----------------------------------
    meta = Goal.unscoped.create(
        household=hogar, name="Viaje a Gaspesie",
        contribution_mode="by_monthly_amount",
        target_amount=Decimal("2400.00"), monthly_amount=Decimal("200.00"),
    )
    GoalContribution.unscoped.create(
        household=hogar, goal=meta, member=membresia_admin,
        amount=Decimal("400.00"), date=hoy - timedelta(days=70),
    )
    GoalContribution.unscoped.create(
        household=hogar, goal=meta, member=None, origen="cascade",
        amount=Decimal("200.00"), date=hoy - timedelta(days=40),
    )

    # --- las reglas del reparto: el ahorro ARRIBA, las mesadas abajo -------
    AllocationRule.unscoped.create(
        household=hogar, order=1, target_type=motor_cascade.GOAL,
        target_goal=meta, method=motor_cascade.FIXED,
        amount=Decimal("200.00"), is_active=True,
    )
    AllocationRule.unscoped.create(
        household=hogar, order=2, target_type=motor_cascade.ALLOWANCE,
        method=motor_cascade.FIXED, amount=Decimal("150.00"),
        split="equal", is_active=True,
    )

    # --- el mes ANTERIOR, cerrado, para que Balance tenga varianza ---------
    primero_de_este = date(hoy.year, hoy.month, 1)
    anterior = primero_de_este - timedelta(days=1)
    mes_anterior = services.materializar(hogar, anterior.year, anterior.month)
    services.planificar_mes(hogar, mes_anterior, Decimal("1200.00"))

    cat_super = _primer_slug(hogar, "expense", "groceries")
    cat_ocio = _primer_slug(hogar, "expense", "fun", "leisure", "entertainment")

    # Los ingresos REALES del mes cerrado. Sin ellos, el cierre da un balance
    # negativo y la varianza culpa a la categoria de ingreso de todo el hueco:
    # el Balance se ve, pero cuenta una mentira.
    if cat_ingreso is not None:
        for quien, importe in ((membresia_admin, Decimal("3200.00")),
                               (pareja, Decimal("2400.00"))):
            Transaction.unscoped.create(
                household=hogar, budget_month=mes_anterior, category=cat_ingreso,
                member=quien, amount=importe,
                date=date(anterior.year, anterior.month, 1), scope="household",
            )

    # Se gasto MAS de lo planeado en el super: eso es la varianza que se vera.
    Transaction.unscoped.create(
        household=hogar, budget_month=mes_anterior, category=cat_super,
        member=membresia_admin, amount=Decimal("925.40"),
        date=date(anterior.year, anterior.month, 12), scope="household",
    )
    if cat_ocio is not None:
        Transaction.unscoped.create(
            household=hogar, budget_month=mes_anterior, category=cat_ocio,
            member=pareja, amount=Decimal("78.00"),
            date=date(anterior.year, anterior.month, 20), scope="personal",
        )
    services.cerrar_mes(mes_anterior)

    # --- el mes CORRIENTE, planificado y con movimientos -------------------
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    services.planificar_mes(hogar, mes, Decimal("1200.00"))

    movimientos = [
        (cat_ingreso, membresia_admin, Decimal("3200.00"), 1, "household"),
        (cat_ingreso, pareja, Decimal("2400.00"), 1, "household"),
        (cat_super, membresia_admin, Decimal("132.75"), 2, "household"),
        (cat_super, pareja, Decimal("64.20"), 5, "household"),
        (cat_ocio, membresia_admin, Decimal("22.50"), 6, "personal"),
        (cat_ocio, pareja, Decimal("41.00"), 8, "personal"),
    ]
    for categoria, quien, importe, dia, ambito in movimientos:
        if categoria is None or dia > hoy.day:
            continue
        Transaction.unscoped.create(
            household=hogar, budget_month=mes, category=categoria,
            member=quien, amount=importe,
            date=date(hoy.year, hoy.month, dia), scope=ambito,
        )

    # --- el ajuste de la mesada, que es lo que hace visible el §4.5.3 ------
    libro = (
        AllowanceLedger.objects.for_household(hogar)
        .filter(member=membresia_admin, budget_month=mes)
        .first()
    )
    if libro is not None:
        libro.carried_in = Decimal("18.00")
        libro.adjustment = Decimal("-35.00")
        libro.spent = Decimal("22.50")
        libro.save(update_fields=["carried_in", "adjustment", "spent"])

    return hogar


def main():
    if "--borrar" in sys.argv:
        borrar()
        return

    if User.objects.filter(email=CORREO_ADMIN).exists():
        print("ya existia: lo borro y lo vuelvo a sembrar")
        borrar()

    hogar = sembrar()
    print()
    print(f"Sembrado: {hogar.name}  (id {hogar.pk})")
    print()
    print("  Entra en  http://127.0.0.1:8000/login/")
    print(f"  Admin        {CORREO_ADMIN}   {CLAVE}")
    print(f"  Pareja       {CORREO_PAREJA}   {CLAVE}")
    print(f"  Adolescente  {CORREO_HIJO}   {CLAVE}   (solo registrar gastos)")
    print()
    print("  Para dejar la base como estaba:")
    print("    .venv/Scripts/python.exe scripts/sembrar_demo.py --borrar")


if __name__ == "__main__":
    main()
