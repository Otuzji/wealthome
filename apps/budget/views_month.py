"""El mes: verlo, registrar en el, planificarlo y cerrarlo.

`mes`, `planificar` y `cerrar` llevan ambito; `registrar` no. Registrar un gasto
es una sola accion —la mas frecuente del §7.1— y el ambito de la fila lo decide
el formulario, no la URL de la que se entro.
"""

from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services
from .forms import BudgetLineForm, TransactionForm
from .models import AllowanceLedger, BudgetLine, MesCerrado, Transaction
from .models.catalog import EXPENSE, HOUSEHOLD, INCOME, PERSONAL
from .scopes import acotar, acotar_por_dueno, validar

# El calendario, no una preferencia: 1..12, y un rango de años que cabe en el
# PositiveSmallIntegerField del modelo y en el que un presupuesto tiene sentido.
ANIO_MINIMO, ANIO_MAXIMO = 2000, 2100


def exigir_en_el_calendario(anio, numero):
    """A las URL con fecha se llega escribiendolas o con un enlace viejo. Sin
    esto, un mes 13 revienta en calendar.monthrange con un 500 y un mes 0 llega
    a crear la fila del BudgetMonth antes de reventar."""
    if not (1 <= numero <= 12) or not (ANIO_MINIMO <= anio <= ANIO_MAXIMO):
        raise Http404(_("That month is not on the calendar."))

MOVIMIENTOS_RECIENTES = 8


def _recientes(hogar, mes_actual=None):
    """Los ultimos movimientos del hogar, para el intercambio de htmx.

    Recibe el mes si quien llama ya lo tiene: `obtener_mes` cierra vencidos y
    materializa, y contra la base remota cada pasada de mas se nota al pulsar
    "Record it"."""
    if mes_actual is None:
        hoy = timezone.localdate()
        mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    if isinstance(mes_actual, services.ProyeccionDeMes):
        return []
    return list(
        Transaction.objects.for_household(hogar)
        .filter(budget_month=mes_actual)
        .select_related("category")
        .order_by("-date", "-pk")[:MOVIMIENTOS_RECIENTES]
    )


def _lineas_para_pagar(hogar, mes, membresia):
    """Las lineas del mes que este miembro puede pagar: las del hogar y las
    personales suyas. Con los pagos anotados: la etiqueta de cada opcion dice
    si esta pendiente, y sin la anotacion seria una consulta por linea."""
    if isinstance(mes, services.ProyeccionDeMes):
        return []
    return list(
        mes.lineas.filter(Q(scope=HOUSEHOLD) | Q(owner=membresia))
        .select_related("category", "source_income", "source_expense_rule", "household")
        .annotate(pagado_total=Sum("transacciones__amount"))
        .order_by("due_date", "pk")
    )


@requiere_permiso("can_add_transactions")
def registrar(request, hogar):
    """La acción más frecuente de la aplicación (§7.1).

    Devuelve un FRAGMENTO cuando la peticion trae HX-Request, y la pagina entera
    si no. La misma vista sirve las dos cosas a proposito: un endpoint aparte
    solo para htmx seria una segunda ruta que puede divergir de la primera, y la
    guardia de suscripcion del §2.2 —que es por METODO y no por vista— dejaria de
    cubrirla sin que nadie se diera cuenta.
    """
    es_htmx = request.headers.get("HX-Request") == "true"
    hoy = timezone.localdate()
    membresia = membresia_actual(request)
    mes_fila = services.obtener_mes(hogar, hoy.year, hoy.month)
    form = TransactionForm(request.POST or None, household=hogar,
                           lineas=_lineas_para_pagar(hogar, mes_fila, membresia),
                           initial={"date": hoy})
    if request.method == "POST" and form.is_valid():
        tx = form.save(commit=False)
        tx.household = hogar
        tx.budget_month = mes_fila
        tx.merchant = form.comercio()
        tx.member = membresia
        try:
            with transaction.atomic():
                _ligar_al_plan(tx, form, mes_fila)
                tx.full_clean()
                tx.save()
        except MesCerrado:
            # §4.3: el mes cerrado no admite escrituras. Que lo diga el
            # formulario y no una página de error del servidor.
            form.add_error(None, _("This month is already closed."))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            if es_htmx:
                # Un formulario limpio en el sitio del enviado, y los
                # movimientos al dia FUERA DE BANDA: solo Overview tiene
                # #recientes, y el modal se envia desde cualquier pantalla.
                limpio = TransactionForm(
                    household=hogar, initial={"date": hoy},
                    lineas=_lineas_para_pagar(hogar, mes_fila, membresia),
                )
                respuesta = render(request, "budget/_fragmentos/gasto_form.html", {
                    "form": limpio, "recientes_oob": _recientes(hogar, mes_fila),
                })
                # Que el gasto entro lo dice el SERVIDOR, no el navegador. Quien
                # abrio esto en un modal lo cierra al oirlo; quien entro por la
                # pagina entera no escucha y no le afecta. Intentarlo desde el
                # cliente —mirando que el evento venga de dentro del <dialog>—
                # no funciono de forma fiable, y ademas ataba el fragmento, que
                # es compartido, a la pantalla que lo muestra.
                respuesta["HX-Trigger"] = "gasto-registrado"
                return respuesta
            return redirect("budget:registrar")

    plantilla = "budget/_fragmentos/gasto_form.html" if es_htmx else "budget/gasto.html"
    return render(request, plantilla, {"form": form})


def _ligar_al_plan(tx, form, mes):
    """Con una linea elegida, la transaccion toma su categoria y su income
    source. Sin linea, nace una partida puntual ya pagada con lo gastado."""
    linea = tx.budget_line
    if linea is not None:
        tx.category = linea.category
        tx.income_source = linea.source_income
        return
    if isinstance(mes, services.ProyeccionDeMes):
        return   # el hogar no puede escribir: la guardia por metodo ya lo paro
    linea = BudgetLine(
        household=tx.household, budget_month=mes, category=tx.category,
        kind=tx.category.kind, planned_amount=tx.amount, due_date=tx.date,
        is_exceptional=True, scope=tx.scope, note=form.nombre_de_la_partida(),
        owner=tx.member if tx.scope == PERSONAL else None,
    )
    linea.full_clean()
    linea.save()
    tx.budget_line = linea


@requiere_permiso("can_view_budget")
def mes(request, hogar, ambito, anio=None, numero=None):
    ambito = validar(ambito)
    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    # `is None`, no `or`: un mes 0 en la URL es falsy y se colaba como "no
    # dado", devolviendo el mes corriente en vez del 404 que merece.
    anio = hoy.year if anio is None else anio
    numero = hoy.month if numero is None else numero
    exigir_en_el_calendario(anio, numero)
    resultado = services.obtener_mes(hogar, anio, numero)
    es_proyeccion = isinstance(resultado, services.ProyeccionDeMes)
    contexto = {
        "resultado": resultado, "es_proyeccion": es_proyeccion,
        "anio": anio, "numero": numero, "ambito": ambito,
        # Para llegar a un mes futuro sin escribir la URL.
        "anterior": services.mes_previo(anio, numero),
        "siguiente": services.mes_siguiente(anio, numero),
        "se_puede_planificar": es_proyeccion or resultado.status == "open",
        "se_puede_cerrar": (
            not es_proyeccion and resultado.status == "open"
            and (anio, numero) <= (hoy.year, hoy.month)
        ),
    }
    if not es_proyeccion:
        # select_related sobre la categoria: la plantilla lee category.etiqueta
        # en cada fila, y sin esto un mes con 120 transacciones son 120
        # consultas contra el pooler.
        # Ingresos arriba y gastos abajo, cada linea con el nombre de su regla:
        # select_related sobre las dos FK de origen o `linea.nombre` es una
        # consulta por fila.
        # `pagado_total` anotado: el estado de cada linea sale de sus pagos, y
        # sin la anotacion serian una consulta por fila.
        lineas = acotar_por_dueno(
            resultado.lineas.select_related(
                "category", "source_income", "source_expense_rule"
            ).annotate(pagado_total=Sum("transacciones__amount"))
            .order_by("due_date", "pk"),
            ambito, membresia,
        )
        contexto["bloques"] = _bloques_del_plan(lineas)
        contexto["transacciones"] = acotar(
            resultado.transacciones.select_related("category"), ambito, membresia
        )
        # Las cifras salen de las MISMAS lineas que la tarjeta Planned, y por
        # tanto respetan el ambito, igual que en el Overview.
        contexto["donas"] = _real_contra_planeado(lineas, contexto["transacciones"])
        contexto["totales"] = {
            "ingresos": contexto["donas"][INCOME]["planeado"],
            "egresos": contexto["donas"][EXPENSE]["planeado"],
            "sobrante": (contexto["donas"][INCOME]["planeado"]
                         - contexto["donas"][EXPENSE]["planeado"]),
        }
    return render(request, "budget/mes.html", contexto)


def _real_contra_planeado(lineas, transacciones):
    """Por tipo: lo planeado, lo que de verdad paso y el porcentaje entero
    que la dona pinta. Lo real sale de las transacciones y no de los pagos de
    las lineas: un gasto sin partida tambien salio del bolsillo."""
    donas = {}
    for kind in (INCOME, EXPENSE):
        planeado = sum((l.planned_amount for l in lineas if l.kind == kind), Decimal("0.00"))
        real = sum((t.amount for t in transacciones if t.category.kind == kind), Decimal("0.00"))
        porcentaje = int(real * 100 / planeado) if planeado else 0
        donas[kind] = {"planeado": planeado, "real": real, "porcentaje": porcentaje}
    return donas


def _bloques_del_plan(lineas):
    """La tarjeta Planned: ingresos, ingresos puntuales, gastos, gastos
    puntuales — cada bloque con su total."""
    orden = (
        (_("Income"), INCOME, False), (_("One-off income"), INCOME, True),
        (_("Expenses"), EXPENSE, False), (_("One-off expenses"), EXPENSE, True),
    )
    bloques = []
    for titulo, kind, puntual in orden:
        filas = [l for l in lineas if l.kind == kind and l.is_exceptional == puntual]
        if puntual and not filas:
            continue   # sin partidas puntuales, sin bloque vacio
        bloques.append({
            "titulo": titulo, "kind": kind, "lineas": filas,
            "total": sum((l.planned_amount for l in filas), Decimal("0.00")),
        })
    return bloques


@requiere_permiso("can_edit_budget")
def cerrar(request, hogar, ambito, anio=None, numero=None):
    """Cierra el mes que se esta viendo; sin fecha, el corriente.

    Con paginacion entre meses, "hoy" ya no vale: desde la pantalla de agosto
    se cierra agosto. Y un mes futuro no se cierra —congelaria un balance sin
    movimientos—, ni uno que el hogar no vivio.
    """
    ambito = validar(ambito)
    hoy = timezone.localdate()
    if anio is None:
        anio, numero = hoy.year, hoy.month
    exigir_en_el_calendario(anio, numero)
    if (anio, numero) > (hoy.year, hoy.month):
        raise Http404(_("That month has not started yet."))
    mes = services.obtener_mes(hogar, anio, numero)
    if isinstance(mes, services.ProyeccionDeMes):
        raise Http404(_("That month cannot be closed."))
    if request.method == "POST":
        try:
            services.cerrar_mes(mes)
        except MesCerrado:
            pass   # ya estaba cerrado: idempotente, no un error del usuario
        return redirect("budget:mes", ambito, anio, numero)
    return render(request, "budget/cerrar.html",
                  {"mes": mes, "ambito": ambito, "anio": anio, "numero": numero})


@requiere_permiso("can_view_budget")
def mesada(request, hogar):
    """Personal > Presupuesto: el libro mayor de la mesada (§7.2).

    Hasta el Plan 3, AllowanceLedger aparecia UNA vez en toda la aplicacion, y
    era una linea de texto en una previsualizacion. Aqui se ensena entero, y
    sobre todo se explica el ajuste: el §4.5.3 descuenta el faltante de un mes
    flojo en la mesada del mes SIGUIENTE, y sin esta pantalla un miembro recibe
    menos dinero por una decision que no puede ver.

    No lleva <ambito> en la ruta porque solo existe en Personal: la mesada es de
    un miembro por definicion, y una "mesada del hogar" no significa nada.
    """
    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)

    libro = None
    gastos = []
    if not isinstance(mes_actual, services.ProyeccionDeMes):
        libro = (
            AllowanceLedger.objects.for_household(hogar)
            .filter(member=membresia, budget_month=mes_actual)
            .first()
        )
        gastos = list(
            Transaction.objects.for_household(hogar)
            .filter(member=membresia, budget_month=mes_actual, scope="personal")
            .select_related("category")
            .order_by("-date", "-pk")
        )

    hay_ajuste = bool(libro and libro.adjustment)
    mes_del_ajuste = services.mes_anterior(mes_actual) if hay_ajuste else None

    return render(request, "budget/mesada.html", {
        "ambito": "personal", "libro": libro, "gastos": gastos,
        "mes": mes_actual, "hay_ajuste": hay_ajuste,
        "mes_del_ajuste": mes_del_ajuste,
    })


@requiere_permiso("can_edit_budget")
def linea_nueva(request, hogar):
    """Anade una partida excepcional al mes corriente (paso 2 del §4.5.6)."""
    hoy = timezone.localdate()
    mes = services.obtener_mes(hogar, hoy.year, hoy.month)
    return _linea_nueva(request, hogar, mes, ("budget:mes", "household"))


# Con el tipo en la ruta, el formulario no lo pregunta y vuelve al paso que
# lo lista: los ingresos al 1, los gastos al 2.
PASO_DE_KIND = {INCOME: 1, EXPENSE: 2}
TITULO_DE_KIND = {
    INCOME: _("One-off income this month"),
    EXPENSE: _("One-off expense this month"),
}


@requiere_permiso("can_edit_budget")
def linea_nueva_del_mes(request, hogar, ambito, anio, numero, kind=EXPENSE):
    """La misma partida, pero en el mes que se esta planificando."""
    ambito = validar(ambito)
    exigir_en_el_calendario(anio, numero)
    if kind not in PASO_DE_KIND:
        raise Http404(_("That kind of item does not exist."))
    mes = services.abrir_para_planificar(hogar, anio, numero)
    if mes is None:
        raise Http404(_("That month cannot be planned."))
    return _linea_nueva(
        request, hogar, mes,
        ("budget:planificar_mes", ambito, anio, numero, PASO_DE_KIND[kind]),
        kind=kind, titulo=TITULO_DE_KIND[kind],
    )


def _linea_nueva(request, hogar, mes, destino, kind=None, titulo=None):
    form = BudgetLineForm(request.POST or None, household=hogar, kind=kind)
    if request.method == "POST" and form.is_valid():
        linea = form.save(commit=False)
        linea.household = hogar
        linea.budget_month = mes
        linea.is_exceptional = True
        try:
            linea.full_clean()
            linea.save()
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect(*destino)
    return render(request, "budget/formulario.html", {
        "form": form, "titulo": titulo or _("One-off item this month"),
        "cancelar": reverse(destino[0], args=destino[1:]),
    })


@require_POST
@requiere_permiso("can_edit_budget")
def linea_quitar(request, hogar, ambito, pk):
    """Quita una partida excepcional. Solo las excepcionales: una linea que
    viene de una regla se pone a cero en el paso 2, no se borra — borrarla
    haria que el mes ya no contara con ese gasto sin dejar rastro."""
    ambito = validar(ambito)
    linea = get_object_or_404(
        BudgetLine.objects.for_household(hogar).select_related("budget_month"),
        pk=pk, is_exceptional=True,
    )
    mes = linea.budget_month
    if mes.esta_cerrado:
        messages.info(request, _("This month is already closed."))
    else:
        linea.delete()
    return redirect("budget:planificar_mes", ambito, mes.year, mes.month, 2)
