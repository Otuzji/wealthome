"""Reportes: la pagina con sus filtros, y la misma seleccion en CSV."""

import csv

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.households.permissions import membresia_actual, requiere_permiso

from . import services_reportes
from .forms import ReporteForm

# Lo que una hoja de calculo ejecutaria como formula al abrir el archivo.
_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")


def _celda(valor):
    """Una nota o un comercio que empieza por = se volveria una formula en
    Excel (inyeccion CSV). Con un apostrofo delante se lee como texto."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto.startswith(_PELIGROSOS) else texto


# `can_view_reports`: el permiso existe en el §6.2 precisamente para esto.
@requiere_permiso("can_view_reports")
def reportes(request, hogar):
    form = ReporteForm(request.GET or None, household=hogar)
    filtros = form.filtros()
    if not request.GET:
        # Sin filtros, el formulario ensena el periodo que el reporte usa.
        form = ReporteForm(household=hogar,
                           initial={"desde": filtros["desde"], "hasta": filtros["hasta"]})
    reporte = services_reportes.generar(hogar, membresia_actual(request), filtros)
    if request.GET.get("formato") == "csv":
        return _csv(reporte)
    return render(request, "budget/reportes.html", {
        "form": form, "reporte": reporte,
        "consulta_csv": _con_formato_csv(request),
    })


def _con_formato_csv(request):
    consulta = request.GET.copy()
    consulta["formato"] = "csv"
    return consulta.urlencode()


def _csv(reporte):
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    nombre = f"wealthome-{reporte['desde']:%Y%m%d}-{reporte['hasta']:%Y%m%d}.csv"
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    # La marca BOM: sin ella, Excel abre un CSV en UTF-8 como si fuera Latin-1
    # y los acentos salen rotos.
    respuesta.write("﻿")
    escritor = csv.writer(respuesta)
    escritor.writerow([_("Date"), _("Type"), _("Category"), _("Merchant"), _("Note"),
                       _("Member"), _("Scope"), _("Amount")])
    for t in reporte["filas"]:
        escritor.writerow([
            t.date.isoformat(),
            _celda(t.category.get_kind_display()),
            _celda(t.category.etiqueta()),
            _celda(t.merchant.name if t.merchant_id else ""),
            _celda(t.note),
            _celda(t.member.user),
            _celda(t.get_scope_display()),
            f"{t.amount:.2f}",
        ])
    return respuesta
