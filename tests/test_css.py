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


def test_las_graficas_no_llevan_colores_literales():
    """Un color en el JS es ilegible en Nocturno y pierde el 14:1 en Accesible.

    Vive aqui y no en las pruebas de vistas: es una guardia de estilo, no de
    comportamiento, y no necesita base de datos.
    """
    js = (RAIZ / "static" / "js" / "graficas.js").read_text(encoding="utf-8")

    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", js)
    assert not re.search(r"\brgba?\s*\(", js)
    assert "getPropertyValue" in js, (
        "graficas.js tiene que LEER las variables CSS en tiempo de ejecucion: "
        "el tema puede cambiar sin recargar."
    )


def test_las_graficas_no_llevan_cadenas_visibles():
    """Las etiquetas de las series salen de atributos data- del <canvas>, para
    que las traduzca Django. Una cadena dentro del JS no pasa por gettext y se
    queda en ingles bajo fr, que es un requisito legal del producto.

    No esta en el plan: la guardia de colores no habria visto una etiqueta
    escrita a mano, y es el mismo fallo por el mismo motivo.
    """
    js = (RAIZ / "static" / "js" / "graficas.js").read_text(encoding="utf-8")
    sin_comentarios = re.sub(r"/\*.*?\*/", "", js, flags=re.DOTALL)
    sin_comentarios = re.sub(r"//.*", "", sin_comentarios)

    literales = re.findall(r'"([^"]*)"', sin_comentarios)
    # Heuristica: una frase de cara al usuario lleva espacios o empieza en
    # mayuscula. Los nombres de variable CSS, los ids del DOM y los tipos de
    # grafica no. MAQUINARIA es la lista explicita de lo que si cumple la forma
    # de una frase y aun asi no lo es; que sea explicita es el punto — anadir
    # una entrada aqui es una decision visible en la revision.
    MAQUINARIA = {"use strict", "DOMContentLoaded", "MutationObserver"}
    sospechosos = [
        s for s in literales
        if s not in MAQUINARIA and (" " in s or s[:1].isupper())
    ]
    assert not sospechosos, (
        f"graficas.js lleva texto que parece visible: {sospechosos}. Va en un "
        f"atributo data- del canvas, traducido por Django."
    )
