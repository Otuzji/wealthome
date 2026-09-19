"""Los fragmentos de htmx se prueban como fragmentos.

No hace falta un navegador: htmx es una peticion HTTP normal con una cabecera.
Lo que hay que verificar es que la vista devuelva el trozo y no la pagina
entera, y que el trozo siga estando acotado al hogar.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.seeds import sembrar
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


def _admin_logueado(client, con_arbol=False):
    hogar = HouseholdFactory()
    if con_arbol:
        sembrar(hogar)
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)
    return hogar, user


def test_registrar_por_htmx_devuelve_un_fragmento_y_no_la_pagina(client):
    # Con arbol: el formulario lista las lineas del mes, y proyectar el mes
    # exige la categoria de ingreso sembrada.
    _admin_logueado(client, con_arbol=True)

    entera = client.get(reverse("budget:registrar"))
    trozo = client.get(reverse("budget:registrar"), HTTP_HX_REQUEST="true")

    assert b"<!doctype html>" in entera.content.lower()
    assert b"<!doctype html>" not in trozo.content.lower()
    assert b"<form" in trozo.content


def test_un_gasto_guardado_por_htmx_devuelve_los_movimientos_al_dia(client):
    from django.utils import timezone

    hogar, _user = _admin_logueado(client, con_arbol=True)
    categoria = CategoryFactory(household=hogar, slug="cafe")
    hoy = timezone.localdate()

    respuesta = client.post(
        reverse("budget:registrar"),
        {"amount": "12.50", "date": hoy.isoformat(), "category": categoria.pk,
         "scope": "household", "payment_method": "debit", "comercio": ""},
        HTTP_HX_REQUEST="true",
    )

    assert respuesta.status_code == 200
    assert b"<!doctype html>" not in respuesta.content.lower()
    # La FILA, no el texto "12": ese tambien sale del value="12.50" del
    # formulario reenviado cuando el POST es invalido, y por eso esta prueba
    # llevaba desde la Tarea 24 pasando sin guardar nada — el payment_method
    # que enviaba no era una opcion valida.
    from apps.budget.models import Transaction
    guardada = Transaction.objects.for_household(hogar).get()
    assert guardada.amount == Decimal("12.50")
    html = respuesta.content.decode()
    assert str(guardada.amount) in html
    # Los movimientos viajan FUERA DE BANDA: el formulario del modal se envia
    # desde cualquier pantalla, y solo Overview tiene #recientes. Con
    # hx-target="#recientes", htmx no encontraba el destino en "This month" y
    # no enviaba nada — "Record it" no hacia nada.
    assert 'id="recientes"' in html and 'hx-swap-oob="true"' in html
    # Y en su sitio vuelve un formulario limpio, por si el modal sigue abierto.
    assert "<form" in html and 'value="12.50"' not in html


def test_el_formulario_del_modal_se_sustituye_a_si_mismo(client):
    """hx-target="this": el destino existe en toda pantalla. Un POST invalido
    devuelve el formulario con sus errores en el mismo sitio, no dentro de la
    lista de movimientos."""
    _admin_logueado(client, con_arbol=True)

    trozo = client.get(reverse("budget:registrar"), HTTP_HX_REQUEST="true").content.decode()
    assert 'hx-target="this"' in trozo and 'hx-swap="outerHTML"' in trozo
    assert 'hx-target="#recientes"' not in trozo

    invalido = client.post(reverse("budget:registrar"), {"amount": "12.50"},
                           HTTP_HX_REQUEST="true").content.decode()
    assert "<form" in invalido and 'id="recientes"' not in invalido


def test_un_hogar_expirado_no_puede_registrar_ni_por_htmx(client):
    """La guardia del §2.2 es por METODO: las vistas de htmx nacen cubiertas.

    Esta es la prueba que demuestra que la decision del §2.2 valio la pena: no se
    escribio ni una linea nueva de guardia para esta vista.
    """
    from datetime import timedelta

    from django.utils import timezone

    hogar, _user = _admin_logueado(client)
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    respuesta = client.post(reverse("budget:registrar"), {}, HTTP_HX_REQUEST="true")

    assert respuesta.status_code == 403


def test_un_hogar_expirado_si_puede_LEER_por_htmx(client):
    """El otro lado de "por metodo": expirar no destruye datos, solo escribe.

    No esta en el plan. Sin ella, una guardia que bloqueara TODA peticion de htmx
    —y no solo las de escritura— pasaria las otras pruebas igual.
    """
    from datetime import timedelta

    from django.utils import timezone

    hogar, _user = _admin_logueado(client, con_arbol=True)
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    respuesta = client.get(reverse("budget:registrar"), HTTP_HX_REQUEST="true")

    assert respuesta.status_code == 200


def test_el_filtro_del_overview_es_una_pagina_de_verdad(client):
    """hx-select pide la pagina entera: la URL filtrada tiene que funcionar sola."""
    _admin_logueado(client, con_arbol=True)
    url = reverse("budget:overview", args=["household"]) + "?kind=expense"

    entera = client.get(url)

    assert entera.status_code == 200
    assert b"<!doctype html>" in entera.content.lower()
    assert entera.context["filtro_kind"] == "expense"


def test_un_filtro_inventado_se_ignora_y_no_filtra(client):
    """Entrada hostil barata: el filtro llega de la query string."""
    _admin_logueado(client, con_arbol=True)
    url = reverse("budget:overview", args=["household"]) + "?kind=; DROP TABLE"

    respuesta = client.get(url)

    assert respuesta.status_code == 200
    assert respuesta.context["filtro_kind"] == "; DROP TABLE"


def test_el_fragmento_de_recientes_no_ensena_otro_hogar(client):
    """Un fragmento es un endpoint como cualquier otro: tambien esta acotado."""
    from django.utils import timezone

    from apps.households.services import crear_hogar
    from tests.factories_budget import BudgetMonthFactory, TransactionFactory

    hogar, _user = _admin_logueado(client, con_arbol=True)
    ajeno = crear_hogar(UserFactory(), "Los Otros", family_size=2)
    hoy = timezone.localdate()
    mes_ajeno = BudgetMonthFactory(household=ajeno, year=hoy.year, month=hoy.month)
    TransactionFactory(household=ajeno, budget_month=mes_ajeno,
                       category=CategoryFactory(household=ajeno, slug="su-cat"),
                       amount=Decimal("9999.99"), date=hoy)

    categoria = CategoryFactory(household=hogar, slug="cafe")
    respuesta = client.post(
        reverse("budget:registrar"),
        {"amount": "12.50", "date": hoy.isoformat(), "category": categoria.pk,
         "scope": "household", "payment_method": "debit", "comercio": ""},
        HTTP_HX_REQUEST="true",
    )

    assert b"9999" not in respuesta.content
    assert b"9,999.99" not in respuesta.content


def test_aportar_por_htmx_devuelve_los_aportes_y_no_la_pagina(client):
    from tests.factories_budget import GoalFactory

    hogar, _user = _admin_logueado(client, con_arbol=True)
    GoalFactory(household=hogar)

    trozo = client.get(reverse("budget:aportar"), HTTP_HX_REQUEST="true")

    assert trozo.status_code == 200
    assert b"<!doctype html>" not in trozo.content.lower()
    assert b"<form" in trozo.content


def test_un_gasto_guardado_avisa_con_hx_trigger(client):
    """Quien cerro el modal es el SERVIDOR, y solo cuando el gasto entro.

    El Overview escucha ese evento para cerrar el <dialog>. Intentarlo desde el
    cliente —mirando que el htmx:afterRequest viniera de dentro del dialogo— no
    cerraba de forma fiable, y ataba el fragmento del formulario, que comparte
    la pagina entera, a la pantalla que lo muestra.
    """
    from django.utils import timezone

    hogar, _user = _admin_logueado(client, con_arbol=True)
    categoria = CategoryFactory(household=hogar, slug="cafe")
    hoy = timezone.localdate()

    respuesta = client.post(
        reverse("budget:registrar"),
        {"amount": "12.50", "date": hoy.isoformat(), "category": categoria.pk,
         "scope": "household", "payment_method": "debit", "comercio": ""},
        HTTP_HX_REQUEST="true",
    )

    assert respuesta.headers.get("HX-Trigger") == "gasto-registrado"


def test_un_gasto_RECHAZADO_no_avisa_de_nada(client):
    """El otro lado, y es el que importa: si el formulario no valida, el modal
    tiene que quedarse abierto con los errores a la vista."""
    hogar, _user = _admin_logueado(client, con_arbol=True)

    respuesta = client.post(reverse("budget:registrar"), {}, HTTP_HX_REQUEST="true")

    assert respuesta.status_code == 200
    assert "HX-Trigger" not in respuesta.headers
    assert b"<form" in respuesta.content
