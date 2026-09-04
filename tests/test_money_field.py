"""Las dos costuras de dinero que el traspaso pedía colocar mientras son gratis.

**MoneyField** — el spec §3.4 dice que todo importe es
`DecimalField(max_digits=12, decimal_places=2)` y que nunca es `float`, porque
en coma flotante `0.1 + 0.2 != 0.3` y un balance que no cuadra por centavos
hace que el usuario deje de confiar en la aplicación entera. Con doce modelos
financieros por delante, esa restricción tiene que estar expresada una vez en
el código y no vigilada doce veces en la revisión.

**La moneda del hogar** — `Household.currency` existe desde el Plan 1 y
`money.py` la ignoraba, leyendo siempre `settings.DEFAULT_CURRENCY`. Que solo
haya CAD es una decisión de producto legítima (spec §5.2), pero la
contradicción entre la columna y el código estaba ahí y alguien la habría
"arreglado" mal dentro de dos planes.
"""

from decimal import Decimal

import pytest
from django.db import models
from django.template import Context, Template

from apps.core.fields import MoneyField
from apps.core.templatetags.money import format_money
from tests.factories import HouseholdFactory


def _normalizar(texto):
    """Babel usa espacio duro y espacio fino; las pruebas comparan en llano."""
    return texto.replace(" ", " ").replace(" ", " ")


# --- MoneyField --------------------------------------------------------------


def test_money_field_lleva_la_precisión_del_spec():
    campo = MoneyField()

    assert isinstance(campo, models.DecimalField)
    assert campo.max_digits == 12
    assert campo.decimal_places == 2


def test_money_field_acepta_las_opciones_normales_de_un_campo():
    campo = MoneyField(null=True, verbose_name="alquiler")

    assert campo.null is True
    assert campo.verbose_name == "alquiler"
    assert campo.max_digits == 12


def test_money_field_acepta_el_verbose_name_como_posicional():
    """Como cualquier campo de Django (`CharField(_("name"), max_length=80)`):
    la Tarea 9 necesitó `MoneyField(_("amount"), null=True, blank=True)` y,
    antes de este cambio, esa forma lanzaba `TypeError` porque la firma solo
    aceptaba `**kwargs`. Ahora el primer posicional es el nombre visible."""
    campo = MoneyField("alquiler", null=True)

    assert campo.verbose_name == "alquiler"
    assert campo.null is True
    assert campo.max_digits == 12
    assert campo.decimal_places == 2


def test_money_field_deja_forzar_la_precisión_pero_hay_que_escribirlo():
    """No se prohíbe: se hace visible. Un importe con otra precisión aparece
    en el diff."""
    campo = MoneyField(max_digits=19)

    assert campo.max_digits == 19
    assert campo.decimal_places == 2


# --- La moneda del hogar -----------------------------------------------------


def test_format_money_usa_la_moneda_por_defecto_cuando_no_se_le_da_otra():
    assert _normalizar(format_money(Decimal("2847.50"), locale="en_CA")) == "$2,847.50"


def test_format_money_respeta_la_moneda_que_se_le_pasa():
    resultado = _normalizar(format_money(Decimal("2847.50"), locale="en_CA", currency="EUR"))

    assert "2,847.50" in resultado
    assert "€" in resultado


def test_el_filtro_acepta_la_moneda_del_hogar_como_argumento():
    plantilla = Template("{% load money %}{{ importe|money:moneda }}")

    salida = _normalizar(plantilla.render(Context({"importe": Decimal("100"), "moneda": "EUR"})))

    assert "€" in salida


@pytest.mark.django_db
def test_el_filtro_sin_argumento_sigue_dando_la_moneda_por_defecto():
    """El hogar del Plan 1 se crea en CAD, así que pasarle su moneda y no
    pasarle nada dan lo mismo hoy. La prueba fija que seguirán coincidiendo:
    si un día el valor por defecto de Household.currency cambiara sin que
    settings.DEFAULT_CURRENCY lo hiciera, las pantallas mostrarían dos
    monedas distintas para el mismo dinero."""
    hogar = HouseholdFactory()
    plantilla = Template("{% load money %}{{ importe|money }}|{{ importe|money:hogar.currency }}")

    izquierda, derecha = plantilla.render(
        Context({"importe": Decimal("100"), "hogar": hogar})
    ).split("|")

    assert izquierda == derecha


@pytest.mark.django_db
def test_una_moneda_vacía_no_rompe_la_pantalla():
    """El filtro recibe `hogar.currency` desde la plantilla, y en una pantalla
    sin hogar en contexto eso llega como cadena vacía. Un TemplateSyntaxError
    en la pantalla de dinero es peor que caer en la moneda por defecto."""
    plantilla = Template("{% load money %}{{ importe|money:moneda }}")

    salida = _normalizar(plantilla.render(Context({"importe": Decimal("100"), "moneda": ""})))

    assert salida == "$100.00"


# --- El hogar en el contexto de las plantillas -------------------------------


@pytest.mark.django_db
def test_las_plantillas_reciben_el_hogar_sin_una_consulta_extra(client):
    """Lo pone el decorador en request.hogar; el procesador de contexto solo
    lo lee. Una plantilla que necesite la moneda del hogar no debe costar una
    consulta por render."""
    from apps.households.services import crear_hogar
    from tests.factories import UserFactory

    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    client.force_login(user)

    respuesta = client.get("/household/settings/")

    assert respuesta.context["hogar"] == hogar


@pytest.mark.django_db
def test_una_pantalla_sin_hogar_deja_el_contexto_en_none(client):
    """La pantalla de registro no tiene hogar, y el procesador de contexto no
    puede reventar por eso."""
    respuesta = client.get("/signup/")

    assert respuesta.context["hogar"] is None
