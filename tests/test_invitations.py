from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.households.models import Household, Invitation, Membership
from apps.households.services import (
    HouseholdLleno,
    InvitacionInvalida,
    aceptar_invitacion,
    crear_hogar,
    invitar,
)
from tests.factories import MembershipFactory, UserFactory


@pytest.mark.django_db
def test_crear_hogar_deja_al_creador_como_admin():
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    membresia = Membership.objects.get(user=user, household=hogar)
    assert membresia.role == Membership.ADMIN
    assert membresia.can_edit_budget


@pytest.mark.django_db
def test_invitar_crea_una_invitacion_valida_por_siete_dias():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "marie@example.com", language="fr")

    assert inv.token
    assert inv.language == "fr"
    assert inv.is_valid()
    assert timedelta(days=6) < (inv.expires_at - timezone.now()) <= timedelta(days=7)


@pytest.mark.django_db
def test_un_miembro_sin_rol_admin_no_puede_invitar():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    otro = UserFactory()
    MembershipFactory(household=hogar, user=otro, role=Membership.MEMBER)

    with pytest.raises(PermissionDenied):
        invitar(otro, hogar, "nuevo@example.com", language="en")


@pytest.mark.django_db
def test_no_se_puede_invitar_cuando_el_hogar_esta_lleno():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    for _ in range(5):
        MembershipFactory(household=hogar, role=Membership.MEMBER)

    with pytest.raises(HouseholdLleno):
        invitar(admin, hogar, "septimo@example.com", language="en")


@pytest.mark.django_db
def test_seis_invitaciones_pendientes_no_desbordan_el_hogar():
    """La validación al aceptar es la que impide el desbordamiento por carrera (spec §6.3)."""
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)

    # El límite al crear cuenta las pendientes: solo caben 5 más.
    invitaciones = [invitar(admin, hogar, f"m{i}@example.com", language="en") for i in range(5)]
    with pytest.raises(HouseholdLleno):
        invitar(admin, hogar, "sexto@example.com", language="en")

    for inv in invitaciones:
        aceptar_invitacion(UserFactory(), inv.token)

    assert hogar.active_memberships().count() == 6


@pytest.mark.django_db
def test_aceptar_dos_veces_la_misma_invitacion_falla():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "marie@example.com", language="en")

    aceptar_invitacion(UserFactory(), inv.token)
    with pytest.raises(InvitacionInvalida):
        aceptar_invitacion(UserFactory(), inv.token)


@pytest.mark.django_db
def test_una_invitacion_caducada_no_se_acepta():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "marie@example.com", language="en")
    token = inv.token
    Invitation.objects.filter(pk=inv.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

    with pytest.raises(InvitacionInvalida):
        aceptar_invitacion(UserFactory(), token)


@pytest.mark.django_db
def test_un_token_inventado_no_se_acepta():
    with pytest.raises(InvitacionInvalida):
        aceptar_invitacion(UserFactory(), "token-que-no-existe")


@pytest.mark.django_db
def test_el_invitado_entra_con_permisos_de_miembro_no_de_admin():
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "hijo@example.com", language="en")

    membresia = aceptar_invitacion(UserFactory(), inv.token)
    assert membresia.role == Membership.MEMBER
    assert not membresia.can_edit_budget
    assert membresia.can_add_transactions


@pytest.mark.django_db
def test_aceptar_invitacion_bloquea_la_fila_del_hogar():
    """Ruling R-6: dos invitaciones distintas al mismo hogar deben serializarse
    sobre la fila del HOGAR, no solo sobre la fila de la invitación — de lo
    contrario dos aceptaciones concurrentes leen el mismo conteo y ambas caben,
    desbordando el hogar. Probar concurrencia real es propenso a parpadeos
    contra el pooler de Supabase, así que esta prueba verifica de forma
    determinista que aceptar_invitacion emite una lectura con bloqueo (`FOR
    UPDATE`) sobre la tabla household sql, no solo sobre la tabla de invitación."""
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=4)
    inv = invitar(admin, hogar, "marie@example.com", language="en")

    with CaptureQueriesContext(connection) as ctx:
        aceptar_invitacion(UserFactory(), inv.token)

    household_table = Household._meta.db_table
    locking_household_queries = [
        q["sql"]
        for q in ctx.captured_queries
        if "FOR UPDATE" in q["sql"].upper() and household_table in q["sql"]
    ]
    assert locking_household_queries, (
        "aceptar_invitacion debe bloquear la fila del hogar (SELECT ... FOR UPDATE) "
        "antes de contar sus membresías activas, no solo la fila de la invitación."
    )
