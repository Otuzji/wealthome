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

    # prefetch_related porque acumulado() agrega sobre esa relacion y la
    # plantilla lista los aportes: sin el, una consulta por meta y otra por
    # meta para la tabla.
    consulta = acotar_por_dueno(
        Goal.objects.for_household(hogar), ambito, membresia
    ).prefetch_related("contributions__member__user")

    filas = []
    for meta in consulta:
        acumulado = meta.acumulado()
        aporte, fecha = meta.derivar(acumulado=acumulado)
        bruto = (acumulado / meta.target_amount * 100) if meta.target_amount else 0
        filas.append({
            "meta": meta, "aporte": aporte, "fecha": fecha,
            "acumulado": acumulado,
            # Dos numeros y no uno: el porcentaje real es un dato ("119%" no es
            # un error), pero la barra se acota a 100 o se sale de su caja.
            "porcentaje": int(bruto),
            "porcentaje_barra": min(100, int(bruto)),
        })
    return render(request, "budget/metas.html", {"filas": filas, "ambito": ambito})


@requiere_permiso("can_edit_budget")
def meta_nueva(request, hogar):
    return crear(request, hogar, GoalForm, _("New goal"),
                 destino="budget:metas", destino_args=("household",))


@requiere_permiso("can_edit_budget")
def aportar(request, hogar):
    """Mismo patron que `registrar`, para no inventar un segundo."""
    es_htmx = request.headers.get("HX-Request") == "true"
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
            if es_htmx:
                return render(request, "budget/_fragmentos/aportes.html", {
                    "meta": aporte.goal,
                    "aportes": aporte.goal.contributions.select_related("member__user"),
                })
            return redirect("budget:metas", "household")

    plantilla = ("budget/_fragmentos/aporte_form.html" if es_htmx
                 else "budget/formulario.html")
    return render(request, plantilla, {"form": form, "titulo": _("Add to a goal")})
