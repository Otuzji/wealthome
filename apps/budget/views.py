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
from .forms import (
    AllocationRuleForm,
    CategoryForm,
    ExpenseRuleForm,
    IncomeSourceForm,
    TransactionForm,
)
from .models import AllocationRule, Category, ExpenseRule, IncomeSource


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
