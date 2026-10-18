from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.contrib.auth.password_validation import validate_password
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from apps.accounts import bloqueo
from apps.accounts.models import Profile

User = get_user_model()


class CuentaNuevaForm(forms.Form):
    """Lo que toda cuenta nueva necesita: quien es, como entra. Base de los
    dos registros —el que crea un hogar y el que se une a uno por
    invitacion— para que la validacion de correo y contrasena no diverja."""

    email = forms.EmailField(label=_("Email address"))
    display_name = forms.CharField(label=_("Your name"), max_length=80)
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Confirm password"), widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        usuario_sin_guardar = User(
            email=self.cleaned_data.get("email", ""),
            display_name=self.cleaned_data.get("display_name", ""),
        )
        validate_password(password, user=usuario_sin_guardar)
        return password

    def clean(self):
        datos = super().clean()
        if datos.get("password1") and datos.get("password1") != datos.get("password2"):
            self.add_error("password2", _("The two passwords do not match."))
        return datos

    def crear_usuario(self):
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            display_name=self.cleaned_data["display_name"],
        )


class RegistroForm(CuentaNuevaForm):
    household_name = forms.CharField(label=_("Household name"), max_length=120)
    family_size = forms.IntegerField(label=_("How many live in your home?"), min_value=1, max_value=20)


class RegistroInvitadoForm(CuentaNuevaForm):
    """Sin hogar ni tamano de familia: el hogar ya existe, lo creo quien invita."""


class PreferenciasForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["theme", "language"]
        labels = {
            "theme": _("Theme"),
            "language": _("Language"),
        }


class EntradaForm(AuthenticationForm):
    """La entrada de siempre, que dice "bloqueada" cuando el backend lo marco.

    El mensaje no dice cuanto falta a proposito: a quien prueba contrasenas
    ajenas no hay que decirle cuando volver a intentarlo.
    """

    error_messages = AuthenticationForm.error_messages | {
        # En una sola linea: test_catalogo_exhaustivo no recompone literales partidos.
        "bloqueada": _("This account is temporarily locked after several failed sign-in attempts. Try again later, or reset your password."),  # noqa: E501
    }

    def get_invalid_login_error(self):
        if self.request is not None and getattr(self.request, bloqueo.MARCA, False):
            return forms.ValidationError(self.error_messages["bloqueada"], code="bloqueada")
        return super().get_invalid_login_error()


class OlvideContrasenaForm(PasswordResetForm):
    """El correo de recuperar sale en el idioma del dueno de la cuenta, no en
    el de quien lo pide (como el aviso de bloqueo)."""

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        perfil = getattr(context["user"], "profile", None)
        idioma = getattr(perfil, "language", None) or settings.LANGUAGE_CODE
        with translation.override(idioma):
            super().send_mail(subject_template_name, email_template_name, context,
                              from_email, to_email, html_email_template_name)
