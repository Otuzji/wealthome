"""Overview y Balance: las dos pantallas que ENSENAN lo que el motor calcula.

Hasta el Plan 3, los cuatro totales del cierre y varianza_por_categoria se
calculaban, se guardaban y no aparecian en ninguna pantalla.
"""

from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services
from .models import Category, MonthlyClose
from .scopes import acotar, acotar_por_dueno, validar

MESES_EN_LA_GRAFICA = 6
MOVIMIENTOS_RECIENTES = 8


@requiere_permiso("can_view_budget")
def overview(request, hogar, ambito):
    ambito = validar(ambito)
    membresia = membresia_actual(request)
    hoy = timezone.localdate()
    resultado = services.obtener_mes(hogar, hoy.year, hoy.month)
    es_proyeccion = isinstance(resultado, services.ProyeccionDeMes)

    planeado, real = {}, {}
    recientes = []
    if not es_proyeccion:
        for linea in acotar_por_dueno(
            resultado.lineas.select_related("category"), ambito, membresia
        ):
            clave = linea.category.etiqueta()
            planeado[clave] = planeado.get(clave, Decimal("0.00")) + linea.planned_amount

        movimientos = acotar(
            resultado.transacciones.select_related("category"), ambito, membresia
        )
        for tx in movimientos:
            clave = tx.category.etiqueta()
            real[clave] = real.get(clave, Decimal("0.00")) + tx.amount
        recientes = list(movimientos.order_by("-date", "-pk")[:MOVIMIENTOS_RECIENTES])
    else:
        for linea in resultado.lineas:
            planeado[linea.nombre] = planeado.get(linea.nombre, Decimal("0.00")) + linea.importe

    etiquetas = sorted(set(planeado) | set(real))
    # Los importes viajan como `str` y no como Decimal: json_script no sabe
    # serializar Decimal, y pasarlos por float seria meter coma flotante en una
    # aplicacion financiera por comodidad de una grafica.
    series_categorias = {
        "etiquetas": etiquetas,
        "planeado": [str(planeado.get(e, Decimal("0.00"))) for e in etiquetas],
        "real": [str(real.get(e, Decimal("0.00"))) for e in etiquetas],
    }

    cierres = list(
        MonthlyClose.objects.for_household(hogar)
        .select_related("budget_month")
        .order_by("-budget_month__year", "-budget_month__month")[:MESES_EN_LA_GRAFICA]
    )[::-1]
    series_balance = {
        "etiquetas": [f"{c.budget_month.year}-{c.budget_month.month:02d}" for c in cierres],
        "balance": [str(c.balance) for c in cierres],
    }

    return render(request, "budget/overview.html", {
        "ambito": ambito, "resultado": resultado, "es_proyeccion": es_proyeccion,
        "recientes": recientes,
        "series_categorias": series_categorias,
        "series_balance": series_balance,
    })


# `can_view_reports` y no `can_view_budget`, que es lo que decia el Step 3 del
# plan para esta vista. Balance ES un informe —la varianza y los cierres
# anteriores— y `can_view_reports` existe en el §6.2 precisamente para eso. Con
# can_view_budget, un miembro al que se le nego ver informes los veria igual.
@requiere_permiso("can_view_reports")
def balance(request, hogar, ambito):
    """El balance actual y los cierres anteriores, con SU VARIANZA.

    varianza_por_categoria se guarda como {str: str} (§1 del spec del Plan 3:
    no se migra). Aqui se reconstruyen los Decimal al leer, que es mas barato
    que una migracion de datos sobre un JSON.
    """
    ambito = validar(ambito)
    cierres_orm = list(
        MonthlyClose.objects.for_household(hogar)
        .select_related("budget_month")
        .order_by("-budget_month__year", "-budget_month__month")
    )

    # Las categorias, de UNA vez para todos los cierres: una consulta por cierre
    # seria un N+1 nuevo recien estrenado, justo lo que la Tarea 4 vino a quitar.
    ids = set()
    for cierre in cierres_orm:
        ids.update(int(k) for k in cierre.varianza_por_categoria)
    categorias = {
        c.pk: c for c in Category.objects.for_household(hogar).filter(pk__in=ids)
    }

    filas = []
    for cierre in cierres_orm:
        varianza = [
            {"categoria": categorias[int(pk)], "importe": Decimal(importe)}
            for pk, importe in cierre.varianza_por_categoria.items()
            if int(pk) in categorias
        ]
        # De la peor desviacion a la mejor: lo que se fue de madre primero.
        varianza.sort(key=lambda v: v["importe"])
        filas.append({"cierre": cierre, "mes": cierre.budget_month, "varianza": varianza})

    return render(request, "budget/balance.html", {"ambito": ambito, "cierres": filas})
