"""La configuracion del presupuesto: reglas, categorias y reparto.

Estas pantallas NO llevan ambito. Se configura el hogar, y lo personal de un
miembro no tiene reglas propias (§7.1).

Primer uso real de `@requiere_permiso`: el decorador resuelve el hogar de la
peticion, comprueba el permiso del §6.2 y pasa el hogar como segundo
argumento. Ninguna vista elige "el" hogar por su cuenta.
"""

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.households.permissions import requiere_permiso

from .forms import (
    AllocationRuleForm,
    CategoryForm,
    ExpenseRuleForm,
    IncomeSourceForm,
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


def crear(request, hogar, form_class, titulo, destino="budget:configurar", destino_args=()):
    """Un formulario de alta, con el hogar acotado por la base segura.

    El `full_clean()` tras fijar el hogar es lo que hace que un POST con el id
    de una fila ajena falle aunque alguien se saltara el formulario: el
    `clean()` del modelo comprueba el hogar de cada relación.

    Vive aqui y no en cada modulo porque lo comparten las altas de setup y las
    de metas, y duplicarlo es como divergen dos formularios que deberian
    validar igual.
    """
    return _guardar(request, hogar, form_class(request.POST or None, household=hogar),
                    titulo, destino, destino_args)


def editar(request, hogar, modelo, form_class, pk, titulo):
    """La edicion EN SITIO de una regla (ingreso, gasto fijo o reparto).

    No es la sucesora del §3.2 —`services.reemplazar_regla`—: un importe mal
    tecleado es una correccion, no un cambio en el tiempo. Y corregir en sitio
    no reescribe historia: el mes abierto ya copio `planned_amount` en sus
    lineas y los cerrados son inmutables, asi que solo cambian las proyecciones.

    `for_household` antes que `get_object_or_404`: el pk de otra familia es un
    404 identico al de un pk inventado, sin decir cual de los dos fue.
    """
    objeto = get_object_or_404(modelo.objects.for_household(hogar), pk=pk)
    form = form_class(request.POST or None, household=hogar, instance=objeto)
    return _guardar(request, hogar, form, titulo)


def _guardar(request, hogar, form, titulo, destino="budget:configurar", destino_args=()):
    if request.method == "POST" and form.is_valid():
        objeto = form.save(commit=False)
        objeto.household = hogar
        try:
            objeto.full_clean()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            objeto.save()
            return redirect(destino, *destino_args)
    return render(request, "budget/formulario.html", {"form": form, "titulo": titulo})


@requiere_permiso("can_edit_budget")
def ingreso_nuevo(request, hogar):
    return crear(request, hogar, IncomeSourceForm, _("New income"))


@requiere_permiso("can_edit_budget")
def gasto_nuevo(request, hogar):
    return crear(request, hogar, ExpenseRuleForm, _("New fixed expense"))


@requiere_permiso("can_edit_budget")
def categoria_nueva(request, hogar):
    return crear(request, hogar, CategoryForm, _("New category"))


@requiere_permiso("can_edit_budget")
def reparto_nuevo(request, hogar):
    return crear(request, hogar, AllocationRuleForm, _("New split rule"))


@requiere_permiso("can_edit_budget")
def ingreso_editar(request, hogar, pk):
    return editar(request, hogar, IncomeSource, IncomeSourceForm, pk, _("Edit income"))


@requiere_permiso("can_edit_budget")
def gasto_editar(request, hogar, pk):
    return editar(request, hogar, ExpenseRule, ExpenseRuleForm, pk, _("Edit fixed expense"))


@requiere_permiso("can_edit_budget")
def reparto_editar(request, hogar, pk):
    return editar(request, hogar, AllocationRule, AllocationRuleForm, pk, _("Edit split rule"))


def borrar(request, hogar, modelo, pk):
    """Quitar una regla. Solo por POST: un GET no destruye nada.

    Las lineas ya materializadas se quedan (las FK son SET_NULL): el mes en
    curso conto con ese gasto, y borrar la regla es "de ahora en adelante".
    """
    objeto = get_object_or_404(modelo.objects.for_household(hogar), pk=pk)
    objeto.delete()
    return redirect("budget:configurar")


@require_POST
@requiere_permiso("can_edit_budget")
def ingreso_borrar(request, hogar, pk):
    return borrar(request, hogar, IncomeSource, pk)


@require_POST
@requiere_permiso("can_edit_budget")
def gasto_borrar(request, hogar, pk):
    return borrar(request, hogar, ExpenseRule, pk)


@require_POST
@requiere_permiso("can_edit_budget")
def reparto_borrar(request, hogar, pk):
    return borrar(request, hogar, AllocationRule, pk)
