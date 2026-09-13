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
from .forms import BudgetLineForm, TransactionForm
from .models import AllowanceLedger, MesCerrado, Transaction
from .scopes import acotar, acotar_por_dueno, validar

# El calendario, no una preferencia: 1..12, y un rango de años que cabe en el
# PositiveSmallIntegerField del modelo y en el que un presupuesto tiene sentido.
ANIO_MINIMO, ANIO_MAXIMO = 2000, 2100

MOVIMIENTOS_RECIENTES = 8


def _recientes(hogar):
    """Los ultimos movimientos del hogar, para el intercambio de htmx."""
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
            if es_htmx:
                # Los movimientos al dia, no un redirect: htmx los intercambia
                # en su sitio y el usuario no pierde la pantalla.
                return render(request, "budget/_fragmentos/recientes.html", {
                    "recientes": _recientes(hogar),
                })
            return redirect("budget:registrar")

    plantilla = "budget/_fragmentos/gasto_form.html" if es_htmx else "budget/gasto.html"
    return render(request, plantilla, {"form": form})


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
    form = BudgetLineForm(request.POST or None, household=hogar)
    if request.method == "POST" and form.is_valid():
        mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
        linea = form.save(commit=False)
        linea.household = hogar
        linea.budget_month = mes_actual
        linea.is_exceptional = True
        try:
            linea.full_clean()
            linea.save()
        except MesCerrado:
            form.add_error(None, _("This month is already closed."))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("budget:mes", "household")
    return render(request, "budget/formulario.html",
                  {"form": form, "titulo": _("One-off item this month")})
