import factory
from django.contrib.auth import get_user_model

from apps.households.models import Household, Membership


class HouseholdScopedFactory(factory.django.DjangoModelFactory):
    """Base de las fábricas de modelos con ámbito de hogar.

    factory_boy crea sus objetos con `model_class.objects.create(...)`, y en
    un modelo con hogar ese manager lanza RuntimeError a propósito (ver
    apps/households/scoping.py). Las fábricas son código de pruebas que ya
    dice a qué hogar pertenece cada fila, así que entran por `unscoped`.

    Toda fábrica del Plan 2 sobre un modelo con hogar debe heredar de aquí.
    """

    class Meta:
        abstract = True

    @classmethod
    def _get_manager(cls, model_class):
        return model_class.unscoped


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"miembro{n}@example.com")
    display_name = factory.Sequence(lambda n: f"Miembro {n}")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "clave-larga-123")
        if create:
            obj.save()


class HouseholdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Household
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Hogar {n}")
    family_size = 4

    @factory.post_generation
    def suscripcion(obj, create, extracted, **kwargs):
        """Sin esto, cada hogar de prueba nace sin suscripcion y la guardia del
        §2.4 lo dejaria escribir por la puerta de atras en vez de por la buena."""
        if not create:
            return
        from apps.subscriptions.services import crear_suscripcion

        crear_suscripcion(obj)


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    household = factory.SubFactory(HouseholdFactory)
    role = Membership.MEMBER


class EtiquetaFactory(HouseholdScopedFactory):
    class Meta:
        model = "tests.Etiqueta"

    household = factory.SubFactory(HouseholdFactory)
    nombre = factory.Sequence(lambda n: f"Etiqueta {n}")


class NotaFactory(HouseholdScopedFactory):
    class Meta:
        model = "tests.Nota"

    household = factory.SubFactory(HouseholdFactory)
    texto = factory.Sequence(lambda n: f"Nota {n}")
