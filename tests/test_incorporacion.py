"""El asistente del §7.2, y sobre todo que se pueda abandonar.

El paso 1 crea el hogar de verdad; los cinco siguientes escriben contra el. Un
asistente obligatorio convertiria cerrar la pestana en el paso 3 en una cuenta
rota, asi que cada paso se puede saltar y el asistente se reanuda.
"""

import pytest
from django.urls import reverse

from apps.budget.seeds import sembrar
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

pytestmark = pytest.mark.django_db


def _admin(client):
    hogar = HouseholdFactory()
    sembrar(hogar)
    user = UserFactory()
    MembershipFactory(user=user, household=hogar, role="admin")
    client.force_login(user)
    return hogar, user


def test_el_registro_deja_al_admin_en_el_paso_dos(client):
    respuesta = client.post(reverse("accounts:registro"), {
        "email": "nuevo@example.com", "password1": "clave-larga-123",
        "password2": "clave-larga-123", "display_name": "Nuevo",
        "household_name": "Los Nuevos", "family_size": 3,
    }, follow=True)

    assert respuesta.status_code == 200
    assert reverse("budget:incorporacion", args=[2]) in respuesta.redirect_chain[-1][0]


@pytest.mark.parametrize("paso", [2, 3, 4, 5, 6])
def test_cada_paso_se_puede_saltar(client, paso):
    _admin(client)

    respuesta = client.get(reverse("budget:incorporacion", args=[paso]))

    assert respuesta.status_code == 200
    assert respuesta.context["paso"] == paso
    assert respuesta.context["siguiente"] is not None or paso == 6


def test_el_ultimo_paso_termina_y_no_encadena(client):
    """No esta en el plan: sin esto, un `siguiente` mal calculado en el paso 6
    mandaria al 7, que es un 404, y el asistente acabaria en un error."""
    _admin(client)

    respuesta = client.get(reverse("budget:incorporacion", args=[6]))

    assert respuesta.context["siguiente"] is None
    assert reverse("budget:mes", args=["household"]) in respuesta.content.decode()


def test_cada_paso_enlaza_a_un_formulario_que_existe(client):
    """Los pasos ENVUELVEN formularios que ya existen. Una ruta mal escrita en el
    mapa reventaria con NoReverseMatch al renderizar, no al definirlo."""
    _admin(client)

    for paso in (2, 3, 4, 5, 6):
        respuesta = client.get(reverse("budget:incorporacion", args=[paso]))
        assert respuesta.status_code == 200


def test_abandonar_a_medias_deja_una_aplicacion_usable(client):
    """Cerrar la pestana en el paso 3 no puede dejar una cuenta rota."""
    _admin(client)

    client.get(reverse("budget:incorporacion", args=[3]))

    # Y ahora, como si hubiera cerrado la pestana: entra por la puerta normal.
    assert client.get(reverse("budget:mes", args=["household"])).status_code == 200
    assert client.get(reverse("budget:configurar")).status_code == 200


def test_un_paso_fuera_de_rango_da_404(client):
    _admin(client)
    assert client.get("/budget/welcome/9/").status_code == 404
