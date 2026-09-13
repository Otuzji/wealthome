import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from tests.factories import MembershipFactory, UserFactory

CATALOGO_FR = Path(settings.BASE_DIR) / "locale/fr/LC_MESSAGES/django.po"

# --- Ruling P-4 ------------------------------------------------------------
# La primera version de esta prueba partia el .po por "\n\n" e inspeccionaba
# los bloques resultantes. Eso es fragil: se rompe con comentarios, con la
# entrada de cabecera (msgid ""), con banderas "#, fuzzy" y con msgid/msgstr
# que ocupan varias lineas de cadenas consecutivas. En su lugar, una expresion
# regular localiza cada entrada msgid/msgstr directamente sobre el texto
# completo del archivo, sin depender de como esten separados los bloques.
_CADENA = r'"(?:[^"\\]|\\.)*"'
_ENTRADA_RE = re.compile(
    r"(?P<comentarios>(?:^#.*\n)*)"
    r"^msgid(?P<msgid>(?:[ \t]*" + _CADENA + r"[ \t]*\n?)+)"
    r"^msgstr(?P<msgstr>(?:[ \t]*" + _CADENA + r"[ \t]*\n?)+)",
    re.MULTILINE,
)


# Una entrada plural es msgid / msgid_plural / msgstr[0] / msgstr[1], y por eso
# _ENTRADA_RE (que exige msgstr pegado al msgid) NO la reconoce. Sin esto, un
# plural sin traducir no lo veria ninguna de las dos guardias del catalogo: ni
# esta ni la de exhaustividad. El agujero se abrio con el primer plural del
# arbol (los dias de prueba que quedan, Tarea 11 del Plan 3).
_ENTRADA_PLURAL_RE = re.compile(
    r"(?P<comentarios>(?:^#.*\n)*)"
    r"^msgid(?P<msgid>(?:[ \t]*" + _CADENA + r"[ \t]*\n?)+)"
    r"^msgid_plural(?P<msgid_plural>(?:[ \t]*" + _CADENA + r"[ \t]*\n?)+)"
    r"(?P<formas>(?:^msgstr\[\d+\](?:[ \t]*" + _CADENA + r"[ \t]*\n?)+)+)",
    re.MULTILINE,
)

_FORMA_RE = re.compile(r"^msgstr\[(?P<n>\d+)\](?P<cad>(?:[ \t]*" + _CADENA + r"[ \t]*\n?)+)",
                       re.MULTILINE)


def _texto_de_cadenas(bloque):
    """Concatena el contenido de 'a' "b" "c"... de un grupo msgid o msgstr."""
    return "".join(trozo[1:-1] for trozo in re.findall(_CADENA, bloque))


def _entradas_sin_traducir_o_fuzzy(texto_po):
    """Toda entrada msgid no vacia cuyo msgstr este vacio, o que este marcada
    "#, fuzzy". Una entrada fuzzy es la conjetura de msgmerge a partir de una
    cadena parecida; compilemessages la descarta al compilar el .mo, asi que
    un catalogo lleno de entradas fuzzy pasaria una revision superficial y
    aun asi se renderizaria en ingles. Se ignora la cabecera (msgid "")."""
    problemas = []
    for m in _ENTRADA_RE.finditer(texto_po):
        msgid = _texto_de_cadenas(m.group("msgid"))
        if msgid == "":
            continue
        msgstr = _texto_de_cadenas(m.group("msgstr"))
        es_fuzzy = "#, fuzzy" in m.group("comentarios")
        if msgstr == "":
            problemas.append(f'sin traducir: msgid "{msgid}"')
        elif es_fuzzy:
            problemas.append(f'fuzzy (compilemessages la descarta): msgid "{msgid}"')

    for m in _ENTRADA_PLURAL_RE.finditer(texto_po):
        msgid = _texto_de_cadenas(m.group("msgid"))
        es_fuzzy = "#, fuzzy" in m.group("comentarios")
        formas = {
            int(f.group("n")): _texto_de_cadenas(f.group("cad"))
            for f in _FORMA_RE.finditer(m.group("formas"))
        }
        if not formas or any(v == "" for v in formas.values()):
            problemas.append(f'plural sin traducir: msgid "{msgid}"')
        elif es_fuzzy:
            problemas.append(f'plural fuzzy (compilemessages la descarta): msgid "{msgid}"')
    return problemas


def test_existe_el_catalogo_frances():
    assert CATALOGO_FR.exists(), "Ejecuta: python manage.py makemessages -l fr"


def test_no_quedan_cadenas_francesas_sin_traducir():
    problemas = _entradas_sin_traducir_o_fuzzy(CATALOGO_FR.read_text(encoding="utf-8"))
    assert not problemas, "Cadenas sin traducir o fuzzy en fr:\n" + "\n".join(problemas)


def test_la_deteccion_de_cadenas_sin_traducir_falla_ante_un_msgstr_vacio():
    """Prueba de la prueba: demuestra, contra un .po de juguete (no el
    catalogo real), que _entradas_sin_traducir_o_fuzzy detecta un msgstr
    vacio en vez de devolver una lista vacia sin haber vigilado nada."""
    po_de_juguete = (
        'msgid ""\n'
        'msgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        "\n"
        'msgid "Save"\n'
        'msgstr ""\n'
    )
    problemas = _entradas_sin_traducir_o_fuzzy(po_de_juguete)
    assert len(problemas) == 1
    assert "Save" in problemas[0]


def test_la_deteccion_de_cadenas_sin_traducir_falla_ante_una_entrada_fuzzy():
    """Una entrada "#, fuzzy" con msgstr relleno tambien debe detectarse:
    compilemessages la ignora igual que si estuviera vacia."""
    po_de_juguete = (
        'msgid ""\n'
        'msgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        "\n"
        "#, fuzzy\n"
        'msgid "Save"\n'
        'msgstr "Guardar (adivinado por msgmerge)"\n'
    )
    problemas = _entradas_sin_traducir_o_fuzzy(po_de_juguete)
    assert len(problemas) == 1
    assert "Save" in problemas[0]


def test_una_traduccion_completa_y_sin_fuzzy_no_dispara_nada():
    po_de_juguete = (
        'msgid ""\n'
        'msgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        "\n"
        'msgid "Save"\n'
        'msgstr "Enregistrer"\n'
    )
    assert _entradas_sin_traducir_o_fuzzy(po_de_juguete) == []


@pytest.mark.django_db
def test_la_interfaz_aparece_en_frances(client):
    user = UserFactory()
    user.profile.language = "fr"
    user.profile.save()
    # El brief invoca a UserFactory() a secas, pero households:ajustes exige
    # una membresia activa (_hogar_activo levanta PermissionDenied si no la
    # hay) y UserFactory no crea ninguna: sin esto la prueba daria 403 sin
    # llegar nunca a comprobar el idioma. Se agrega la membresia minima para
    # que la peticion llegue a renderizar la plantilla real.
    MembershipFactory(user=user)
    client.force_login(user)

    html = client.get(reverse("households:ajustes")).content.decode()
    assert "Membres" in html or "Paramètres" in html


def test_los_idiomas_declarados_son_solo_en_y_fr():
    assert [c for c, _ in settings.LANGUAGES] == ["en", "fr"]
