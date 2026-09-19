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


@pytest.mark.django_db
def test_un_403_devuelve_una_página_traducida_y_no_un_cuerpo_vacío(client, admin_con_hogar):
    """Deuda §4 del traspaso: había cuatro dialectos para "no puedes hacer
    eso", y uno era HttpResponseForbidden() sin cuerpo — el usuario veía una
    página en blanco, sin una sola palabra traducida, en un producto cuyo
    bilingüismo es un requisito legal."""
    _, hogar = admin_con_hogar
    miembro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(miembro.user)

    respuesta = client.post(
        reverse("households:invitar"), {"email": "x@example.com", "language": "en"}
    )

    assert respuesta.status_code == 403
    assert "You do not have permission" in respuesta.content.decode()


@pytest.mark.django_db
def test_un_403_se_traduce_al_francés(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    miembro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    miembro.user.profile.language = "fr"
    miembro.user.profile.save()
    client.force_login(miembro.user)

    respuesta = client.post(
        reverse("households:invitar"), {"email": "x@example.com", "language": "en"}
    )

    assert respuesta.status_code == 403
    assert "autorisation" in respuesta.content.decode()


@pytest.mark.django_db
def test_un_404_devuelve_una_página_traducida(client, admin_con_hogar):
    admin, _ = admin_con_hogar
    client.force_login(admin)

    respuesta = client.get("/household/settings/permissions/999999/")

    assert respuesta.status_code == 404
    assert "does not exist" in respuesta.content.decode()


def test_las_rutas_visibles_están_en_inglés():
    """Deuda §4 del traspaso: todo el texto de la aplicación está traducido a
    inglés y francés, y luego la barra de direcciones decía /registro/ y
    /hogar/ajustes/. Cambiarlo cuesta nada hoy y más con cada ruta que añada
    el Plan 2. Los nombres internos siguen en español, como el resto del
    código: ningún {% url %} ni reverse() cambia."""
    assert reverse("accounts:registro") == "/signup/"
    assert reverse("accounts:login") == "/login/"
    assert reverse("accounts:logout") == "/logout/"
    assert reverse("accounts:preferencias") == "/preferences/"
    assert reverse("households:ajustes") == "/household/settings/"
    assert reverse("households:invitar") == "/household/settings/invite/"
    assert reverse("households:permisos", args=[7]) == "/household/settings/permissions/7/"
    assert reverse("households:aceptar", args=["abc"]) == "/household/invitation/abc/"


@pytest.mark.django_db
def test_al_invitar_se_envia_el_correo_con_el_enlace_absoluto(client, admin_con_hogar, mailoutbox):
    admin, hogar = admin_con_hogar
    client.force_login(admin)

    client.post(reverse("households:invitar"), {"email": "marie@example.com", "language": "en"})

    inv = Invitation.objects.get(household=hogar)
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["marie@example.com"]
    assert "http://testserver" + reverse("households:aceptar", args=[inv.token]) in mailoutbox[0].body


@pytest.mark.django_db
def test_si_el_correo_falla_la_invitacion_se_conserva_y_se_avisa(client, admin_con_hogar, monkeypatch):
    import smtplib

    from apps.households import views

    def _falla(*args, **kwargs):
        raise smtplib.SMTPException("boom")

    monkeypatch.setattr(views, "enviar_invitacion", _falla)
    admin, hogar = admin_con_hogar
    client.force_login(admin)

    respuesta = client.post(
        reverse("households:invitar"), {"email": "marie@example.com", "language": "en"}, follow=True
    )

    assert Invitation.objects.filter(household=hogar, email="marie@example.com").exists()
    html = respuesta.content.decode()
    assert "could not send the email" in html


@pytest.mark.django_db
def test_el_admin_ve_las_invitaciones_pendientes_con_su_enlace(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    pendiente = invitar(admin, hogar, "marie@example.com", language="fr")
    aceptada = invitar(admin, hogar, "paul@example.com", language="en")
    aceptar_invitacion(UserFactory(), aceptada.token)
    client.force_login(admin)

    html = client.get(reverse("households:ajustes")).content.decode()

    assert "marie@example.com" in html
    assert "http://testserver" + reverse("households:aceptar", args=[pendiente.token]) in html
    assert "paul@example.com" not in html


@pytest.mark.django_db
def test_un_miembro_normal_no_ve_las_invitaciones_pendientes(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    invitar(admin, hogar, "marie@example.com", language="en")
    miembro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(miembro.user)

    html = client.get(reverse("households:ajustes")).content.decode()
    assert "marie@example.com" not in html


@pytest.mark.django_db
def test_revocar_una_invitacion_libera_su_puesto(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    for i in range(5):
        invitar(admin, hogar, f"p{i}@example.com", language="en")
    victima = Invitation.objects.filter(household=hogar).first()
    client.force_login(admin)

    respuesta = client.post(reverse("households:revocar", args=[victima.pk]))

    assert respuesta.status_code == 302
    assert not Invitation.objects.filter(pk=victima.pk).exists()
    # El sexto puesto vuelve a estar libre.
    assert invitar(admin, hogar, "sexto@example.com", language="en")


@pytest.mark.django_db
def test_un_admin_no_puede_revocar_una_invitacion_de_otro_hogar(client, admin_con_hogar):
    admin, _ = admin_con_hogar
    otro_admin = UserFactory()
    otro_hogar = crear_hogar(otro_admin, "Family Martin", family_size=2)
    ajena = invitar(otro_admin, otro_hogar, "x@example.com", language="en")
    client.force_login(admin)

    respuesta = client.post(reverse("households:revocar", args=[ajena.pk]))

    assert respuesta.status_code == 404
    assert Invitation.objects.filter(pk=ajena.pk).exists()


@pytest.mark.django_db
def test_un_miembro_normal_no_puede_revocar_ni_reenviar(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    inv = invitar(admin, hogar, "marie@example.com", language="en")
    miembro = MembershipFactory(household=hogar, role=Membership.MEMBER)
    client.force_login(miembro.user)

    assert client.post(reverse("households:revocar", args=[inv.pk])).status_code == 403
    assert client.post(reverse("households:reenviar", args=[inv.pk])).status_code == 403
    assert Invitation.objects.filter(pk=inv.pk).exists()


@pytest.mark.django_db
def test_reenviar_manda_otra_vez_el_correo_de_la_misma_invitacion(client, admin_con_hogar, mailoutbox):
    admin, hogar = admin_con_hogar
    inv = invitar(admin, hogar, "marie@example.com", language="fr")
    client.force_login(admin)

    respuesta = client.post(reverse("households:reenviar", args=[inv.pk]))

    assert respuesta.status_code == 302
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["marie@example.com"]
    assert inv.token in mailoutbox[0].body
    assert Invitation.objects.filter(household=hogar).count() == 1


@pytest.mark.django_db
def test_revocar_y_reenviar_solo_aceptan_post(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    inv = invitar(admin, hogar, "marie@example.com", language="en")
    client.force_login(admin)

    assert client.get(reverse("households:revocar", args=[inv.pk])).status_code == 405
    assert client.get(reverse("households:reenviar", args=[inv.pk])).status_code == 405
