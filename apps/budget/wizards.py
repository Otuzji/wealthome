"""Los dos asistentes: planificar el mes (§4.5.6) e incorporacion (§7.2).

El de planificar existe porque el Plan 2 lo colapso en una pantalla con permiso
explicito de su plan, y el criterio de aceptacion 3 —"una pareja planifica el
mes en tres pasos"— se dio por bueno sobre una pantalla que no tiene tres.
"""

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.households.permissions import requiere_permiso

from . import services
from .engine.cascade import repartir
from .forms import LineasDelMesForm
from .models import AllocationRule, MesCerrado
from .models.catalog import EXPENSE, INCOME
from .scopes import validar
from .views_month import exigir_en_el_calendario

PASOS = (1, 2, 3)

# El rango de la primera pasada al reordenar. Tiene que estar fuera de cualquier
# orden real y caber en el PositiveSmallIntegerField del modelo.
_LIMBO = 10000


@requiere_permiso("can_edit_budget")
def planificar(request, hogar, ambito, paso=1, anio=None, numero=None):
    """Un paso del asistente, sobre las LINEAS del mes.

    Sin fecha es el mes corriente. Con fecha, cualquier mes que no este
    cerrado: el futuro se materializa al entrar y desde ahi se edita aqui, no en
    el setup (§2.3). Los pasos 1 y 2 guardan los importes tecleados; el 3
    escribe el reparto, y lo reescribe si ya lo habia.
    """
    ambito = validar(ambito)
    if paso not in PASOS:
        raise Http404(_("That step does not exist."))

    hoy = timezone.localdate()
    if anio is None:
        anio, numero = hoy.year, hoy.month
    exigir_en_el_calendario(anio, numero)

    mes = services.abrir_para_planificar(hogar, anio, numero, hoy)
    if mes is None:
        raise Http404(_("That month cannot be planned."))
    if mes.esta_cerrado:
        # No un 404: el mes existe, solo que ya no se toca. La pantalla del mes
        # lo ensena cerrado.
        messages.info(request, _("This month is already closed."))
        return redirect("budget:mes", ambito, anio, numero)

    lineas = mes.lineas.select_related(
        "category", "source_income", "source_expense_rule"
    ).order_by("is_exceptional", "pk")
    contexto = {"paso": paso, "ambito": ambito, "mes": mes, "anio": anio, "numero": numero}

    if paso == 3:
        if request.method == "POST":
            totales = services.totales_del_mes(mes)
            services.planificar_mes(hogar, mes, totales.sobrante)
            request.session["plan_confirmado"] = True
            return redirect("budget:mes", ambito, anio, numero)
        contexto["totales"] = services.totales_del_mes(mes)
        contexto.update(_reparto(hogar, contexto["totales"].sobrante))
        return render(request, "wizards/planificar_3.html", contexto)

    lineas = lineas.filter(kind=INCOME if paso == 1 else EXPENSE)
    # Por METODO y no `request.POST or None`: un POST sin campos (un mes sin
    # lineas, o "Next" sin tocar nada) es un QueryDict vacio, que es falsy, y
    # dejaria el formulario sin enlazar — is_valid() False y la pagina de nuevo.
    form = LineasDelMesForm(request.POST if request.method == "POST" else None, lineas=lineas)
    if request.method == "POST" and form.is_valid():
        try:
            form.guardar()
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        else:
            return redirect("budget:planificar_mes", ambito, anio, numero, paso + 1)
    contexto["form"] = form
    return render(request, f"wizards/planificar_{paso}.html", contexto)


@require_POST
@requiere_permiso("can_edit_budget")
def refrescar(request, hogar, ambito, anio, numero, paso):
    """El boton "Refresh from setup" de los pasos 1 y 2: vuelve al mismo paso."""
    ambito = validar(ambito)
    exigir_en_el_calendario(anio, numero)
    mes = services.abrir_para_planificar(hogar, anio, numero)
    if mes is None:
        raise Http404(_("That month cannot be planned."))
    try:
        services.refrescar_desde_las_reglas(hogar, mes)
    except MesCerrado:
        messages.info(request, _("This month is already closed."))
        return redirect("budget:mes", ambito, anio, numero)
    messages.success(request, _("This month now matches your setup. One-off items were kept."))
    return redirect("budget:planificar_mes", ambito, anio, numero, paso)


def _reparto(hogar, sobrante):
    """El paso 3: el sobrante, la cascada y la mesada por miembro."""
    reglas_orm = {
        r.order: r
        for r in AllocationRule.objects.for_household(hogar).filter(is_active=True)
    }
    reglas = [
        r.a_regla_de_reparto(services.miembros_activos(hogar))
        for r in reglas_orm.values()
    ]
    miembros = {m.pk: m for m in hogar.active_memberships()}
    return {
        "reglas": list(reglas_orm.values()),
        "asignaciones": [
            {"importe": a.importe, "miembro": miembros.get(a.miembro_id),
             "regla": reglas_orm[a.orden]}
            for a in repartir(sobrante, reglas)
        ],
    }


@requiere_permiso("can_edit_budget")
def reordenar_reglas(request, hogar):
    """El arrastre del paso 3 (§4.5.6): "las reglas se reordenan arrastrando".

    Recibe la lista de pks en su orden nuevo y reescribe `order`. Se hace en
    DOS PASADAS y dentro de una transaccion porque AllocationRule tiene un
    UniqueConstraint sobre (household, order): asignar el orden final de una
    sola pasada choca con las filas que aun no se han movido. No es paranoia —
    mover la regla 2 a la posicion 1 choca con la que todavia ocupa la 1.
    """
    if request.method != "POST":
        return HttpResponseBadRequest()

    pks = [p for p in request.POST.getlist("orden") if p.isdigit()]
    if len(set(pks)) != len(pks):
        # Un pk repetido daria dos reglas con el mismo orden final.
        return HttpResponseBadRequest()

    activas = {
        r.pk: r
        for r in AllocationRule.objects.for_household(hogar).filter(is_active=True)
    }
    reglas = {
        r.pk: r for r in AllocationRule.objects.for_household(hogar).filter(pk__in=pks)
    }
    if not pks or len(reglas) != len(pks):
        # Un pk de otra familia, o inventado. La barrera de ambito ya lo filtro;
        # esto solo evita reordenar a medias.
        return HttpResponseBadRequest()

    # Y la lista tiene que venir COMPLETA. Con una parcial, las reglas que no se
    # mencionan conservan su orden y chocan con los nuevos: reglas 1,2,3 y una
    # lista [3,2] deja a la 3 pidiendo el orden 1, que la 1 todavia ocupa, y el
    # UniqueConstraint(household, order) lo tumba con un IntegrityError — un 500
    # en un POST. La interfaz manda siempre la lista entera; esto cubre al que
    # llegue por otro camino.
    if set(pks) != {str(pk) for pk in activas}:
        return HttpResponseBadRequest()

    with transaction.atomic():
        for desplazamiento, pk in enumerate(pks, start=1):
            regla = reglas[int(pk)]
            regla.order = _LIMBO + desplazamiento
            regla.save(update_fields=["order"])
        for posicion, pk in enumerate(pks, start=1):
            regla = reglas[int(pk)]
            regla.order = posicion
            regla.save(update_fields=["order"])

    return render(request, "wizards/_reglas.html", {
        "reglas": AllocationRule.objects.for_household(hogar).filter(is_active=True),
    })


# El paso 1 es accounts:registro, que ya crea usuario y hogar. Del 2 al 6, cada
# paso ENVUELVE un formulario que ya existe en Configurar en vez de duplicarlo:
# el asistente es una guia, no una segunda forma de crear las mismas cosas.
PASOS_INCORPORACION = {
    2: ("miembros", "households:invitar", _("Who else lives here")),
    3: ("ingresos", "budget:ingreso_nuevo", _("What comes in")),
    4: ("gastos", "budget:gasto_nuevo", _("What goes out every month")),
    5: ("meta", "budget:meta_nueva", _("What you are saving for")),
    6: ("reparto", "budget:reparto_nuevo", _("How the leftover gets split")),
}

TOTAL_INCORPORACION = 6


@requiere_permiso("can_edit_budget")
def incorporacion(request, hogar, paso):
    """El asistente del §7.2, del paso 2 al 6. El 1 es el registro.

    Cada paso se puede saltar, y eso NO es un adorno: el paso 1 crea el hogar de
    verdad y los cinco siguientes escriben contra el, asi que quien cierre la
    pestana en el paso 3 ya tiene un hogar. Un asistente que hay que terminar de
    una sentada convierte una interrupcion en una cuenta rota.
    """
    if paso not in PASOS_INCORPORACION:
        raise Http404(_("That step does not exist."))

    nombre, ruta, titulo = PASOS_INCORPORACION[paso]
    siguiente = paso + 1 if paso + 1 in PASOS_INCORPORACION else None
    return render(request, "wizards/incorporacion.html", {
        "paso": paso, "total": TOTAL_INCORPORACION, "nombre": nombre,
        "titulo": titulo, "ruta_del_formulario": ruta, "siguiente": siguiente,
    })
