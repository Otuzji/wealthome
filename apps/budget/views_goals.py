"""Las metas de ahorro: verlas, crearlas, corregirlas y aportar.

`metas` lleva ambito porque Goal tiene `scope` y `owner`: una meta personal es
de su dueno y no del hogar. Las escrituras no lo llevan: la fila ya sabe su
ambito, y a el se vuelve.
"""

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services, services_goals
from .forms import GoalContributionForm, GoalForm
from .models import Goal, GoalContribution, MesCerrado
from .scopes import HOGAR, PERSONAL, acotar_por_dueno, validar
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


def _fila(hogar, meta):
    """La fila de resumen() de UNA meta, para devolver su tarjeta."""
    consulta = _con_aportes(Goal.objects.for_household(hogar).filter(pk=meta.pk), hogar)
    return services_goals.resumen(hogar, consulta)[0]


@requiere_permiso("can_edit_budget")
def aportar(request, hogar):
    """Mismo patron que `registrar`: por htmx devuelve el fragmento y, al
    guardar, el formulario limpio con la tarjeta de la meta FUERA DE BANDA
    (solo Metas tiene ese id; desde otra pantalla htmx la ignora) y la
    cabecera que cierra el modal. Sin htmx, la pagina entera y de vuelta a
    Metas del ambito de la meta."""
    es_htmx = request.headers.get("HX-Request") == "true"
    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    initial = {"date": hoy}
    if request.GET.get("goal", "").isdigit():
        initial["goal"] = int(request.GET["goal"])
    form = GoalContributionForm(request.POST or None, household=hogar,
                                membresia=membresia, initial=initial)
    contexto = {"titulo": _("Add to a goal"),
                "cancelar": reverse("budget:metas", args=["household"])}
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            aporte = services_goals.aportar(
                hogar, datos["goal"], datos["amount"], datos["date"], membresia
            )
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        else:
            if es_htmx:
                limpio = GoalContributionForm(household=hogar, membresia=membresia,
                                              initial={"date": hoy})
                respuesta = render(request, "budget/_fragmentos/aporte_form.html", {
                    "form": limpio, "tarjeta_oob": _fila(hogar, aporte.goal), **contexto,
                })
                respuesta["HX-Trigger"] = "gasto-registrado"
                return respuesta
            return redirect("budget:metas", aporte.goal.scope)

    plantilla = ("budget/_fragmentos/aporte_form.html" if es_htmx
                 else "budget/formulario.html")
    return render(request, plantilla, {
        # Una exists() solo al pintar el formulario, no por pagina: es lo que
        # permite que el selector del [+] ofrezca siempre la tercera opcion.
        "form": form, "sin_metas": not form.fields["goal"].queryset.exists(), **contexto,
    })


def _meta(request, hogar, pk):
    """Una meta que quien pide puede tocar: las del hogar, y las personales
    solo de su dueno. `for_household` antes que `get_object_or_404`: el pk de
    otra familia (o la personal de otro miembro) es un 404 identico al de un
    pk inventado, sin decir cual fue."""
    membresia = membresia_actual(request)
    visibles = Q(scope=HOGAR) | Q(scope=PERSONAL, owner=membresia)
    return get_object_or_404(Goal.objects.for_household(hogar).filter(visibles), pk=pk)


@requiere_permiso("can_edit_budget")
def meta_editar(request, hogar, pk):
    """Corregir en sitio, como una regla del setup. Tras guardar se recalcula
    el estado: subir el objetivo reabre una alcanzada, bajarlo puede cubrirla."""
    meta = _meta(request, hogar, pk)
    form = GoalForm(request.POST or None, household=hogar, instance=meta)
    if request.method == "POST" and form.is_valid():
        meta = form.save()
        services_goals.recalcular_estado(meta)
        return redirect("budget:metas", meta.scope)
    return render(request, "budget/formulario.html", {
        "form": form, "titulo": _("Edit goal"),
        "cancelar": reverse("budget:metas", args=[meta.scope]),
    })


@require_POST
@requiere_permiso("can_edit_budget")
def meta_borrar(request, hogar, pk):
    """Solo por POST: un GET no destruye nada. Con aportes de cascada no se
    borra: MonthlyAllocation.rule es RESTRICT y el mes cerrado conto con ese
    reparto. Se abandona, que es lo que la tarjeta ofrece en su lugar."""
    meta = _meta(request, hogar, pk)
    if meta.contributions.filter(origen="cascade").exists():
        messages.error(request, _(
            "This goal already took part in a closed month — abandon it instead."
        ))
    else:
        meta.delete()
    return redirect("budget:metas", meta.scope)


@require_POST
@requiere_permiso("can_edit_budget")
def meta_estado(request, hogar, pk, estado):
    meta = _meta(request, hogar, pk)
    try:
        services_goals.cambiar_estado(meta, estado)
    except ValueError:
        return HttpResponseBadRequest(_("That change is not possible."))
    return redirect("budget:metas", meta.scope)


def _aporte(request, hogar, pk):
    """Como _meta, para un aporte: el de la meta personal de otro es 404."""
    membresia = membresia_actual(request)
    visibles = Q(goal__scope=HOGAR) | Q(goal__scope=PERSONAL, goal__owner=membresia)
    return get_object_or_404(
        GoalContribution.objects.for_household(hogar)
        .select_related("goal", "budget_month").filter(visibles),
        pk=pk,
    )


def _intocable(aporte):
    """Por que un aporte no se corrige, o None si se puede."""
    if aporte.origen != "manual":
        return HttpResponseForbidden(
            _("Contributions from the monthly split cannot be changed.")
        )
    return None


@requiere_permiso("can_edit_budget")
def aporte_editar(request, hogar, pk):
    """Corregir un aporte mal tecleado. Si su mes ya esta cerrado no se toca:
    moverle la fecha sacaria dinero de un balance ya cuadrado. Si la fecha
    NUEVA cae en un mes cerrado, lo dice el formulario."""
    aporte = _aporte(request, hogar, pk)
    if (prohibido := _intocable(aporte)) is not None:
        return prohibido
    meta = aporte.goal
    if aporte.budget_month_id and aporte.budget_month.esta_cerrado:
        messages.error(request, _("This month is already closed."))
        return redirect("budget:metas", meta.scope)
    form = GoalContributionForm(request.POST or None, household=hogar,
                                membresia=membresia_actual(request), instance=aporte)
    if request.method == "POST" and form.is_valid():
        aporte = form.save(commit=False)
        aporte.budget_month = services.mes_de_fecha(hogar, aporte.date)
        try:
            aporte.full_clean()
            aporte.save()
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        else:
            services_goals.recalcular_estado(aporte.goal)
            return redirect("budget:metas", aporte.goal.scope)
    return render(request, "budget/formulario.html", {
        "form": form, "titulo": _("Edit contribution"),
        "cancelar": reverse("budget:metas", args=[meta.scope]),
    })


@require_POST
@requiere_permiso("can_edit_budget")
def aporte_borrar(request, hogar, pk):
    aporte = _aporte(request, hogar, pk)
    if (prohibido := _intocable(aporte)) is not None:
        return prohibido
    meta = aporte.goal
    if aporte.budget_month_id and aporte.budget_month.esta_cerrado:
        messages.error(request, _("This month is already closed."))
    else:
        aporte.delete()
        services_goals.recalcular_estado(meta)
    return redirect("budget:metas", meta.scope)
