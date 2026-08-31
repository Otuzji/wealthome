import pytest
from django.urls import reverse

from apps.households.models import Invitation, Membership
from apps.households.services import aceptar_invitacion, crear_hogar, invitar
from tests.factories import MembershipFactory, UserFactory


@pytest.fixture
def admin_con_hogar(db):
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    return user, hogar


@pytest.mark.django_db
def test_el_admin_ve_la_lista_de_miembros(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    otro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(admin)

    html = client.get(reverse("households:ajustes")).content.decode()
    assert str(otro.user) in html


@pytest.mark.django_db
def test_el_admin_invita_y_se_crea_la_invitacion(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    client.force_login(admin)

    respuesta = client.post(reverse("households:invitar"), {"email": "marie@example.com", "language": "fr"})
    assert respuesta.status_code == 302
    inv = Invitation.objects.get(household=hogar)
    assert inv.email == "marie@example.com"
    assert inv.language == "fr"


@pytest.mark.django_db
def test_un_miembro_normal_no_puede_invitar(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    miembro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(miembro.user)

    respuesta = client.post(reverse("households:invitar"), {"email": "x@example.com", "language": "en"})
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_el_admin_cambia_los_permisos_de_un_miembro(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    miembro = MembershipFactory(household=hogar, role=Membership.MEMBER, can_view_budget=True)
    client.force_login(admin)

    client.post(
        reverse("households:permisos", args=[miembro.pk]),
        {"can_add_transactions": "on", "can_view_reports": "on"},
    )
    miembro.refresh_from_db()
    assert not miembro.can_view_budget
    assert miembro.can_add_transactions


@pytest.mark.django_db
def test_un_admin_no_puede_tocar_los_permisos_de_otro_hogar(client, admin_con_hogar):
    admin, _ = admin_con_hogar
    ajena = MembershipFactory(role=Membership.MEMBER)  # otro hogar
    client.force_login(admin)

    respuesta = client.post(reverse("households:permisos", args=[ajena.pk]), {"can_view_reports": "on"})
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_aceptar_una_invitacion_desde_el_enlace(client, admin_con_hogar):
    admin, hogar = admin_con_hogar

    inv = invitar(admin, hogar, "marie@example.com", language="en")
    marie = UserFactory()
    client.force_login(marie)

    respuesta = client.post(reverse("households:aceptar", args=[inv.token]))
    assert respuesta.status_code == 302
    assert Membership.objects.filter(user=marie, household=hogar).exists()


@pytest.mark.django_db
def test_el_usuario_cambia_su_tema_y_su_idioma(client):
    user = UserFactory()
    client.force_login(user)

    client.post(reverse("accounts:preferencias"), {"theme": "accesible", "language": "fr"})
    user.profile.refresh_from_db()
    assert user.profile.theme == "accesible"
    assert user.profile.language == "fr"


@pytest.mark.django_db
def test_cambiar_el_tema_no_afecta_a_los_demas_miembros(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    otro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(admin)

    client.post(reverse("accounts:preferencias"), {"theme": "accesible", "language": "en"})
    otro.user.profile.refresh_from_db()
    assert otro.user.profile.theme == "sereno"


@pytest.mark.django_db
def test_aceptar_una_invitacion_siendo_ya_miembro_muestra_un_error(client, admin_con_hogar):
    """Hallazgo heredado de la Tarea 5: si Marie ya es miembro del hogar y acepta
    otra invitación al mismo hogar, la vista debe mostrar un error traducido,
    no una IntegrityError cruda de la restricción única."""
    admin, hogar = admin_con_hogar
    inv1 = invitar(admin, hogar, "marie@example.com", language="en")
    marie = UserFactory()
    aceptar_invitacion(marie, inv1.token)

    inv2 = invitar(admin, hogar, "marie@example.com", language="en")
    client.force_login(marie)

    respuesta = client.post(reverse("households:aceptar", args=[inv2.token]))
    assert respuesta.status_code == 200
    assert "already a member" in respuesta.content.decode()
