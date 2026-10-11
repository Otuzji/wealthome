"""Sort by de "What actually happened": por fecha (lo mas reciente arriba) o
por categoria. Es un enlace con ?orden=categoria y no JavaScript: funciona sin
Alpine y la URL se puede compartir. Al ordenar, la pestana de lo real queda
abierta en el movil; si no, el toque te devolveria a Planned.
"""

import re
from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.budget.models import Transaction
from tests.budget.test_registrar_contra_el_plan import _pago, hogar_con_plan  # noqa: F401
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def tres_registros(client, hogar_con_plan):
    """Zapatos el dia 3, Farmacia el 1 y otra vez Farmacia el 2."""
    admin, hogar, mes = hogar_con_plan
    client.force_login(admin)
    zapatos = CategoryFactory(household=hogar, slug="zapatos", kind="expense", name="Zapatos")
    farmacia = CategoryFactory(household=hogar, slug="farmacia", kind="expense", name="Farmacia")
    hoy = timezone.localdate()
    for categoria, dia, importe in [(zapatos, 3, "70.00"), (farmacia, 1, "11.00"), (farmacia, 2, "22.00")]:
        client.post(reverse("budget:registrar"), _pago(
            budget_line="", category=categoria.pk, name=f"x{dia}", amount=importe,
            date=date(hoy.year, hoy.month, dia).isoformat(),
        ))
    assert Transaction.objects.for_household(hogar).count() == 3
    return admin, hogar, mes


def _importes_de_lo_real(html):
    panel = html.split('id="panel-real"', 1)[1].split("</section>", 1)[0]
    return re.findall(r"(\d+\.\d\d)", panel)


def test_por_defecto_ordena_por_fecha(client, tres_registros):
    html = client.get(reverse("budget:mes", args=["household"])).content.decode()

    assert _importes_de_lo_real(html) == ["70.00", "22.00", "11.00"]
    assert "vista: 'plan'" in html


def test_por_categoria_agrupa_y_abre_la_pestana_de_lo_real(client, tres_registros):
    html = client.get(reverse("budget:mes", args=["household"]) + "?orden=categoria").content.decode()

    assert _importes_de_lo_real(html) == ["22.00", "11.00", "70.00"]
    assert "vista: 'real'" in html


def test_el_selector_marca_el_orden_activo(client, tres_registros):
    html = client.get(reverse("budget:mes", args=["household"]) + "?orden=categoria").content.decode()

    assert re.search(r'href="\?orden=categoria"[^>]*aria-current="true"', html)
