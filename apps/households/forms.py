from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Membership


class InvitarForm(forms.Form):
    email = forms.EmailField(label=_("Email address of the person you are inviting"))
    language = forms.ChoiceField(
        label=_("Send the invitation in"),
        choices=[("en", _("English")), ("fr", _("Français"))],
    )


class PermisosForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = list(Membership.PERMISSION_FIELDS)
