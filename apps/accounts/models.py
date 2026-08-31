from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

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
