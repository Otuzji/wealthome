"""Limite de intentos de entrada: tres fallos seguidos bloquean la cuenta 30 minutos.

Vive en un backend de autenticacion y no en el formulario de entrada porque
TODA autenticacion pasa por aqui: la pantalla de entrada, /admin/login/ y
cualquier camino que se anada despues. Con la regla en el formulario, /admin/
seria una puerta trasera para probar contrasenas sin limite.

El bloqueo es por CUENTA, no por dispositivo. Un desconocido puede bloquear a
alguien tecleando su correo; por eso cambiar la contrasena con el enlace de
recuperacion desbloquea (ver `desbloquear` y la vista de cambio).
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

INTENTOS = 3
DURACION = timedelta(minutes=30)
# Fallos separados por mas que esto no son "seguidos": dos fallos el mes
# pasado y uno hoy no deben bloquear a nadie.
VENTANA = timedelta(minutes=30)

# Lo marca el backend en la peticion para que el formulario de entrada diga
# "bloqueada" en vez del error generico de clave incorrecta.
MARCA = "_wealthome_cuenta_bloqueada"


def esta_bloqueada(user, ahora=None):
    ahora = ahora or timezone.now()
    return user.locked_until is not None and user.locked_until > ahora


def desbloquear(user):
    """Contador a cero y sin bloqueo. Lo llama la entrada correcta y el cambio
    de contrasena por enlace."""
    get_user_model().objects.filter(pk=user.pk).update(
        failed_logins=0, last_failed_login=None, locked_until=None,
    )
    user.failed_logins, user.last_failed_login, user.locked_until = 0, None, None


def registrar_fallo(user, request=None):
    """Suma un fallo y, si es el tercero seguido, bloquea y avisa.

    Devuelve True si este fallo bloqueo la cuenta. Con la fila bloqueada para
    escritura: dos intentos simultaneos no pueden leer el mismo contador y
    perder un fallo.
    """
    ahora = timezone.now()
    with transaction.atomic():
        fila = get_user_model().objects.select_for_update().get(pk=user.pk)
        if esta_bloqueada(fila, ahora):
            # Fallos durante el bloqueo no lo alargan ni mandan otro correo.
            return False
        # Un bloqueo ya cumplido tambien reinicia la cuenta: el que espero sus
        # 30 minutos vuelve a tener sus tres intentos.
        reciente = (
            fila.locked_until is None
            and fila.last_failed_login is not None
            and ahora - fila.last_failed_login <= VENTANA
        )
        fila.failed_logins = (fila.failed_logins + 1) if reciente else 1
        fila.last_failed_login = ahora
        bloquea = fila.failed_logins >= INTENTOS
        if bloquea:
            fila.locked_until = ahora + DURACION
        else:
            fila.locked_until = None
        fila.save(update_fields=["failed_logins", "last_failed_login", "locked_until"])

    if bloquea:
        try:
            enviar_aviso_de_bloqueo(fila, ahora, request)
        except Exception:
            # Sin correo el bloqueo sigue valiendo: un SMTP caido no puede
            # convertirse en un 500 en la pantalla de entrada.
            logger.exception("No se pudo enviar el aviso de bloqueo a %s", fila.pk)
    return bloquea


def enviar_aviso_de_bloqueo(user, cuando, request=None):
    """El correo al dueno: que paso, y que hacer si no fue el."""
    ruta = reverse("accounts:password_reset")
    enlace = request.build_absolute_uri(ruta) if request is not None else ruta
    idioma = getattr(getattr(user, "profile", None), "language", None) or settings.LANGUAGE_CODE
    with translation.override(idioma):
        contexto = {
            "user": user,
            "intentos": INTENTOS,
            "cuando": timezone.localtime(cuando),
            "enlace": enlace,
            "idioma": idioma,
        }
        asunto = _("Wealthome: failed sign-in attempts on your account")
        texto = render_to_string("accounts/email/bloqueo.txt", contexto)
        html = render_to_string("accounts/email/bloqueo.html", contexto)

    correo = EmailMultiAlternatives(
        subject=asunto,
        body=texto,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    correo.attach_alternative(html, "text/html")
    correo.send()
    return correo


class BackendConLimiteDeIntentos(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        try:
            user = User.objects.get(email__iexact=username)
        except User.DoesNotExist:
            # Correo desconocido: el hash de ModelBackend iguala el tiempo de
            # respuesta, y no hay a quien contar ni avisar.
            return super().authenticate(request, username=username, password=password, **kwargs)

        if esta_bloqueada(user):
            # Ni se mira la contrasena: bloqueada es bloqueada.
            if request is not None:
                setattr(request, MARCA, True)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            if user.failed_logins or user.locked_until or user.last_failed_login:
                desbloquear(user)
            return user

        if registrar_fallo(user, request) and request is not None:
            setattr(request, MARCA, True)
        return None
