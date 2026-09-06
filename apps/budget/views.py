"""Las pantallas del presupuesto.

Primer uso real de `@requiere_permiso`: el decorador resuelve el hogar de la
petición, comprueba el permiso del §6.2 y pasa el hogar como segundo
argumento. Ninguna vista elige "el" hogar por su cuenta.
"""

from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services
from .engine.cascade import repartir
from .forms import (
    AllocationRuleForm,
    CategoryForm,
    ExpenseRuleForm,
    GoalContributionForm,
    GoalForm,
    IncomeSourceForm,
    TransactionForm,
)
from .models import (
    AllocationRule,
    Category,
    ExpenseRule,
    Goal,
    IncomeSource,
    MesCerrado,
)


@requiere_permiso("can_edit_budget")
def configurar(request, hogar):
    return render(request, "budget/configurar.html", {
        "ingresos": IncomeSource.objects.for_household(hogar).select_related("owner__user"),
        "gastos": ExpenseRule.objects.for_household(hogar).select_related("category"),
        "categorias": Category.objects.for_household(hogar).order_by("parent_id", "slug"),
        "repartos": AllocationRule.objects.for_household(hogar),
    })


def _crear(request, hogar, form_class, titulo):
    """Un formulario de alta, con el hogar acotado por la base segura.

    El `full_clean()` tras fijar el hogar es lo que hace que un POST con el id
    de una fila ajena falle aunque alguien se saltara el formulario: el
    `clean()` del modelo comprueba el hogar de cada relación.
    """
    form = form_class(request.POST or None, household=hogar)
    if request.method == "POST" and form.is_valid():
        objeto = form.save(commit=False)
        objeto.household = hogar
        try:
            objeto.full_clean()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            objeto.save()
            return redirect("budget:configurar")
    return render(request, "budget/formulario.html", {"form": form, "titulo": titulo})


@requiere_permiso("can_edit_budget")
def ingreso_nuevo(request, hogar):
    return _crear(request, hogar, IncomeSourceForm, _("New income"))


@requiere_permiso("can_edit_budget")
def gasto_nuevo(request, hogar):
    return _crear(request, hogar, ExpenseRuleForm, _("New fixed expense"))


@requiere_permiso("can_edit_budget")
def categoria_nueva(request, hogar):
    return _crear(request, hogar, CategoryForm, _("New category"))


@requiere_permiso("can_edit_budget")
def reparto_nuevo(request, hogar):
    return _crear(request, hogar, AllocationRuleForm, _("New split rule"))


@requiere_permiso("can_add_transactions")
def registrar(request, hogar):
    """La acción más frecuente de la aplicación (§7.1)."""
    hoy = timezone.localdate()
    form = TransactionForm(request.POST or None, household=hogar,
                           initial={"date": hoy})
    if request.method == "POST" and form.is_valid():
        mes = services.obtener_mes(hogar, hoy.year, hoy.month)
        tx = form.save(commit=False)
        tx.household = hogar
        tx.budget_month = mes
        tx.merchant = form.comercio()
        tx.member = membresia_actual(request)
        tx.full_clean()
        tx.save()
        return redirect("budget:registrar")
    return render(request, "budget/gasto.html", {"form": form})


@requiere_permiso("can_view_budget")
def mes(request, hogar, anio=None, numero=None):
    hoy = timezone.localdate()
    anio = anio or hoy.year
    numero = numero or hoy.month
    resultado = services.obtener_mes(hogar, anio, numero)
    return render(request, "budget/mes.html", {
        "resultado": resultado,
        "es_proyeccion": isinstance(resultado, services.ProyeccionDeMes),
        "anio": anio, "numero": numero,
    })


@requiere_permiso("can_edit_budget")
def planificar(request, hogar):
    """El asistente del §4.5.6, en una sola pantalla.

    Los tres pasos del spec —ingresos, salidas, reparto— se presentan juntos
    porque el Plan 3 rehará la navegación; lo que importa aquí es que el
    cálculo y la escritura sean los definitivos.
    """
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    proyeccion = services.proyectar(hogar, hoy.year, hoy.month)

    if request.method == "POST":
        services.planificar_mes(hogar, mes_actual, proyeccion.sobrante)
        return redirect("budget:mes")

    reglas_orm = {
        r.order: r
        for r in AllocationRule.objects.for_household(hogar).filter(is_active=True)
    }
    reglas = [
        r.a_regla_de_reparto(services.miembros_activos(hogar))
        for r in reglas_orm.values()
    ]
    # Con nombre y destino, no solo importes: §13.5 dice que cada uno sepa
    # cuánta mesada tiene, y un número suelto en una lista no dice de quién es.
    miembros = {m.pk: m for m in hogar.active_memberships()}
    asignaciones = [
        {
            "importe": a.importe,
            "miembro": miembros.get(a.miembro_id),
            "regla": reglas_orm[a.orden],
        }
        for a in repartir(proyeccion.sobrante, reglas)
    ]
    return render(request, "budget/planificar.html", {
        "proyeccion": proyeccion,
        "asignaciones": asignaciones,
        "mes": mes_actual,
    })


@requiere_permiso("can_edit_budget")
def cerrar(request, hogar):
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    if request.method == "POST":
        try:
            services.cerrar_mes(mes_actual)
        except MesCerrado:
            pass   # ya estaba cerrado: idempotente, no un error del usuario
        return redirect("budget:mes")
    return render(request, "budget/cerrar.html", {"mes": mes_actual})


@requiere_permiso("can_view_budget")
def metas(request, hogar):
    filas = []
    for meta in Goal.objects.for_household(hogar):
        aporte, fecha = meta.derivar()
        filas.append({"meta": meta, "aporte": aporte, "fecha": fecha,
                      "acumulado": meta.acumulado()})
    return render(request, "budget/metas.html", {"filas": filas})


@requiere_permiso("can_edit_budget")
def meta_nueva(request, hogar):
    return _crear(request, hogar, GoalForm, _("New goal"))


@requiere_permiso("can_edit_budget")
def aportar(request, hogar):
    form = GoalContributionForm(request.POST or None, household=hogar)
    if request.method == "POST" and form.is_valid():
        aporte = form.save(commit=False)
        aporte.household = hogar
        aporte.member = membresia_actual(request)
        aporte.full_clean()
        aporte.save()
        return redirect("budget:metas")
    return render(request, "budget/formulario.html",
                  {"form": form, "titulo": _("Add to a goal")})
