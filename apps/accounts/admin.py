from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import Profile, User


class UserCreationForm(DjangoUserCreationForm):
    """UserCreationForm de Django adaptado: este modelo se identifica por
    correo (USERNAME_FIELD = "email"), no por un campo username."""

    class Meta(DjangoUserCreationForm.Meta):
        model = User
        fields = ("email",)


class UserChangeForm(DjangoUserChangeForm):
    class Meta(DjangoUserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """UserAdmin propio en vez de admin.site.register(User) a secas.

    Sin un ModelAdmin dedicado, Django genera un ModelForm genérico donde
    "password" es un CharField de texto plano: una cuenta creada desde
    /admin/ guardaría la contraseña tecleada TAL CUAL en Postgres, sin pasar
    por set_password(), y esa cuenta no podría autenticarse. add_form/form
    usan los formularios de auth (adaptados a un modelo sin username), que sí
    hashean la contraseña.
    """

    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("display_name",)}),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )
    list_display = ("email", "display_name", "is_staff", "is_active")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "display_name")
    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")
    readonly_fields = ("date_joined",)


admin.site.register(Profile)
