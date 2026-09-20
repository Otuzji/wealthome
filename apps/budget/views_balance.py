"""El balance del hogar: activos, pasivos y patrimonio neto.

Verlo es un informe (`can_view_reports`); anadir, corregir y quitar una
linea es configurar el hogar (`can_edit_budget`), como una regla del setup.
Las escrituras no llevan ambito: el balance es del hogar, y a el se vuelve.
"""

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services_balance
from .forms import BalanceItemForm
from .models import BalanceItem
from .scopes import HOGAR, validar


@requiere_permiso("can_view_reports")
def balance(request, hogar, ambito):
    ambito = validar(ambito)
    return render(request, "budget/balance.html", {
        "ambito": ambito,
        "patrimonio": services_balance.patrimonio(hogar, membresia_actual(request)),
    })


def _volver():
    return redirect("budget:balance", HOGAR)


def _formulario(request, hogar, form, titulo):
    if request.method == "POST" and form.is_valid():
        form.save()
        return _volver()
    return render(request, "budget/formulario.html", {
        "form": form, "titulo": titulo,
        "cancelar": reverse("budget:balance", args=[HOGAR]),
    })


@requiere_permiso("can_edit_budget")
def item_nuevo(request, hogar):
    """`group` puede venir en la query: el boton "Add" de cada grupo lo trae
    ya elegido. Solo rellena; el formulario valida igual."""
    initial = {}
    if request.GET.get("group") in dict(BalanceItem._meta.get_field("group").choices):
        initial["group"] = request.GET["group"]
    form = BalanceItemForm(request.POST or None, household=hogar, initial=initial)
    return _formulario(request, hogar, form, _("New balance item"))


def _item(hogar, pk):
    """`for_household` antes que `get_object_or_404`: el pk de otra familia
    es un 404 identico al de un pk inventado."""
    return get_object_or_404(BalanceItem.objects.for_household(hogar), pk=pk)


@requiere_permiso("can_edit_budget")
def item_editar(request, hogar, pk):
    form = BalanceItemForm(request.POST or None, household=hogar, instance=_item(hogar, pk))
    return _formulario(request, hogar, form, _("Edit balance item"))


@require_POST
@requiere_permiso("can_edit_budget")
def item_borrar(request, hogar, pk):
    """Solo por POST: un GET no destruye nada."""
    _item(hogar, pk).delete()
    return _volver()
