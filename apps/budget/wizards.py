"""Los dos asistentes: planificar el mes (§4.5.6) e incorporacion (§7.2).

El de planificar existe porque el Plan 2 lo colapso en una pantalla con permiso
explicito de su plan, y el criterio de aceptacion 3 —"una pareja planifica el
mes en tres pasos"— se dio por bueno sobre una pantalla que no tiene tres.
"""

from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.households.permissions import requiere_permiso

from . import services
from .engine.cascade import repartir
from .models import AllocationRule
from .scopes import validar

PASOS = (1, 2, 3)

# El rango de la primera pasada al reordenar. Tiene que estar fuera de cualquier
# orden real y caber en el PositiveSmallIntegerField del modelo.
_LIMBO = 10000


@requiere_permiso("can_edit_budget")
def planificar(request, hogar, ambito, paso=1):
    """Un paso del asistente. Solo el tercero escribe."""
    ambito = validar(ambito)
    if paso not in PASOS:
        raise Http404(_("That step does not exist."))

    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    proyeccion = (
        mes_actual if isinstance(mes_actual, services.ProyeccionDeMes)
        else services.proyectar(hogar, hoy.year, hoy.month)
    )

    if request.method == "POST":
        if paso < 3:
            # Los pasos 1 y 2 no escriben nada: el usuario ya edito lo suyo con
            # los formularios de reglas y de linea excepcional, que guardan por
            # su cuenta. Avanzar es solo avanzar.
            return redirect("budget:planificar_paso", ambito=ambito, paso=paso + 1)
        services.planificar_mes(hogar, mes_actual, proyeccion.sobrante)
        request.session["plan_confirmado"] = True
        return redirect("budget:mes", ambito)

    contexto = {
        "paso": paso, "ambito": ambito, "mes": mes_actual,
        "proyeccion": proyeccion,
    }
    if paso == 1:
        contexto["ingresos"] = [l for l in proyeccion.lineas if l.kind == "income"]
    elif paso == 2:
        contexto["egresos"] = [l for l in proyeccion.lineas if l.kind == "expense"]
    else:
        contexto.update(_reparto(hogar, proyeccion))

    return render(request, f"wizards/planificar_{paso}.html", contexto)


def _reparto(hogar, proyeccion):
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
            for a in repartir(proyeccion.sobrante, reglas)
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
    reglas = {
        r.pk: r for r in AllocationRule.objects.for_household(hogar).filter(pk__in=pks)
    }
    if not pks or len(reglas) != len(pks):
        # Un pk de otra familia, o inventado. La barrera de ambito ya lo filtro;
        # esto solo evita reordenar a medias.
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
