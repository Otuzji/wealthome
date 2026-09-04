"""El motor no toca el ORM.

Es la condición que hace baratas las pruebas del §9 del diseño de la Fase 1:
la cascada, las periodicidades y el arrastre se prueban con Decimal y listas,
en menos de un segundo, en vez de contra el pooler de Supabase a 3,5 minutos
la corrida.

Sin esta guardia la pureza se erosiona en la tercera tarea: alguien necesita
el hogar "solo para un caso", importa un modelo, y para cuando se nota ya hay
seis módulos que no se pueden importar sin Django configurado.
"""

import ast
import pathlib

import pytest

RAIZ_MOTOR = (
    pathlib.Path(__file__).resolve().parents[3] / "apps" / "budget" / "engine"
)

PROHIBIDOS = ("django.db", "django.conf", "django.contrib")


def _modulos_importados(codigo):
    """Cada módulo que un archivo importa, en cualquiera de las dos formas."""
    arbol = ast.parse(codigo)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                yield alias.name
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level == 0 and nodo.module:
                yield nodo.module


def _infractores(raiz):
    encontrados = []
    for archivo in sorted(raiz.rglob("*.py")):
        if "__pycache__" in archivo.parts:
            continue
        for modulo in _modulos_importados(archivo.read_text(encoding="utf-8")):
            if modulo.startswith(PROHIBIDOS) or (
                modulo.startswith("apps.") and ".models" in modulo
            ):
                encontrados.append(f"{archivo.name}: import {modulo}")
    return encontrados


def test_el_motor_no_importa_el_orm():
    infractores = _infractores(RAIZ_MOTOR)
    assert infractores == [], (
        "Módulos de apps/budget/engine/ que importan el ORM. El motor recibe "
        "Decimal, fechas y listas; quien necesite el ORM lo hace en "
        "apps/budget/services.py:\n" + "\n".join(infractores)
    )


def test_la_guardia_de_pureza_falla_ante_un_infractor(tmp_path):
    """Prueba de la prueba: una guardia que no puede fallar no vigila nada."""
    (tmp_path / "sucio.py").write_text(
        "from django.db import models\n\n\ndef calcular():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "limpio.py").write_text(
        "from decimal import Decimal\n\n\ndef calcular():\n    return Decimal('1')\n",
        encoding="utf-8",
    )

    infractores = _infractores(tmp_path)

    assert len(infractores) == 1
    assert "sucio.py" in infractores[0]
    assert "django.db" in infractores[0]


def test_la_guardia_tambien_ve_un_import_de_modelos_propios(tmp_path):
    (tmp_path / "sucio.py").write_text(
        "from apps.budget.models import Transaction\n", encoding="utf-8"
    )

    assert len(_infractores(tmp_path)) == 1


def test_el_paquete_del_motor_existe_y_esta_vacio_de_orm():
    assert RAIZ_MOTOR.is_dir(), "apps/budget/engine/ tiene que existir"
