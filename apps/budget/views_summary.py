"""Summary: lo que los meses cerrados dicen, en tabla y en graficas.

Antes aqui vivia tambien el Overview. Se quito: This month es la pantalla
principal, y sus graficas del mes en curso ya no aportaban nada que la
tarjeta de This month no ensene. La ruta raiz del ambito se queda como
redireccion para no romper enlaces ni lo que el service worker tenga.
"""

from django.shortcuts import redirect, render

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services_goals, services_summary
from .scopes import validar


@requiere_permiso("can_view_budget")
def overview(request, hogar, ambito):
    return redirect("budget:mes", validar(ambito))


# `can_view_reports` y no `can_view_budget`: Summary ES un informe —los
# cierres anteriores y su varianza— y `can_view_reports` existe en el §6.2
# precisamente para eso.
@requiere_permiso("can_view_reports")
def summary(request, hogar, ambito):
    """Los cierres anteriores, con su varianza, y las series de las graficas.

    varianza_por_categoria se guarda como {str: str} (§1 del spec del Plan 3:
    no se migra); services_summary reconstruye los Decimal al leer.
    """
    ambito = validar(ambito)
    resumen = services_summary.resumen_de_cierres(hogar)
    return render(request, "budget/summary.html", {
        "ambito": ambito,
        "cierres": resumen["filas"],
        "series_meses": resumen["series"]["meses"],
        "series_por_mes": resumen["series"]["por_mes"],
        "series_categorias": resumen["series"]["categorias"],
        # El ahorro no sale de los cierres: un aporte a mano es dinero de
        # fuera del presupuesto, y aqui es donde se ve.
        "ahorro": services_goals.resumen_ahorro(hogar, ambito, membresia_actual(request)),
    })
