"""Reportes: gastos e ingresos filtrados (Fase 2, §12 del diseno de la Fase 1).

Filtros por periodo, tipo, ambito, categoria, miembro y comercio, y la misma
seleccion descargable en CSV. Lo personal de otro miembro no aparece nunca,
ni filtrando por ese miembro: la misma regla que el resto de la aplicacion.
"""
import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.models import Merchant
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import BudgetMonthFactory, CategoryFactory, TransactionFactory

pytestmark = pytest.mark.django_db

URL = "budget:reportes"
OCTUBRE = {"desde": "2026-10-01", "hasta": "2026-10-31"}


def _comercio(hogar, nombre):
    m = Merchant(household=hogar, name=nombre)
    m.save()
    return m


@pytest.fixture
def datos():
    a = UserFactory(display_name="Ana")
    hogar = crear_hogar(a, "Family Test", family_size=2)
    mem_a = Membership.objects.get(household=hogar, user=a)
    mem_b = MembershipFactory(household=hogar, can_view_reports=True)
    octubre = BudgetMonthFactory(household=hogar, year=2026, month=10)
    septiembre = BudgetMonthFactory(household=hogar, year=2026, month=9)

    super_ = CategoryFactory(household=hogar, name="CAT-SUPER", slug="r-super", kind="expense")
    sueldo = CategoryFactory(household=hogar, name="CAT-SUELDO", slug="r-sueldo", kind="income")
    pers_a = CategoryFactory(household=hogar, name="CAT-PERSONAL-A", slug="r-pa", kind="expense")
    pers_b = CategoryFactory(household=hogar, name="CAT-PERSONAL-B", slug="r-pb", kind="expense")
    walmart = _comercio(hogar, "Walmart")
    costco = _comercio(hogar, "Costco")

    def tx(**kw):
        kw.setdefault("budget_month", octubre)
        return TransactionFactory(household=hogar, **kw)

    tx(category=super_, amount=Decimal("100.00"), date=date(2026, 10, 5), member=mem_a,
       merchant=walmart, note="compra semanal")
    tx(category=sueldo, amount=Decimal("3000.00"), date=date(2026, 10, 1), member=mem_a)
    tx(category=super_, amount=Decimal("40.00"), date=date(2026, 10, 8), member=mem_b,
       merchant=costco)
    tx(category=pers_a, amount=Decimal("25.00"), date=date(2026, 10, 9), member=mem_a,
       scope="personal")
    tx(category=pers_b, amount=Decimal("60.00"), date=date(2026, 10, 10), member=mem_b,
       scope="personal", note="SECRETO-DE-B")
    tx(category=super_, amount=Decimal("70.00"), date=date(2026, 9, 20), member=mem_a,
       budget_month=septiembre)
    return {"hogar": hogar, "a": mem_a, "b": mem_b, "super": super_, "sueldo": sueldo,
            "pers_a": pers_a, "pers_b": pers_b, "octubre": octubre}


def _reporte(client, membresia, **filtros):
    client.force_login(membresia.user)
    respuesta = client.get(reverse(URL), filtros)
    assert respuesta.status_code == 200
    return respuesta.context["reporte"]


def _importes(reporte):
    return sorted(t.amount for t in reporte["filas"])


# --- donde vive y quien lo ve ---------------------------------------------------


def test_reportes_esta_en_el_menu_lateral(client, datos):
    client.force_login(datos["a"].user)
    respuesta = client.get(reverse("budget:mes", args=["household"]))
    urls = [e["url"] for e in respuesta.context["nav_drawer"]]
    assert reverse(URL) in urls


def test_sin_permiso_de_reportes_no_se_abre(client, datos):
    datos["b"].can_view_reports = False
    datos["b"].save()
    client.force_login(datos["b"].user)
    assert client.get(reverse(URL)).status_code == 403


def test_sin_filtros_es_el_mes_en_curso(client, datos):
    from django.utils import timezone

    client.force_login(datos["a"].user)
    reporte = client.get(reverse(URL)).context["reporte"]
    hoy = timezone.localdate()
    assert reporte["desde"] == hoy.replace(day=1)
    assert reporte["hasta"] >= hoy


# --- filtros ---------------------------------------------------------------------


def test_el_periodo_filtra(client, datos):
    reporte = _reporte(client, datos["a"], **OCTUBRE)
    assert Decimal("70.00") not in _importes(reporte)
    assert Decimal("100.00") in _importes(reporte)


def test_solo_gastos(client, datos):
    reporte = _reporte(client, datos["a"], tipo="expense", **OCTUBRE)
    assert Decimal("3000.00") not in _importes(reporte)
    assert reporte["total_ingresos"] == Decimal("0.00")


def test_solo_ingresos(client, datos):
    reporte = _reporte(client, datos["a"], tipo="income", **OCTUBRE)
    assert _importes(reporte) == [Decimal("3000.00")]


def test_por_defecto_lo_del_hogar_y_lo_mio(client, datos):
    reporte = _reporte(client, datos["a"], **OCTUBRE)
    assert _importes(reporte) == [Decimal("25.00"), Decimal("40.00"), Decimal("100.00"),
                                  Decimal("3000.00")]


def test_lo_personal_de_otro_no_aparece_nunca(client, datos):
    for filtros in ({}, {"ambito": "personal"}, {"miembro": datos["b"].pk},
                    {"categoria": datos["pers_b"].pk}):
        reporte = _reporte(client, datos["a"], **OCTUBRE, **filtros)
        assert Decimal("60.00") not in _importes(reporte), filtros


def test_lo_personal_de_otro_no_sale_en_el_html_ni_en_el_csv(client, datos):
    client.force_login(datos["a"].user)
    html = client.get(reverse(URL), OCTUBRE).content.decode()
    csv_ = client.get(reverse(URL), {**OCTUBRE, "formato": "csv"}).content.decode()
    for texto in (html, csv_):
        assert "SECRETO-DE-B" not in texto
        assert "60.00" not in texto
    # Las categorias son el catalogo comun del hogar (salen en el filtro); lo
    # privado es el registro de B, que no sale en ninguna fila.
    assert "CAT-PERSONAL-B" not in csv_


def test_ambito_hogar(client, datos):
    reporte = _reporte(client, datos["a"], ambito="household", **OCTUBRE)
    assert Decimal("25.00") not in _importes(reporte)


def test_ambito_personal_es_solo_lo_mio(client, datos):
    reporte = _reporte(client, datos["a"], ambito="personal", **OCTUBRE)
    assert _importes(reporte) == [Decimal("25.00")]


def test_por_categoria(client, datos):
    reporte = _reporte(client, datos["a"], categoria=datos["super"].pk, **OCTUBRE)
    assert _importes(reporte) == [Decimal("40.00"), Decimal("100.00")]


def test_por_miembro(client, datos):
    reporte = _reporte(client, datos["a"], miembro=datos["b"].pk, **OCTUBRE)
    assert _importes(reporte) == [Decimal("40.00")]


def test_por_comercio_sin_importar_mayusculas(client, datos):
    reporte = _reporte(client, datos["a"], comercio="walm", **OCTUBRE)
    assert _importes(reporte) == [Decimal("100.00")]


def test_una_categoria_de_otro_hogar_no_revienta_ni_filtra_nada_ajeno(client, datos):
    otro = crear_hogar(UserFactory(), "Otro", family_size=1)
    ajena = CategoryFactory(household=otro, name="CAT-AJENA", slug="r-ajena")
    client.force_login(datos["a"].user)

    respuesta = client.get(reverse(URL), {**OCTUBRE, "categoria": ajena.pk})

    assert respuesta.status_code == 200
    assert "CAT-AJENA" not in respuesta.content.decode()


def test_fechas_al_reves_o_invalidas_no_revientan(client, datos):
    client.force_login(datos["a"].user)
    for filtros in ({"desde": "2026-10-31", "hasta": "2026-10-01"},
                    {"desde": "no-es-fecha"}):
        assert client.get(reverse(URL), filtros).status_code == 200


def test_otro_hogar_no_aparece(client, datos):
    otro = crear_hogar(UserFactory(), "Otro", family_size=1)
    TransactionFactory(household=otro, amount=Decimal("9999.00"), date=date(2026, 10, 3),
                       budget_month=BudgetMonthFactory(household=otro, year=2026, month=10))
    reporte = _reporte(client, datos["a"], **OCTUBRE)
    assert Decimal("9999.00") not in _importes(reporte)


# --- cifras ----------------------------------------------------------------------


def test_totales(client, datos):
    reporte = _reporte(client, datos["a"], **OCTUBRE)
    assert reporte["total_ingresos"] == Decimal("3000.00")
    assert reporte["total_gastos"] == Decimal("165.00")
    assert reporte["neto"] == Decimal("2835.00")


def test_desglose_por_categoria_de_mayor_a_menor(client, datos):
    reporte = _reporte(client, datos["a"], tipo="expense", **OCTUBRE)
    filas = [(f["categoria"].pk, f["total"]) for f in reporte["por_categoria"]]
    assert filas == [(datos["super"].pk, Decimal("140.00")),
                     (datos["pers_a"].pk, Decimal("25.00"))]
    assert reporte["por_categoria"][0]["porcentaje"] == 85


def test_desglose_por_miembro(client, datos):
    reporte = _reporte(client, datos["a"], tipo="expense", **OCTUBRE)
    totales = {f["miembro"].pk: f["total"] for f in reporte["por_miembro"]}
    assert totales == {datos["a"].pk: Decimal("125.00"), datos["b"].pk: Decimal("40.00")}


# --- CSV -------------------------------------------------------------------------


def test_el_csv_lleva_la_misma_seleccion(client, datos):
    client.force_login(datos["a"].user)
    respuesta = client.get(reverse(URL), {**OCTUBRE, "tipo": "expense", "formato": "csv"})

    assert respuesta["Content-Type"].startswith("text/csv")
    assert "attachment" in respuesta["Content-Disposition"]
    filas = list(csv.reader(io.StringIO(respuesta.content.decode("utf-8-sig"))))
    cabecera, cuerpo = filas[0], filas[1:]
    assert len(cabecera) >= 6
    assert sorted(f[-1] for f in cuerpo) == ["100.00", "25.00", "40.00"]


def test_el_csv_no_deja_formulas_que_ejecutar(client, datos):
    """Una nota que empieza por = la ejecutaria Excel al abrir el archivo."""
    TransactionFactory(household=datos["hogar"], category=datos["super"],
                       amount=Decimal("1.00"), date=date(2026, 10, 11), member=datos["a"],
                       note="=HYPERLINK(\"http://malo\")", budget_month=datos["octubre"])
    client.force_login(datos["a"].user)
    contenido = client.get(reverse(URL), {**OCTUBRE, "formato": "csv"}).content.decode("utf-8-sig")
    assert ",=HYPERLINK" not in contenido
    assert "'=HYPERLINK" in contenido
