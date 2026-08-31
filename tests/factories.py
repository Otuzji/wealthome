import factory
from django.contrib.auth import get_user_model


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


from apps.households.models import Household, Membership  # noqa: E402


class HouseholdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Household

    name = factory.Sequence(lambda n: f"Hogar {n}")
    family_size = 4


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    household = factory.SubFactory(HouseholdFactory)
    role = Membership.MEMBER
