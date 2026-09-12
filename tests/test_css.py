"""La guardia del §7.4: los componentes se escriben UNA vez.

El tema Accesible no es "Sereno con letra grande": sustituye las sombras por
bordes, y eso se hace cambiando variables en tokens.css. Un componente que
traiga su propio [data-theme] rompe esa promesa en cuanto alguien anada el
cuarto tema, y nadie lo notaria hasta entonces.
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

CSS = RAIZ / "static" / "css"

# Cinco series categoricas mas la rejilla. Mas de cinco categorias en una
# grafica ya no se distinguen por color, se distinguen por etiqueta.
VARIABLES_DE_GRAFICA = [f"--chart-{i}" for i in range(1, 6)] + ["--chart-grid"]

TEMAS = ("nocturno", "accesible")


def _texto(nombre):
    return (CSS / nombre).read_text(encoding="utf-8")


def _bloque_del_tema(texto, tema):
    """El cuerpo de la regla [data-theme="<tema>"] { ... }."""
    marca = f'[data-theme="{tema}"]'
    assert marca in texto, f"tokens.css no declara el tema {tema}"
    return texto.split(marca, 1)[1].split("}", 1)[0]


def test_ningun_componente_contiene_un_selector_de_tema():
    for nombre in ("components.css", "modules.css", "base.css"):
        texto = _texto(nombre)
        assert "data-theme" not in texto, (
            f"{nombre} contiene un selector de tema. Los tres temas se "
            f"expresan cambiando variables en tokens.css, no duplicando "
            f"componentes."
        )


def test_los_tres_temas_definen_las_mismas_variables_de_grafica():
    texto = _texto("tokens.css")
    # Sereno vive en :root, no en un [data-theme].
    sereno = texto.split(":root", 1)[1].split("}", 1)[0]
    bloques = {"sereno": sereno}
    bloques.update({tema: _bloque_del_tema(texto, tema) for tema in TEMAS})

    for tema, bloque in bloques.items():
        for variable in VARIABLES_DE_GRAFICA:
            assert f"{variable}:" in bloque, (
                f"El tema {tema} no define {variable}: una grafica con colores "
                f"que no cambian con el tema es ilegible en Nocturno y pierde "
                f"el contraste 14:1 en Accesible."
            )


def test_ningun_componente_lleva_un_color_literal():
    """Un literal donde debia ir una variable es invisible hasta que alguien
    cambia de tema y el componente se queda igual. Es el fallo que el Step 6 del
    plan mandaba buscar a ojo; aqui se busca solo.
    """
    literal = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    for nombre in ("components.css", "modules.css", "base.css"):
        encontrados = literal.findall(_texto(nombre))
        assert not encontrados, (
            f"{nombre} lleva colores literales {encontrados}: van en "
            f"tokens.css, o el componente no cambia con el tema."
        )
