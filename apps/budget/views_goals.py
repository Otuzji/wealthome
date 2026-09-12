"""Las metas de ahorro: verlas, crearlas y aportar.

`metas` lleva ambito porque Goal tiene `scope` y `owner`: una meta personal es
de su dueno y no del hogar. Las altas no lo llevan — el formulario decide el
ambito de la fila.
"""

from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services
from .forms import GoalContributionForm, GoalForm
from .models import Goal, MesCerrado
from .scopes import acotar_por_dueno, validar
from .views_setup import crear


@requiere_permiso("can_view_budget")
def metas(request, hogar, ambito):
    ambito = validar(ambito)
    membresia = membresia_actual(request)
    filas = []
    for meta in acotar_por_dueno(Goal.objects.for_household(hogar), ambito, membresia):
        acumulado = meta.acumulado()
        aporte, fecha = meta.derivar(acumulado=acumulado)
        filas.append({"meta": meta, "aporte": aporte, "fecha": fecha,
                      "acumulado": acumulado})
    return render(request, "budget/metas.html", {"filas": filas, "ambito": ambito})


@requiere_permiso("can_edit_budget")
def meta_nueva(request, hogar):
    return crear(request, hogar, GoalForm, _("New goal"),
                 destino="budget:metas", destino_args=("household",))


@requiere_permiso("can_edit_budget")
def aportar(request, hogar):
    form = GoalContributionForm(request.POST or None, household=hogar)
    if request.method == "POST" and form.is_valid():
        aporte = form.save(commit=False)
        aporte.household = hogar
        aporte.member = membresia_actual(request)
        aporte.budget_month = services.mes_de_fecha(hogar, aporte.date)
        try:
            aporte.full_clean()
            aporte.save()
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        else:
            return redirect("budget:metas", "household")
    return render(request, "budget/formulario.html",
                  {"form": form, "titulo": _("Add to a goal")})
