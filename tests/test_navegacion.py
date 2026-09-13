"""La navegacion como entregable con nombre propio.

El Plan 2 dejo un menu que enlazaba 1 de 6 pantallas y un miembro con solo
can_add_transactions sin ningun camino a registrar un gasto, y ninguna prueba
lo vio: todas llegan por reverse(), que no navega.

El mapa PERFILES es un dato, no prosa. Anadir una pantalla sin ponerla en el
menu rompe esta prueba, que es justo lo que se quiere.
"""

import pytest
from django.urls import reverse

from apps.budget.seeds import sembrar
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory

ADMIN = "admin"
SOLO_VER = "solo_ver"
ADOLESCENTE = "adolescente"

PERMISOS = {
    ADMIN: {"can_view_budget": True, "can_edit_budget": True,
            "can_add_transactions": True, "can_view_reports": True},
    SOLO_VER: {"can_view_budget": True, "can_edit_budget": False,
               "can_add_transactions": False, "can_view_reports": False},
    # El adolescente del §6.2: registra sus gastos y no ve la hipoteca.
    ADOLESCENTE: {"can_view_budget": False, "can_edit_budget": False,
                  "can_add_transactions": True, "can_view_reports": False},
}

# Lo que CADA perfil tiene que poder alcanzar desde el menu, por nombre de
# entrada. Ni una mas, ni una menos.
ESPERADO = {
    ADMIN: {"hogar", "personal", "mesada", "registrar", "metas", "balance", "ajustes"},
    # SOLO_VER no tiene can_view_reports, asi que NO ve Balance. Es la prueba de
    # que la entrada esta bajo el permiso correcto y no bajo can_view_budget.
    SOLO_VER: {"hogar", "personal", "mesada", "metas", "ajustes"},
    ADOLESCENTE: {"registrar", "ajustes"},
}


def _sesion(client, perfil):
    hogar = HouseholdFactory()
    # sembrar() y no HouseholdFactory() a secas: sin el arbol de categorias,
    # seguir el enlace del mes revienta con LookupError en cuanto obtener_mes
    # intenta materializar. Es el mismo vicio que el ruling de la Tarea 4 del
    # plan ya corto en la fixture del presupuesto de consultas, y esta prueba
    # existe precisamente para SEGUIR los enlaces, no para hacer reverse().
    sembrar(hogar)
    user = UserFactory()
    membresia = MembershipFactory(user=user, household=hogar, role="member")
    for campo, valor in PERMISOS[perfil].items():
        setattr(membresia, campo, valor)
    membresia.save()
    client.force_login(user)
    return hogar, user


@pytest.mark.django_db
@pytest.mark.parametrize("perfil", [ADMIN, SOLO_VER, ADOLESCENTE])
def test_el_menu_ensena_exactamente_lo_que_el_perfil_puede_abrir(client, perfil):
    _sesion(client, perfil)
    respuesta = client.get(reverse("households:ajustes"))
    nombres = {e["nombre"] for e in respuesta.context["nav_entradas"]}
    assert nombres == ESPERADO[perfil]


@pytest.mark.django_db
@pytest.mark.parametrize("perfil", [ADMIN, SOLO_VER, ADOLESCENTE])
def test_ningun_enlace_del_menu_devuelve_403(client, perfil):
    """Un 403 al hacer clic es correcto pero grosero (§7 del Plan 2)."""
    _sesion(client, perfil)
    respuesta = client.get(reverse("households:ajustes"))
    for entrada in respuesta.context["nav_entradas"]:
        seguimiento = client.get(entrada["url"])
        assert seguimiento.status_code == 200, (
            f"El perfil {perfil} ve en su menu {entrada['nombre']} "
            f"({entrada['url']}) y al seguirlo recibe {seguimiento.status_code}."
        )


@pytest.mark.django_db
def test_el_adolescente_llega_a_registrar_un_gasto_sin_teclear_la_url(client):
    """El criterio de aceptacion 5, escrito como prueba."""
    _sesion(client, ADOLESCENTE)
    respuesta = client.get(reverse("households:ajustes"))
    urls = [e["url"] for e in respuesta.context["nav_entradas"]]
    assert reverse("budget:registrar") in urls
    assert client.get(reverse("budget:registrar")).status_code == 200


@pytest.mark.django_db
def test_un_hogar_expirado_pierde_el_mas_y_gana_el_aviso(client):
    """§5.2 y §7 juntos: expirar quita el [+] en vez de dejarlo dar un 403.

    No esta en el plan. La comprobacion equivalente del context processor la
    hace el mapa de arriba solo para hogares vigentes, asi que sin esto la rama
    `if not nav_puede_escribir` de _nav.html no la ejercitaba nadie.
    """
    from datetime import timedelta

    from django.utils import timezone

    hogar, _user = _sesion(client, ADMIN)
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    respuesta = client.get(reverse("households:ajustes"))
    nombres = {e["nombre"] for e in respuesta.context["nav_entradas"]}

    assert "registrar" not in nombres
    assert respuesta.context["nav_puede_escribir"] is False
    assert reverse("subscriptions:estado") in respuesta.content.decode()


@pytest.mark.django_db
def test_el_menu_no_aparece_sin_sesion(client):
    """En login y registro no hay hogar, y el context processor no debe reventar."""
    respuesta = client.get(reverse("accounts:login"))

    assert respuesta.status_code == 200
    assert respuesta.context["nav_entradas"] == []


@pytest.mark.django_db
def test_cada_entrada_del_menu_trae_su_icono(client):
    """La barra de movil se apoya en los iconos, no en el texto.

    Con siete destinos y etiquetas de texto la barra no cabia en 390 px y dos
    pantallas quedaban fuera de la pantalla, inalcanzables. Ahora en movil manda
    el icono — asi que una entrada nueva SIN icono deja un hueco por el que no se
    puede pinchar, y esta prueba lo caza: _nav_icono.html cae en un circulo
    generico, que es lo que se busca aqui.
    """
    from apps.core.context_processors import navegacion

    _sesion(client, ADMIN)
    respuesta = client.get(reverse("households:ajustes"))
    cuerpo = respuesta.content.decode()

    conocidos = {"home", "persona", "mesada", "mas", "meta", "balance", "ajustes"}
    for entrada in respuesta.context["nav_entradas"]:
        assert entrada["icono"] in conocidos, (
            f"la entrada {entrada['nombre']!r} usa el icono {entrada['icono']!r}, "
            f"que _nav_icono.html no dibuja: saldria un circulo generico"
        )

    # Y que los SVG llegan de verdad al HTML, uno por entrada.
    assert cuerpo.count('class="nav__icono"') == len(respuesta.context["nav_entradas"])


@pytest.mark.django_db
def test_el_menu_conserva_su_etiqueta_para_los_lectores_de_pantalla(client):
    """El icono se ve, el texto no — pero sigue en el DOM. Ocultarlo con
    display:none lo quitaria tambien del lector de pantalla."""
    _sesion(client, ADMIN)

    cuerpo = client.get(reverse("households:ajustes")).content.decode()

    assert 'class="nav__texto"' in cuerpo
    assert "Balance" in cuerpo
