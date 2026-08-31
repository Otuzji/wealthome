import pytest
from django.core.exceptions import PermissionDenied
from django.db import models

from apps.households.models import Membership
from apps.households.permissions import get_membership, require_permission
from apps.households.scoping import HouseholdScoped
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory


@pytest.mark.django_db
def test_for_user_solo_devuelve_datos_del_hogar_del_usuario():
    """La prueba que impide que los Thompson vean las finanzas de los García."""
    from tests.models import Nota  # modelo de prueba, ver tests/models.py

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    papa = UserFactory()
    MembershipFactory(household=thompson, user=papa, role=Membership.ADMIN)

    Nota.objects.create(household=thompson, texto="hipoteca de los Thompson")
    Nota.objects.create(household=garcia, texto="hipoteca de los García")

    visibles = Nota.objects.for_user(papa)
    assert [n.texto for n in visibles] == ["hipoteca de los Thompson"]


@pytest.mark.django_db
def test_for_user_no_devuelve_nada_a_quien_no_tiene_membresia():
    from tests.models import Nota

    hogar = HouseholdFactory()
    Nota.objects.create(household=hogar, texto="secreto")
    assert Nota.objects.for_user(UserFactory()).count() == 0


@pytest.mark.django_db
def test_una_membresia_inactiva_no_da_acceso():
    from tests.models import Nota

    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, is_active=False)
    Nota.objects.create(household=hogar, texto="secreto")
    assert Nota.objects.for_user(user).count() == 0


@pytest.mark.django_db
def test_todo_modelo_con_hogar_hereda_de_household_scoped():
    """Un modelo con FK a Household que no herede de HouseholdScoped es un agujero.

    Esta prueba vigila al Plan 2 y al Plan 3: cada modelo nuevo con ámbito de
    hogar la rompe hasta que hereda de HouseholdScoped, que es justo lo que
    queremos que pase.
    """
    from django.apps import apps as django_apps

    from apps.households.models import Household

    # Relacionan usuarios con el hogar; no son datos del hogar.
    EXCEPCIONES = {"Membership", "Invitation"}

    infractores = []
    for modelo in django_apps.get_models():
        if modelo is Household or modelo.__name__ in EXCEPCIONES:
            continue
        tiene_fk_a_hogar = any(
            isinstance(campo, models.ForeignKey) and campo.related_model is Household
            for campo in modelo._meta.get_fields()
            if isinstance(campo, models.ForeignKey)
        )
        if tiene_fk_a_hogar and not issubclass(modelo, HouseholdScoped):
            infractores.append(modelo.__name__)

    assert infractores == [], f"Modelos con hogar sin HouseholdScoped: {infractores}"


@pytest.mark.django_db
def test_get_membership_devuelve_none_para_un_extrano():
    assert get_membership(UserFactory(), HouseholdFactory()) is None


@pytest.mark.django_db
def test_require_permission_deja_pasar_al_que_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=True)
    require_permission(user, hogar, "can_edit_budget")  # no debe lanzar


@pytest.mark.django_db
def test_require_permission_bloquea_al_que_no_lo_tiene():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user, can_edit_budget=False)
    with pytest.raises(PermissionDenied):
        require_permission(user, hogar, "can_edit_budget")


@pytest.mark.django_db
def test_require_permission_bloquea_a_quien_no_es_del_hogar():
    with pytest.raises(PermissionDenied):
        require_permission(UserFactory(), HouseholdFactory(), "can_view_budget")


@pytest.mark.django_db
def test_require_permission_rechaza_un_permiso_inexistente():
    hogar = HouseholdFactory()
    user = UserFactory()
    MembershipFactory(household=hogar, user=user)
    with pytest.raises(ValueError):
        require_permission(user, hogar, "can_do_anything")
