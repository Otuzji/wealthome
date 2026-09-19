from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext as _


def enviar_invitacion(invitacion, enlace):
    """Manda el correo de invitación en el idioma que eligió quien invita.

    El invitado aún no tiene perfil ni preferencia de idioma (§8 de la spec),
    por eso el idioma viaja en la propia invitación y no en el hilo actual.
    """
    contexto = {
        "invitacion": invitacion,
        "enlace": enlace,
        "invitador": str(invitacion.invited_by),
        "hogar": invitacion.household.name,
        "dias": invitacion.VIGENCIA.days,
    }
    with translation.override(invitacion.language):
        asunto = _("%(invitador)s invites you to join %(hogar)s on Wealthome") % contexto
        texto = render_to_string("households/email/invitacion.txt", contexto)
        html = render_to_string("households/email/invitacion.html", contexto)

    correo = EmailMultiAlternatives(
        subject=asunto,
        body=texto,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[invitacion.email],
    )
    correo.attach_alternative(html, "text/html")
    correo.send()
    return correo
