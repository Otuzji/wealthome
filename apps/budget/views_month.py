"""El mes: verlo, registrar en el, planificarlo y cerrarlo.

`mes`, `planificar` y `cerrar` llevan ambito; `registrar` no. Registrar un gasto
es una sola accion —la mas frecuente del §7.1— y el ambito de la fila lo decide
el formulario, no la URL de la que se entro.
"""

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services
from .engine.cascade import repartir
from .forms import TransactionForm
from .models import AllocationRule, MesCerrado
from .scopes import acotar, acotar_por_dueno, validar

# El calendario, no una preferencia: 1..12, y un rango de años que cabe en el
# PositiveSmallIntegerField del modelo y en el que un presupuesto tiene sentido.
ANIO_MINIMO, ANIO_MAXIMO = 2000, 2100


@requiere_permiso("can_add_transactions")
def registrar(request, hogar):
    """La acción más frecuente de la aplicación (§7.1)."""
    hoy = timezone.localdate()
    form = TransactionForm(request.POST or None, household=hogar,
                           initial={"date": hoy})
    if request.method == "POST" and form.is_valid():
        mes_fila = services.obtener_mes(hogar, hoy.year, hoy.month)
        tx = form.save(commit=False)
        tx.household = hogar
        tx.budget_month = mes_fila
        tx.merchant = form.comercio()
        tx.member = membresia_actual(request)
        try:
            tx.full_clean()
            tx.save()
        except MesCerrado:
            # §4.3: el mes cerrado no admite escrituras. Que lo diga el
            # formulario y no una página de error del servidor.
            form.add_error(None, _("This month is already closed."))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("budget:registrar")
    return render(request, "budget/gasto.html", {"form": form})


@requiere_permiso("can_view_budget")
def mes(request, hogar, ambito, anio=None, numero=None):
    ambito = validar(ambito)
    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    # `is None`, no `or`: un mes 0 en la URL es falsy y se colaba como "no
    # dado", devolviendo el mes corriente en vez del 404 que merece.
    anio = hoy.year if anio is None else anio
    numero = hoy.month if numero is None else numero
    # A esta URL se llega escribiéndola o con un enlace viejo. Sin esto, un mes
    # 13 revienta en calendar.monthrange con un 500 y un mes 0 llega a crear la
    # fila del BudgetMonth antes de reventar.
    if not (1 <= numero <= 12) or not (ANIO_MINIMO <= anio <= ANIO_MAXIMO):
        raise Http404(_("That month is not on the calendar."))
    resultado = services.obtener_mes(hogar, anio, numero)
    es_proyeccion = isinstance(resultado, services.ProyeccionDeMes)
    contexto = {
        "resultado": resultado, "es_proyeccion": es_proyeccion,
        "anio": anio, "numero": numero, "ambito": ambito,
    }
    if not es_proyeccion:
        # select_related sobre la categoria: la plantilla lee category.etiqueta
        # en cada fila, y sin esto un mes con 120 transacciones son 120
        # consultas contra el pooler.
        contexto["lineas"] = acotar_por_dueno(
            resultado.lineas.select_related("category"), ambito, membresia
        )
        contexto["transacciones"] = acotar(
            resultado.transacciones.select_related("category"), ambito, membresia
        )
    return render(request, "budget/mes.html", contexto)


@requiere_permiso("can_edit_budget")
def planificar(request, hogar, ambito):
    """El asistente del §4.5.6, en una sola pantalla.

    Los tres pasos del spec —ingresos, salidas, reparto— se presentan juntos
    porque el Plan 3 rehará la navegación; lo que importa aquí es que el
    cálculo y la escritura sean los definitivos.
    """
    ambito = validar(ambito)
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    # obtener_mes devuelve una fila (mes corriente materializado) o una
    # ProyeccionDeMes. Solo en el primer caso hace falta proyectar aparte,
    # porque planificar reparte sobre el sobrante proyectado del mes.
    proyeccion = (
        mes_actual if isinstance(mes_actual, services.ProyeccionDeMes)
        else services.proyectar(hogar, hoy.year, hoy.month)
    )

    if request.method == "POST":
        services.planificar_mes(hogar, mes_actual, proyeccion.sobrante)
        return redirect("budget:mes", ambito)

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
        "ambito": ambito,
    })


@requiere_permiso("can_edit_budget")
def cerrar(request, hogar, ambito):
    ambito = validar(ambito)
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    if request.method == "POST":
        try:
            services.cerrar_mes(mes_actual)
        except MesCerrado:
            pass   # ya estaba cerrado: idempotente, no un error del usuario
        return redirect("budget:mes", ambito)
    return render(request, "budget/cerrar.html", {"mes": mes_actual, "ambito": ambito})
