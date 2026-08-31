from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        """Minúsculas en la dirección completa, no solo en el dominio.

        BaseUserManager.normalize_email de Django solo baja el dominio: el RFC
        permite que la parte local distinga mayúsculas. Para este producto eso
        está mal: en una app familiar Marie@example.com y marie@example.com son
        la misma persona, y el Plan 3 empareja invitaciones con usuarios por
        correo — justo donde un duplicado de identidad termina con alguien
        entrando al hogar equivocado. Se baja la dirección entera.
        """
        return (email or "").strip().lower()

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError(_("An email address is required."))
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_("email address"), unique=True)
    display_name = models.CharField(_("display name"), max_length=80, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff status"), default=False)
    date_joined = models.DateTimeField(_("date joined"), auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            # Refuerzo a nivel de base de datos: la unicidad no debe depender de
            # que cada llamador recuerde pasar por normalize_email (createsuperuser,
            # /admin/ y UserFactory lo hacían distinto antes de este arreglo).
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def __str__(self):
        return self.display_name or self.email


class Profile(models.Model):
    SERENO = "sereno"
    NOCTURNO = "nocturno"
    ACCESIBLE = "accesible"
    THEME_CHOICES = [
        (SERENO, _("Serene")),
        (NOCTURNO, _("Nocturne")),
        (ACCESIBLE, _("Accessible")),
    ]
    LANGUAGE_CHOICES = [("en", _("English")), ("fr", _("Français"))]

    THEMES = [SERENO, NOCTURNO, ACCESIBLE]
    LANGUAGES = ["en", "fr"]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(_("avatar"), upload_to="avatars/", blank=True, null=True)
    theme = models.CharField(_("theme"), max_length=16, choices=THEME_CHOICES, default=SERENO)
    language = models.CharField(_("language"), max_length=5, choices=LANGUAGE_CHOICES, default="en")

    class Meta:
        verbose_name = _("profile")
        verbose_name_plural = _("profiles")

    def __str__(self):
        return f"{self.user} · {self.theme}/{self.language}"


@receiver(post_save, sender=User)
def crear_perfil(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
