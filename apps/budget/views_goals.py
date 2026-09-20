"""Las metas de ahorro: verlas, crearlas, corregirlas y aportar.

`metas` lleva ambito porque Goal tiene `scope` y `owner`: una meta personal es
de su dueno y no del hogar. Las escrituras no lo llevan: la fila ya sabe su
ambito, y a el se vuelve.
"""

from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services, services_goals
from .forms import GoalContributionForm, GoalForm
from .models import Goal, GoalContribution, MesCerrado
from .scopes import acotar_por_dueno, validar
from .views_setup import crear


def _con_aportes(queryset, hogar):
    """Los aportes de cada meta en UNA consulta, con quien los hizo y su mes:
    resumen() suma en Python y decide que aporte se puede tocar sin volver a
    la base."""
    return queryset.prefetch_related(
        Prefetch(
            "contributions",
            queryset=GoalContribution.objects.for_household(hogar)
            .select_related("member__user", "budget_month"),
        )
    )


@requiere_permiso("can_view_budget")
def metas(request, hogar, ambito):
    ambito = validar(ambito)
    membresia = membresia_actual(request)
    consulta = _con_aportes(
        acotar_por_dueno(Goal.objects.for_household(hogar), ambito, membresia), hogar
    )
    filas = services_goals.resumen(hogar, consulta)
    por_estado = {Goal.ACTIVE: [], Goal.REACHED: [], Goal.ABANDONED: []}
    for fila in filas:
        por_estado[fila["meta"].status].append(fila)
    return render(request, "budget/metas.html", {
        # `filas` sigue existiendo: las pruebas de la Tarea 21 leen de ahi.
        "filas": filas, "ambito": ambito,
        "activas": por_estado[Goal.ACTIVE],
        "alcanzadas": por_estado[Goal.REACHED],
        "abandonadas": por_estado[Goal.ABANDONED],
    })


@requiere_permiso("can_edit_budget")
def meta_nueva(request, hogar):
    return crear(request, hogar, GoalForm, _("New goal"),
                 destino="budget:metas", destino_args=("household",))


@requiere_permiso("can_edit_budget")
def aportar(request, hogar):
    """Mismo patron que `registrar`, para no inventar un segundo."""
    es_htmx = request.headers.get("HX-Request") == "true"
    form = GoalContributionForm(request.POST or None, household=hogar,
                                membresia=membresia_actual(request))
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

    plantilla = ("budget/_fragmentos/aporte_form.html" if es_htmx
                 else "budget/formulario.html")
    return render(request, plantilla, {"form": form, "titulo": _("Add to a goal")})
