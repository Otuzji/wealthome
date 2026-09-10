import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _


class Household(models.Model):
    name = models.CharField(_("household name"), max_length=120)
    currency = models.CharField(_("currency"), max_length=3, default="CAD")
    timezone = models.CharField(_("time zone"), max_length=64, default="America/Toronto")
    budget_start_month = models.PositiveSmallIntegerField(_("budget start month"), default=1)
    family_size = models.PositiveSmallIntegerField(
        _("family size"),
        default=1,
        help_text=_("How many people live in the home. Not the same as how many use the app."),
    )
    allowance_rollover = models.BooleanField(
        _("allowance rolls over"),
        default=True,
        help_text=_("Unspent personal allowance carries into the next month."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("household")
        verbose_name_plural = _("households")

    def __str__(self):
        return self.name

    def active_memberships(self):
        return self.memberships.filter(is_active=True)

    @cached_property
    def puede_escribir(self):
        """Si este hogar admite escrituras hoy (§5.2).

        Un hogar SIN fila de suscripcion puede escribir. Es deliberado (§2.4
        del spec del Plan 3): fallar cerrado romperia toda fabrica de pruebas
        que no pase por crear_hogar, y lo que hay que impedir es que escriba un
        hogar con una suscripcion vencida, no uno sin fila. Los tres sitios que
        crean hogares crean la suscripcion, y hay prueba de ello.

        `cached_property` y no `property`: la guardia de HouseholdScoped.save()
        pregunta esto en cada guardado, y sin cache seria una consulta por fila
        escrita.
        """
        suscripcion = getattr(self, "subscription", None)
        return True if suscripcion is None else suscripcion.esta_vigente


class Membership(models.Model):
    MAX_PER_HOUSEHOLD = 6

    ADMIN = "admin"
    MEMBER = "member"
    ROLE_CHOICES = [(ADMIN, _("Administrator")), (MEMBER, _("Member"))]

    PERMISSION_FIELDS = (
        "can_view_budget",
        "can_edit_budget",
        "can_add_transactions",
        "can_view_reports",
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(_("role"), max_length=10, choices=ROLE_CHOICES, default=MEMBER)

    can_view_budget = models.BooleanField(_("can view the budget"), default=True)
    can_edit_budget = models.BooleanField(_("can edit the budget"), default=False)
    can_add_transactions = models.BooleanField(_("can add transactions"), default=True)
    can_view_reports = models.BooleanField(_("can view reports"), default=True)

    joined_at = models.DateTimeField(_("joined at"), auto_now_add=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        constraints = [
            models.UniqueConstraint(fields=["user", "household"], name="una_membresia_por_usuario_y_hogar")
        ]

    def __str__(self):
        return f"{self.user} @ {self.household} ({self.role})"

    def save(self, *args, **kwargs):
        if self.role == self.ADMIN:
            for campo in self.PERMISSION_FIELDS:
                setattr(self, campo, True)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.is_active and self.household_id:
            ocupadas = Membership.objects.filter(household_id=self.household_id, is_active=True)
            if self.pk:
                ocupadas = ocupadas.exclude(pk=self.pk)
            if ocupadas.count() >= self.MAX_PER_HOUSEHOLD:
                raise ValidationError(
                    _("A household can have at most %(max)d members.")
                    % {"max": self.MAX_PER_HOUSEHOLD}
                )


def _token_invitacion():
    return secrets.token_urlsafe(32)


class Invitation(models.Model):
    VIGENCIA = timedelta(days=7)

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(_("email address"))
    token = models.CharField(max_length=64, unique=True, default=_token_invitacion, editable=False)
    language = models.CharField(_("language"), max_length=5, default="en")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_invitations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("invitation")
        verbose_name_plural = _("invitations")

    def __str__(self):
        return f"{self.email} → {self.household}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + self.VIGENCIA
        super().save(*args, **kwargs)

    def is_valid(self):
        return self.accepted_at is None and self.expires_at > timezone.now()
