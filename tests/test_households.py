import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.households.models import Household, Membership
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


@pytest.mark.django_db
def test_hogar_tiene_valores_por_defecto_canadienses():
    hogar = Household.objects.create(name="Family Thompson", family_size=4)
    assert hogar.currency == "CAD"
    assert hogar.allowance_rollover is True


@pytest.mark.django_db
def test_family_size_es_independiente_del_numero_de_cuentas():
    """Un hogar de cinco personas puede tener dos cuentas (spec §3.1)."""
    hogar = HouseholdFactory(family_size=5)
    MembershipFactory(household=hogar, role=Membership.ADMIN)
    MembershipFactory(household=hogar, role=Membership.MEMBER)
    assert hogar.family_size == 5
    assert hogar.active_memberships().count() == 2


@pytest.mark.django_db
def test_el_administrador_tiene_los_cuatro_permisos():
    membresia = MembershipFactory(role=Membership.ADMIN)
    assert membresia.can_view_budget
    assert membresia.can_edit_budget
    assert membresia.can_add_transactions
    assert membresia.can_view_reports


@pytest.mark.django_db
def test_un_miembro_puede_tener_permisos_recortados():
    membresia = MembershipFactory(role=Membership.MEMBER, can_view_budget=False, can_edit_budget=False)
    assert not membresia.can_view_budget
    assert membresia.can_add_transactions  # sigue pudiendo registrar sus gastos


@pytest.mark.django_db
def test_un_usuario_no_puede_estar_dos_veces_en_el_mismo_hogar():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Membership.objects.create(household=hogar, user=user, role=Membership.MEMBER)


@pytest.mark.django_db
def test_el_hogar_no_admite_una_septima_membresia():
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar, role=Membership.ADMIN)
    for _ in range(5):
        MembershipFactory(household=hogar, role=Membership.MEMBER)
    assert hogar.active_memberships().count() == 6

    septima = Membership(household=hogar, user=UserFactory(), role=Membership.MEMBER)
    with pytest.raises(ValidationError):
        septima.full_clean()


@pytest.mark.django_db
def test_una_membresia_inactiva_libera_un_puesto():
    hogar = HouseholdFactory()
    MembershipFactory(household=hogar, role=Membership.ADMIN)
    ocupantes = [MembershipFactory(household=hogar, role=Membership.MEMBER) for _ in range(5)]
    ocupantes[0].is_active = False
    ocupantes[0].save()

    nueva = Membership(household=hogar, user=UserFactory(), role=Membership.MEMBER)
    nueva.full_clean()  # no debe lanzar
