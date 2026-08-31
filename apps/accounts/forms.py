from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Profile

User = get_user_model()


class RegistroForm(forms.Form):
    email = forms.EmailField(label=_("Email address"))
    display_name = forms.CharField(label=_("Your name"), max_length=80)
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Confirm password"), widget=forms.PasswordInput)
    household_name = forms.CharField(label=_("Household name"), max_length=120)
    family_size = forms.IntegerField(label=_("How many live in your home?"), min_value=1, max_value=20)

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


class PreferenciasForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["theme", "language"]
        labels = {
            "theme": _("Theme"),
            "language": _("Language"),
        }
