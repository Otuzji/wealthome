"""La navegacion como entregable con nombre propio.

El Plan 2 dejo un menu que enlazaba 1 de 6 pantallas y un miembro con solo
can_add_transactions sin ningun camino a registrar un gasto, y ninguna prueba
lo vio: todas llegan por reverse(), que no navega.

Desde el rediseno de la interfaz el menu tiene cuatro piezas, todas datos del
context processor `navegacion`:

- `nav_ambitos`: el conmutador Household | Personal de la barra superior.
- `nav_pantallas`: las pestanas del ambito actual (Overview, This month...).
- `nav_drawer`: lo que abre el avatar (preferencias, miembros, suscripcion...).
- `nav_fab`: si se pinta el boton flotante de registrar un gasto.

Los mapas ESPERADO_* son datos, no prosa. Anadir una pantalla sin ponerla en el
menu rompe estas pruebas, que es justo lo que se quiere.
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
ROL = {ADMIN: "admin", SOLO_VER: "member", ADOLESCENTE: "member"}

# Las pestanas de HOUSEHOLD por perfil. Ni una mas, ni una menos.
ESPERADO_PANTALLAS = {
    # SOLO_VER no tiene can_view_reports, asi que NO ve Balance. Es la prueba de
    # que la pestana esta bajo el permiso correcto y no bajo can_view_budget.
    ADMIN: ["resumen", "mes", "metas", "balance"],
    SOLO_VER: ["resumen", "mes", "metas"],
    ADOLESCENTE: [],
}

# Lo que abre el avatar, por perfil.
ESPERADO_DRAWER = {
    ADMIN: ["preferencias", "configurar", "miembros", "invitar", "suscripcion"],
    SOLO_VER: ["preferencias", "miembros", "suscripcion"],
    ADOLESCENTE: ["preferencias", "miembros", "suscripcion"],
}

ESPERADO_FAB = {ADMIN: True, SOLO_VER: False, ADOLESCENTE: True}


def _sesion(client, perfil):
    hogar = HouseholdFactory()
    # sembrar() y no HouseholdFactory() a secas: sin el arbol de categorias,
    # seguir el enlace del mes revienta con LookupError en cuanto obtener_mes
    # intenta materializar. Esta prueba existe precisamente para SEGUIR los
    # enlaces, no para hacer reverse().
    sembrar(hogar)
    user = UserFactory()
    membresia = MembershipFactory(user=user, household=hogar, role=ROL[perfil])
    for campo, valor in PERMISOS[perfil].items():
        setattr(membresia, campo, valor)
    membresia.save()
    client.force_login(user)
    return hogar, user


def _nombres(entradas):
    return [e["nombre"] for e in entradas]


def _todas_las_urls(contexto):
    return (
        [a["url"] for a in contexto["nav_ambitos"]]
        + [p["url"] for p in contexto["nav_pantallas"]]
        + [d["url"] for d in contexto["nav_drawer"]]
    )


# ---------- pestanas ----------

@pytest.mark.django_db
@pytest.mark.parametrize("perfil", [ADMIN, SOLO_VER, ADOLESCENTE])
def test_las_pestanas_ensenan_exactamente_lo_que_el_perfil_puede_abrir(client, perfil):
    _sesion(client, perfil)
    respuesta = client.get(reverse("accounts:preferencias"))
    assert _nombres(respuesta.context["nav_pantallas"]) == ESPERADO_PANTALLAS[perfil]


@pytest.mark.django_db
def test_la_mesada_solo_es_una_pestana_de_personal(client):
    """La mesada es de un miembro por definicion: una "mesada del hogar" no
    significa nada, asi que en Household no aparece."""
    _sesion(client, ADMIN)

    en_personal = client.get(reverse("budget:overview", args=["personal"]))
    en_hogar = client.get(reverse("budget:overview", args=["household"]))

    assert "mesada" in _nombres(en_personal.context["nav_pantallas"])
    assert "mesada" not in _nombres(en_hogar.context["nav_pantallas"])


@pytest.mark.django_db
def test_las_pestanas_apuntan_al_ambito_en_el_que_estas(client):
    _sesion(client, ADMIN)
    respuesta = client.get(reverse("budget:metas", args=["personal"]))
    urls = [p["url"] for p in respuesta.context["nav_pantallas"]]
    assert reverse("budget:mes", args=["personal"]) in urls
    assert reverse("budget:mes", args=["household"]) not in urls


@pytest.mark.django_db
def test_solo_la_pestana_de_la_pantalla_actual_esta_activa(client):
    """El [+] del menu viejo parecia siempre pulsado y ninguna entrada decia
    donde estabas. Ahora exactamente una pestana lleva `activa`."""
    _sesion(client, ADMIN)
    respuesta = client.get(reverse("budget:metas", args=["household"]))
    activas = [p["nombre"] for p in respuesta.context["nav_pantallas"] if p["activa"]]
    assert activas == ["metas"]


@pytest.mark.django_db
def test_overview_no_se_queda_activa_por_ser_prefijo_de_todo(client):
    """/budget/household/ es prefijo de /budget/household/month/: gana la
    coincidencia mas larga, no la primera."""
    _sesion(client, ADMIN)
    respuesta = client.get(reverse("budget:mes", args=["household"]))
    activas = [p["nombre"] for p in respuesta.context["nav_pantallas"] if p["activa"]]
    assert activas == ["mes"]


@pytest.mark.django_db
def test_planificar_y_cerrar_encienden_la_pestana_del_mes(client):
    """Plan y Close no son destinos del menu: son el ciclo de vida del mes y
    viven como botones dentro de This month. Al estar en ellos, la pestana
    encendida es la del mes."""
    _sesion(client, ADMIN)
    respuesta = client.get(reverse("budget:planificar", args=["household"]))
    activas = [p["nombre"] for p in respuesta.context["nav_pantallas"] if p["activa"]]
    assert activas == ["mes"]


# ---------- conmutador de ambito ----------

@pytest.mark.django_db
def test_el_conmutador_conserva_la_pantalla_al_cambiar_de_ambito(client):
    """Estar en Household > Goals y tocar Personal lleva a Personal > Goals.
    Es lo que hace que se sienta un conmutador y no dos menus."""
    _sesion(client, ADMIN)
    respuesta = client.get(reverse("budget:metas", args=["household"]))
    ambitos = {a["nombre"]: a for a in respuesta.context["nav_ambitos"]}

    assert ambitos["hogar"]["activo"] is True
    assert ambitos["personal"]["activo"] is False
    assert ambitos["personal"]["url"] == reverse("budget:metas", args=["personal"])


@pytest.mark.django_db
def test_desde_la_mesada_el_conmutador_cae_en_el_resumen_del_hogar(client):
    """La mesada no existe en Household, asi que el destino es el Overview."""
    _sesion(client, ADMIN)
    respuesta = client.get(reverse("budget:mesada"))
    ambitos = {a["nombre"]: a for a in respuesta.context["nav_ambitos"]}

    assert ambitos["personal"]["activo"] is True
    assert ambitos["hogar"]["url"] == reverse("budget:overview", args=["household"])


@pytest.mark.django_db
def test_fuera_del_presupuesto_el_conmutador_lleva_a_los_resumenes(client):
    """En preferencias no hay pantalla que conservar: cada ambito lleva a su
    Overview y ninguno esta activo."""
    _sesion(client, ADMIN)
    respuesta = client.get(reverse("accounts:preferencias"))
    ambitos = {a["nombre"]: a for a in respuesta.context["nav_ambitos"]}

    assert ambitos["hogar"]["url"] == reverse("budget:overview", args=["household"])
    assert ambitos["personal"]["url"] == reverse("budget:overview", args=["personal"])
    assert not any(a["activo"] for a in ambitos.values())


@pytest.mark.django_db
def test_el_adolescente_no_ve_el_conmutador(client):
    _sesion(client, ADOLESCENTE)
    respuesta = client.get(reverse("accounts:preferencias"))
    assert respuesta.context["nav_ambitos"] == []


# ---------- drawer ----------

@pytest.mark.django_db
@pytest.mark.parametrize("perfil", [ADMIN, SOLO_VER, ADOLESCENTE])
def test_el_drawer_ensena_exactamente_lo_que_el_perfil_puede_abrir(client, perfil):
    _sesion(client, perfil)
    respuesta = client.get(reverse("accounts:preferencias"))
    assert _nombres(respuesta.context["nav_drawer"]) == ESPERADO_DRAWER[perfil]


# ---------- ninguno da 403 ----------

@pytest.mark.django_db
@pytest.mark.parametrize("perfil", [ADMIN, SOLO_VER, ADOLESCENTE])
def test_ningun_enlace_del_menu_devuelve_403(client, perfil):
    """Un 403 al hacer clic es correcto pero grosero (§7 del Plan 2)."""
    _sesion(client, perfil)
    # Desde Personal, que es donde mas pestanas hay.
    origen = "budget:overview" if PERMISOS[perfil]["can_view_budget"] else "accounts:preferencias"
    args = ["personal"] if PERMISOS[perfil]["can_view_budget"] else []
    respuesta = client.get(reverse(origen, args=args))
    for url in _todas_las_urls(respuesta.context):
        seguimiento = client.get(url)
        assert seguimiento.status_code == 200, (
            f"El perfil {perfil} ve en su menu {url} y al seguirlo recibe "
            f"{seguimiento.status_code}."
        )


# ---------- el [+] ----------

@pytest.mark.django_db
@pytest.mark.parametrize("perfil", [ADMIN, SOLO_VER, ADOLESCENTE])
def test_el_fab_depende_solo_de_can_add_transactions(client, perfil):
    """El criterio de aceptacion 5: el adolescente registra un gasto sin
    teclear la URL. Ahora ese camino es el boton flotante."""
    _sesion(client, perfil)
    respuesta = client.get(reverse("accounts:preferencias"))
    assert respuesta.context["nav_fab"] is ESPERADO_FAB[perfil]
    if ESPERADO_FAB[perfil]:
        assert client.get(reverse("budget:registrar")).status_code == 200


@pytest.mark.django_db
def test_un_hogar_expirado_pierde_el_fab_y_gana_el_aviso(client):
    """§5.2 y §7 juntos: expirar quita el [+] en vez de dejarlo dar un 403."""
    from datetime import timedelta

    from django.utils import timezone

    hogar, _user = _sesion(client, ADMIN)
    hogar.subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    hogar.subscription.save()

    respuesta = client.get(reverse("accounts:preferencias"))

    assert respuesta.context["nav_fab"] is False
    assert respuesta.context["nav_puede_escribir"] is False
    assert reverse("subscriptions:estado") in respuesta.content.decode()


# ---------- sin sesion ----------

@pytest.mark.django_db
def test_el_menu_no_aparece_sin_sesion(client):
    """En login y registro no hay hogar, y el context processor no debe reventar."""
    respuesta = client.get(reverse("accounts:login"))

    assert respuesta.status_code == 200
    assert respuesta.context["nav_ambitos"] == []
    assert respuesta.context["nav_pantallas"] == []
    assert respuesta.context["nav_drawer"] == []
    assert respuesta.context["nav_fab"] is False


# ---------- lo que llega al HTML ----------

@pytest.mark.django_db
def test_cada_pestana_trae_su_icono(client):
    """La barra inferior de movil se apoya en los iconos, no en el texto: una
    pestana SIN icono deja un hueco por el que no se puede pinchar."""
    _sesion(client, ADMIN)
    respuesta = client.get(reverse("budget:overview", args=["personal"]))
    cuerpo = respuesta.content.decode()

    conocidos = {"resumen", "mes", "meta", "balance", "mesada"}
    for pantalla in respuesta.context["nav_pantallas"]:
        assert pantalla["icono"] in conocidos, (
            f"la pestana {pantalla['nombre']!r} usa el icono {pantalla['icono']!r}, "
            f"que _nav_icono.html no dibuja: saldria un circulo generico"
        )
    assert cuerpo.count('class="nav__icono"') == len(respuesta.context["nav_pantallas"])


@pytest.mark.django_db
def test_la_pestana_activa_lo_dice_en_el_html(client):
    """aria-current="page" es a la vez el estado visual y el que oye un lector
    de pantalla: un solo atributo, una sola verdad."""
    _sesion(client, ADMIN)
    cuerpo = client.get(reverse("budget:metas", args=["household"])).content.decode()
    assert cuerpo.count('aria-current="page"') == 1


@pytest.mark.django_db
def test_el_menu_conserva_su_etiqueta_para_los_lectores_de_pantalla(client):
    """El icono se ve, el texto no — pero sigue en el DOM. Ocultarlo con
    display:none lo quitaria tambien del lector de pantalla."""
    _sesion(client, ADMIN)

    cuerpo = client.get(reverse("budget:overview", args=["household"])).content.decode()

    assert 'class="nav__texto"' in cuerpo
    assert "Goals" in cuerpo


@pytest.mark.django_db
def test_el_drawer_lleva_el_cierre_de_sesion_en_toda_pantalla(client):
    """Antes Sign out vivia solo en Settings; ahora el avatar esta en la barra
    de todas las pantallas, asi que salir esta siempre a dos toques."""
    _sesion(client, SOLO_VER)
    cuerpo = client.get(reverse("budget:overview", args=["household"])).content.decode()
    assert f'action="{reverse("accounts:logout")}"' in cuerpo


@pytest.mark.django_db
def test_el_fab_llega_al_html_solo_cuando_toca(client):
    _sesion(client, SOLO_VER)
    cuerpo = client.get(reverse("budget:overview", args=["household"])).content.decode()
    assert 'class="fab"' not in cuerpo

    _sesion(client, ADMIN)
    cuerpo = client.get(reverse("budget:overview", args=["household"])).content.decode()
    assert 'class="fab"' in cuerpo
