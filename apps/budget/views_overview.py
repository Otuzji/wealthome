"""Overview: el mes en curso de un vistazo, solo lectura.

Forecast (lo planeado y como se reparte), Real (lo que paso), Desvios (donde
lo real se aparta del plan), Expenses (lo del presupuesto contra lo puntual)
y, en el hogar, la alerta de si lo que hay en mano alcanza hasta el proximo
ingreso. Las cifras salen de `services_overview`, las mismas funciones que
usa This month: las dos pantallas no pueden divergir.

Un GET no escribe: salvo lo que ya hace `obtener_mes` del mes corriente, nada
se crea aqui.
"""

from decimal import Decimal

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services, services_overview
from .forms import SaldoInicialForm
from .models.catalog import HOUSEHOLD
from .scopes import validar

CERO = Decimal("0.00")

# El Forecast personal de quien aun no tiene mes: todo en cero. No se llama a
# `forecast_personal`, que leeria el libro de la mesada de un mes sin fila.
FORECAST_PERSONAL_VACIO = {
    "ingresos": CERO, "egresos": CERO, "mesada": CERO, "arrastre": CERO,
    "ajuste": CERO, "disponible": CERO, "queda": CERO,
}


def _contexto(request, hogar, ambito, form=None):
    """Todo lo que el Overview pinta, o solo lo que cabe del mes si no hay
    mas. Lo comparten la pantalla y el guardado del saldo inicial: al guardar,
    la alerta se recalcula con las mismas cuentas que la pantalla entera.

    `form` es el del saldo inicial con sus errores, si venia de un POST fallido."""
    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    es_proyeccion = isinstance(mes, services.ProyeccionDeMes)
    contexto = {
        "ambito": ambito,
        "primer_dia": hoy.replace(day=1),
        # Todo lo que el Overview ofrece (montar el presupuesto, planear el mes
        # siguiente, anotar el saldo) es una escritura: ademas del permiso, el
        # hogar tiene que poder escribir (§5.2), como en This month.
        "puede_editar": membresia.can_edit_budget and hogar.puede_escribir,
        "es_proyeccion": es_proyeccion,
        "cerrado": False,
        "sin_presupuesto": not services_overview.hay_presupuesto(hogar, mes, hoy),
        "alerta": None,
    }
    if contexto["sin_presupuesto"]:
        return contexto

    if es_proyeccion:
        # El hogar no puede escribir, o el mes aun no existe: lo planeado sale
        # de las reglas y no hay nada real que contar. En Personal no hay
        # proyeccion que valga (la mesada pide las lineas del mes).
        if ambito == HOUSEHOLD:
            # `proyectar` lee tambien las reglas personales de cada miembro;
            # las cifras del hogar llevan solo las del hogar.
            planeado = services_overview.totales_proyectados_del_hogar(hogar, mes)
            contexto["forecast"] = services_overview.forecast_hogar(hogar, planeado)
        else:
            planeado = services_overview.totales(CERO, CERO, CERO, CERO)
            contexto["forecast"] = FORECAST_PERSONAL_VACIO
        contexto.update(
            real=planeado, expenses=services_overview.expenses([]), desvios=[],
        )
        return contexto

    # Las mismas lineas, transacciones y totales que This month.
    lineas, transacciones, totales = services_overview.totales_del_ambito(mes, ambito, membresia)
    cerrado = mes.esta_cerrado
    if ambito == HOUSEHOLD:
        forecast = services_overview.forecast_hogar(hogar, totales)
    else:
        forecast = services_overview.forecast_personal(hogar, mes, membresia, totales)

    contexto.update(
        cerrado=cerrado, forecast=forecast, real=totales,
        expenses=services_overview.expenses(transacciones),
        desvios=services_overview.desvios(lineas, transacciones, cerrado),
    )
    if cerrado:
        contexto["siguiente"] = services.mes_siguiente(mes.year, mes.month)
    elif ambito == HOUSEHOLD:
        # La alerta es de lo que hay en mano del hogar. Un mes cerrado ya no
        # espera nada, y en Personal el dinero en mano no es de uno.
        alerta = services_overview.alerta_cash_float(
            hogar, mes, lineas, totales["sobrante_real"], hoy,
        )
        contexto["alerta"] = alerta
        if alerta["falta_saldo"]:
            contexto["sugerencia_saldo"] = services_overview.sugerencia_saldo_inicial(mes)
        if contexto["puede_editar"]:
            contexto["form"] = form if form is not None else _formulario_del_saldo(mes, contexto)
    return contexto


def _formulario_del_saldo(mes, contexto):
    """El formulario ya relleno: con lo guardado, o, si falta, con la sugerencia
    del ultimo cierre (que solo se propone: no se guarda hasta que se acepta)."""
    inicial = mes.opening_balance
    if inicial is None:
        inicial = contexto.get("sugerencia_saldo")
    return SaldoInicialForm(initial={"opening_balance": inicial})


@requiere_permiso("can_view_budget")
def overview(request, hogar, ambito):
    ambito = validar(ambito)
    return render(request, "budget/overview.html", _contexto(request, hogar, ambito))


@require_POST
@requiere_permiso("can_edit_budget")
def saldo_inicial(request, hogar):
    """Guarda el saldo con el que abre el mes en curso. Por htmx devuelve la
    alerta recalculada para que sustituya a la anterior; sin htmx, vuelve al
    Overview. Solo el mes corriente y solo el hogar: es lo que la alerta mira."""
    es_htmx = request.headers.get("HX-Request") == "true"
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    if isinstance(mes, services.ProyeccionDeMes):
        raise Http404
    vuelta = reverse("budget:overview", args=[HOUSEHOLD])
    if mes.esta_cerrado:
        # BudgetMonth no hereda la guarda de los meses cerrados. Y un mes
        # cerrado ya no tiene alerta que repintar: se recarga la pantalla,
        # que lo dice.
        messages.error(request, _("This month is already closed."))
        return _recargar(es_htmx, vuelta)

    form = SaldoInicialForm(request.POST)
    if form.is_valid():
        mes.opening_balance = form.cleaned_data["opening_balance"]
        mes.save(update_fields=["opening_balance"])
        form = None
    if not es_htmx:
        if form is not None:
            messages.error(request, form.errors["opening_balance"][0])
        return redirect(vuelta)
    contexto = _contexto(request, hogar, HOUSEHOLD, form=form)
    if contexto["alerta"] is None:
        # Sin alerta que repintar (no hay presupuesto): que la pantalla lo diga.
        return _recargar(es_htmx, vuelta)
    return render(request, "budget/_fragmentos/overview_alerta.html", contexto)


def _recargar(es_htmx, destino):
    """Volver a la pantalla: por htmx, pidiendole que la recargue entera."""
    if es_htmx:
        respuesta = HttpResponse()
        respuesta["HX-Redirect"] = destino
        return respuesta
    return redirect(destino)
