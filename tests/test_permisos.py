"""Quién es "el hogar" de una petición, y quién puede hacer qué en él.

Puerta 2: hasta el Plan 1 había dos respuestas distintas a "¿qué hogar?".
`scoping.for_user` devolvía filas de **todos** los hogares activos del
usuario; `views._hogar_activo` devolvía **el primero**. Coincidían porque
cada usuario tenía un hogar. El día que no coincidieran, el Plan 2 habría
sumado el dinero de dos familias en un solo presupuesto sin lanzar nada:
nadie ve una traza, ven un número equivocado y plausible. Ahora hay una sola
respuesta, `hogar_actual`, y `for_user` no existe.

Puerta 3: los cuatro permisos del spec §6.2 estaban probados y no los
llamaba ningún código de producción; las dos vistas que controlaban algo
comprobaban el rol a mano y devolvían un `HttpResponseForbidden()` de cuerpo
vacío — una página en blanco, sin texto traducido. Los tres decoradores de
abajo son la capa central que el spec §6.1 pide en vez de "permisos
repartidos a mano vista por vista".
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser

from apps.households.models import Membership
from apps.households.permissions import (
    con_hogar,
    get_membership,
    hogar_actual,
    require_permission,
    requiere_permiso,
    solo_admin,
)
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


def _peticion(user):
    peticion = RequestFactory().get("/")
    peticion.user = user
    return peticion


# --- Puerta 2: hogar_actual --------------------------------------------------


@pytest.mark.django_db
def test_hogar_actual_devuelve_el_hogar_de_la_membresía_activa():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)

    assert hogar_actual(_peticion(user)) == hogar


@pytest.mark.django_db
def test_hogar_actual_rechaza_a_quien_no_tiene_membresía():
    with pytest.raises(PermissionDenied):
        hogar_actual(_peticion(UserFactory()))


@pytest.mark.django_db
def test_hogar_actual_ignora_una_membresía_inactiva():
    user = UserFactory()
    MembershipFactory(household=HouseholdFactory(), user=user, is_active=False)

    with pytest.raises(PermissionDenied):
        hogar_actual(_peticion(user))


@pytest.mark.django_db
def test_hogar_actual_elige_la_membresía_más_antigua():
    """La Fase 1 asume un hogar por usuario, pero "asume" no es "impide".
    Cuando hay dos, la elección tiene que ser la misma en cada petición: un
    hogar que cambiara entre peticiones repartiría las transacciones de una
    familia entre dos presupuestos."""
    from django.utils import timezone
    from datetime import timedelta

    user = UserFactory()
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    MembershipFactory(household=thompson, user=user)
    segunda = MembershipFactory(household=garcia, user=user)

    # joined_at es auto_now_add: para probar que ordena por fecha y no por
    # id de fila, se retrasa a mano la del hogar creado en segundo lugar.
    Membership.objects.filter(pk=segunda.pk).update(
        joined_at=timezone.now() - timedelta(days=30)
    )

    assert hogar_actual(_peticion(user)) == garcia


@pytest.mark.django_db
def test_hogar_actual_es_estable_entre_peticiones():
    user = UserFactory()
    MembershipFactory(household=HouseholdFactory(), user=user)
    MembershipFactory(household=HouseholdFactory(), user=user)

    assert hogar_actual(_peticion(user)) == hogar_actual(_peticion(user))


@pytest.mark.django_db
def test_hogar_actual_no_devuelve_los_dos_hogares():
    """El fallo que la Puerta 2 existe para impedir: `for_user` habría
    devuelto las filas de ambos."""
    user = UserFactory()
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    MembershipFactory(household=thompson, user=user)
    MembershipFactory(household=garcia, user=user)

    elegido = hogar_actual(_peticion(user))

    assert elegido in (thompson, garcia)
    assert not isinstance(elegido, (list, tuple))


@pytest.mark.django_db
def test_hogar_actual_se_resuelve_una_sola_vez_por_petición():
    """Cada vista del Plan 2 lo consultará varias veces; que cueste una
    consulta y no seis es la diferencia entre una capa central y un peaje."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    user = UserFactory()
    MembershipFactory(household=HouseholdFactory(), user=user)
    peticion = _peticion(user)

    with CaptureQueriesContext(connection) as consultas:
        hogar_actual(peticion)
        hogar_actual(peticion)
        hogar_actual(peticion)

    assert len(consultas) == 1


# --- Puerta 3: los decoradores ----------------------------------------------


@con_hogar
def _vista_abierta(request, hogar):
    return HttpResponse(hogar.name)


@solo_admin
def _vista_de_admin(request, hogar):
    return HttpResponse(hogar.name)


@requiere_permiso("can_edit_budget")
def _vista_de_presupuesto(request, hogar):
    return HttpResponse(hogar.name)


@requiere_permiso("can_edit_budget")
def _vista_con_argumento_de_url(request, hogar, pk):
    return HttpResponse(f"{hogar.name}:{pk}")


@pytest.mark.django_db
def test_con_hogar_pasa_el_hogar_a_la_vista():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)

    assert _vista_abierta(_peticion(user)).content.decode() == hogar.name


@pytest.mark.django_db
def test_con_hogar_manda_al_anónimo_a_iniciar_sesión():
    """Un anónimo no es un intruso: no ha dicho quién es. 302 al login, no
    403."""
    respuesta = _vista_abierta(_peticion(AnonymousUser()))

    assert respuesta.status_code == 302
    assert "/" in respuesta["Location"]


@pytest.mark.django_db
def test_con_hogar_rechaza_a_quien_no_tiene_hogar():
    with pytest.raises(PermissionDenied):
        _vista_abierta(_peticion(UserFactory()))


@pytest.mark.django_db
def test_solo_admin_deja_pasar_al_administrador():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, role=Membership.ADMIN)

    assert _vista_de_admin(_peticion(user)).status_code == 200


@pytest.mark.django_db
def test_solo_admin_bloquea_a_un_miembro():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, role=Membership.MEMBER)

    with pytest.raises(PermissionDenied):
        _vista_de_admin(_peticion(user))


@pytest.mark.django_db
def test_requiere_permiso_deja_pasar_a_quien_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=True)

    assert _vista_de_presupuesto(_peticion(user)).status_code == 200


@pytest.mark.django_db
def test_requiere_permiso_bloquea_a_quien_no_lo_tiene():
    """El adolescente del spec §6.2: registra sus gastos, no toca la hipoteca."""
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=False)

    with pytest.raises(PermissionDenied):
        _vista_de_presupuesto(_peticion(user))


@pytest.mark.django_db
def test_los_decoradores_conservan_los_argumentos_de_la_url():
    """El hogar se inserta después de request, así que los kwargs de la ruta
    (`<int:pk>`) tienen que seguir llegando intactos."""
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=True)

    respuesta = _vista_con_argumento_de_url(_peticion(user), pk=7)

    assert respuesta.content.decode() == f"{hogar.name}:7"


def test_requiere_permiso_rechaza_un_permiso_inexistente_al_declararse():
    """Un permiso mal escrito es un error de programación: tiene que reventar
    al importar el módulo de vistas, no la primera vez que alguien entre a
    esa pantalla."""
    with pytest.raises(ValueError):
        requiere_permiso("can_do_anything")


@pytest.mark.django_db
def test_los_decoradores_dejan_el_hogar_en_la_petición():
    """Para que las plantillas puedan formatear el dinero en la moneda del
    hogar sin una consulta extra (ver apps/core/context_processors.py)."""
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)
    peticion = _peticion(user)

    _vista_abierta(peticion)

    assert peticion.hogar == hogar


# --- La capa que ya existía --------------------------------------------------


@pytest.mark.django_db
def test_get_membership_devuelve_none_para_un_extraño():
    assert get_membership(UserFactory(), HouseholdFactory()) is None


@pytest.mark.django_db
def test_require_permission_deja_pasar_al_que_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=True)
    require_permission(user, hogar, "can_edit_budget")  # no debe lanzar


@pytest.mark.django_db
def test_require_permission_bloquea_al_que_no_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=False)
    with pytest.raises(PermissionDenied):
        require_permission(user, hogar, "can_edit_budget")


@pytest.mark.django_db
def test_require_permission_bloquea_a_quien_no_es_del_hogar():
    with pytest.raises(PermissionDenied):
        require_permission(UserFactory(), HouseholdFactory(), "can_view_budget")


@pytest.mark.django_db
def test_require_permission_rechaza_un_permiso_inexistente():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)
    with pytest.raises(ValueError):
        require_permission(user, hogar, "can_do_anything")
