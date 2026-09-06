# Wealthome Fase 1 · Plan 2: el motor financiero

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el motor de presupuesto de Wealthome — las ocho periodicidades, los cinco modos de ingreso variable, el ciclo de vida del mes, el cierre con arrastre, las metas y el reparto en cascada del sobrante con mesada personal — más los trece modelos que lo persisten y seis pantallas mínimas que permiten ejercitarlo a mano de punta a punta.

**Architecture:** La aritmética vive en `apps/budget/engine/`, un paquete de funciones puras que **no importa el ORM**: recibe `Decimal`, fechas y listas, y devuelve lo mismo. `apps/budget/services.py` es el único que lee modelos, llama al motor y escribe el resultado. Los trece modelos heredan de `HouseholdScoped`, así que toda consulta exige el hogar; todo formulario hereda de `HouseholdScopedModelForm`; toda vista lleva uno de los tres decoradores de `apps/households/permissions.py`.

**Tech Stack:** Python 3.11, Django 5.1, Postgres (Supabase), pytest + pytest-django + factory_boy, CSS puro. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-03-wealthome-motor-financiero-design.md`
**Spec de la Fase 1:** `docs/superpowers/specs/2026-08-30-wealthome-nucleo-financiero-design.md`
**Traspaso del Plan 1:** `docs/superpowers/2026-08-31-estado-y-puertas-plan-2.md`

## Global Constraints

- **Python 3.11**, **Django 5.1**. En Django 5.x `USE_L10N` fue eliminado — no lo escribas en settings.
- **Todo importe monetario usa `apps.core.fields.MoneyField`.** Nunca `float`, nunca `DecimalField` a mano. (Spec Fase 1 §3.4)
- **Un solo punto de redondeo:** `apps.budget.engine.money.centavos()`, con `ROUND_HALF_UP` a dos decimales. Ninguna otra función del proyecto redondea dinero.
- **`apps/budget/engine/` no importa el ORM.** Ni `django.db`, ni `django.conf`, ni `apps.*.models`. `tests/budget/engine/test_pureza.py` lo vigila.
- **Todo texto visible al usuario pasa por `gettext`** (`{% translate %}` en plantillas, `gettext_lazy as _` en Python), y **cada cadena nueva se escribe a mano en `locale/en/LC_MESSAGES/django.po` y `locale/fr/LC_MESSAGES/django.po`** y se compila. No hay cadena GNU gettext en esta máquina.
- **Todo modelo con datos del hogar hereda de `apps.households.scoping.HouseholdScoped`.** Sin excepciones. Si declara su propia `Meta`, debe heredarla: `class Meta(HouseholdScoped.Meta):`.
- **Toda fábrica de pruebas de un modelo con hogar hereda de `tests.factories.HouseholdScopedFactory`**, o `factory_boy` reventará contra el manager estricto.
- **Todo formulario sobre un modelo con hogar hereda de `apps.households.scoped_forms.HouseholdScopedModelForm`** y recibe `household=` de solo palabra clave.
- **Toda vista lleva `@con_hogar`, `@solo_admin` o `@requiere_permiso("...")`** de `apps.households.permissions`, y recibe el hogar como segundo argumento.
- **Moneda: CAD.** Idiomas: `en` (por defecto) y `fr`. Temas: `sereno`, `nocturno`, `accesible`.
- Mensajes de commit en español, en imperativo.

## Cómo correr las pruebas en esta máquina

```bash
.venv/Scripts/python.exe -m pytest tests/budget/engine -q     # el motor: bajo un segundo
.venv/Scripts/python.exe -m pytest tests/budget -q            # el motor + su persistencia
.venv/Scripts/python.exe -m pytest -q                         # todo: ~4 min
.venv/Scripts/python.exe -m pytest -q --create-db             # OBLIGATORIO tras una migración nueva
```

**Trampas del entorno, heredadas del Plan 1 — leer antes de la primera tarea:**

- **Tras añadir una migración hay que correr una vez con `--create-db`**, o la base reutilizada conserva el esquema viejo y las pruebas mienten.
- **Corre las pruebas en primer plano y espera el resultado.** Lanzarlas en segundo plano y esperar un aviso cuelga al agente. Pasó tres veces en el Plan 1.
- El pooler de Supabase deja sesiones abiertas: dos corridas seguidas pueden dar un error de arranque espurio que un reintento limpia.
- La base `test_postgres` **no es basura**: es la que reutiliza `--reuse-db`.
- Para compilar los catálogos:
  ```bash
  MSGFMT="C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py"
  for L in en fr; do .venv/Scripts/python.exe "$MSGFMT" -o "locale/$L/LC_MESSAGES/django.mo" "locale/$L/LC_MESSAGES/django.po"; done
  ```

---

## Estructura de archivos

```
apps/budget/
  __init__.py  apps.py
  models/
    __init__.py        # reexporta los trece modelos
    catalog.py         # Category, Merchant
    rules.py           # IncomeSource, ExpenseRule
    months.py          # BudgetMonth, BudgetLine, MonthlyClose
    ledger.py          # Transaction
    goals.py           # Goal, GoalContribution
    allocation.py      # AllocationRule, MonthlyAllocation, AllowanceLedger
  engine/
    __init__.py
    money.py           # centavos(), repartir_proporcional()
    periodicity.py     # ocurrencias(), importe_del_mes()
    income.py          # cifra_conservadora()
    cascade.py         # repartir(), absorber_faltante()
    closing.py         # cerrar()
    allowance.py       # saldo(), carried_out()
    goals.py           # derivar()
    merchants.py       # normalizar()
  services.py          # el único módulo que cruza ORM y motor
  seeds.py             # el árbol de categorías precargado
  forms.py  views.py  urls.py  admin.py
  management/commands/cerrar_meses_vencidos.py
  migrations/
templates/budget/
tests/budget/
  __init__.py
  engine/                          # PURAS: ni una lleva django_db
    __init__.py
    test_pureza.py     test_money.py      test_periodicity.py
    test_income.py     test_cascade.py    test_closing.py
    test_allowance.py  test_goals_engine.py  test_merchants.py
  test_models.py    test_mes_cerrado.py  test_services.py
  test_month_cycle.py  test_views.py     test_aislamiento.py
  test_aceptacion.py
tests/factories_budget.py
```

**Por qué así:** `engine/` es un paquete separado y sin ORM porque los casos que el spec de la Fase 1 §9 exige cubrir son aritmética, no persistencia — y la suite tarda 3,5 minutos contra el pooler de Supabase. `models/` es un paquete y no un archivo de 500 líneas porque seis tareas distintas de este plan lo editan. `services.py` es el único sitio donde el ORM y el motor se tocan, para que la frontera sea auditable de un vistazo.

**Puntos de control usables:** al terminar la **Tarea 8** el motor está completo y sus pruebas corren en menos de dos segundos sin tocar Postgres. Al terminar la **Tarea 11** los trece modelos están completos. Si hay que parar, se para en uno de esos dos sitios y no a medio formulario.

---

### Task 1: Andamiaje de `apps/budget` y la guardia de pureza

**Files:**
- Create: `apps/budget/__init__.py`, `apps/budget/apps.py`, `apps/budget/models/__init__.py`, `apps/budget/engine/__init__.py`, `apps/budget/migrations/__init__.py`
- Modify: `config/settings.py` (añadir la app), `pytest.ini` (marcador `db`)
- Test: `tests/budget/__init__.py`, `tests/budget/engine/test_pureza.py`

**Interfaces:**
- Consumes: nada (primera tarea)
- Produce: la app `apps.budget` registrada y migrable; `tests/budget/` como paquete; la guardia que todas las tareas 2-7 tienen que satisfacer.

- [x] **Step 1: Escribir la prueba de pureza que falla**

`tests/budget/engine/test_pureza.py`:

```python
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
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_pureza.py -q`
Expected: FAIL — `test_el_paquete_del_motor_existe_y_esta_vacio_de_orm` falla porque `apps/budget/engine/` no existe. (Los otros tres pasan: la guardia funciona sobre árboles de juguete desde el principio.)

- [x] **Step 3: Crear el andamiaje**

```bash
mkdir -p apps/budget/models apps/budget/engine apps/budget/migrations \
         apps/budget/management/commands tests/budget/engine templates/budget
touch apps/budget/models/__init__.py apps/budget/engine/__init__.py \
      apps/budget/migrations/__init__.py apps/budget/management/__init__.py \
      apps/budget/management/commands/__init__.py \
      tests/budget/__init__.py tests/budget/engine/__init__.py
```

`apps/budget/__init__.py`: vacío.

`apps/budget/apps.py`:

```python
from django.apps import AppConfig


class BudgetConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.budget"
    verbose_name = "Budget"
```

- [x] **Step 4: Registrar la app y el marcador de pruebas**

En `config/settings.py`, dentro de `INSTALLED_APPS`, después de `"apps.households"`:

```python
    "apps.budget",
```

`pytest.ini` no necesita ningún cambio. "Correr solo el motor" es una **ruta**,
no una convención: las pruebas puras viven en `tests/budget/engine/` y las que
necesitan Postgres en `tests/budget/`. Un marcador que hubiera que acordarse de
poner se olvida a la tercera tarea; un directorio no se olvida.

- [x] **Step 5: Verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS — 4 pruebas.

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 143 pruebas (139 anteriores + 4).

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "Crea la app budget y la guardia de pureza del motor

El motor de presupuesto vivirá en apps/budget/engine/ sin importar el ORM,
para que los casos que el §9 exige cubrir se prueben con Decimal y listas en
lugar de contra el pooler de Supabase. Esa pureza no se sostiene sola: la
guardia recorre el AST de cada módulo del paquete y falla si aparece un import
de django.db, django.conf o de los modelos propios."
```

---

### Task 2: `engine/money.py` — el único punto de redondeo

**Files:**
- Create: `apps/budget/engine/money.py`
- Test: `tests/budget/engine/test_money.py`

**Interfaces:**
- Consumes: nada del proyecto.
- Produce:
  - `centavos(valor: Decimal | int | str) -> Decimal` — redondea a 2 decimales con `ROUND_HALF_UP`.
  - `repartir_proporcional(total: Decimal, pesos: Sequence[Decimal]) -> list[Decimal]` — reparte `total` según `pesos`; **la suma es exactamente `total`**; los centavos sobrantes se reparten de uno en uno por orden de índice.
  - Las usan las Tareas 4, 5, 6 y 7.

- [x] **Step 1: Escribir las pruebas que fallan**

`tests/budget/engine/test_money.py`:

```python
"""El redondeo del dinero, en un solo sitio.

El §3.4 del diseño de la Fase 1 exige que el redondeo sea explícito, a dos
decimales, y siempre en el mismo punto del cálculo. Este módulo ES ese punto:
ninguna otra función del proyecto redondea dinero.

repartir_proporcional es la que hace que una mesada de $100 entre tres
miembros dé 33,34 / 33,33 / 33,33 y no 33,33 tres veces. Diez centavos
perdidos al mes durante un año son $1,20 que no cuadran, y un usuario que ve
un balance que no cuadra deja de confiar en la aplicación entera.
"""

from decimal import Decimal

import pytest

from apps.budget.engine.money import centavos, repartir_proporcional


def test_centavos_redondea_a_dos_decimales():
    assert centavos(Decimal("10.004")) == Decimal("10.00")
    assert centavos(Decimal("10.005")) == Decimal("10.01")
    assert centavos(Decimal("10.006")) == Decimal("10.01")


def test_centavos_redondea_hacia_arriba_en_el_empate():
    """ROUND_HALF_UP y no el ROUND_HALF_EVEN por defecto de Decimal: el
    banquero redondea 2,675 a 2,68 y Python a 2,67, y la diferencia aparece
    en el extracto del usuario."""
    assert centavos(Decimal("2.675")) == Decimal("2.68")
    assert centavos(Decimal("2.665")) == Decimal("2.67")


def test_centavos_acepta_enteros_y_cadenas():
    assert centavos(100) == Decimal("100.00")
    assert centavos("3.1") == Decimal("3.10")


def test_centavos_conserva_el_signo():
    assert centavos(Decimal("-10.005")) == Decimal("-10.01")


def test_repartir_en_partes_iguales_que_dividen_exacto():
    assert repartir_proporcional(Decimal("90.00"), [1, 1, 1]) == [
        Decimal("30.00"),
        Decimal("30.00"),
        Decimal("30.00"),
    ]


def test_repartir_en_partes_iguales_que_no_dividen_exacto():
    """El caso del spec: $100 entre tres da 33,34 / 33,33 / 33,33."""
    partes = repartir_proporcional(Decimal("100.00"), [1, 1, 1])

    assert partes == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum(partes) == Decimal("100.00")


def test_repartir_con_pesos_explicitos():
    partes = repartir_proporcional(Decimal("100.00"), [Decimal("3"), Decimal("1")])

    assert partes == [Decimal("75.00"), Decimal("25.00")]
    assert sum(partes) == Decimal("100.00")


def test_la_suma_es_exactamente_el_total_en_todos_los_casos_feos():
    """La invariante que importa, contra los repartos que más rompen."""
    casos = [
        (Decimal("0.01"), [1, 1, 1]),
        (Decimal("100.00"), [1, 1, 1, 1, 1, 1]),
        (Decimal("0.10"), [1, 1, 1, 1, 1, 1, 1]),
        (Decimal("1000.00"), [Decimal("1"), Decimal("2"), Decimal("7")]),
        (Decimal("999.99"), [1, 1]),
    ]
    for total, pesos in casos:
        assert sum(repartir_proporcional(total, pesos)) == total, (total, pesos)


def test_repartir_da_siempre_el_mismo_resultado():
    """Dos ejecuciones del mismo reparto tienen que coincidir al centavo, o
    replanificar un mes movería la mesada de sitio sin que nadie tocara nada."""
    primera = repartir_proporcional(Decimal("100.00"), [1, 1, 1])
    segunda = repartir_proporcional(Decimal("100.00"), [1, 1, 1])

    assert primera == segunda


def test_repartir_cero_da_ceros():
    assert repartir_proporcional(Decimal("0.00"), [1, 1]) == [
        Decimal("0.00"),
        Decimal("0.00"),
    ]


def test_repartir_sin_pesos_da_lista_vacia():
    assert repartir_proporcional(Decimal("100.00"), []) == []


def test_repartir_con_pesos_que_suman_cero_da_lista_vacia():
    """Una regla de mesada con todos los pesos a cero no reparte nada, en vez
    de dividir por cero."""
    assert repartir_proporcional(Decimal("100.00"), [0, 0]) == []


def test_repartir_un_importe_negativo_reparte_el_signo():
    """Los ajustes del §4.5.3 son negativos: el faltante que se descuenta de
    la mesada del mes siguiente se reparte con el mismo mecanismo."""
    partes = repartir_proporcional(Decimal("-80.00"), [1, 1])

    assert partes == [Decimal("-40.00"), Decimal("-40.00")]
    assert sum(partes) == Decimal("-80.00")
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_money.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.budget.engine.money'`

- [x] **Step 3: Implementar**

`apps/budget/engine/money.py`:

```python
"""El redondeo del dinero, en un solo sitio.

§3.4 del diseño de la Fase 1: los importes son Decimal, nunca float, y el
redondeo es explícito, a dos decimales, y siempre en el mismo punto del
cálculo. Este módulo es ese punto.
"""

from decimal import ROUND_HALF_UP, Decimal

DOS_DECIMALES = Decimal("0.01")


def centavos(valor):
    """Redondea a dos decimales con ROUND_HALF_UP.

    No con el ROUND_HALF_EVEN por defecto de Decimal: el redondeo del
    banquero lleva 2,675 a 2,67, y el usuario que compara contra su recibo ve
    un centavo que falta.
    """
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    return valor.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def repartir_proporcional(total, pesos):
    """Reparte `total` según `pesos`. La suma es EXACTAMENTE `total`.

    Se reparte en centavos enteros y los que sobran se dan de uno en uno por
    orden de índice —quien llama ordena la lista, normalmente por `pk` de la
    membresía—, de modo que dos ejecuciones del mismo reparto coincidan al
    centavo. Sin eso, replanificar un mes movería la mesada de sitio sin que
    nadie hubiera tocado nada.
    """
    pesos = [Decimal(str(p)) for p in pesos]
    total_pesos = sum(pesos)
    if not pesos or total_pesos == 0:
        return []

    total_centavos = int(centavos(total) * 100)
    signo = -1 if total_centavos < 0 else 1
    restantes = abs(total_centavos)

    exactos = [restantes * peso / total_pesos for peso in pesos]
    partes = [int(x) for x in exactos]

    sobrantes = restantes - sum(partes)
    for i in range(sobrantes):
        partes[i % len(partes)] += 1

    return [Decimal(signo * p) / 100 for p in partes]
```

- [x] **Step 4: Ejecutar y verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_money.py -q`
Expected: PASS — 13 pruebas, en menos de un segundo.

- [x] **Step 5: Commit**

```bash
git add apps/budget/engine/money.py tests/budget/engine/test_money.py
git commit -m "Añade el único punto de redondeo del dinero

§3.4 exige que el redondeo sea explícito, a dos decimales y siempre en el
mismo punto; centavos() es ese punto y usa ROUND_HALF_UP, no el redondeo del
banquero que Decimal trae por defecto y que llevaría 2,675 a 2,67.

repartir_proporcional garantiza que la suma de las partes sea exactamente el
total: una mesada de \$100 entre tres miembros da 33,34 / 33,33 / 33,33. Diez
centavos perdidos al mes durante un año son \$1,20 que no cuadran, y un
balance que no cuadra cuesta la confianza en la aplicación entera."
```

---

### Task 3: `engine/periodicity.py` — las ocho periodicidades

**Files:**
- Create: `apps/budget/engine/periodicity.py`
- Test: `tests/budget/engine/test_periodicity.py`

**Interfaces:**
- Consumes: `apps.budget.engine.money.centavos`
- Produce:
  - Constantes `WEEKLY`, `BIWEEKLY`, `SEMIMONTHLY`, `MONTHLY`, `BIMONTHLY`, `QUARTERLY`, `SEMIANNUAL`, `ANNUAL`, y la tupla `PERIODICIDADES` con las ocho.
  - `PERIODICITY_CHOICES: list[tuple[str, str]]` — para los modelos de la Tarea 8. Las etiquetas usan `gettext_lazy`… **no**: el motor no importa `django.conf` ni `django.utils`. Las etiquetas viven en `apps/budget/models/rules.py`; aquí solo los valores.
  - `ocurrencias(periodicidad, ancla, anio, mes, hasta=None) -> list[date]`
  - `importe_del_mes(importe, periodicidad, ancla, anio, mes, hasta=None) -> Decimal`
  - Las usan las Tareas 8, 11 y 12.

- [x] **Step 1: Escribir las pruebas que fallan**

`tests/budget/engine/test_periodicity.py`:

```python
"""Cuándo dispara una regla dentro de un mes concreto.

La decisión §2.2 del diseño del Plan 2: calendario real, no prorrateo. Se
cuentan las ocurrencias reales ancladas en effective_from, así que un mes con
tres quincenas presupuesta tres sueldos y el seguro anual cae entero en su mes
de aniversario.

Prorratear habría dado doce meses idénticos y cómodos, y luego el seguro de
$1.200 llega en agosto contra un presupuesto que decía $100: once meses
cuadran y uno se descuadra por $1.100 sin que el plan lo hubiera anunciado.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget.engine.periodicity import (
    ANNUAL,
    BIMONTHLY,
    BIWEEKLY,
    MONTHLY,
    PERIODICIDADES,
    QUARTERLY,
    SEMIANNUAL,
    SEMIMONTHLY,
    WEEKLY,
    importe_del_mes,
    ocurrencias,
)


def test_las_ocho_periodicidades_del_spec_existen():
    assert set(PERIODICIDADES) == {
        WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY,
        BIMONTHLY, QUARTERLY, SEMIANNUAL, ANNUAL,
    }


# --- semanal y quincenal -----------------------------------------------------


def test_semanal_dispara_cada_siete_dias_desde_el_ancla():
    # 2026-01-02 es viernes. Enero de 2026 tiene cinco viernes.
    assert ocurrencias(WEEKLY, date(2026, 1, 2), 2026, 1) == [
        date(2026, 1, 2), date(2026, 1, 9), date(2026, 1, 16),
        date(2026, 1, 23), date(2026, 1, 30),
    ]


def test_un_mes_de_cuatro_semanas_y_uno_de_cinco_se_distinguen():
    """El mes de cinco viernes es más caro, y el presupuesto tiene que
    decirlo antes de que pase."""
    cinco = ocurrencias(WEEKLY, date(2026, 1, 2), 2026, 1)
    cuatro = ocurrencias(WEEKLY, date(2026, 1, 2), 2026, 2)

    assert len(cinco) == 5
    assert len(cuatro) == 4


def test_quincenal_dispara_cada_catorce_dias():
    assert ocurrencias(BIWEEKLY, date(2026, 1, 2), 2026, 1) == [
        date(2026, 1, 2), date(2026, 1, 16), date(2026, 1, 30),
    ]


def test_el_mes_de_tres_quincenas_es_el_que_genera_el_sobrante():
    """El caso del §2.2: tres sueldos en un mes es sobrante de verdad, y la
    cascada del §4.5 lo reparte."""
    assert len(ocurrencias(BIWEEKLY, date(2026, 1, 2), 2026, 1)) == 3
    assert len(ocurrencias(BIWEEKLY, date(2026, 1, 2), 2026, 2)) == 2


# --- bimensual (dos veces al mes) --------------------------------------------


def test_bimensual_dispara_el_dia_del_ancla_y_ese_dia_mas_quince():
    assert ocurrencias(SEMIMONTHLY, date(2026, 1, 5), 2026, 3) == [
        date(2026, 3, 5), date(2026, 3, 20),
    ]


def test_bimensual_recorta_su_segunda_fecha_a_fin_de_mes():
    """Ancla el 20: la segunda fecha sería el 35, que no existe."""
    assert ocurrencias(SEMIMONTHLY, date(2026, 1, 20), 2026, 2) == [
        date(2026, 2, 20), date(2026, 2, 28),
    ]


# --- mensual y los múltiplos --------------------------------------------------


def test_mensual_dispara_una_vez_el_dia_del_ancla():
    assert ocurrencias(MONTHLY, date(2026, 1, 15), 2026, 7) == [date(2026, 7, 15)]


def test_una_regla_anclada_el_31_dispara_el_ultimo_dia_de_los_meses_cortos():
    """Nunca se salta un mes: el alquiler de febrero se paga en febrero."""
    assert ocurrencias(MONTHLY, date(2026, 1, 31), 2026, 2) == [date(2026, 2, 28)]
    assert ocurrencias(MONTHLY, date(2026, 1, 31), 2026, 4) == [date(2026, 4, 30)]
    assert ocurrencias(MONTHLY, date(2026, 1, 31), 2026, 5) == [date(2026, 5, 31)]


def test_una_regla_anclada_el_29_en_un_ano_bisiesto():
    assert ocurrencias(MONTHLY, date(2024, 1, 29), 2024, 2) == [date(2024, 2, 29)]


def test_bimestral_dispara_en_los_meses_a_distancia_par():
    ancla = date(2026, 1, 10)
    assert ocurrencias(BIMONTHLY, ancla, 2026, 1) == [date(2026, 1, 10)]
    assert ocurrencias(BIMONTHLY, ancla, 2026, 2) == []
    assert ocurrencias(BIMONTHLY, ancla, 2026, 3) == [date(2026, 3, 10)]


def test_trimestral_dispara_cada_tres_meses():
    ancla = date(2026, 2, 10)
    assert ocurrencias(QUARTERLY, ancla, 2026, 2) == [date(2026, 2, 10)]
    assert ocurrencias(QUARTERLY, ancla, 2026, 4) == []
    assert ocurrencias(QUARTERLY, ancla, 2026, 5) == [date(2026, 5, 10)]


def test_semestral_dispara_cada_seis_meses():
    ancla = date(2026, 3, 1)
    assert ocurrencias(SEMIANNUAL, ancla, 2026, 3) == [date(2026, 3, 1)]
    assert ocurrencias(SEMIANNUAL, ancla, 2026, 9) == [date(2026, 9, 1)]
    assert ocurrencias(SEMIANNUAL, ancla, 2026, 6) == []


def test_anual_cae_entero_en_su_mes_de_aniversario():
    """El seguro del §2.2: $1.200 en agosto, no $100 cada mes."""
    ancla = date(2026, 8, 15)
    assert ocurrencias(ANNUAL, ancla, 2027, 8) == [date(2027, 8, 15)]
    assert ocurrencias(ANNUAL, ancla, 2027, 7) == []
    assert ocurrencias(ANNUAL, ancla, 2027, 9) == []


# --- vigencia ----------------------------------------------------------------


def test_una_regla_no_dispara_antes_de_su_ancla():
    assert ocurrencias(MONTHLY, date(2026, 6, 1), 2026, 5) == []


def test_effective_to_corta_la_regla():
    """§3.2: subir el alquiler cierra la regla vieja con effective_to y crea
    una nueva. La vieja no puede seguir disparando."""
    assert ocurrencias(MONTHLY, date(2026, 1, 1), 2026, 3, hasta=date(2026, 3, 31)) == [
        date(2026, 3, 1)
    ]
    assert ocurrencias(MONTHLY, date(2026, 1, 1), 2026, 4, hasta=date(2026, 3, 31)) == []


def test_effective_to_corta_a_media_semana():
    ocs = ocurrencias(WEEKLY, date(2026, 1, 2), 2026, 1, hasta=date(2026, 1, 16))

    assert ocs == [date(2026, 1, 2), date(2026, 1, 9), date(2026, 1, 16)]


# --- el importe del mes -------------------------------------------------------


def test_el_importe_del_mes_multiplica_por_las_ocurrencias():
    assert importe_del_mes(
        Decimal("1400.00"), BIWEEKLY, date(2026, 1, 2), 2026, 1
    ) == Decimal("4200.00")


def test_el_importe_de_un_mes_sin_ocurrencias_es_cero():
    assert importe_del_mes(
        Decimal("1200.00"), ANNUAL, date(2026, 8, 15), 2027, 7
    ) == Decimal("0.00")


def test_el_importe_del_mes_esta_redondeado_a_centavos():
    assert importe_del_mes(
        Decimal("33.333"), MONTHLY, date(2026, 1, 1), 2026, 1
    ) == Decimal("33.33")


def test_una_periodicidad_desconocida_revienta():
    """Un valor no soportado es un error de programación, no un mes vacío que
    haría desaparecer el alquiler del presupuesto sin decir nada."""
    with pytest.raises(ValueError, match="Periodicidad desconocida"):
        ocurrencias("cada_luna_llena", date(2026, 1, 1), 2026, 1)
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_periodicity.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.budget.engine.periodicity'`

- [x] **Step 3: Implementar**

`apps/budget/engine/periodicity.py`:

```python
"""Cuándo dispara una regla dentro de un mes concreto.

Decisión §2.2 del diseño del Plan 2: calendario real, no prorrateo. El
presupuesto tiene que predecir CUÁNDO sale el dinero, o el §4.4 —balance real
contra presupuestado— no significa nada.

Los valores de las periodicidades están en inglés como el resto del esquema.
Sus etiquetas traducibles viven en apps/budget/models/rules.py: este módulo no
importa django.utils, igual que no importa el ORM.
"""

import calendar
from datetime import date, timedelta

from .money import centavos

WEEKLY = "weekly"
BIWEEKLY = "biweekly"
SEMIMONTHLY = "semimonthly"
MONTHLY = "monthly"
BIMONTHLY = "bimonthly"
QUARTERLY = "quarterly"
SEMIANNUAL = "semiannual"
ANNUAL = "annual"

PERIODICIDADES = (
    WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY,
    BIMONTHLY, QUARTERLY, SEMIANNUAL, ANNUAL,
)

# Cada cuántos meses dispara una periodicidad de las que caen en su día del mes.
CADA_N_MESES = {
    MONTHLY: 1,
    BIMONTHLY: 2,
    QUARTERLY: 3,
    SEMIANNUAL: 6,
    ANNUAL: 12,
}

DIAS_ENTRE = {WEEKLY: 7, BIWEEKLY: 14}


def _dia_del_mes(anio, mes, dia):
    """El día pedido, recortado al último del mes si no existe.

    Una regla anclada el 31 dispara el 28 en febrero: nunca se salta un mes,
    porque el alquiler de febrero se paga en febrero.
    """
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(dia, ultimo))


def _dentro_de_vigencia(dia, ancla, hasta):
    return dia >= ancla and (hasta is None or dia <= hasta)


def ocurrencias(periodicidad, ancla, anio, mes, hasta=None):
    """Las fechas en que la regla dispara dentro de ese mes.

    `ancla` es effective_from y `hasta` es effective_to, que corta.
    """
    if periodicidad in DIAS_ENTRE:
        paso = timedelta(days=DIAS_ENTRE[periodicidad])
        primero = date(anio, mes, 1)
        ultimo = _dia_del_mes(anio, mes, 31)
        # Avanza desde el ancla en saltos del tamaño del paso.
        dia = ancla
        if dia < primero:
            saltos = (primero - dia).days // paso.days
            dia = dia + paso * saltos
            while dia < primero:
                dia += paso
        encontradas = []
        while dia <= ultimo:
            if _dentro_de_vigencia(dia, ancla, hasta):
                encontradas.append(dia)
            dia += paso
        return encontradas

    if periodicidad == SEMIMONTHLY:
        candidatas = [
            _dia_del_mes(anio, mes, ancla.day),
            _dia_del_mes(anio, mes, ancla.day + 15),
        ]
        # Un ancla el 16 daría 31 y 31: dos veces el mismo día no son dos pagos.
        vistas = []
        for dia in candidatas:
            if dia not in vistas and _dentro_de_vigencia(dia, ancla, hasta):
                vistas.append(dia)
        return vistas

    if periodicidad in CADA_N_MESES:
        distancia = (anio - ancla.year) * 12 + (mes - ancla.month)
        if distancia < 0 or distancia % CADA_N_MESES[periodicidad] != 0:
            return []
        dia = _dia_del_mes(anio, mes, ancla.day)
        return [dia] if _dentro_de_vigencia(dia, ancla, hasta) else []

    raise ValueError(f"Periodicidad desconocida: {periodicidad!r}")


def importe_del_mes(importe, periodicidad, ancla, anio, mes, hasta=None):
    """Lo que esa regla presupuesta para ese mes: importe x ocurrencias."""
    veces = len(ocurrencias(periodicidad, ancla, anio, mes, hasta))
    return centavos(importe * veces)
```

- [x] **Step 4: Ejecutar y verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_periodicity.py -q`
Expected: PASS — 21 pruebas.

Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS — la guardia de pureza sigue verde con el módulo nuevo.

- [x] **Step 5: Commit**

```bash
git add apps/budget/engine/periodicity.py tests/budget/engine/test_periodicity.py
git commit -m "Añade las ocho periodicidades por calendario real

Decisión §2.2: se cuentan las ocurrencias reales ancladas en effective_from,
no se prorratea. Un mes con tres quincenas presupuesta tres sueldos —y ese es
el sobrante que la cascada del §4.5 reparte— y el seguro anual cae entero en
su mes de aniversario en vez de en doce doceavos que dejan once meses
cuadrados y uno descuadrado por \$1.100 sin haberlo anunciado.

Dos bordes fijados con prueba porque son dinero: una regla anclada el 31
dispara el último día de los meses cortos, nunca se salta uno; y bimensual
recorta igual su segunda fecha."
```

---

### Task 4: `engine/income.py` — los cinco modos de ingreso variable

**Files:**
- Create: `apps/budget/engine/income.py`
- Test: `tests/budget/engine/test_income.py`

**Interfaces:**
- Consumes: `apps.budget.engine.money.centavos`
- Produce:
  - Constantes `FIXED`, `ESTIMATED`, `RANGE`, `ROLLING_AVERAGE`, `IRREGULAR`, la tupla `MODOS`, y `MESES_DE_LA_MEDIA = 6`, `MESES_MINIMOS_PARA_MEDIA = 3`.
  - `cifra_conservadora(amount_type, *, amount=None, amount_min=None, amount_max=None, historial=()) -> Decimal | None`
  - La usan las Tareas 9, 12 y 13.

- [x] **Step 1: Escribir las pruebas que fallan**

`tests/budget/engine/test_income.py`:

```python
"""Los cinco modos de ingreso variable del §4.1.

La regla que gobierna todo el motor: EL PRESUPUESTO SIEMPRE USA LA CIFRA
CONSERVADORA. Un hogar que presupuesta el mejor mes de un ingreso variable se
endeuda en el peor. El optimismo va en la proyección; nunca en el plan.
"""

from decimal import Decimal

import pytest

from apps.budget.engine.income import (
    ESTIMATED,
    FIXED,
    IRREGULAR,
    MESES_MINIMOS_PARA_MEDIA,
    MODOS,
    RANGE,
    ROLLING_AVERAGE,
    cifra_conservadora,
)


def test_los_cinco_modos_del_spec_existen():
    assert set(MODOS) == {FIXED, ESTIMATED, RANGE, ROLLING_AVERAGE, IRREGULAR}


def test_fixed_presupuesta_el_monto_declarado():
    assert cifra_conservadora(FIXED, amount=Decimal("4000")) == Decimal("4000.00")


def test_estimated_presupuesta_la_estimacion_del_usuario():
    assert cifra_conservadora(ESTIMATED, amount=Decimal("2500")) == Decimal("2500.00")


def test_range_presupuesta_el_minimo_y_no_el_maximo():
    """Comisiones y propinas: se presupuesta el mínimo, y lo que exceda es
    superávit al cierre (§13.4). Presupuestar el máximo es exactamente cómo
    una familia se endeuda en un mes flojo."""
    cifra = cifra_conservadora(
        RANGE, amount_min=Decimal("800"), amount_max=Decimal("2400")
    )

    assert cifra == Decimal("800.00")


def test_range_no_presupuesta_ni_el_promedio_del_rango():
    cifra = cifra_conservadora(
        RANGE, amount_min=Decimal("800"), amount_max=Decimal("2400")
    )

    assert cifra != Decimal("1600.00")


def test_irregular_presupuesta_cero():
    """Trabajos esporádicos y bonos: cuando entra, es ingreso excepcional."""
    assert cifra_conservadora(IRREGULAR, amount=Decimal("5000")) == Decimal("0.00")


def test_rolling_average_promedia_los_meses_con_datos():
    historial = [Decimal("3000"), Decimal("3600"), Decimal("2400")]

    assert cifra_conservadora(ROLLING_AVERAGE, historial=historial) == Decimal("3000.00")


def test_rolling_average_redondea_a_centavos():
    historial = [Decimal("1000"), Decimal("1000"), Decimal("1001")]

    assert cifra_conservadora(ROLLING_AVERAGE, historial=historial) == Decimal("1000.33")


def test_rolling_average_devuelve_none_sin_historia_suficiente():
    """§4.1: el modo solo se ofrece cuando existe historia suficiente. Antes
    de eso la interfaz dice explícitamente que aún no hay datos, EN VEZ DE
    INVENTAR UN NÚMERO."""
    assert cifra_conservadora(ROLLING_AVERAGE, historial=[]) is None
    assert cifra_conservadora(ROLLING_AVERAGE, historial=[Decimal("3000")]) is None
    assert (
        cifra_conservadora(ROLLING_AVERAGE, historial=[Decimal("3000"), Decimal("3000")])
        is None
    )


def test_rolling_average_se_habilita_justo_en_el_tercer_mes():
    historial = [Decimal("3000")] * MESES_MINIMOS_PARA_MEDIA

    assert cifra_conservadora(ROLLING_AVERAGE, historial=historial) == Decimal("3000.00")


def test_rolling_average_usa_como_mucho_los_ultimos_seis_meses():
    """Doce meses de historia: solo cuentan los seis últimos."""
    historial = [Decimal("9999")] * 6 + [Decimal("1000")] * 6

    assert cifra_conservadora(ROLLING_AVERAGE, historial=historial) == Decimal("1000.00")


def test_un_modo_desconocido_revienta():
    with pytest.raises(ValueError, match="Modo de ingreso desconocido"):
        cifra_conservadora("adivinalo", amount=Decimal("100"))


def test_fixed_sin_monto_revienta():
    """Un ingreso fijo sin monto es un dato roto, no un cero silencioso que
    haría desaparecer un sueldo del presupuesto."""
    with pytest.raises(ValueError):
        cifra_conservadora(FIXED)


def test_range_sin_minimo_revienta():
    with pytest.raises(ValueError):
        cifra_conservadora(RANGE, amount_max=Decimal("2400"))
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_income.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.budget.engine.income'`

- [x] **Step 3: Implementar**

`apps/budget/engine/income.py`:

```python
"""Los cinco modos de ingreso variable del §4.1.

La regla que gobierna todo el motor: el presupuesto siempre usa la cifra
conservadora. Un hogar que presupuesta el mejor mes de un ingreso variable se
endeuda en el peor. El optimismo va en la proyección; nunca en el plan.
"""

from decimal import Decimal

from .money import centavos

FIXED = "fixed"
ESTIMATED = "estimated"
RANGE = "range"
ROLLING_AVERAGE = "rolling_average"
IRREGULAR = "irregular"

MODOS = (FIXED, ESTIMATED, RANGE, ROLLING_AVERAGE, IRREGULAR)

MESES_DE_LA_MEDIA = 6
MESES_MINIMOS_PARA_MEDIA = 3


def cifra_conservadora(amount_type, *, amount=None, amount_min=None,
                       amount_max=None, historial=()):
    """Lo que este ingreso presupuesta para un mes.

    Devuelve None solo en `rolling_average` sin historia suficiente: significa
    "aún no hay datos", y la interfaz lo dice con todas sus letras en vez de
    inventar un número.
    """
    if amount_type in (FIXED, ESTIMATED):
        if amount is None:
            raise ValueError(f"Un ingreso {amount_type} necesita `amount`.")
        return centavos(amount)

    if amount_type == RANGE:
        if amount_min is None:
            raise ValueError("Un ingreso `range` necesita `amount_min`.")
        # El mínimo, no el promedio y desde luego no el máximo: lo que exceda
        # aparece como superávit al cierre.
        return centavos(amount_min)

    if amount_type == IRREGULAR:
        return centavos(0)

    if amount_type == ROLLING_AVERAGE:
        meses = list(historial)[-MESES_DE_LA_MEDIA:]
        if len(meses) < MESES_MINIMOS_PARA_MEDIA:
            return None
        return centavos(sum(meses) / Decimal(len(meses)))

    raise ValueError(f"Modo de ingreso desconocido: {amount_type!r}")
```

- [x] **Step 4: Ejecutar y verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_income.py -q`
Expected: PASS — 14 pruebas.

- [x] **Step 5: Commit**

```bash
git add apps/budget/engine/income.py tests/budget/engine/test_income.py
git commit -m "Anade los cinco modos de ingreso variable"
```

El cuerpo del mensaje: §4.1 exige la cifra conservadora, porque un hogar que presupuesta el mejor mes de un ingreso variable se endeuda en el peor. `range` devuelve el mínimo —ni el máximo ni el promedio del rango— e `irregular` devuelve cero. `rolling_average` devuelve `None` con menos de tres meses de historia, y `None` no es cero: significa "aún no hay datos", y la interfaz lo dirá con todas sus letras en vez de inventar un número que la familia creería.

---

### Task 5: `engine/cascade.py` — el reparto del sobrante

Esta tarea y la siguiente construyen la función que distingue al producto (§4.5). Nace de un ritual real: una pareja se sienta cada mes, estima el ingreso variable, agrega los gastos excepcionales, y reparte lo que sobra entre el ahorro y una mesada personal para cada uno.

**Files:**
- Create: `apps/budget/engine/cascade.py`
- Test: `tests/budget/engine/test_cascade.py`

**Interfaces:**
- Consumes: `apps.budget.engine.money.centavos`, `repartir_proporcional`
- Produce:
  - Constantes de destino `GOAL`, `ALLOWANCE`, `CATEGORY` (tupla `DESTINOS`); de método `FIXED`, `PERCENTAGE`, `REMAINDER` (tupla `METODOS`).
  - `@dataclass(frozen=True) ReglaReparto(orden, destino, metodo, importe=None, porcentaje=None, destino_id=None, miembros=(), pesos=None)`
  - `@dataclass(frozen=True) Asignacion(orden, importe, miembro_id=None)`
  - `repartir(sobrante: Decimal, reglas: Sequence[ReglaReparto]) -> list[Asignacion]`
  - La Tarea 6 añade `Ajuste` y `absorber_faltante` a este mismo módulo.

- [x] **Step 1: Escribir las pruebas que fallan**

`tests/budget/engine/test_cascade.py`:

```python
"""El reparto en cascada del sobrante (§4.5).

Cada AllocationRule tiene un destino (una meta, la mesada de los miembros, una
categoría) y un método (monto fijo, porcentaje del sobrante, o todo el resto).
Las reglas se ordenan por prioridad y el sobrante cae por ellas en cascada.
"""

from decimal import Decimal

import pytest

from apps.budget.engine.cascade import (
    ALLOWANCE,
    CATEGORY,
    FIXED,
    GOAL,
    PERCENTAGE,
    REMAINDER,
    Asignacion,
    ReglaReparto,
    repartir,
)


def _ahorro(orden=1, importe="600"):
    return ReglaReparto(orden=orden, destino=GOAL, metodo=FIXED,
                        importe=Decimal(importe), destino_id=1)


def _mesada(orden=2, miembros=(10, 20), pesos=None, metodo=REMAINDER, **kw):
    return ReglaReparto(orden=orden, destino=ALLOWANCE, metodo=metodo,
                        miembros=miembros, pesos=pesos, **kw)


# --- el ejemplo canónico del §4.5.2 -------------------------------------------


def test_el_ejemplo_canonico_del_spec():
    """(1) Ahorro familiar, monto fijo $600. (2) Mesada personal, el resto,
    repartido en partes iguales."""
    asignaciones = repartir(Decimal("800.00"), [_ahorro(), _mesada()])

    assert asignaciones == [
        Asignacion(orden=1, importe=Decimal("600.00"), miembro_id=None),
        Asignacion(orden=2, importe=Decimal("100.00"), miembro_id=10),
        Asignacion(orden=2, importe=Decimal("100.00"), miembro_id=20),
    ]


def test_la_suma_del_reparto_no_excede_nunca_el_sobrante():
    for sobrante in ["800.00", "600.00", "599.99", "0.01", "1234.56"]:
        asignaciones = repartir(Decimal(sobrante), [_ahorro(), _mesada()])
        assert sum(a.importe for a in asignaciones) <= Decimal(sobrante)


def test_con_una_regla_remainder_la_suma_es_exactamente_el_sobrante():
    for sobrante in ["800.00", "1000.03", "0.07", "1234.56"]:
        asignaciones = repartir(Decimal(sobrante), [_ahorro(), _mesada()])
        assert sum(a.importe for a in asignaciones) == Decimal(sobrante)


# --- los tres métodos ---------------------------------------------------------


def test_fixed_toma_su_monto_declarado():
    asignaciones = repartir(Decimal("1000.00"), [_ahorro(importe="600")])

    assert asignaciones == [Asignacion(1, Decimal("600.00"), None)]


def test_fixed_se_limita_a_lo_que_queda():
    """Una regla fija de $600 sobre un sobrante de $400 toma $400, no $600.
    Repartir más de lo que hay es inventar dinero."""
    asignaciones = repartir(Decimal("400.00"), [_ahorro(importe="600")])

    assert asignaciones == [Asignacion(1, Decimal("400.00"), None)]


def test_percentage_es_sobre_el_sobrante_que_entro_a_la_cascada():
    """§4.3 del diseño del Plan 2: '10% al fondo de vacaciones' significa el
    10% del sobrante, que es como lo dice una familia — no el 10% de lo que
    sobrevivió a las reglas anteriores."""
    vacaciones = ReglaReparto(orden=2, destino=CATEGORY, metodo=PERCENTAGE,
                              porcentaje=Decimal("0.10"), destino_id=5)

    asignaciones = repartir(Decimal("1000.00"), [_ahorro(importe="600"), vacaciones])

    # 10% de 1000, no 10% de los 400 que quedaban.
    assert asignaciones[1] == Asignacion(2, Decimal("100.00"), None)


def test_percentage_se_limita_a_lo_que_queda():
    grande = ReglaReparto(orden=2, destino=CATEGORY, metodo=PERCENTAGE,
                          porcentaje=Decimal("0.90"), destino_id=5)

    asignaciones = repartir(Decimal("1000.00"), [_ahorro(importe="600"), grande])

    assert asignaciones[1].importe == Decimal("400.00")


def test_remainder_toma_todo_lo_que_queda():
    resto = ReglaReparto(orden=2, destino=CATEGORY, metodo=REMAINDER, destino_id=5)

    asignaciones = repartir(Decimal("1000.00"), [_ahorro(importe="600"), resto])

    assert asignaciones[1].importe == Decimal("400.00")


# --- el orden importa ---------------------------------------------------------


def test_las_reglas_se_recorren_por_orden_y_no_por_posicion_en_la_lista():
    asignaciones = repartir(Decimal("800.00"), [_mesada(orden=2), _ahorro(orden=1)])

    assert asignaciones[0].orden == 1
    assert asignaciones[0].importe == Decimal("600.00")


def test_reordenar_las_reglas_cambia_quien_cobra_primero():
    """§4.5.3: con el ahorro arriba y las mesadas abajo, un mes flojo se come
    la diversión y no el ahorro. Una familia que prefiera lo contrario solo
    reordena las reglas."""
    ahorro_arriba = repartir(Decimal("500.00"), [_ahorro(orden=1), _mesada(orden=2)])
    mesada_arriba = repartir(
        Decimal("500.00"),
        [_mesada(orden=1, metodo=FIXED, importe=Decimal("400")), _ahorro(orden=2)],
    )

    assert ahorro_arriba[0].importe == Decimal("500.00")   # el ahorro se lleva todo
    assert mesada_arriba[-1].importe == Decimal("100.00")  # al ahorro le queda el resto


def test_una_regla_sin_nada_disponible_no_produce_asignacion():
    asignaciones = repartir(Decimal("600.00"), [_ahorro(importe="600"), _mesada()])

    assert [a.orden for a in asignaciones] == [1]


# --- la mesada ----------------------------------------------------------------


def test_la_mesada_se_reparte_entre_los_miembros():
    asignaciones = repartir(Decimal("700.00"), [_ahorro(), _mesada(miembros=(10, 20))])

    mesadas = [a for a in asignaciones if a.miembro_id is not None]
    assert [a.miembro_id for a in mesadas] == [10, 20]
    assert [a.importe for a in mesadas] == [Decimal("50.00"), Decimal("50.00")]


def test_la_mesada_cuadra_al_centavo_entre_tres_miembros():
    """El caso del spec: $100 entre tres da 33,34 / 33,33 / 33,33."""
    asignaciones = repartir(Decimal("700.00"), [_ahorro(), _mesada(miembros=(10, 20, 30))])

    mesadas = [a.importe for a in asignaciones if a.miembro_id is not None]
    assert mesadas == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum(mesadas) == Decimal("100.00")


def test_la_mesada_admite_pesos_explicitos():
    """§3.3: `split` es `equal` o pesos explícitos — $50 a cada hijo no tiene
    por qué ser lo mismo que la mitad para cada adulto."""
    regla = _mesada(miembros=(10, 20), pesos=(Decimal("3"), Decimal("1")))

    asignaciones = repartir(Decimal("700.00"), [_ahorro(), regla])

    mesadas = [a.importe for a in asignaciones if a.miembro_id is not None]
    assert mesadas == [Decimal("75.00"), Decimal("25.00")]


def test_una_mesada_sin_miembros_no_asigna_nada():
    """Un hogar cuyo único miembro se dio de baja no debe recibir una
    asignación huérfana ni dividir por cero."""
    asignaciones = repartir(Decimal("700.00"), [_ahorro(), _mesada(miembros=())])

    assert [a.orden for a in asignaciones] == [1]


# --- los bordes ---------------------------------------------------------------


def test_un_sobrante_negativo_no_reparte_nada():
    """§9: un mes deficitario no reparte nada y no genera mesada."""
    assert repartir(Decimal("-200.00"), [_ahorro(), _mesada()]) == []


def test_un_sobrante_de_cero_no_reparte_nada():
    assert repartir(Decimal("0.00"), [_ahorro(), _mesada()]) == []


def test_sin_reglas_no_reparte_nada():
    assert repartir(Decimal("800.00"), []) == []


def test_lo_que_las_reglas_no_agotan_se_queda_sin_asignar():
    """§2.7: una familia cuyas reglas reparten $600 de un sobrante de $800
    deja $200 a propósito; esos $200 se quedan en el balance y se arrastran.
    Empujarlos a la última regla sería inventarle una decisión que no tomó."""
    asignaciones = repartir(Decimal("800.00"), [_ahorro(importe="600")])

    assert sum(a.importe for a in asignaciones) == Decimal("600.00")


def test_dos_ejecuciones_dan_el_mismo_reparto():
    reglas = [_ahorro(), _mesada(miembros=(10, 20, 30))]

    assert repartir(Decimal("1000.03"), reglas) == repartir(Decimal("1000.03"), reglas)


def test_un_metodo_desconocido_revienta():
    regla = ReglaReparto(orden=1, destino=GOAL, metodo="a_ojo", destino_id=1)

    with pytest.raises(ValueError, match="Método de reparto desconocido"):
        repartir(Decimal("800.00"), [regla])
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_cascade.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.budget.engine.cascade'`

- [x] **Step 3: Implementar**

`apps/budget/engine/cascade.py`:

```python
"""El reparto en cascada del sobrante (§4.5).

La función que distingue al producto. Nace de un ritual real: una pareja se
sienta cada mes, estima el ingreso variable, agrega los gastos excepcionales,
y reparte lo que sobra entre el ahorro y una mesada personal para cada uno.
Casi ninguna aplicación de presupuesto lo modela, porque todas asumen que el
sobrante "se queda ahí".
"""

from dataclasses import dataclass
from decimal import Decimal

from .money import centavos, repartir_proporcional

GOAL = "goal"
ALLOWANCE = "allowance"
CATEGORY = "category"
DESTINOS = (GOAL, ALLOWANCE, CATEGORY)

FIXED = "fixed"
PERCENTAGE = "percentage"
REMAINDER = "remainder"
METODOS = (FIXED, PERCENTAGE, REMAINDER)


@dataclass(frozen=True)
class ReglaReparto:
    orden: int
    destino: str
    metodo: str
    importe: Decimal | None = None
    porcentaje: Decimal | None = None
    destino_id: int | None = None
    miembros: tuple = ()
    pesos: tuple | None = None


@dataclass(frozen=True)
class Asignacion:
    orden: int
    importe: Decimal
    miembro_id: int | None = None


def _bruto(regla, sobrante, disponible):
    if regla.metodo == FIXED:
        return regla.importe or Decimal("0")
    if regla.metodo == PERCENTAGE:
        return sobrante * (regla.porcentaje or Decimal("0"))
    if regla.metodo == REMAINDER:
        return disponible
    raise ValueError(f"Método de reparto desconocido: {regla.metodo!r}")


def _asignaciones_de(regla, importe):
    """Una asignación, o una por miembro si el destino es la mesada."""
    if regla.destino != ALLOWANCE:
        return [Asignacion(regla.orden, importe, None)]

    if not regla.miembros:
        return []
    pesos = regla.pesos or tuple(Decimal("1") for _ in regla.miembros)
    partes = repartir_proporcional(importe, pesos)
    return [
        Asignacion(regla.orden, parte, miembro)
        for miembro, parte in zip(regla.miembros, partes)
    ]


def repartir(sobrante, reglas):
    """Cómo cae el sobrante por las reglas, ordenadas por prioridad.

    La suma nunca excede el sobrante. Lo que las reglas no agoten se queda sin
    asignar a propósito y se arrastra en el balance (§2.7).
    """
    sobrante = centavos(sobrante)
    if sobrante <= 0:
        return []

    disponible = sobrante
    asignaciones = []

    for regla in sorted(reglas, key=lambda r: r.orden):
        if disponible <= 0:
            break
        importe = min(centavos(_bruto(regla, sobrante, disponible)), disponible)
        if importe <= 0:
            continue
        nuevas = _asignaciones_de(regla, importe)
        if not nuevas:
            # Una mesada sin miembros no consume sobrante: cae a la siguiente.
            continue
        asignaciones.extend(nuevas)
        disponible -= importe

    return asignaciones
```

- [x] **Step 4: Ejecutar y verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_cascade.py -q`
Expected: PASS — 21 pruebas.

- [x] **Step 5: Commit**

```bash
git add apps/budget/engine/cascade.py tests/budget/engine/test_cascade.py
git commit -m "Anade el reparto en cascada del sobrante"
```

Cuerpo del mensaje: la función que distingue al producto (§4.5). Tres invariantes con prueba: la suma nunca excede el sobrante; dentro de una regla de mesada las partes suman exactamente su importe; y con una regla `remainder` la suma es exactamente el sobrante. Lo que las reglas no agotan se queda sin asignar y se arrastra — empujarlo a la última regla sería inventarle a la familia una decisión que no tomó. Un sobrante negativo no reparte nada y no genera mesada.

---

### Task 6: `engine/cascade.py` — el faltante, y la mesada que no se retira

**Files:**
- Modify: `apps/budget/engine/cascade.py`
- Test: `tests/budget/engine/test_cascade.py` (añadir al final)

**Interfaces:**
- Consumes: `ReglaReparto`, `Asignacion`, `centavos`, `repartir_proporcional`
- Produce:
  - `@dataclass(frozen=True) Ajuste(miembro_id: int, importe: Decimal)` — importe negativo, se descuenta de la mesada del **mes siguiente**.
  - `absorber_faltante(planeado, reglas, sobrante_real) -> tuple[list[Asignacion], list[Ajuste]]`
  - Los usa la Tarea 13.

- [x] **Step 1: Escribir las pruebas que fallan**

Añadir al final de `tests/budget/engine/test_cascade.py` (el import va arriba, junto a los demás):

```python
# --- el faltante (§4.5.3) -----------------------------------------------------


def test_el_ejemplo_literal_del_spec_4_5_3():
    """Sobrante proyectado $800 → $600 al ahorro, $100 a cada uno. Sobrante
    real $720. El ahorro recibe sus $600 íntegros; el faltante de $80 se
    descuenta de las mesadas de octubre, $40 a cada uno. Nadie pierde dinero
    que ya gastó."""
    reglas = [_ahorro(), _mesada(miembros=(10, 20))]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("720.00"))

    assert final == planeado, "la mesada ya asignada NUNCA se retira"
    assert ajustes == [
        Ajuste(miembro_id=10, importe=Decimal("-40.00")),
        Ajuste(miembro_id=20, importe=Decimal("-40.00")),
    ]


def test_sin_faltante_no_hay_ni_ajustes_ni_cambios():
    reglas = [_ahorro(), _mesada()]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("800.00"))

    assert final == planeado
    assert ajustes == []


def test_un_sobrante_real_mayor_al_proyectado_no_cambia_nada():
    """El exceso es superávit y se arrastra; no se reparte retroactivamente."""
    reglas = [_ahorro(), _mesada()]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("900.00"))

    assert final == planeado
    assert ajustes == []


def test_el_faltante_se_absorbe_desde_la_ultima_regla_hacia_arriba():
    """Con una categoría abajo (que sí se puede reducir), el ahorro de arriba
    queda intacto."""
    fondo = ReglaReparto(orden=2, destino=CATEGORY, metodo=REMAINDER, destino_id=5)
    reglas = [_ahorro(importe="600"), fondo]
    planeado = repartir(Decimal("800.00"), reglas)   # 600 + 200

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("700.00"))

    assert final == [
        Asignacion(1, Decimal("600.00"), None),
        Asignacion(2, Decimal("100.00"), None),
    ]
    assert ajustes == []


def test_si_la_ultima_no_alcanza_el_faltante_sube_a_la_penultima():
    fondo = ReglaReparto(orden=2, destino=CATEGORY, metodo=REMAINDER, destino_id=5)
    reglas = [_ahorro(importe="600"), fondo]
    planeado = repartir(Decimal("800.00"), reglas)   # 600 + 200

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("500.00"))

    # Faltan 300: la regla 2 aporta sus 200 y la regla 1 los 100 restantes.
    assert final == [Asignacion(1, Decimal("500.00"), None)]
    assert ajustes == []


def test_una_regla_reducida_a_cero_desaparece_del_reparto():
    fondo = ReglaReparto(orden=2, destino=CATEGORY, metodo=REMAINDER, destino_id=5)
    reglas = [_ahorro(importe="600"), fondo]
    planeado = repartir(Decimal("800.00"), reglas)

    final, _ = absorber_faltante(planeado, reglas, Decimal("600.00"))

    assert [a.orden for a in final] == [1]


def test_la_mesada_nunca_se_reduce_aunque_el_faltante_la_supere():
    """De nada sirve enterarse el día 30 de que tenías $100 para gastar."""
    reglas = [_ahorro(importe="600"), _mesada(miembros=(10, 20))]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("400.00"))

    mesadas = [a for a in final if a.miembro_id is not None]
    assert [a.importe for a in mesadas] == [Decimal("100.00"), Decimal("100.00")]
    # Faltan 400: la mesada aporta sus 200 como ajuste, el ahorro los otros 200.
    assert sum(a.importe for a in ajustes) == Decimal("-200.00")
    assert [a for a in final if a.miembro_id is None] == [
        Asignacion(1, Decimal("400.00"), None)
    ]


def test_los_ajustes_se_reparten_en_la_misma_proporcion_que_la_mesada():
    regla = _mesada(miembros=(10, 20), pesos=(Decimal("3"), Decimal("1")))
    reglas = [_ahorro(importe="600"), regla]
    planeado = repartir(Decimal("800.00"), reglas)   # mesada 150 / 50

    _, ajustes = absorber_faltante(planeado, reglas, Decimal("720.00"))

    assert ajustes == [
        Ajuste(miembro_id=10, importe=Decimal("-60.00")),
        Ajuste(miembro_id=20, importe=Decimal("-20.00")),
    ]


def test_los_ajustes_suman_exactamente_el_faltante_de_la_mesada():
    regla = _mesada(miembros=(10, 20, 30))
    reglas = [_ahorro(importe="600"), regla]
    planeado = repartir(Decimal("800.00"), reglas)

    _, ajustes = absorber_faltante(planeado, reglas, Decimal("799.99"))

    assert sum(a.importe for a in ajustes) == Decimal("-0.01")


def test_un_sobrante_real_negativo_deja_la_mesada_y_vacia_el_resto():
    reglas = [_ahorro(importe="600"), _mesada(miembros=(10, 20))]
    planeado = repartir(Decimal("800.00"), reglas)

    final, ajustes = absorber_faltante(planeado, reglas, Decimal("-50.00"))

    assert [a for a in final if a.miembro_id is None] == []
    assert sum(a.importe for a in ajustes) == Decimal("-200.00")
```

Y añadir `Ajuste` y `absorber_faltante` al bloque de imports del principio del archivo.

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_cascade.py -q`
Expected: FAIL — `ImportError: cannot import name 'Ajuste' from 'apps.budget.engine.cascade'`

- [x] **Step 3: Implementar**

Añadir a `apps/budget/engine/cascade.py`:

```python
@dataclass(frozen=True)
class Ajuste:
    """Lo que se descuenta de la mesada del MES SIGUIENTE. Siempre negativo."""

    miembro_id: int
    importe: Decimal


def absorber_faltante(planeado, reglas, sobrante_real):
    """Reparte el faltante cuando el sobrante real queda bajo el proyectado.

    §4.5.3. Pasa constantemente: un ingreso por horas cierra por debajo de lo
    estimado. El faltante lo absorbe la última regla de la cascada, y si no
    alcanza, la penúltima — eso es lo que significa una cascada, y hace que el
    orden importe de verdad: con el ahorro arriba y las mesadas abajo, un mes
    flojo se come la diversión y no el ahorro.

    PERO LA MESADA YA ASIGNADA NUNCA SE RETIRA. Se fija al planificar y no se
    mueve durante el mes: de nada sirve enterarse el día 30 de que tenías $100
    para gastar. Su parte del faltante vuelve como Ajuste negativo, que
    services.py escribe en el AllowanceLedger del mes siguiente.

    Devuelve (asignaciones finales, ajustes para el mes siguiente).
    """
    planeado = list(planeado)
    faltante = sum(a.importe for a in planeado) - centavos(sobrante_real)
    if faltante <= 0:
        return planeado, []

    por_orden = {regla.orden: regla for regla in reglas}
    restante = faltante
    ajustes = []
    reducciones = {}

    # De la última regla hacia arriba.
    for orden in sorted({a.orden for a in planeado}, reverse=True):
        if restante <= 0:
            break
        del_orden = [a for a in planeado if a.orden == orden]
        disponible = sum(a.importe for a in del_orden)
        quita = min(restante, disponible)
        if quita <= 0:
            continue

        if por_orden[orden].destino == ALLOWANCE:
            # No se retira: se convierte en ajuste del mes siguiente, repartido
            # entre los miembros en la misma proporción en que cobraron.
            partes = repartir_proporcional(-quita, [a.importe for a in del_orden])
            ajustes.extend(
                Ajuste(miembro_id=a.miembro_id, importe=parte)
                for a, parte in zip(del_orden, partes)
            )
        else:
            reducciones[orden] = quita
        restante -= quita

    finales = []
    for asignacion in planeado:
        quita = reducciones.get(asignacion.orden)
        if quita is None:
            finales.append(asignacion)
            continue
        nuevo = centavos(asignacion.importe - quita)
        if nuevo > 0:
            finales.append(Asignacion(asignacion.orden, nuevo, asignacion.miembro_id))

    return finales, ajustes
```

- [x] **Step 4: Ejecutar y verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_cascade.py -q`
Expected: PASS — 31 pruebas.

- [x] **Step 5: Commit**

```bash
git add apps/budget/engine/cascade.py tests/budget/engine/test_cascade.py
git commit -m "Absorbe el faltante desde la ultima regla, sin tocar la mesada"
```

Cuerpo: §4.5.3, la parte delicada del §4.5. El ejemplo literal del spec es una prueba: $800 proyectado, $720 real, el ahorro conserva sus $600 íntegros y las mesadas del mes siguiente bajan $40 cada una. Nadie pierde dinero que ya gastó.

---

### Task 7: `engine/closing.py` y `engine/allowance.py` — el cierre y el libro mayor

**Files:**
- Create: `apps/budget/engine/closing.py`, `apps/budget/engine/allowance.py`
- Test: `tests/budget/engine/test_closing.py`, `tests/budget/engine/test_allowance.py`

**Interfaces:**
- Consumes: `apps.budget.engine.money.centavos`
- Produce:
  - `@dataclass(frozen=True) Renglon(categoria_id: int, kind: str, presupuestado: Decimal, real: Decimal)`
  - `@dataclass(frozen=True) Cierre(ingresos_presupuestados, ingresos_reales, egresos_presupuestados, egresos_reales, varianza_por_categoria: dict[int, Decimal], balance, arrastre)`
  - `cerrar(renglones: Sequence[Renglon], saldo_arrastrado: Decimal) -> Cierre`
  - `saldo(carried_in, granted, adjustment, spent) -> Decimal`
  - `carried_out(saldo_del_mes: Decimal, rollover: bool) -> Decimal`
  - Los usa la Tarea 12.

- [x] **Step 1: Escribir las pruebas del cierre**

`tests/budget/engine/test_closing.py`:

```python
"""El cierre del mes y el arrastre del saldo (§4.4).

El balance de un mes es: saldo arrastrado del cierre anterior + ingresos
reales − egresos reales. El superávit o déficit se arrastra al mes siguiente
al cerrar.
"""

from decimal import Decimal

from apps.budget.engine.closing import Cierre, Renglon, cerrar

INGRESO, GASTO = "income", "expense"


def _renglones():
    return [
        Renglon(1, INGRESO, Decimal("3000.00"), Decimal("3200.00")),
        Renglon(2, GASTO, Decimal("1800.00"), Decimal("1800.00")),
        Renglon(3, GASTO, Decimal("400.00"), Decimal("520.00")),
    ]


def test_los_cuatro_totales():
    cierre = cerrar(_renglones(), Decimal("0.00"))

    assert cierre.ingresos_presupuestados == Decimal("3000.00")
    assert cierre.ingresos_reales == Decimal("3200.00")
    assert cierre.egresos_presupuestados == Decimal("2200.00")
    assert cierre.egresos_reales == Decimal("2320.00")


def test_el_balance_es_arrastrado_mas_ingresos_reales_menos_egresos_reales():
    cierre = cerrar(_renglones(), Decimal("150.00"))

    assert cierre.balance == Decimal("1030.00")


def test_el_balance_del_mes_es_el_arrastre_del_siguiente():
    cierre = cerrar(_renglones(), Decimal("150.00"))

    assert cierre.arrastre == cierre.balance


def test_un_deficit_se_arrastra_igual_que_un_superavit():
    """§4.4 no distingue: el déficit también viaja al mes siguiente. Ocultarlo
    haría que un mes malo desapareciera del historial."""
    renglones = [Renglon(1, GASTO, Decimal("100.00"), Decimal("900.00"))]

    cierre = cerrar(renglones, Decimal("0.00"))

    assert cierre.balance == Decimal("-900.00")
    assert cierre.arrastre == Decimal("-900.00")


def test_el_arrastre_entre_cierres_consecutivos_cuadra_al_centavo():
    """§9: la prueba que el spec exige explícitamente. Tres meses seguidos,
    con importes que no dividen redondo."""
    mes1 = cerrar([Renglon(1, INGRESO, Decimal("1000.00"), Decimal("1000.03"))],
                  Decimal("0.00"))
    mes2 = cerrar([Renglon(2, GASTO, Decimal("300.00"), Decimal("333.34"))],
                  mes1.arrastre)
    mes3 = cerrar([Renglon(1, INGRESO, Decimal("500.00"), Decimal("500.00"))],
                  mes2.arrastre)

    assert mes1.arrastre == Decimal("1000.03")
    assert mes2.arrastre == Decimal("666.69")
    assert mes3.arrastre == Decimal("1166.69")


def test_la_varianza_por_categoria_es_real_menos_presupuestado():
    """Signo: en ingresos, positivo es haber ganado más; en gastos, positivo
    es haber gastado más. Es el mismo cálculo y la interfaz lo colorea según
    el kind."""
    cierre = cerrar(_renglones(), Decimal("0.00"))

    assert cierre.varianza_por_categoria == {
        1: Decimal("200.00"),
        2: Decimal("0.00"),
        3: Decimal("120.00"),
    }


def test_dos_renglones_de_la_misma_categoria_se_suman():
    renglones = [
        Renglon(7, GASTO, Decimal("100.00"), Decimal("110.00")),
        Renglon(7, GASTO, Decimal("50.00"), Decimal("45.00")),
    ]

    cierre = cerrar(renglones, Decimal("0.00"))

    assert cierre.varianza_por_categoria == {7: Decimal("5.00")}
    assert cierre.egresos_reales == Decimal("155.00")


def test_un_mes_sin_movimiento_arrastra_lo_que_recibio():
    cierre = cerrar([], Decimal("42.00"))

    assert cierre.balance == Decimal("42.00")
    assert cierre.arrastre == Decimal("42.00")
    assert cierre.varianza_por_categoria == {}


def test_el_ingreso_en_modo_range_deja_su_exceso_como_superavit():
    """§13.4: un ingreso `range` presupuesta el mínimo y el exceso aparece
    como superávit al cierre."""
    renglones = [Renglon(1, INGRESO, Decimal("800.00"), Decimal("2400.00"))]

    cierre = cerrar(renglones, Decimal("0.00"))

    assert cierre.balance == Decimal("2400.00")
    assert cierre.varianza_por_categoria[1] == Decimal("1600.00")
```

- [x] **Step 2: Escribir las pruebas del libro mayor**

`tests/budget/engine/test_allowance.py`:

```python
"""El libro mayor de la mesada (§3.3, §4.5.4).

Es un libro mayor, no un campo mutable: cada mes es una fila y el saldo se
deriva sumando. Así "¿por qué tengo $145 este mes?" siempre tiene respuesta.
"""

from decimal import Decimal

from apps.budget.engine.allowance import carried_out, saldo


def test_el_saldo_es_la_suma_del_libro():
    assert saldo(
        carried_in=Decimal("45.00"),
        granted=Decimal("100.00"),
        adjustment=Decimal("0.00"),
        spent=Decimal("30.00"),
    ) == Decimal("115.00")


def test_el_ajuste_negativo_del_mes_anterior_baja_el_saldo():
    """El faltante del §4.5.3 llega aquí: $40 menos en octubre."""
    assert saldo(
        carried_in=Decimal("0.00"),
        granted=Decimal("100.00"),
        adjustment=Decimal("-40.00"),
        spent=Decimal("0.00"),
    ) == Decimal("60.00")


def test_gastar_mas_que_la_mesada_deja_saldo_negativo():
    """No se impide gastar de más: se registra. Bloquear una compra ya hecha
    no la deshace, y un saldo negativo es información."""
    assert saldo(
        carried_in=Decimal("0.00"),
        granted=Decimal("100.00"),
        adjustment=Decimal("0.00"),
        spent=Decimal("130.00"),
    ) == Decimal("-30.00")


def test_con_acumulacion_activada_el_saldo_viaja_al_mes_siguiente():
    """§4.5.4, activada por defecto: guardar $100 durante tres meses para
    comprar algo de $300 es lo que hace que se sienta dinero propio y no una
    asignación que caduca."""
    assert carried_out(Decimal("70.00"), rollover=True) == Decimal("70.00")


def test_con_acumulacion_desactivada_lo_no_gastado_vuelve_al_hogar():
    assert carried_out(Decimal("70.00"), rollover=False) == Decimal("0.00")


def test_un_saldo_negativo_viaja_aunque_la_acumulacion_este_desactivada():
    """Una deuda no se perdona por apagar una opción: quien gastó de más lo
    arrastra igual, o la opción sería una forma de gastar gratis."""
    assert carried_out(Decimal("-30.00"), rollover=False) == Decimal("-30.00")
    assert carried_out(Decimal("-30.00"), rollover=True) == Decimal("-30.00")


def test_el_acumulado_cuadra_al_centavo_a_lo_largo_de_varios_meses():
    """§9: la prueba que el spec exige. Tres meses con acumulación."""
    entra = Decimal("0.00")
    for gastado in [Decimal("30.00"), Decimal("0.00"), Decimal("45.50")]:
        s = saldo(entra, Decimal("100.00"), Decimal("0.00"), gastado)
        entra = carried_out(s, rollover=True)

    # 100-30 = 70; 70+100 = 170; 170+100-45,50 = 224,50
    assert entra == Decimal("224.50")


def test_el_acumulado_sin_acumulacion_no_pasa_de_la_mesada_del_mes():
    entra = Decimal("0.00")
    for gastado in [Decimal("30.00"), Decimal("0.00"), Decimal("45.50")]:
        s = saldo(entra, Decimal("100.00"), Decimal("0.00"), gastado)
        entra = carried_out(s, rollover=False)

    assert entra == Decimal("0.00")
```

- [x] **Step 3: Ejecutar y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_closing.py tests/budget/engine/test_allowance.py -q`
Expected: FAIL — `ModuleNotFoundError` para los dos módulos.

- [x] **Step 4: Implementar el cierre**

`apps/budget/engine/closing.py`:

```python
"""El cierre del mes y el arrastre del saldo (§4.4)."""

from dataclasses import dataclass
from decimal import Decimal

from .money import centavos

INGRESO = "income"
GASTO = "expense"


@dataclass(frozen=True)
class Renglon:
    categoria_id: int
    kind: str
    presupuestado: Decimal
    real: Decimal


@dataclass(frozen=True)
class Cierre:
    ingresos_presupuestados: Decimal
    ingresos_reales: Decimal
    egresos_presupuestados: Decimal
    egresos_reales: Decimal
    varianza_por_categoria: dict
    balance: Decimal
    arrastre: Decimal


def _total(renglones, kind, campo):
    return centavos(sum(getattr(r, campo) for r in renglones if r.kind == kind))


def cerrar(renglones, saldo_arrastrado):
    """La foto congelada de un mes.

    §4.4: balance = saldo arrastrado + ingresos reales − egresos reales, y ese
    balance es el arrastre del mes siguiente. El déficit se arrastra igual que
    el superávit: ocultarlo haría que un mes malo desapareciera del historial.
    """
    renglones = list(renglones)

    ingresos_reales = _total(renglones, INGRESO, "real")
    egresos_reales = _total(renglones, GASTO, "real")

    varianza = {}
    for renglon in renglones:
        acumulado = varianza.get(renglon.categoria_id, Decimal("0"))
        varianza[renglon.categoria_id] = acumulado + (renglon.real - renglon.presupuestado)
    varianza = {cat: centavos(v) for cat, v in varianza.items()}

    balance = centavos(centavos(saldo_arrastrado) + ingresos_reales - egresos_reales)

    return Cierre(
        ingresos_presupuestados=_total(renglones, INGRESO, "presupuestado"),
        ingresos_reales=ingresos_reales,
        egresos_presupuestados=_total(renglones, GASTO, "presupuestado"),
        egresos_reales=egresos_reales,
        varianza_por_categoria=varianza,
        balance=balance,
        arrastre=balance,
    )
```

- [x] **Step 5: Implementar el libro mayor**

`apps/budget/engine/allowance.py`:

```python
"""El libro mayor de la mesada (§3.3, §4.5.4).

Cada mes es una fila y el saldo se deriva sumando, no un campo que se
sobrescribe. Así "¿por qué tengo $145 este mes?" siempre tiene respuesta.
"""

from decimal import Decimal

from .money import centavos


def saldo(carried_in, granted, adjustment, spent):
    """Lo que este miembro tiene disponible este mes."""
    return centavos(
        centavos(carried_in) + centavos(granted) + centavos(adjustment) - centavos(spent)
    )


def carried_out(saldo_del_mes, rollover):
    """Lo que viaja al mes siguiente al cerrar.

    §4.5.4: con la acumulación activada (por defecto) el saldo no gastado se
    acumula — guardar $100 durante tres meses para comprar algo de $300 es lo
    que hace que se sienta dinero propio y no una asignación que caduca. Con
    la opción desactivada, lo no gastado vuelve al hogar.

    Un saldo NEGATIVO viaja siempre, con acumulación o sin ella: una deuda no
    se perdona por apagar una opción, o desactivarla sería una forma de gastar
    gratis.
    """
    saldo_del_mes = centavos(saldo_del_mes)
    if saldo_del_mes < 0:
        return saldo_del_mes
    return saldo_del_mes if rollover else Decimal("0.00")
```

- [x] **Step 6: Ejecutar y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS — todo el motor, en menos de dos segundos.

- [x] **Step 7: Commit**

```bash
git add apps/budget/engine/closing.py apps/budget/engine/allowance.py \
        tests/budget/engine/test_closing.py tests/budget/engine/test_allowance.py
git commit -m "Anade el cierre del mes y el libro mayor de la mesada"
```

Cuerpo: §4.4 y §4.5.4. Dos pruebas que el §9 exige por su nombre: el arrastre entre cierres consecutivos cuadra al centavo, y el acumulado de mesada cuadra al centavo a lo largo de varios meses con la acumulación activada y desactivada. Un saldo negativo de mesada viaja al mes siguiente aunque la acumulación esté desactivada: una deuda no se perdona por apagar una opción.

---

### Task 8: `engine/goals.py` y `engine/merchants.py`

**Files:**
- Create: `apps/budget/engine/goals.py`, `apps/budget/engine/merchants.py`
- Test: `tests/budget/engine/test_goals_engine.py`, `tests/budget/engine/test_merchants.py`

**Interfaces:**
- Consumes: `apps.budget.engine.money.centavos`
- Produce:
  - `BY_TARGET_DATE = "by_target_date"`, `BY_MONTHLY_AMOUNT = "by_monthly_amount"`, `MODOS_DE_META`
  - `derivar(modo, objetivo, acumulado, desde, fecha_objetivo=None, aporte_mensual=None) -> tuple[Decimal, date]` — devuelve `(aporte_mensual, fecha_de_llegada)`.
  - `normalizar(nombre: str) -> str`
  - Los usan las Tareas 11 y 16.

- [x] **Step 1: Escribir las pruebas de las metas**

`tests/budget/engine/test_goals_engine.py`:

```python
"""Las dos formas de expresar una meta (§3.3).

Son la misma cosa vista al revés: el usuario da dos datos y la aplicación
deriva el tercero. Ambas formas deben existir, porque las familias piensan de
las dos maneras.

El tercer dato NUNCA se guarda: se deriva al mostrarlo, o quedaría obsoleto en
cuanto cambie el acumulado.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget.engine.goals import BY_MONTHLY_AMOUNT, BY_TARGET_DATE, derivar


def test_por_fecha_objetivo_deriva_el_aporte_mensual():
    """"$7.200 para el 30 de junio de 2027", desde septiembre de 2026: son
    diez meses contando septiembre y junio, así que $720 al mes."""
    aporte, fecha = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("7200.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 9, 3),
        fecha_objetivo=date(2027, 6, 30),
    )

    assert aporte == Decimal("720.00")
    assert fecha == date(2027, 6, 30)


def test_por_fecha_objetivo_descuenta_lo_ya_acumulado():
    aporte, _ = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("7200.00"),
        acumulado=Decimal("2200.00"),
        desde=date(2026, 9, 3),
        fecha_objetivo=date(2027, 6, 30),
    )

    assert aporte == Decimal("500.00")


def test_por_fecha_objetivo_redondea_hacia_arriba_al_centavo():
    """$1.000 en tres meses: 333,34 y no 333,33, o el último mes falta un
    centavo y la meta no se alcanza en su fecha."""
    aporte, _ = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("1000.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 1, 1),
        fecha_objetivo=date(2026, 3, 31),
    )

    assert aporte == Decimal("333.34")


def test_por_monto_mensual_deriva_la_fecha_de_llegada():
    """"$600 cada mes" sobre $7.200: doce meses."""
    aporte, fecha = derivar(
        BY_MONTHLY_AMOUNT,
        objetivo=Decimal("7200.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 9, 1),
        aporte_mensual=Decimal("600.00"),
    )

    assert aporte == Decimal("600.00")
    assert fecha == date(2027, 8, 1)


def test_por_monto_mensual_redondea_hacia_arriba_los_meses():
    """$1.000 a $300 al mes son cuatro meses, no tres y un tercio."""
    _, fecha = derivar(
        BY_MONTHLY_AMOUNT,
        objetivo=Decimal("1000.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 1, 1),
        aporte_mensual=Decimal("300.00"),
    )

    assert fecha == date(2026, 4, 1)


def test_una_meta_ya_alcanzada_no_pide_mas_aportes():
    aporte, fecha = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("1000.00"),
        acumulado=Decimal("1000.00"),
        desde=date(2026, 1, 1),
        fecha_objetivo=date(2026, 6, 30),
    )

    assert aporte == Decimal("0.00")
    assert fecha == date(2026, 1, 1)


def test_una_fecha_objetivo_ya_pasada_pide_todo_de_una_vez():
    """No se divide entre cero meses ni se inventa un plazo: lo que falta se
    pide ahora, que es la verdad."""
    aporte, _ = derivar(
        BY_TARGET_DATE,
        objetivo=Decimal("1000.00"),
        acumulado=Decimal("0.00"),
        desde=date(2026, 6, 1),
        fecha_objetivo=date(2026, 1, 1),
    )

    assert aporte == Decimal("1000.00")


def test_un_aporte_mensual_de_cero_revienta():
    with pytest.raises(ValueError):
        derivar(
            BY_MONTHLY_AMOUNT,
            objetivo=Decimal("1000.00"),
            acumulado=Decimal("0.00"),
            desde=date(2026, 1, 1),
            aporte_mensual=Decimal("0.00"),
        )


def test_un_modo_desconocido_revienta():
    with pytest.raises(ValueError, match="Modo de meta desconocido"):
        derivar("algun_dia", objetivo=Decimal("1"), acumulado=Decimal("0"),
                desde=date(2026, 1, 1))
```

- [x] **Step 2: Escribir las pruebas de la normalización**

`tests/budget/engine/test_merchants.py`:

```python
"""Normalización de nombres de comercio (§3.3).

Es la base de las consultas tipo "¿cuánto gastamos en Walmart este año?" que
llegan en la Fase 2.

LÍMITE CONOCIDO, documentado aquí para que nadie confíe de más: la
normalización unifica variantes del MISMO nombre —mayúsculas, puntuación,
número de sucursal— pero no puede unificar nombres distintos. "WALMART #3421"
y "Walmart Supercentre" siguen siendo dos comercios: fundirlos exige una
acción del usuario, que llega con los reportes de la Fase 2. El ejemplo del
§3.3 promete más de lo que la normalización sola puede dar.
"""

from apps.budget.engine.merchants import normalizar


def test_pone_en_mayusculas():
    assert normalizar("walmart") == "WALMART"


def test_quita_el_numero_de_sucursal():
    assert normalizar("WALMART #3421") == "WALMART"
    assert normalizar("Metro #14") == "METRO"


def test_unifica_las_variantes_del_mismo_nombre():
    assert normalizar("WALMART #3421") == normalizar("walmart")
    assert normalizar("  Tim Hortons  ") == normalizar("TIM HORTONS")


def test_quita_la_puntuacion():
    assert normalizar("Couche-Tard") == "COUCHE TARD"
    assert normalizar("A&W") == "A W"


def test_colapsa_los_espacios():
    assert normalizar("SUPER   C") == "SUPER C"


def test_quita_los_acentos():
    """fr-CA: 'Métro' y 'Metro' son el mismo comercio."""
    assert normalizar("Métro") == "METRO"


def test_no_funde_nombres_distintos():
    """El límite documentado arriba, fijado como prueba para que nadie lo
    'arregle' con heurísticas que fundirían comercios de verdad distintos."""
    assert normalizar("WALMART #3421") != normalizar("Walmart Supercentre")


def test_un_nombre_vacio_da_cadena_vacia():
    assert normalizar("") == ""
    assert normalizar("   ") == ""
```

- [x] **Step 3: Ejecutar y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/engine/test_goals_engine.py tests/budget/engine/test_merchants.py -q`
Expected: FAIL — `ModuleNotFoundError` para los dos módulos.

- [x] **Step 4: Implementar las metas**

`apps/budget/engine/goals.py`:

```python
"""Las dos formas de expresar una meta (§3.3).

Son la misma cosa vista al revés: el usuario da dos datos y la aplicación
deriva el tercero. Ambas formas deben existir, porque las familias piensan de
las dos maneras.
"""

import calendar
from datetime import date
from decimal import ROUND_CEILING, Decimal

from .money import DOS_DECIMALES, centavos

BY_TARGET_DATE = "by_target_date"
BY_MONTHLY_AMOUNT = "by_monthly_amount"
MODOS_DE_META = (BY_TARGET_DATE, BY_MONTHLY_AMOUNT)


def _meses_hasta(desde, hasta):
    """Cuántos aportes caben entre las dos fechas, contando ambos meses."""
    meses = (hasta.year - desde.year) * 12 + (hasta.month - desde.month) + 1
    return max(meses, 1)


def _sumar_meses(origen, meses):
    total = origen.month - 1 + meses
    anio = origen.year + total // 12
    mes = total % 12 + 1
    return date(anio, mes, min(origen.day, calendar.monthrange(anio, mes)[1]))


def derivar(modo, objetivo, acumulado, desde, fecha_objetivo=None, aporte_mensual=None):
    """Devuelve (aporte mensual, fecha de llegada).

    El tercer dato nunca se guarda: se deriva al mostrarlo, o quedaría
    obsoleto en cuanto cambie el acumulado.
    """
    falta = centavos(objetivo) - centavos(acumulado)
    if falta <= 0:
        return Decimal("0.00"), desde

    if modo == BY_TARGET_DATE:
        if fecha_objetivo is None:
            raise ValueError("Una meta by_target_date necesita `fecha_objetivo`.")
        if fecha_objetivo < desde:
            # No se divide entre cero meses ni se inventa un plazo: lo que
            # falta se pide ahora, que es la verdad.
            return falta, fecha_objetivo
        meses = _meses_hasta(desde, fecha_objetivo)
        # Hacia arriba: 333,33 tres veces deja un centavo sin ahorrar y la
        # meta no se alcanza en su fecha.
        aporte = (falta / meses).quantize(DOS_DECIMALES, rounding=ROUND_CEILING)
        return aporte, fecha_objetivo

    if modo == BY_MONTHLY_AMOUNT:
        if not aporte_mensual or centavos(aporte_mensual) <= 0:
            raise ValueError("Una meta by_monthly_amount necesita un aporte positivo.")
        aporte = centavos(aporte_mensual)
        meses = int((falta / aporte).to_integral_value(rounding=ROUND_CEILING))
        return aporte, _sumar_meses(desde, meses - 1)

    raise ValueError(f"Modo de meta desconocido: {modo!r}")
```

- [x] **Step 5: Implementar la normalización**

`apps/budget/engine/merchants.py`:

```python
"""Normalización de nombres de comercio (§3.3).

Unifica las variantes del MISMO nombre —mayúsculas, acentos, puntuación,
número de sucursal— para que `WALMART #3421` y `walmart` sean el mismo
comercio. Es la base de las consultas tipo "¿cuánto gastamos en Walmart este
año?" que llegan en la Fase 2.

Lo que NO hace, y conviene saberlo: no funde nombres distintos.
"Walmart Supercentre" sigue siendo otro comercio. Fundirlos exige una acción
del usuario, que llega con los reportes de la Fase 2 — el ejemplo del §3.3
promete más de lo que la normalización sola puede dar. Añadir heurísticas de
sufijos aquí fundiría comercios de verdad distintos, que es un error peor.
"""

import re
import unicodedata

_SUCURSAL = re.compile(r"#\s*\d+")
_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]+")


def normalizar(nombre):
    if not nombre:
        return ""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c)
    )
    sin_sucursal = _SUCURSAL.sub(" ", sin_acentos.upper())
    return _NO_ALFANUMERICO.sub(" ", sin_sucursal).strip()
```

- [x] **Step 6: Ejecutar y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget -q`
Expected: PASS — el motor completo.

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — la suite entera.

- [x] **Step 7: Commit**

```bash
git add apps/budget/engine/goals.py apps/budget/engine/merchants.py \
        tests/budget/engine/test_goals_engine.py tests/budget/engine/test_merchants.py
git commit -m "Anade la derivacion de metas y la normalizacion de comercios"
```

Cuerpo: las dos formas de expresar una meta son la misma vista al revés y el tercer dato nunca se guarda —quedaría obsoleto en cuanto cambie el acumulado—. El aporte por fecha redondea hacia arriba: 333,33 tres veces deja un centavo sin ahorrar y la meta no llega en su fecha. La normalización de comercios documenta su límite con una prueba: unifica variantes del mismo nombre, no funde nombres distintos, y el ejemplo del §3.3 promete más de lo que puede dar.

---

**PUNTO DE CONTROL 1 — el motor está completo.** Todas las pruebas del §9 que son aritmética están en verde y corren en menos de dos segundos sin tocar Postgres. Lo que sigue lo persiste.

---

### Task 9: Modelos, tanda 1 — el catálogo y las reglas

**Files:**
- Create: `apps/budget/models/catalog.py`, `apps/budget/models/rules.py`, `apps/budget/models/__init__.py` (contenido), `apps/budget/seeds.py`, `tests/factories_budget.py`
- Modify: `apps/households/services.py` (sembrar el árbol al crear el hogar)
- Test: `tests/budget/test_models.py`

**Interfaces:**
- Consumes: `apps.core.fields.MoneyField`, `apps.households.scoping.HouseholdScoped`, `apps.budget.engine.periodicity.PERIODICIDADES`, `apps.budget.engine.income.MODOS`, `apps.budget.engine.merchants.normalizar`, `tests.factories.HouseholdScopedFactory`
- Produce:
  - `Category(household, slug, name, is_system, parent, kind, tax_category)` con `etiqueta()` que devuelve `name` o el `slug` traducido.
  - `Merchant(household, name, normalized_name)`; `normalized_name` se calcula en `save()`.
  - `IncomeSource(household, owner, name, source_type, amount_type, amount, amount_min, amount_max, periodicity, effective_from, effective_to, scope)` con `cifra_del_mes(historial)`.
  - `ExpenseRule(household, category, name, amount, periodicity, effective_from, effective_to, is_essential, owner, scope)` con `importe_del_mes(anio, mes)`.
  - `PERIODICITY_CHOICES`, `AMOUNT_TYPE_CHOICES`, `SOURCE_TYPE_CHOICES`, `SCOPE_CHOICES`, `KIND_CHOICES` — las etiquetas traducibles.
  - `seeds.ARBOL` y `seeds.sembrar(hogar)`.
  - `CategoryFactory`, `MerchantFactory`, `IncomeSourceFactory`, `ExpenseRuleFactory`.

- [x] **Step 1: Escribir las pruebas que fallan**

`tests/budget/test_models.py`:

```python
"""Los modelos del motor: lo que garantizan por sí solos."""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget.engine.income import RANGE, ROLLING_AVERAGE
from apps.budget.engine.periodicity import BIWEEKLY, MONTHLY
from apps.budget.models import Category, ExpenseRule, IncomeSource, Merchant
from apps.budget.seeds import ARBOL, sembrar
from apps.households.services import crear_hogar
from tests.factories import HouseholdFactory, MembershipFactory, UserFactory
from tests.factories_budget import (
    CategoryFactory,
    ExpenseRuleFactory,
    IncomeSourceFactory,
    MerchantFactory,
)

pytestmark = pytest.mark.django_db


# --- la barrera sigue puesta --------------------------------------------------


def test_ningun_modelo_del_motor_se_consulta_sin_hogar():
    """La barrera del lote de puertas aplica igual a los modelos nuevos."""
    for modelo in (Category, Merchant, IncomeSource, ExpenseRule):
        with pytest.raises(RuntimeError):
            list(modelo.objects.all())


def test_for_household_acota_cada_modelo():
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    CategoryFactory(household=thompson, slug="rent")
    CategoryFactory(household=garcia, slug="rent")

    assert Category.objects.for_household(thompson).count() == 1


# --- Category -----------------------------------------------------------------


def test_crear_un_hogar_siembra_el_arbol_de_categorias():
    """Desviación 1 del diseño: las categorías del sistema se copian por
    hogar, porque HouseholdScoped.household no admite nulo y ablandarlo
    destriparía la barrera."""
    hogar = crear_hogar(UserFactory(), "Family Thompson", family_size=4)

    sembradas = Category.objects.for_household(hogar)
    assert sembradas.count() == len(ARBOL)
    assert sembradas.filter(is_system=True).count() == len(ARBOL)


def test_el_arbol_sembrado_tiene_los_padres_del_spec():
    hogar = crear_hogar(UserFactory(), "Family Thompson", family_size=4)

    alquiler = Category.objects.for_household(hogar).get(slug="rent")
    assert alquiler.parent.slug == "housing"


def test_una_categoria_del_sistema_se_muestra_desde_su_slug():
    """Se muestra traducida mientras `name` esté vacío."""
    hogar = HouseholdFactory()
    sembrar(hogar)

    alquiler = Category.objects.for_household(hogar).get(slug="rent")
    assert alquiler.name == ""
    assert alquiler.etiqueta() == "Rent"


def test_renombrar_una_categoria_del_sistema_solo_escribe_name():
    """§3.2: 'el hogar puede añadir y renombrar'. Con el árbol sembrado por
    hogar eso es cierto sin una tabla de anulaciones."""
    hogar = HouseholdFactory()
    sembrar(hogar)
    alquiler = Category.objects.for_household(hogar).get(slug="rent")

    alquiler.name = "Loyer de la maison"
    alquiler.save()

    assert alquiler.etiqueta() == "Loyer de la maison"
    assert alquiler.is_system is True


def test_renombrar_en_un_hogar_no_toca_al_otro():
    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    sembrar(thompson)
    sembrar(garcia)

    suyo = Category.objects.for_household(thompson).get(slug="rent")
    suyo.name = "Hipoteca"
    suyo.save()

    ajeno = Category.objects.for_household(garcia).get(slug="rent")
    assert ajeno.name == ""


def test_el_slug_es_unico_dentro_del_hogar():
    from django.db.utils import IntegrityError

    hogar = HouseholdFactory()
    CategoryFactory(household=hogar, slug="rent")

    with pytest.raises(IntegrityError):
        CategoryFactory(household=hogar, slug="rent")


# --- Merchant -----------------------------------------------------------------


def test_el_comercio_normaliza_su_nombre_al_guardar():
    comercio = MerchantFactory(name="WALMART #3421")

    assert comercio.normalized_name == "WALMART"


def test_dos_variantes_del_mismo_comercio_chocan_dentro_del_hogar():
    from django.db.utils import IntegrityError

    hogar = HouseholdFactory()
    MerchantFactory(household=hogar, name="WALMART #3421")

    with pytest.raises(IntegrityError):
        MerchantFactory(household=hogar, name="walmart")


def test_el_mismo_comercio_puede_existir_en_dos_hogares():
    MerchantFactory(household=HouseholdFactory(), name="Walmart")
    MerchantFactory(household=HouseholdFactory(), name="Walmart")

    assert Merchant.unscoped.count() == 2


# --- IncomeSource -------------------------------------------------------------


def test_el_ingreso_calcula_su_cifra_conservadora():
    fuente = IncomeSourceFactory(
        amount_type=RANGE, amount_min=Decimal("800"), amount_max=Decimal("2400")
    )

    assert fuente.cifra_del_mes() == Decimal("800.00")


def test_el_ingreso_en_media_movil_sin_historia_devuelve_none():
    fuente = IncomeSourceFactory(amount_type=ROLLING_AVERAGE)

    assert fuente.cifra_del_mes(historial=[]) is None


def test_el_dueno_de_un_ingreso_es_una_membresia_no_un_usuario():
    """Desviación 3: con FK a User se podría asignar el sueldo de una casa a
    alguien que no vive en ella; con FK a Membership eso es irrepresentable."""
    campo = IncomeSource._meta.get_field("owner")

    assert campo.related_model.__name__ == "Membership"


# --- ExpenseRule --------------------------------------------------------------


def test_la_regla_de_gasto_calcula_el_importe_de_un_mes():
    regla = ExpenseRuleFactory(
        amount=Decimal("1400.00"), periodicity=BIWEEKLY,
        effective_from=date(2026, 1, 2),
    )

    assert regla.importe_del_mes(2026, 1) == Decimal("4200.00")


def test_una_regla_cerrada_no_aporta_a_los_meses_posteriores():
    """§3.2: las reglas nunca se mutan; subir el alquiler cierra la vieja."""
    regla = ExpenseRuleFactory(
        amount=Decimal("1800.00"), periodicity=MONTHLY,
        effective_from=date(2026, 1, 1), effective_to=date(2026, 3, 31),
    )

    assert regla.importe_del_mes(2026, 3) == Decimal("1800.00")
    assert regla.importe_del_mes(2026, 4) == Decimal("0.00")


def test_una_regla_de_gasto_solo_acepta_una_categoria_de_su_hogar():
    """La barrera aplica también entre modelos del motor."""
    from django.core.exceptions import ValidationError

    thompson, garcia = HouseholdFactory(), HouseholdFactory()
    ajena = CategoryFactory(household=garcia, slug="rent")
    regla = ExpenseRuleFactory.build(household=thompson, category=ajena)

    with pytest.raises(ValidationError):
        regla.full_clean()
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.budget.seeds'`

- [x] **Step 3: Escribir `apps/budget/models/catalog.py`**

```python
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.budget.engine.merchants import normalizar
from apps.households.scoping import HouseholdScoped

INCOME = "income"
EXPENSE = "expense"
KIND_CHOICES = [(INCOME, _("Income")), (EXPENSE, _("Expense"))]

HOUSEHOLD = "household"
PERSONAL = "personal"
SCOPE_CHOICES = [(HOUSEHOLD, _("Household")), (PERSONAL, _("Personal"))]


class Category(HouseholdScoped):
    """Una categoría del árbol del hogar.

    Las del sistema se siembran por hogar al crearlo (apps/budget/seeds.py):
    `slug` puesto, `name` vacío, `is_system=True`. Se muestran traducidas
    desde el slug mientras `name` esté vacío, y renombrarlas solo escribe
    `name` — así el "el hogar puede añadir y renombrar" del §3.2 es cierto sin
    una tabla de anulaciones.
    """

    slug = models.SlugField(_("identifier"), max_length=50)
    name = models.CharField(_("name"), max_length=80, blank=True)
    is_system = models.BooleanField(_("preloaded"), default=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    kind = models.CharField(_("kind"), max_length=10, choices=KIND_CHOICES, default=EXPENSE)
    # Fase 4 (CRA). Se siembra desde ya porque etiquetar dos años de gastos
    # retroactivamente es un trabajo que nadie hace nunca.
    tax_category = models.CharField(_("tax category"), max_length=30, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        constraints = [
            models.UniqueConstraint(fields=["household", "slug"], name="una_categoria_por_slug_y_hogar")
        ]

    def __str__(self):
        return self.etiqueta()

    def etiqueta(self):
        """El nombre visible: el que puso el hogar, o el del sistema traducido."""
        if self.name:
            return self.name
        from apps.budget.seeds import etiqueta_de_slug

        return etiqueta_de_slug(self.slug)

    def clean(self):
        super().clean()
        if self.parent_id and self.parent.household_id != self.household_id:
            raise ValidationError({"parent": _("That category belongs to another household.")})


class Merchant(HouseholdScoped):
    name = models.CharField(_("merchant"), max_length=120)
    normalized_name = models.CharField(max_length=120, editable=False)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("merchant")
        verbose_name_plural = _("merchants")
        constraints = [
            models.UniqueConstraint(
                fields=["household", "normalized_name"], name="un_comercio_por_nombre_y_hogar"
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.normalized_name = normalizar(self.name)
        super().save(*args, **kwargs)
```

- [x] **Step 4: Escribir `apps/budget/models/rules.py`**

```python
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.budget.engine import income as motor_income
from apps.budget.engine import periodicity as motor_periodicity
from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import HOUSEHOLD, SCOPE_CHOICES

PERIODICITY_CHOICES = [
    (motor_periodicity.WEEKLY, _("Weekly")),
    (motor_periodicity.BIWEEKLY, _("Every two weeks")),
    (motor_periodicity.SEMIMONTHLY, _("Twice a month")),
    (motor_periodicity.MONTHLY, _("Monthly")),
    (motor_periodicity.BIMONTHLY, _("Every two months")),
    (motor_periodicity.QUARTERLY, _("Quarterly")),
    (motor_periodicity.SEMIANNUAL, _("Twice a year")),
    (motor_periodicity.ANNUAL, _("Yearly")),
]

AMOUNT_TYPE_CHOICES = [
    (motor_income.FIXED, _("A fixed amount")),
    (motor_income.ESTIMATED, _("An amount I estimate each month")),
    (motor_income.RANGE, _("A range — the budget uses the minimum")),
    (motor_income.ROLLING_AVERAGE, _("The average of my last months")),
    (motor_income.IRREGULAR, _("Irregular — the budget counts zero")),
]

SOURCE_TYPE_CHOICES = [
    ("salary", _("Salary")),
    ("freelance", _("Freelance")),
    ("rental", _("Rental")),
    ("pension", _("Pension")),
    ("benefits", _("Benefits")),
    ("other", _("Other")),
]


class ReglaVigente(HouseholdScoped):
    """Lo común a las dos clases de regla.

    §3.2: LAS REGLAS NUNCA SE MUTAN. Subir el alquiler de $1800 a $1950 cierra
    la regla vieja con effective_to = 31 de marzo y crea una nueva con
    effective_from = 1 de abril. El historial queda intacto sin un modelo
    adicional, y "¿desde cuándo pagamos más?" es una consulta y no una
    investigación. Lo hace apps/budget/services.py::reemplazar_regla.
    """

    name = models.CharField(_("name"), max_length=120)
    periodicity = models.CharField(_("how often"), max_length=20, choices=PERIODICITY_CHOICES)
    effective_from = models.DateField(_("in effect from"))
    effective_to = models.DateField(_("in effect until"), null=True, blank=True)
    scope = models.CharField(_("scope"), max_length=10, choices=SCOPE_CHOICES, default=HOUSEHOLD)

    class Meta(HouseholdScoped.Meta):
        abstract = True

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": _("A rule cannot end before it starts.")})

    def ocurrencias_en(self, anio, mes):
        return motor_periodicity.ocurrencias(
            self.periodicity, self.effective_from, anio, mes, self.effective_to
        )


class IncomeSource(ReglaVigente):
    owner = models.ForeignKey(
        "households.Membership", on_delete=models.PROTECT, related_name="income_sources"
    )
    source_type = models.CharField(_("kind of income"), max_length=20, choices=SOURCE_TYPE_CHOICES)
    amount_type = models.CharField(_("how much"), max_length=20, choices=AMOUNT_TYPE_CHOICES)
    amount = MoneyField(_("amount"), null=True, blank=True)
    amount_min = MoneyField(_("at least"), null=True, blank=True)
    amount_max = MoneyField(_("at most"), null=True, blank=True)

    class Meta(ReglaVigente.Meta):
        verbose_name = _("income source")
        verbose_name_plural = _("income sources")

    def clean(self):
        super().clean()
        if self.owner_id and self.owner.household_id != self.household_id:
            raise ValidationError({"owner": _("That member belongs to another household.")})

    def cifra_del_mes(self, historial=()):
        """La cifra conservadora del §4.1. None significa 'aún no hay datos'."""
        return motor_income.cifra_conservadora(
            self.amount_type,
            amount=self.amount,
            amount_min=self.amount_min,
            amount_max=self.amount_max,
            historial=historial,
        )


class ExpenseRule(ReglaVigente):
    category = models.ForeignKey("budget.Category", on_delete=models.PROTECT, related_name="expense_rules")
    amount = MoneyField(_("amount"))
    is_essential = models.BooleanField(
        _("essential"),
        default=True,
        help_text=_("Essential expenses are the last ones a recommendation will touch."),
    )
    owner = models.ForeignKey(
        "households.Membership", on_delete=models.PROTECT,
        null=True, blank=True, related_name="expense_rules",
    )

    class Meta(ReglaVigente.Meta):
        verbose_name = _("fixed expense")
        verbose_name_plural = _("fixed expenses")

    def clean(self):
        super().clean()
        if self.category_id and self.category.household_id != self.household_id:
            raise ValidationError({"category": _("That category belongs to another household.")})
        if self.owner_id and self.owner.household_id != self.household_id:
            raise ValidationError({"owner": _("That member belongs to another household.")})

    def importe_del_mes(self, anio, mes):
        return motor_periodicity.importe_del_mes(
            self.amount, self.periodicity, self.effective_from, anio, mes, self.effective_to
        )
```

- [x] **Step 5: Escribir `apps/budget/seeds.py` y el `models/__init__.py`**

`apps/budget/seeds.py`:

```python
"""El árbol de categorías precargado del §3.2.

Se copia por hogar al crearlo. Las etiquetas viven aquí y no en la base de
datos: así se muestran en el idioma de cada miembro, y un hogar en inglés y
otro en francés ven los mismos datos con sus propias palabras.
"""

from django.utils.translation import gettext as _

# (slug, etiqueta, slug del padre, kind)
ARBOL = [
    ("housing", "Housing", None, "expense"),
    ("rent", "Rent", "housing", "expense"),
    ("mortgage", "Mortgage", "housing", "expense"),
    ("utilities", "Utilities", None, "expense"),
    ("water", "Water", "utilities", "expense"),
    ("gas", "Gas", "utilities", "expense"),
    ("electricity", "Electricity", "utilities", "expense"),
    ("internet", "Internet", "utilities", "expense"),
    ("subscriptions", "Subscriptions", None, "expense"),
    ("groceries", "Groceries", None, "expense"),
    ("transport", "Transport", None, "expense"),
    ("fuel", "Fuel", "transport", "expense"),
    ("entertainment", "Entertainment", None, "expense"),
    ("financial_obligations", "Financial obligations", None, "expense"),
    ("bank_loans", "Bank loans", "financial_obligations", "expense"),
    ("salary", "Salary", None, "income"),
    ("other_income", "Other income", None, "income"),
]

ETIQUETAS = {slug: etiqueta for slug, etiqueta, _padre, _kind in ARBOL}


def etiqueta_de_slug(slug):
    """La etiqueta traducida de una categoría del sistema."""
    return _(ETIQUETAS.get(slug, slug))


def sembrar(household):
    """Copia el árbol en un hogar recién creado. Idempotente."""
    from apps.budget.models import Category

    if Category.objects.for_household(household).exists():
        return

    creadas = {}
    for slug, _etiqueta, padre, kind in ARBOL:
        # `Category.objects.create(...)` lanzaria RuntimeError: el manager
        # estricto del lote de puertas no deja consultar sin hogar, y `create`
        # pasa por `get_queryset()`. Se instancia y se guarda.
        categoria = Category(
            household=household, slug=slug, is_system=True,
            kind=kind, parent=creadas.get(padre),
        )
        categoria.save()
        creadas[slug] = categoria
    return creadas
```

`apps/budget/models/__init__.py`:

```python
from .catalog import EXPENSE, HOUSEHOLD, INCOME, KIND_CHOICES, PERSONAL, SCOPE_CHOICES, Category, Merchant
from .rules import (
    AMOUNT_TYPE_CHOICES,
    PERIODICITY_CHOICES,
    SOURCE_TYPE_CHOICES,
    ExpenseRule,
    IncomeSource,
)

__all__ = [
    "Category", "Merchant", "IncomeSource", "ExpenseRule",
    "INCOME", "EXPENSE", "HOUSEHOLD", "PERSONAL",
    "KIND_CHOICES", "SCOPE_CHOICES", "PERIODICITY_CHOICES",
    "AMOUNT_TYPE_CHOICES", "SOURCE_TYPE_CHOICES",
]
```

- [x] **Step 6: Sembrar al crear el hogar**

En `apps/households/services.py::crear_hogar`, después de crear la membresía:

```python
    # El árbol de categorías del §3.2 se copia por hogar (desviación 1 del
    # diseño del Plan 2): HouseholdScoped.household no admite nulo, y sembrar
    # por hogar hace además que renombrar una categoría del sistema no
    # necesite una tabla de anulaciones.
    from apps.budget.seeds import sembrar

    sembrar(household)
```

El import va dentro de la función a propósito: `apps.budget` depende de `apps.households`, y un import a nivel de módulo cerraría el ciclo.

- [x] **Step 7: Escribir las fábricas**

`tests/factories_budget.py`:

```python
from datetime import date
from decimal import Decimal

import factory

from apps.budget.engine.income import FIXED
from apps.budget.engine.periodicity import MONTHLY
from tests.factories import HouseholdFactory, HouseholdScopedFactory, MembershipFactory


class CategoryFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.Category"

    household = factory.SubFactory(HouseholdFactory)
    slug = factory.Sequence(lambda n: f"categoria-{n}")
    kind = "expense"


class MerchantFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.Merchant"

    household = factory.SubFactory(HouseholdFactory)
    name = factory.Sequence(lambda n: f"Comercio {n}")


class IncomeSourceFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.IncomeSource"

    household = factory.SubFactory(HouseholdFactory)
    owner = factory.LazyAttribute(
        lambda o: MembershipFactory(household=o.household)
    )
    name = factory.Sequence(lambda n: f"Ingreso {n}")
    source_type = "salary"
    amount_type = FIXED
    amount = Decimal("3000.00")
    periodicity = MONTHLY
    effective_from = date(2026, 1, 1)


class ExpenseRuleFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.ExpenseRule"

    household = factory.SubFactory(HouseholdFactory)
    category = factory.LazyAttribute(lambda o: CategoryFactory(household=o.household))
    name = factory.Sequence(lambda n: f"Gasto {n}")
    amount = Decimal("1800.00")
    periodicity = MONTHLY
    effective_from = date(2026, 1, 1)
```

`MerchantFactory` deja que `save()` calcule `normalized_name`, así que `HouseholdScopedFactory._get_manager` devuelve `unscoped` y `create()` llama a `save()` — correcto.

- [x] **Step 8: Generar la migración y correr con `--create-db`**

```bash
.venv/Scripts/python.exe manage.py makemigrations budget
.venv/Scripts/python.exe -m pytest tests/budget/test_models.py -q --create-db
```

Expected: PASS — 17 pruebas. **`--create-db` es obligatorio**: sin él la base reutilizada no tiene las tablas nuevas.

- [x] **Step 9: Correr la suite entera**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS. Ojo con `tests/test_scoping.py::test_todo_modelo_con_hogar_conserva_base_manager_name`: si falla, alguna `Meta` nueva no heredó de `HouseholdScoped.Meta`.

- [x] **Step 10: Commit**

```bash
git add -A
git commit -m "Anade el catalogo y las reglas del presupuesto"
```

Cuerpo: los cuatro primeros modelos del motor. `Category` se siembra por hogar (desviación 1 del diseño): `HouseholdScoped.household` no admite nulo y ablandarlo destriparía la barrera del lote de puertas; sembrar por hogar hace además que el "añadir **y renombrar**" del §3.2 sea cierto sin una tabla de anulaciones. Los dueños son `Membership` y no `User` (desviación 3): con FK a `User` se podría asignar el sueldo de una casa a alguien que no vive en ella.

---

### Task 10: Modelos, tanda 2 — el mes, sus líneas y las transacciones

**Files:**
- Create: `apps/budget/models/months.py`, `apps/budget/models/ledger.py`
- Modify: `apps/budget/models/__init__.py`
- Test: `tests/budget/test_models.py` (añadir), `tests/budget/test_mes_cerrado.py`

**Interfaces:**
- Consumes: los de la Tarea 9.
- Produce:
  - `BudgetMonth(household, year, month, status, opened_at, closed_at)` con `FUTURE`/`OPEN`/`CLOSED`, `esta_cerrado`, y `UniqueConstraint(household, year, month)`.
  - `BudgetLine(household, budget_month, category, kind, planned_amount, is_exceptional, source_income, source_expense_rule, owner, scope, note)`.
  - `MonthlyClose(household, budget_month, ...)` — inmutable.
  - `Transaction(household, budget_month, category, merchant, income_source, amount, date, member, payment_method, scope, note, budget_line, receipt_image)`.
  - `MesCerrado(Exception)` en `apps/budget/models/months.py`.
  - `BudgetMonthFactory`, `BudgetLineFactory`, `TransactionFactory` en `tests/factories_budget.py`.

- [x] **Step 1: Escribir las pruebas del mes cerrado**

`tests/budget/test_mes_cerrado.py`:

```python
"""Un mes cerrado rechaza toda escritura (§9).

En DOS capas: el servicio la rechaza (Tarea 12) y el modelo también. Dos
capas porque el Plan 3 añadirá caminos de escritura que hoy no existen, y la
capa de modelo es la que no se puede rodear.
"""

from decimal import Decimal

import pytest

from apps.budget.models import BudgetMonth, MesCerrado
from tests.factories_budget import (
    BudgetLineFactory,
    BudgetMonthFactory,
    MonthlyCloseFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db


def test_no_se_puede_anadir_una_linea_a_un_mes_cerrado():
    mes = BudgetMonthFactory(status=BudgetMonth.CLOSED)

    with pytest.raises(MesCerrado):
        BudgetLineFactory(budget_month=mes, household=mes.household)


def test_no_se_puede_registrar_una_transaccion_en_un_mes_cerrado():
    mes = BudgetMonthFactory(status=BudgetMonth.CLOSED)

    with pytest.raises(MesCerrado):
        TransactionFactory(budget_month=mes, household=mes.household)


def test_no_se_puede_editar_una_linea_de_un_mes_que_se_cerro_despues():
    mes = BudgetMonthFactory(status=BudgetMonth.OPEN)
    linea = BudgetLineFactory(budget_month=mes, household=mes.household)
    mes.status = BudgetMonth.CLOSED
    mes.save()

    linea.planned_amount = Decimal("1.00")
    with pytest.raises(MesCerrado):
        linea.save()


def test_un_mes_abierto_acepta_escrituras():
    mes = BudgetMonthFactory(status=BudgetMonth.OPEN)

    linea = BudgetLineFactory(budget_month=mes, household=mes.household)

    assert linea.pk is not None


def test_el_cierre_es_inmutable():
    """§3.3: MonthlyClose es inmutable una vez escrito. Un balance que se
    puede reescribir no es un balance."""
    cierre = MonthlyCloseFactory()

    cierre.balance = Decimal("999.00")
    with pytest.raises(MesCerrado):
        cierre.save()


def test_un_mes_solo_existe_una_vez_por_hogar():
    from django.db.utils import IntegrityError

    mes = BudgetMonthFactory(year=2026, month=3)

    with pytest.raises(IntegrityError):
        BudgetMonthFactory(household=mes.household, year=2026, month=3)


def test_dos_hogares_pueden_tener_el_mismo_mes():
    BudgetMonthFactory(year=2026, month=3)
    BudgetMonthFactory(year=2026, month=3)

    assert BudgetMonth.unscoped.filter(year=2026, month=3).count() == 2


def test_la_linea_no_puede_pertenecer_a_un_hogar_distinto_al_de_su_mes():
    """Desviación 2.6: se denormaliza `household` en todos los modelos, y la
    consistencia se valida aquí porque un CheckConstraint no cruza tablas."""
    from django.core.exceptions import ValidationError

    from tests.factories import HouseholdFactory

    mes = BudgetMonthFactory()
    linea = BudgetLineFactory.build(budget_month=mes, household=HouseholdFactory())

    with pytest.raises(ValidationError):
        linea.full_clean()


def test_una_linea_no_puede_venir_de_dos_reglas_a_la_vez():
    """Desviación 2: source_rule se parte en dos FK anulables, con un
    CheckConstraint que exige como máximo una."""
    from django.db.utils import IntegrityError

    from tests.factories_budget import ExpenseRuleFactory, IncomeSourceFactory

    mes = BudgetMonthFactory()
    with pytest.raises(IntegrityError):
        BudgetLineFactory(
            budget_month=mes,
            household=mes.household,
            source_income=IncomeSourceFactory(household=mes.household),
            source_expense_rule=ExpenseRuleFactory(household=mes.household),
        )
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_mes_cerrado.py -q`
Expected: FAIL — `ImportError: cannot import name 'BudgetMonth'`

- [x] **Step 3: Escribir `apps/budget/models/months.py`**

```python
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import EXPENSE, HOUSEHOLD, KIND_CHOICES, SCOPE_CHOICES

DIAS_PARA_EL_CIERRE_AUTOMATICO = 5


class MesCerrado(Exception):
    """Se intentó escribir en un mes que ya está cerrado."""


class BudgetMonth(HouseholdScoped):
    """El ciclo de vida del §4.2: futuro → abierto → cerrado.

    Los meses `future` NO existen como filas: se calculan desde las reglas al
    consultarlos, para que cambiar el alquiler se refleje al instante en todos
    los meses futuros (§2.3). El estado FUTURE existe solo para el instante
    entre crear la fila y materializarla.
    """

    FUTURE, OPEN, CLOSED = "future", "open", "closed"
    STATUS_CHOICES = [(FUTURE, _("Upcoming")), (OPEN, _("Open")), (CLOSED, _("Closed"))]

    year = models.PositiveSmallIntegerField(_("year"))
    month = models.PositiveSmallIntegerField(_("month"))
    status = models.CharField(_("status"), max_length=10, choices=STATUS_CHOICES, default=OPEN)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("budget month")
        verbose_name_plural = _("budget months")
        ordering = ["year", "month"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "year", "month"], name="un_mes_por_hogar"
            )
        ]

    def __str__(self):
        return f"{self.year}-{self.month:02d}"

    @property
    def esta_cerrado(self):
        return self.status == self.CLOSED


class EscrituraAcotadaAlMes(models.Model):
    """Base de todo lo que se escribe dentro de un mes.

    Rechaza la escritura si el mes está cerrado (§9) y comprueba que el hogar
    denormalizado coincida con el de su mes. Un CheckConstraint no puede
    cruzar tablas, así que esto vive en Python — pero en el modelo, no en la
    vista, porque la vista se puede rodear.
    """

    class Meta:
        abstract = True

    def _mes(self):
        return self.budget_month

    def clean(self):
        super().clean()
        if self.budget_month_id and self.household_id != self.budget_month.household_id:
            raise ValidationError(
                {"household": _("This row does not belong to the same household as its month.")}
            )

    def save(self, *args, **kwargs):
        if self.budget_month_id and self._mes().esta_cerrado:
            raise MesCerrado(
                f"El mes {self._mes()} está cerrado y no admite escrituras."
            )
        super().save(*args, **kwargs)


class BudgetLine(EscrituraAcotadaAlMes, HouseholdScoped):
    """Las filas materializadas de un mes abierto.

    Lo excepcional vive aquí: el viaje, la matrícula, los regalos de Navidad.
    Se agregan al mes abierto y no afectan a ningún otro mes.
    """

    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.CASCADE, related_name="lineas")
    category = models.ForeignKey("budget.Category", on_delete=models.PROTECT, related_name="lineas")
    kind = models.CharField(_("kind"), max_length=10, choices=KIND_CHOICES, default=EXPENSE)
    planned_amount = MoneyField(_("planned"))
    is_exceptional = models.BooleanField(_("one-off"), default=False)
    # Desviación 2: dos FK anulables en vez de un source_rule genérico. Una
    # regla es o una IncomeSource o una ExpenseRule; una FK genérica
    # arrastraría contenttypes a cambio de nada.
    source_income = models.ForeignKey(
        "budget.IncomeSource", on_delete=models.SET_NULL, null=True, blank=True, related_name="lineas"
    )
    source_expense_rule = models.ForeignKey(
        "budget.ExpenseRule", on_delete=models.SET_NULL, null=True, blank=True, related_name="lineas"
    )
    owner = models.ForeignKey(
        "households.Membership", on_delete=models.PROTECT, null=True, blank=True, related_name="lineas"
    )
    scope = models.CharField(_("scope"), max_length=10, choices=SCOPE_CHOICES, default=HOUSEHOLD)
    note = models.CharField(_("note"), max_length=200, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("budget line")
        verbose_name_plural = _("budget lines")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(source_income__isnull=True) | models.Q(source_expense_rule__isnull=True),
                name="una_linea_viene_de_una_sola_regla",
            )
        ]

    def __str__(self):
        return f"{self.category} · {self.planned_amount}"


class MonthlyClose(HouseholdScoped):
    """La foto congelada del mes. INMUTABLE una vez escrita (§3.3).

    Un balance que se puede reescribir no es un balance: el usuario que
    consulta enero dentro de un año tiene que ver lo que vio entonces.
    """

    budget_month = models.OneToOneField(BudgetMonth, on_delete=models.CASCADE, related_name="cierre")
    ingresos_presupuestados = MoneyField()
    ingresos_reales = MoneyField()
    egresos_presupuestados = MoneyField()
    egresos_reales = MoneyField()
    varianza_por_categoria = models.JSONField(default=dict)
    balance = MoneyField()
    arrastre = MoneyField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("monthly close")
        verbose_name_plural = _("monthly closes")

    def __str__(self):
        return f"Cierre de {self.budget_month}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise MesCerrado("Un cierre mensual es inmutable: no se puede modificar.")
        super().save(*args, **kwargs)
```

**Nota:** en Django 5.1 `CheckConstraint` usa `condition=`; `check=` está en desuso. Si la versión instalada se queja, usa `check=`.

- [x] **Step 4: Escribir `apps/budget/models/ledger.py`**

```python
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import HOUSEHOLD, SCOPE_CHOICES
from .months import BudgetMonth, EscrituraAcotadaAlMes

PAYMENT_METHOD_CHOICES = [
    ("debit", _("Debit card")),
    ("credit", _("Credit card")),
    ("cash", _("Cash")),
    ("transfer", _("Transfer")),
    ("other", _("Other")),
]


class Transaction(EscrituraAcotadaAlMes, HouseholdScoped):
    """Lo que realmente pasó."""

    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.PROTECT, related_name="transacciones")
    category = models.ForeignKey("budget.Category", on_delete=models.PROTECT, related_name="transacciones")
    merchant = models.ForeignKey(
        "budget.Merchant", on_delete=models.SET_NULL, null=True, blank=True, related_name="transacciones"
    )
    # Desviación 4: sin esta FK, el modo rolling_average del §4.1 no se puede
    # calcular — §3.3 definía Transaction sin ningún vínculo con IncomeSource.
    income_source = models.ForeignKey(
        "budget.IncomeSource", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transacciones",
        help_text=_("Which income this belongs to, so its average can be computed."),
    )
    amount = MoneyField(_("amount"))
    date = models.DateField(_("date"))
    member = models.ForeignKey("households.Membership", on_delete=models.PROTECT, related_name="transacciones")
    payment_method = models.CharField(
        _("paid with"), max_length=20, choices=PAYMENT_METHOD_CHOICES, default="debit"
    )
    scope = models.CharField(_("scope"), max_length=10, choices=SCOPE_CHOICES, default=HOUSEHOLD)
    note = models.CharField(_("note"), max_length=200, blank=True)
    budget_line = models.ForeignKey(
        "budget.BudgetLine", on_delete=models.SET_NULL, null=True, blank=True, related_name="transacciones"
    )
    # Fase 2. Entra anulable y sin usar; el destino real es Supabase Storage.
    receipt_image = models.ImageField(_("receipt"), upload_to="receipts/", null=True, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")
        ordering = ["-date", "-pk"]

    def __str__(self):
        return f"{self.date} · {self.category} · {self.amount}"

    def clean(self):
        super().clean()
        for campo in ("category", "merchant", "income_source", "member", "budget_line"):
            relacionado = getattr(self, campo, None)
            if relacionado is not None and relacionado.household_id != self.household_id:
                raise ValidationError({campo: _("That belongs to another household.")})
```

- [x] **Step 5: Ampliar `models/__init__.py` y las fábricas**

Añadir a `apps/budget/models/__init__.py`:

```python
from .ledger import PAYMENT_METHOD_CHOICES, Transaction
from .months import (
    DIAS_PARA_EL_CIERRE_AUTOMATICO,
    BudgetLine,
    BudgetMonth,
    MesCerrado,
    MonthlyClose,
)
```

y sus nombres a `__all__`.

Añadir a `tests/factories_budget.py`:

```python
class BudgetMonthFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.BudgetMonth"

    household = factory.SubFactory(HouseholdFactory)
    year = 2026
    month = factory.Sequence(lambda n: (n % 12) + 1)
    status = "open"


class BudgetLineFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.BudgetLine"

    household = factory.SubFactory(HouseholdFactory)
    budget_month = factory.LazyAttribute(lambda o: BudgetMonthFactory(household=o.household))
    category = factory.LazyAttribute(lambda o: CategoryFactory(household=o.household))
    kind = "expense"
    planned_amount = Decimal("100.00")


class TransactionFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.Transaction"

    household = factory.SubFactory(HouseholdFactory)
    budget_month = factory.LazyAttribute(lambda o: BudgetMonthFactory(household=o.household))
    category = factory.LazyAttribute(lambda o: CategoryFactory(household=o.household))
    member = factory.LazyAttribute(lambda o: MembershipFactory(household=o.household))
    amount = Decimal("50.00")
    date = date(2026, 1, 15)


class MonthlyCloseFactory(HouseholdScopedFactory):
    class Meta:
        model = "budget.MonthlyClose"

    household = factory.SubFactory(HouseholdFactory)
    budget_month = factory.LazyAttribute(lambda o: BudgetMonthFactory(household=o.household))
    ingresos_presupuestados = Decimal("0.00")
    ingresos_reales = Decimal("0.00")
    egresos_presupuestados = Decimal("0.00")
    egresos_reales = Decimal("0.00")
    balance = Decimal("0.00")
    arrastre = Decimal("0.00")
```

- [x] **Step 6: Migrar y verificar**

```bash
.venv/Scripts/python.exe manage.py makemigrations budget
.venv/Scripts/python.exe -m pytest tests/budget -q --create-db
```

Expected: PASS.

- [x] **Step 7: Correr la suite entera y commitear**

Run: `.venv/Scripts/python.exe -m pytest -q` → PASS.

```bash
git add -A
git commit -m "Anade el mes, sus lineas y las transacciones"
```

Cuerpo: un mes cerrado rechaza toda escritura en la capa de modelo, no solo en el servicio, porque el Plan 3 añadirá caminos de escritura que hoy no existen y la capa de modelo es la que no se puede rodear. `MonthlyClose` lanza si ya tiene `pk`: un balance que se puede reescribir no es un balance. `BudgetLine` parte `source_rule` en dos FK anulables con un `CheckConstraint` (desviación 2) y `Transaction` gana `income_source` (desviación 4), sin la cual el modo `rolling_average` del §4.1 no se puede calcular.

---

### Task 11: Modelos, tanda 3 — metas, reparto y libro mayor

**Files:**
- Create: `apps/budget/models/goals.py`, `apps/budget/models/allocation.py`, `apps/budget/admin.py`
- Modify: `apps/budget/models/__init__.py`, `tests/factories_budget.py`
- Test: `tests/budget/test_models.py` (añadir)

**Interfaces:**
- Produce:
  - `Goal(household, name, scope, owner, status, contribution_mode, target_amount, target_date, monthly_amount)` con `acumulado()` y `derivar()`.
  - `GoalContribution(household, goal, amount, date, member, origen)`.
  - `AllocationRule(household, order, target_type, target_goal, target_category, method, amount, percentage, split, pesos, is_active)` con `a_regla_de_reparto(miembros)`.
  - `MonthlyAllocation(household, budget_month, rule, planned_amount, actual_amount, member)`.
  - `AllowanceLedger(household, member, budget_month, granted, spent, adjustment, carried_in, carried_out)` con `saldo()`.
  - `GoalFactory`, `AllocationRuleFactory`, `AllowanceLedgerFactory`.

- [x] **Step 1: Escribir las pruebas**

Añadir a `tests/budget/test_models.py`:

```python
# --- Goal ---------------------------------------------------------------------


def test_la_meta_deriva_su_aporte_mensual_desde_la_fecha():
    from apps.budget.engine.goals import BY_TARGET_DATE
    from tests.factories_budget import GoalFactory

    meta = GoalFactory(
        contribution_mode=BY_TARGET_DATE,
        target_amount=Decimal("7200.00"),
        target_date=date(2027, 6, 30),
    )

    aporte, fecha = meta.derivar(desde=date(2026, 9, 3))

    assert aporte == Decimal("720.00")
    assert fecha == date(2027, 6, 30)


def test_la_meta_descuenta_sus_contribuciones():
    from apps.budget.engine.goals import BY_TARGET_DATE
    from tests.factories_budget import GoalContributionFactory, GoalFactory

    meta = GoalFactory(
        contribution_mode=BY_TARGET_DATE,
        target_amount=Decimal("7200.00"),
        target_date=date(2027, 6, 30),
    )
    GoalContributionFactory(goal=meta, household=meta.household, amount=Decimal("2200.00"))

    assert meta.acumulado() == Decimal("2200.00")
    assert meta.derivar(desde=date(2026, 9, 3))[0] == Decimal("500.00")


def test_la_meta_no_guarda_el_dato_derivado():
    """§3.3: el tercer dato se deriva al mostrarlo, o quedaría obsoleto en
    cuanto cambie el acumulado."""
    from apps.budget.models import Goal

    campos = {c.name for c in Goal._meta.get_fields()}
    assert "aporte_derivado" not in campos
    assert "fecha_derivada" not in campos


# --- AllocationRule y el libro mayor -----------------------------------------


def test_la_regla_de_reparto_se_traduce_al_tipo_del_motor():
    from apps.budget.engine.cascade import ALLOWANCE, REMAINDER
    from tests.factories_budget import AllocationRuleFactory

    regla = AllocationRuleFactory(target_type=ALLOWANCE, method=REMAINDER, order=2)

    del_motor = regla.a_regla_de_reparto(miembros=(10, 20))

    assert del_motor.orden == 2
    assert del_motor.destino == ALLOWANCE
    assert del_motor.miembros == (10, 20)


def test_el_orden_de_reparto_es_unico_dentro_del_hogar():
    from django.db.utils import IntegrityError

    from tests.factories_budget import AllocationRuleFactory

    regla = AllocationRuleFactory(order=1)

    with pytest.raises(IntegrityError):
        AllocationRuleFactory(household=regla.household, order=1)


def test_el_libro_mayor_deriva_su_saldo():
    from tests.factories_budget import AllowanceLedgerFactory

    fila = AllowanceLedgerFactory(
        carried_in=Decimal("45.00"), granted=Decimal("100.00"),
        adjustment=Decimal("0.00"), spent=Decimal("30.00"),
    )

    assert fila.saldo() == Decimal("115.00")


def test_hay_una_sola_fila_de_mesada_por_miembro_y_mes():
    from django.db.utils import IntegrityError

    from tests.factories_budget import AllowanceLedgerFactory

    fila = AllowanceLedgerFactory()

    with pytest.raises(IntegrityError):
        AllowanceLedgerFactory(
            household=fila.household, member=fila.member, budget_month=fila.budget_month
        )
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_models.py -q`
Expected: FAIL — `ImportError` sobre `GoalFactory`.

- [x] **Step 3: Escribir `apps/budget/models/goals.py`**

```python
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.budget.engine import goals as motor_goals
from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .catalog import HOUSEHOLD, SCOPE_CHOICES

CONTRIBUTION_MODE_CHOICES = [
    (motor_goals.BY_TARGET_DATE, _("By a target date")),
    (motor_goals.BY_MONTHLY_AMOUNT, _("By a monthly amount")),
]

ORIGEN_CHOICES = [("manual", _("Added by hand")), ("cascade", _("From the monthly split"))]


class Goal(HouseholdScoped):
    ACTIVE, REACHED, ABANDONED = "active", "reached", "abandoned"
    STATUS_CHOICES = [
        (ACTIVE, _("Active")), (REACHED, _("Reached")), (ABANDONED, _("Abandoned"))
    ]

    name = models.CharField(_("goal"), max_length=120)
    scope = models.CharField(_("scope"), max_length=10, choices=SCOPE_CHOICES, default=HOUSEHOLD)
    owner = models.ForeignKey(
        "households.Membership", on_delete=models.PROTECT, null=True, blank=True, related_name="goals"
    )
    status = models.CharField(_("status"), max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    contribution_mode = models.CharField(
        _("how to reach it"), max_length=20, choices=CONTRIBUTION_MODE_CHOICES
    )
    target_amount = MoneyField(_("target amount"))
    target_date = models.DateField(_("target date"), null=True, blank=True)
    monthly_amount = MoneyField(_("monthly amount"), null=True, blank=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("goal")
        verbose_name_plural = _("goals")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.contribution_mode == motor_goals.BY_TARGET_DATE and not self.target_date:
            raise ValidationError({"target_date": _("Pick the date you want to reach it by.")})
        if self.contribution_mode == motor_goals.BY_MONTHLY_AMOUNT and not self.monthly_amount:
            raise ValidationError({"monthly_amount": _("Say how much you will put in each month.")})

    def acumulado(self):
        total = self.contributions.aggregate(total=models.Sum("amount"))["total"]
        return total if total is not None else Decimal("0.00")

    def derivar(self, desde=None):
        """El dato que falta: el aporte mensual o la fecha de llegada."""
        return motor_goals.derivar(
            self.contribution_mode,
            objetivo=self.target_amount,
            acumulado=self.acumulado(),
            desde=desde or timezone.localdate(),
            fecha_objetivo=self.target_date,
            aporte_mensual=self.monthly_amount,
        )


class GoalContribution(HouseholdScoped):
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="contributions")
    amount = MoneyField(_("amount"))
    date = models.DateField(_("date"))
    member = models.ForeignKey(
        "households.Membership", on_delete=models.PROTECT, related_name="goal_contributions"
    )
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default="manual")

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("contribution")
        verbose_name_plural = _("contributions")
        ordering = ["-date", "-pk"]

    def __str__(self):
        return f"{self.goal} · {self.amount}"
```

- [x] **Step 4: Escribir `apps/budget/models/allocation.py`**

```python
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.budget.engine import allowance as motor_allowance
from apps.budget.engine import cascade as motor_cascade
from apps.core.fields import MoneyField
from apps.households.scoping import HouseholdScoped

from .months import BudgetMonth

TARGET_TYPE_CHOICES = [
    (motor_cascade.GOAL, _("A savings goal")),
    (motor_cascade.ALLOWANCE, _("Personal allowance")),
    (motor_cascade.CATEGORY, _("A category or fund")),
]

METHOD_CHOICES = [
    (motor_cascade.FIXED, _("A fixed amount")),
    (motor_cascade.PERCENTAGE, _("A percentage of what is left over")),
    (motor_cascade.REMAINDER, _("Everything that is left")),
]

EQUAL = "equal"
WEIGHTED = "weighted"
SPLIT_CHOICES = [(EQUAL, _("Equally")), (WEIGHTED, _("By weights"))]


class AllocationRule(HouseholdScoped):
    """Una regla del reparto en cascada (§4.5).

    `order` define la prioridad: el sobrante cae por las reglas de menor a
    mayor. Con el ahorro arriba y las mesadas abajo, un mes flojo se come la
    diversión y no el ahorro; una familia que prefiera lo contrario solo
    reordena las reglas.
    """

    order = models.PositiveSmallIntegerField(_("priority"))
    target_type = models.CharField(_("goes to"), max_length=12, choices=TARGET_TYPE_CHOICES)
    target_goal = models.ForeignKey(
        "budget.Goal", on_delete=models.CASCADE, null=True, blank=True, related_name="allocation_rules"
    )
    target_category = models.ForeignKey(
        "budget.Category", on_delete=models.PROTECT, null=True, blank=True, related_name="allocation_rules"
    )
    method = models.CharField(_("how much"), max_length=12, choices=METHOD_CHOICES)
    amount = MoneyField(_("amount"), null=True, blank=True)
    percentage = models.DecimalField(
        _("percentage"), max_digits=5, decimal_places=4, null=True, blank=True,
        help_text=_("0.10 means ten percent of what is left over."),
    )
    split = models.CharField(_("split"), max_length=10, choices=SPLIT_CHOICES, default=EQUAL)
    pesos = models.JSONField(default=dict, blank=True, help_text=_("Membership id to weight."))
    is_active = models.BooleanField(_("active"), default=True)

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("split rule")
        verbose_name_plural = _("split rules")
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["household", "order"], name="un_orden_de_reparto_por_hogar")
        ]

    def __str__(self):
        return f"{self.order}. {self.get_target_type_display()}"

    def clean(self):
        super().clean()
        if self.method == motor_cascade.FIXED and self.amount is None:
            raise ValidationError({"amount": _("A fixed rule needs an amount.")})
        if self.method == motor_cascade.PERCENTAGE and self.percentage is None:
            raise ValidationError({"percentage": _("A percentage rule needs a percentage.")})
        if self.target_type == motor_cascade.GOAL and not self.target_goal_id:
            raise ValidationError({"target_goal": _("Pick the goal this goes to.")})
        if self.target_type == motor_cascade.CATEGORY and not self.target_category_id:
            raise ValidationError({"target_category": _("Pick the category this goes to.")})

    def a_regla_de_reparto(self, miembros=()):
        """La traduce al tipo del motor. Es el único puente ORM → engine."""
        miembros = tuple(miembros)
        pesos = None
        if self.split == WEIGHTED and self.pesos:
            pesos = tuple(Decimal(str(self.pesos.get(str(m), 1))) for m in miembros)
        return motor_cascade.ReglaReparto(
            orden=self.order,
            destino=self.target_type,
            metodo=self.method,
            importe=self.amount,
            porcentaje=self.percentage,
            destino_id=self.target_goal_id or self.target_category_id,
            miembros=miembros if self.target_type == motor_cascade.ALLOWANCE else (),
            pesos=pesos,
        )


class MonthlyAllocation(HouseholdScoped):
    """El reparto materializado de un mes."""

    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.CASCADE, related_name="asignaciones")
    rule = models.ForeignKey(AllocationRule, on_delete=models.PROTECT, related_name="asignaciones")
    planned_amount = MoneyField(_("planned"))
    actual_amount = MoneyField(_("actual"), null=True, blank=True)
    member = models.ForeignKey(
        "households.Membership", on_delete=models.PROTECT, null=True, blank=True, related_name="asignaciones"
    )

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("monthly split")
        verbose_name_plural = _("monthly splits")


class AllowanceLedger(HouseholdScoped):
    """El saldo de mesada de cada miembro (§3.3).

    Es un libro mayor, no un campo mutable: cada mes es una fila y el saldo se
    deriva sumando. Así "¿por qué tengo $145 este mes?" siempre tiene
    respuesta.
    """

    member = models.ForeignKey(
        "households.Membership", on_delete=models.PROTECT, related_name="mesadas"
    )
    budget_month = models.ForeignKey(BudgetMonth, on_delete=models.CASCADE, related_name="mesadas")
    granted = MoneyField(_("granted"), default=Decimal("0.00"))
    spent = MoneyField(_("spent"), default=Decimal("0.00"))
    adjustment = MoneyField(_("adjustment"), default=Decimal("0.00"))
    carried_in = MoneyField(_("carried in"), default=Decimal("0.00"))
    carried_out = MoneyField(_("carried out"), default=Decimal("0.00"))

    class Meta(HouseholdScoped.Meta):
        verbose_name = _("allowance")
        verbose_name_plural = _("allowances")
        constraints = [
            models.UniqueConstraint(
                fields=["household", "member", "budget_month"], name="una_mesada_por_miembro_y_mes"
            )
        ]

    def __str__(self):
        return f"{self.member} · {self.budget_month} · {self.saldo()}"

    def saldo(self):
        return motor_allowance.saldo(self.carried_in, self.granted, self.adjustment, self.spent)
```

- [x] **Step 5: El admin de la app**

`apps/budget/admin.py`:

```python
from django.contrib import admin

from apps.households.admin import HouseholdScopedAdmin

from .models import (
    AllocationRule,
    AllowanceLedger,
    BudgetLine,
    BudgetMonth,
    Category,
    ExpenseRule,
    Goal,
    GoalContribution,
    IncomeSource,
    Merchant,
    MonthlyAllocation,
    MonthlyClose,
    Transaction,
)

# Todos con el mixin: un ModelAdmin normal lanza RuntimeError al listar y al
# construir su formulario, porque el manager estricto es _default_manager.
for modelo in (
    Category, Merchant, IncomeSource, ExpenseRule, BudgetMonth, BudgetLine,
    MonthlyClose, Transaction, Goal, GoalContribution, AllocationRule,
    MonthlyAllocation, AllowanceLedger,
):
    admin.site.register(modelo, HouseholdScopedAdmin)
```

- [x] **Step 6: Fábricas, migración y verificación**

Añadir `GoalFactory`, `GoalContributionFactory`, `AllocationRuleFactory`, `MonthlyAllocationFactory` y `AllowanceLedgerFactory` a `tests/factories_budget.py`, todas heredando de `HouseholdScopedFactory` y con `household = factory.SubFactory(HouseholdFactory)`.

```bash
.venv/Scripts/python.exe manage.py makemigrations budget
.venv/Scripts/python.exe -m pytest -q --create-db
```

Expected: PASS — la suite entera, con los trece modelos.

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "Anade metas, reglas de reparto y el libro mayor de la mesada"
```

---

**PUNTO DE CONTROL 2 — el motor y los trece modelos están completos.** Si hay que parar, se para aquí: todas las pruebas del §9 que no dependen de una pantalla están en verde.

---

### Task 12: `services.py` — el ciclo del mes

**Files:**
- Create: `apps/budget/services.py`, `apps/budget/management/commands/cerrar_meses_vencidos.py`
- Test: `tests/budget/test_month_cycle.py`

**Interfaces:**
- Consumes: todos los modelos, `engine.periodicity`, `engine.income`, `engine.closing`
- Produce:
  - `@dataclass(frozen=True) LineaProyectada(categoria_id, kind, importe, origen, nombre)`
  - `@dataclass(frozen=True) ProyeccionDeMes(anio, mes, lineas, total_ingresos, total_egresos, sobrante)`
  - `proyectar(hogar, anio, mes) -> ProyeccionDeMes`
  - `obtener_mes(hogar, anio, mes, hoy=None) -> BudgetMonth | ProyeccionDeMes`
  - `materializar(hogar, anio, mes) -> BudgetMonth`
  - `cerrar_mes(mes) -> MonthlyClose`
  - `cerrar_vencidos(hogar, hoy=None) -> list[MonthlyClose]`
  - `historial_de_ingreso(fuente, hasta) -> list[Decimal]`
  - Los usa la Tarea 13 y las pantallas.

- [x] **Step 1: Escribir las pruebas**

`tests/budget/test_month_cycle.py`:

```python
"""El ciclo de vida del mes (§4.2) y el arrastre (§4.4).

FUTURO (proyección desde reglas, sin filas) → ABIERTO (filas reales,
editables) → CERRADO (foto congelada, inmutable).

El disparador es entrar (decisión §2.3 del diseño del Plan 2): no hay cron ni
Celery en el stack, y un comando programado como único disparador no correría
en desarrollo.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services
from apps.budget.engine.periodicity import MONTHLY
from apps.budget.models import BudgetMonth, MonthlyClose
from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import ExpenseRuleFactory, IncomeSourceFactory, TransactionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar_con_reglas():
    hogar = crear_hogar(UserFactory(), "Family Thompson", family_size=4)
    IncomeSourceFactory(
        household=hogar, amount=Decimal("3000.00"), periodicity=MONTHLY,
        effective_from=date(2026, 1, 1),
    )
    ExpenseRuleFactory(
        household=hogar, amount=Decimal("1800.00"), periodicity=MONTHLY,
        effective_from=date(2026, 1, 1),
    )
    return hogar


# --- futuro: proyección sin filas --------------------------------------------


def test_un_mes_futuro_se_proyecta_y_no_persiste(hogar_con_reglas):
    """§2.3: los meses future NO existen como filas."""
    proyeccion = services.obtener_mes(hogar_con_reglas, 2027, 5, hoy=date(2026, 3, 10))

    assert isinstance(proyeccion, services.ProyeccionDeMes)
    assert not BudgetMonth.objects.for_household(hogar_con_reglas).filter(
        year=2027, month=5
    ).exists()


def test_la_proyeccion_suma_las_reglas_vigentes(hogar_con_reglas):
    proyeccion = services.proyectar(hogar_con_reglas, 2027, 5)

    assert proyeccion.total_ingresos == Decimal("3000.00")
    assert proyeccion.total_egresos == Decimal("1800.00")
    assert proyeccion.sobrante == Decimal("1200.00")


def test_cambiar_una_regla_se_refleja_al_instante_en_los_meses_futuros(hogar_con_reglas):
    """§2.3, la razón de que los meses futuros no se persistan."""
    regla = hogar_con_reglas.budget_expenserule_set.first()
    regla.amount = Decimal("1950.00")
    regla.save()

    assert services.proyectar(hogar_con_reglas, 2027, 5).total_egresos == Decimal("1950.00")


# --- abierto: materialización -------------------------------------------------


def test_entrar_al_mes_corriente_lo_materializa(hogar_con_reglas):
    mes = services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))

    assert isinstance(mes, BudgetMonth)
    assert mes.status == BudgetMonth.OPEN
    assert mes.lineas.count() == 2


def test_materializar_dos_veces_no_duplica_lineas(hogar_con_reglas):
    """Dos pestañas abiertas el día 1 es el caso normal, no el raro."""
    services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))
    mes = services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))

    assert mes.lineas.count() == 2


def test_las_lineas_materializadas_recuerdan_su_regla(hogar_con_reglas):
    mes = services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))

    gasto = mes.lineas.get(kind="expense")
    assert gasto.source_expense_rule is not None
    assert gasto.planned_amount == Decimal("1800.00")


def test_editar_una_linea_de_un_mes_abierto_no_toca_la_regla(hogar_con_reglas):
    """§4.3: la vista mensual toca las líneas; la anual toca la regla."""
    mes = services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 10))
    linea = mes.lineas.get(kind="expense")
    linea.planned_amount = Decimal("2000.00")
    linea.save()

    regla = hogar_con_reglas.budget_expenserule_set.first()
    assert regla.amount == Decimal("1800.00")


# --- cerrado ------------------------------------------------------------------


def test_cerrar_escribe_el_cierre_y_congela_el_mes(hogar_con_reglas):
    mes = services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))
    TransactionFactory(
        household=hogar_con_reglas, budget_month=mes, amount=Decimal("500.00"),
        date=date(2026, 1, 20),
        category=mes.lineas.get(kind="expense").category,
    )

    cierre = services.cerrar_mes(mes)
    mes.refresh_from_db()

    assert mes.status == BudgetMonth.CLOSED
    assert cierre.egresos_reales == Decimal("500.00")


def test_entrar_tras_dos_meses_fuera_cierra_en_cadena(hogar_con_reglas):
    """El caso del §2.3: la familia vuelve el 12 de marzo tras dos meses. Se
    cierran enero y febrero EN ORDEN, porque cada cierre arrastra su saldo."""
    services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))

    services.obtener_mes(hogar_con_reglas, 2026, 3, hoy=date(2026, 3, 12))

    cerrados = BudgetMonth.objects.for_household(hogar_con_reglas).filter(
        status=BudgetMonth.CLOSED
    )
    assert [(m.year, m.month) for m in cerrados] == [(2026, 1), (2026, 2)]


def test_el_saldo_se_arrastra_de_un_cierre_al_siguiente(hogar_con_reglas):
    """§13.3: el mes siguiente arranca con el saldo arrastrado correcto."""
    enero = services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))
    TransactionFactory(
        household=hogar_con_reglas, budget_month=enero, amount=Decimal("3000.00"),
        date=date(2026, 1, 5),
        category=enero.lineas.get(kind="income").category,
    )
    cierre_enero = services.cerrar_mes(enero)

    febrero = services.materializar(hogar_con_reglas, 2026, 2)
    cierre_febrero = services.cerrar_mes(febrero)

    assert cierre_febrero.balance == cierre_enero.arrastre


def test_un_mes_ya_cerrado_no_se_cierra_dos_veces(hogar_con_reglas):
    mes = services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))
    services.cerrar_mes(mes)

    with pytest.raises(Exception):
        services.cerrar_mes(mes)


def test_editar_una_regla_no_altera_un_cierre_anterior(hogar_con_reglas):
    """§13.7: editar el alquiler en marzo no altera ningún cierre de enero."""
    enero = services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))
    cierre = services.cerrar_mes(enero)
    antes = cierre.egresos_presupuestados

    services.reemplazar_regla(
        hogar_con_reglas.budget_expenserule_set.first(),
        nuevo_importe=Decimal("1950.00"),
        desde=date(2026, 4, 1),
    )

    cierre.refresh_from_db()
    assert cierre.egresos_presupuestados == antes


# --- el comando de reserva ----------------------------------------------------


def test_el_comando_cierra_los_meses_vencidos_de_todos_los_hogares(hogar_con_reglas):
    """§2.3: la misma lógica, disponible sin una petición HTTP, para que el
    Plan 3 pueda enchufarle un cron o un correo sin extraerla de una vista."""
    from django.core.management import call_command

    services.obtener_mes(hogar_con_reglas, 2026, 1, hoy=date(2026, 1, 10))

    call_command("cerrar_meses_vencidos", "--hoy", "2026-03-12")

    assert MonthlyClose.unscoped.count() >= 1
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_month_cycle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.budget.services'`

- [x] **Step 3: Implementar `apps/budget/services.py`**

```python
"""El único módulo que cruza el ORM y el motor.

Lee modelos, llama a apps/budget/engine/ y escribe el resultado. Que la
frontera esté en un solo archivo es lo que la hace auditable de un vistazo.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.budget.engine import closing as motor_closing
from apps.budget.engine.money import centavos
from apps.budget.models import (
    DIAS_PARA_EL_CIERRE_AUTOMATICO,
    BudgetLine,
    BudgetMonth,
    ExpenseRule,
    IncomeSource,
    MesCerrado,
    MonthlyClose,
    Transaction,
)
from apps.budget.models.catalog import EXPENSE, INCOME


@dataclass(frozen=True)
class LineaProyectada:
    categoria_id: int          # nunca None: los ingresos usan la categoria de ingreso
    kind: str
    importe: Decimal
    origen: str          # "income" | "expense"
    origen_id: int
    nombre: str


@dataclass(frozen=True)
class ProyeccionDeMes:
    anio: int
    mes: int
    lineas: tuple
    total_ingresos: Decimal
    total_egresos: Decimal
    sobrante: Decimal


def _ultimo_dia(anio, mes):
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def historial_de_ingreso(fuente, hasta):
    """Los totales mensuales reales de esa fuente, del más antiguo al último.

    Es lo que alimenta el modo rolling_average del §4.1. Sin
    Transaction.income_source (desviación 4) no se podría calcular.
    """
    desde = date(hasta.year - 1, hasta.month, 1)
    filas = (
        Transaction.objects.for_household(fuente.household)
        .filter(income_source=fuente, date__gte=desde, date__lt=hasta)
        .values("budget_month__year", "budget_month__month")
        .annotate(total=Sum("amount"))
        .order_by("budget_month__year", "budget_month__month")
    )
    return [centavos(f["total"]) for f in filas]


def proyectar(hogar, anio, mes):
    """Un mes calculado desde las reglas vigentes, sin persistir nada."""
    primero = date(anio, mes, 1)
    categoria_de_ingreso = _categoria_de_ingreso(hogar)
    lineas = []

    for fuente in IncomeSource.objects.for_household(hogar):
        veces = len(fuente.ocurrencias_en(anio, mes))
        if not veces:
            continue
        cifra = fuente.cifra_del_mes(historial=historial_de_ingreso(fuente, primero))
        if cifra is None:
            # rolling_average sin historia: aún no hay datos, y no se inventa
            # un número. La interfaz lo dice con todas sus letras.
            continue
        lineas.append(
            LineaProyectada(
                categoria_id=categoria_de_ingreso.pk, kind=INCOME,
                importe=centavos(cifra * veces),
                origen="income", origen_id=fuente.pk, nombre=fuente.name,
            )
        )

    for regla in ExpenseRule.objects.for_household(hogar).select_related("category"):
        importe = regla.importe_del_mes(anio, mes)
        if importe <= 0:
            continue
        lineas.append(
            LineaProyectada(
                categoria_id=regla.category_id, kind=EXPENSE, importe=importe,
                origen="expense", origen_id=regla.pk, nombre=regla.name,
            )
        )

    ingresos = centavos(sum(l.importe for l in lineas if l.kind == INCOME))
    egresos = centavos(sum(l.importe for l in lineas if l.kind == EXPENSE))
    return ProyeccionDeMes(
        anio=anio, mes=mes, lineas=tuple(lineas),
        total_ingresos=ingresos, total_egresos=egresos,
        sobrante=centavos(ingresos - egresos),
    )


@transaction.atomic
def materializar(hogar, anio, mes):
    """Convierte la proyección de un mes en filas editables (§4.2)."""
    fila, creado = BudgetMonth.unscoped.get_or_create(
        household=hogar, year=anio, month=mes,
        defaults={"status": BudgetMonth.OPEN, "opened_at": timezone.now()},
    )
    # Bloquea la fila: dos pestañas abiertas el día 1 es el caso normal.
    fila = BudgetMonth.unscoped.select_for_update().get(pk=fila.pk)
    if fila.lineas.exists():
        return fila

    for proyectada in proyectar(hogar, anio, mes).lineas:
        linea = BudgetLine(
            household=hogar, budget_month=fila, kind=proyectada.kind,
            planned_amount=proyectada.importe,
            category_id=proyectada.categoria_id,
        )
        if proyectada.origen == "income":
            linea.source_income_id = proyectada.origen_id
        else:
            linea.source_expense_rule_id = proyectada.origen_id
        linea.save()
    return fila


def _categoria_de_ingreso(hogar):
    """La categoría donde caen las líneas de ingreso.

    Falla aquí y con su motivo si el hogar no tiene ninguna: un hogar sin
    árbol sembrado es un hogar mal creado (`crear_hogar` lo siembra), y
    devolver None haría reventar la proyección con un AttributeError lejos
    de la causa.
    """
    from apps.budget.models import Category

    categoria = Category.objects.for_household(hogar).filter(kind=INCOME).first()
    if categoria is None:
        raise LookupError(
            f"El hogar {hogar.pk} no tiene ninguna categoría de ingreso. "
            "¿Se creó sin pasar por households.services.crear_hogar, que "
            "siembra el árbol de apps/budget/seeds.py?"
        )
    return categoria


@transaction.atomic
def cerrar_mes(mes):
    """Escribe el MonthlyClose y congela el mes (§4.2)."""
    if mes.esta_cerrado:
        raise MesCerrado(f"El mes {mes} ya está cerrado.")

    reales = _reales_por_categoria(mes)

    renglones = []
    vistos = set()
    for linea in mes.lineas.all():
        clave = (linea.category_id, linea.kind)
        vistos.add(clave)
        renglones.append(
            motor_closing.Renglon(
                categoria_id=linea.category_id, kind=linea.kind,
                presupuestado=linea.planned_amount,
                real=reales.get(clave, Decimal("0.00")),
            )
        )
    # Lo real sin línea planeada (un gasto en una categoría que nadie
    # presupuestó) cuenta igual: si no, el balance no cuadraría.
    for clave, real in reales.items():
        if clave in vistos:
            continue
        renglones.append(
            motor_closing.Renglon(
                categoria_id=clave[0], kind=clave[1],
                presupuestado=Decimal("0.00"), real=real,
            )
        )

    cierre_calculado = motor_closing.cerrar(renglones, _arrastre_previo(mes))

    cierre = MonthlyClose(
        household=mes.household, budget_month=mes,
        ingresos_presupuestados=cierre_calculado.ingresos_presupuestados,
        ingresos_reales=cierre_calculado.ingresos_reales,
        egresos_presupuestados=cierre_calculado.egresos_presupuestados,
        egresos_reales=cierre_calculado.egresos_reales,
        varianza_por_categoria={str(k): str(v) for k, v in cierre_calculado.varianza_por_categoria.items()},
        balance=cierre_calculado.balance,
        arrastre=cierre_calculado.arrastre,
    )
    cierre.save()

    mes.status = BudgetMonth.CLOSED
    mes.closed_at = timezone.now()
    mes.save(update_fields=["status", "closed_at"])
    return cierre


def _reales_por_categoria(mes):
    reales = {}
    for tx in Transaction.objects.for_household(mes.household).filter(
        budget_month=mes
    ).select_related("category"):
        clave = (tx.category_id, tx.category.kind)
        reales[clave] = reales.get(clave, Decimal("0.00")) + tx.amount
    return {k: centavos(v) for k, v in reales.items()}


def _arrastre_previo(mes):
    anterior = (
        MonthlyClose.objects.for_household(mes.household)
        .filter(budget_month__year__lte=mes.year)
        .exclude(budget_month=mes)
        .order_by("-budget_month__year", "-budget_month__month")
        .first()
    )
    return anterior.arrastre if anterior else Decimal("0.00")


def _esta_vencido(mes, hoy):
    fin = _ultimo_dia(mes.year, mes.month)
    return hoy > fin + timedelta(days=DIAS_PARA_EL_CIERRE_AUTOMATICO)


def cerrar_vencidos(hogar, hoy=None):
    """Cierra en cadena, EN ORDEN, porque cada cierre arrastra su saldo."""
    hoy = hoy or timezone.localdate()
    cerrados = []
    abiertos = (
        BudgetMonth.objects.for_household(hogar)
        .filter(status=BudgetMonth.OPEN)
        .order_by("year", "month")
    )
    for mes in abiertos:
        if _esta_vencido(mes, hoy):
            cerrados.append(cerrar_mes(mes))
    return cerrados


def obtener_mes(hogar, anio, mes, hoy=None):
    """El único punto de entrada al ciclo del mes (§2.3).

    Cierra los vencidos, materializa el corriente, proyecta el futuro y
    devuelve el cierre congelado si ya pasó.
    """
    hoy = hoy or timezone.localdate()
    cerrar_vencidos(hogar, hoy)

    existente = BudgetMonth.objects.for_household(hogar).filter(year=anio, month=mes).first()
    if existente is not None:
        return existente

    if (anio, mes) > (hoy.year, hoy.month):
        return proyectar(hogar, anio, mes)

    return materializar(hogar, anio, mes)


@transaction.atomic
def reemplazar_regla(regla, nuevo_importe, desde):
    """§3.2: las reglas nunca se mutan.

    Subir el alquiler cierra la regla vieja con effective_to = el día anterior
    y crea su sucesora. El historial queda intacto sin un modelo adicional, y
    ningún mes ya cerrado cambia.
    """
    regla.effective_to = desde - timedelta(days=1)
    regla.save(update_fields=["effective_to"])

    sucesora = ExpenseRule(
        household=regla.household, category=regla.category, name=regla.name,
        amount=nuevo_importe, periodicity=regla.periodicity,
        effective_from=desde, is_essential=regla.is_essential,
        owner=regla.owner, scope=regla.scope,
    )
    sucesora.save()
    return sucesora
```

- [x] **Step 4: El comando de reserva**

`apps/budget/management/commands/cerrar_meses_vencidos.py`:

```python
"""Cierra los meses vencidos de todos los hogares.

§2.3: el disparador normal es entrar a la aplicación. Este comando existe
para que el Plan 3 pueda enchufar un cron o un correo de aviso sin extraer la
lógica de dentro de una vista. Hoy no lo llama nadie, y eso es correcto.
"""

from datetime import date

from django.core.management.base import BaseCommand

from apps.budget import services
from apps.households.models import Household


class Command(BaseCommand):
    help = "Cierra los meses vencidos de todos los hogares."

    def add_arguments(self, parser):
        parser.add_argument("--hoy", help="Fecha en formato AAAA-MM-DD, para pruebas.")

    def handle(self, *args, **opciones):
        hoy = date.fromisoformat(opciones["hoy"]) if opciones.get("hoy") else None
        total = 0
        for hogar in Household.objects.all():
            cerrados = services.cerrar_vencidos(hogar, hoy)
            total += len(cerrados)
            for cierre in cerrados:
                self.stdout.write(f"{hogar}: cerrado {cierre.budget_month}")
        self.stdout.write(self.style.SUCCESS(f"{total} meses cerrados."))
```

- [x] **Step 5: Ejecutar y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_month_cycle.py -q`
Expected: PASS — 14 pruebas.

- [x] **Step 6: Correr la suite entera y commitear**

```bash
.venv/Scripts/python.exe -m pytest -q
git add -A
git commit -m "Anade el ciclo del mes: proyeccion, materializacion y cierre"
```

Cuerpo: §4.2 y §4.4. El disparador es entrar: al pedir un mes se cierran en cadena los vencidos —en orden, porque cada cierre arrastra su saldo— y se materializa el corriente. Los meses futuros se proyectan sin persistir, para que cambiar el alquiler se refleje al instante en todos ellos (§2.3). `reemplazar_regla` cierra la regla vieja y crea su sucesora en vez de mutarla, así que editar el alquiler en marzo no altera ningún cierre de enero (§13.7).

---

### Task 13: `services.py` — planificar el mes y aplicar la cascada

**Files:**
- Modify: `apps/budget/services.py`
- Test: `tests/budget/test_services.py`

**Interfaces:**
- Consumes: `engine.cascade`, `engine.allowance`, `AllocationRule`, `MonthlyAllocation`, `AllowanceLedger`, `GoalContribution`
- Produce:
  - `miembros_activos(hogar) -> tuple[int, ...]`
  - `planificar_mes(hogar, mes, sobrante_proyectado) -> list[MonthlyAllocation]`
  - `aplicar_cascada_al_cierre(mes, sobrante_real) -> list[Ajuste]`
  - `gasto_personal_del_mes(membresia, mes) -> Decimal`
  - `mesada_de(membresia, mes) -> AllowanceLedger`

- [x] **Step 1: Escribir las pruebas**

`tests/budget/test_services.py`:

```python
"""La cascada aplicada a datos reales, y el libro mayor de la mesada."""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services
from apps.budget.engine.cascade import ALLOWANCE, FIXED, GOAL, REMAINDER
from apps.budget.models import AllowanceLedger, MonthlyAllocation
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    AllocationRuleFactory,
    BudgetMonthFactory,
    CategoryFactory,
    GoalFactory,
    TransactionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def hogar_con_cascada():
    """El ejemplo canónico del §4.5.2: ahorro fijo de $600, mesada el resto."""
    admin = UserFactory()
    hogar = crear_hogar(admin, "Family Thompson", family_size=2)
    otra = MembershipFactory(household=hogar)
    meta = GoalFactory(household=hogar, target_amount=Decimal("10000.00"))
    AllocationRuleFactory(
        household=hogar, order=1, target_type=GOAL, target_goal=meta,
        method=FIXED, amount=Decimal("600.00"),
    )
    AllocationRuleFactory(
        household=hogar, order=2, target_type=ALLOWANCE, method=REMAINDER,
        target_goal=None,
    )
    return hogar


def test_planificar_escribe_las_asignaciones_y_las_mesadas(hogar_con_cascada):
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)

    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))

    assert MonthlyAllocation.objects.for_household(hogar_con_cascada).count() == 3
    mesadas = AllowanceLedger.objects.for_household(hogar_con_cascada).filter(budget_month=mes)
    assert [m.granted for m in mesadas.order_by("member_id")] == [
        Decimal("100.00"), Decimal("100.00")
    ]


def test_cada_miembro_sabe_su_mesada_desde_el_dia_uno(hogar_con_cascada):
    """§13.5: cada uno sabe desde el día 1 cuánta mesada tiene."""
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))

    membresia = hogar_con_cascada.active_memberships().first()
    assert services.mesada_de(membresia, mes).saldo() == Decimal("100.00")


def test_planificar_dos_veces_no_duplica(hogar_con_cascada):
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))
    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))

    assert MonthlyAllocation.objects.for_household(hogar_con_cascada).count() == 3


def test_un_sobrante_negativo_no_genera_mesada(hogar_con_cascada):
    """§9."""
    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)

    services.planificar_mes(hogar_con_cascada, mes, Decimal("-100.00"))

    assert MonthlyAllocation.objects.for_household(hogar_con_cascada).count() == 0
    assert AllowanceLedger.objects.for_household(hogar_con_cascada).count() == 0


def test_el_faltante_ajusta_la_mesada_del_mes_siguiente(hogar_con_cascada):
    """§13.6, el ejemplo literal del §4.5.3: proyectado $800, real $720. El
    ahorro conserva sus $600; las mesadas de octubre bajan $40 cada una."""
    septiembre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    octubre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=10)
    services.planificar_mes(hogar_con_cascada, septiembre, Decimal("800.00"))

    services.aplicar_cascada_al_cierre(septiembre, Decimal("720.00"))

    ahorro = MonthlyAllocation.objects.for_household(hogar_con_cascada).get(
        budget_month=septiembre, member__isnull=True
    )
    assert ahorro.actual_amount == Decimal("600.00")

    ajustes = AllowanceLedger.objects.for_household(hogar_con_cascada).filter(
        budget_month=octubre
    )
    assert [a.adjustment for a in ajustes.order_by("member_id")] == [
        Decimal("-40.00"), Decimal("-40.00")
    ]


def test_la_mesada_ya_asignada_no_se_reduce_dentro_del_mes(hogar_con_cascada):
    """§9: de nada sirve enterarse el día 30 de que tenías $100 para gastar."""
    septiembre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=10)
    services.planificar_mes(hogar_con_cascada, septiembre, Decimal("800.00"))

    services.aplicar_cascada_al_cierre(septiembre, Decimal("720.00"))

    mesadas = AllowanceLedger.objects.for_household(hogar_con_cascada).filter(
        budget_month=septiembre
    )
    assert all(m.granted == Decimal("100.00") for m in mesadas)


def test_lo_gastado_con_ambito_personal_baja_la_mesada(hogar_con_cascada):
    septiembre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, septiembre, Decimal("800.00"))
    membresia = hogar_con_cascada.active_memberships().order_by("pk").first()
    TransactionFactory(
        household=hogar_con_cascada, budget_month=septiembre, member=membresia,
        scope="personal", amount=Decimal("30.00"), date=date(2026, 9, 5),
        category=CategoryFactory(household=hogar_con_cascada),
    )

    assert services.gasto_personal_del_mes(membresia, septiembre) == Decimal("30.00")


def test_un_gasto_del_hogar_no_baja_la_mesada(hogar_con_cascada):
    """§4.5.5: entretenimiento familiar ≠ mesada personal. Confundirlas es lo
    que hace que las parejas discutan por dinero."""
    septiembre = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, septiembre, Decimal("800.00"))
    membresia = hogar_con_cascada.active_memberships().order_by("pk").first()
    TransactionFactory(
        household=hogar_con_cascada, budget_month=septiembre, member=membresia,
        scope="household", amount=Decimal("30.00"), date=date(2026, 9, 5),
        category=CategoryFactory(household=hogar_con_cascada),
    )

    assert services.gasto_personal_del_mes(membresia, septiembre) == Decimal("0.00")


def test_la_cascada_aporta_a_la_meta(hogar_con_cascada):
    from apps.budget.models import GoalContribution

    mes = BudgetMonthFactory(household=hogar_con_cascada, year=2026, month=9)
    services.planificar_mes(hogar_con_cascada, mes, Decimal("800.00"))
    services.aplicar_cascada_al_cierre(mes, Decimal("800.00"))

    aporte = GoalContribution.objects.for_household(hogar_con_cascada).get()
    assert aporte.amount == Decimal("600.00")
    assert aporte.origen == "cascade"
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_services.py -q`
Expected: FAIL — `AttributeError: module 'apps.budget.services' has no attribute 'planificar_mes'`

- [x] **Step 3: Implementar**

Añadir a `apps/budget/services.py`:

```python
from apps.budget.engine import allowance as motor_allowance
from apps.budget.engine import cascade as motor_cascade
from apps.budget.models import (
    AllocationRule,
    AllowanceLedger,
    GoalContribution,
    MonthlyAllocation,
)


def miembros_activos(hogar):
    """Los miembros activos, por pk, para que el reparto sea determinista."""
    return tuple(hogar.active_memberships().order_by("pk").values_list("pk", flat=True))


def _reglas_del_motor(hogar):
    miembros = miembros_activos(hogar)
    return [
        regla.a_regla_de_reparto(miembros)
        for regla in AllocationRule.objects.for_household(hogar).filter(is_active=True)
    ]


def _mes_anterior(mes):
    anio, numero = (mes.year - 1, 12) if mes.month == 1 else (mes.year, mes.month - 1)
    return BudgetMonth.objects.for_household(mes.household).filter(
        year=anio, month=numero
    ).first()


def _mes_siguiente(mes):
    anio, numero = (mes.year + 1, 1) if mes.month == 12 else (mes.year, mes.month + 1)
    fila, _ = BudgetMonth.unscoped.get_or_create(
        household=mes.household, year=anio, month=numero,
        defaults={"status": BudgetMonth.OPEN, "opened_at": timezone.now()},
    )
    return fila


def mesada_de(membresia, mes):
    return mesada_de_por_id(mes.household, membresia.pk, mes)


def gasto_personal_del_mes(membresia, mes):
    """Lo gastado con ámbito personal por ese miembro en ese mes (§3.3).

    §4.5.5: no cuenta el entretenimiento familiar, que es un gasto fijo del
    hogar decidido al configurar. Confundirlos es lo que hace que las parejas
    discutan por dinero.
    """
    total = (
        Transaction.objects.for_household(mes.household)
        .filter(member=membresia, budget_month=mes, scope="personal")
        .aggregate(total=Sum("amount"))["total"]
    )
    return centavos(total or 0)


@transaction.atomic
def planificar_mes(hogar, mes, sobrante_proyectado):
    """Aplica la cascada y escribe el reparto y las mesadas del mes (§4.5.6).

    Al confirmar la planificación, cada miembro sabe desde el día 1 cuánta
    mesada tiene, y esa cifra ya no se mueve durante el mes.
    """
    if MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes).exists():
        return list(MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes))

    reglas_orm = {r.order: r for r in AllocationRule.objects.for_household(hogar).filter(is_active=True)}
    asignaciones = motor_cascade.repartir(sobrante_proyectado, _reglas_del_motor(hogar))

    escritas = []
    for asignacion in asignaciones:
        fila = MonthlyAllocation(
            household=hogar, budget_month=mes, rule=reglas_orm[asignacion.orden],
            planned_amount=asignacion.importe,
            member_id=asignacion.miembro_id,
        )
        fila.save()
        escritas.append(fila)

        if asignacion.miembro_id is not None:
            libro = mesada_de_por_id(hogar, asignacion.miembro_id, mes)
            libro.granted = asignacion.importe
            libro.carried_in = _carried_in(hogar, asignacion.miembro_id, mes)
            libro.save()

    return escritas


def mesada_de_por_id(hogar, membresia_id, mes):
    fila, _ = AllowanceLedger.unscoped.get_or_create(
        household=hogar, member_id=membresia_id, budget_month=mes
    )
    return fila


def _carried_in(hogar, membresia_id, mes):
    anterior = _mes_anterior(mes)
    if anterior is None:
        return Decimal("0.00")
    libro = AllowanceLedger.objects.for_household(hogar).filter(
        member_id=membresia_id, budget_month=anterior
    ).first()
    return libro.carried_out if libro else Decimal("0.00")


@transaction.atomic
def aplicar_cascada_al_cierre(mes, sobrante_real):
    """Ajusta el reparto a lo que de verdad sobró (§4.5.3).

    El faltante lo absorbe la última regla hacia arriba, pero la mesada ya
    asignada nunca se retira: su parte cae como ajuste del mes siguiente.
    """
    hogar = mes.household
    planeadas = list(MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes))
    planeado = [
        motor_cascade.Asignacion(a.rule.order, a.planned_amount, a.member_id)
        for a in planeadas
    ]

    finales, ajustes = motor_cascade.absorber_faltante(
        planeado, _reglas_del_motor(hogar), sobrante_real
    )

    por_clave = {(f.orden, f.miembro_id): f.importe for f in finales}
    for fila in planeadas:
        fila.actual_amount = por_clave.get(
            (fila.rule.order, fila.member_id), Decimal("0.00")
        )
        fila.save(update_fields=["actual_amount"])

        if fila.member_id is None and fila.rule.target_type == motor_cascade.GOAL:
            aporte = GoalContribution(
                household=hogar, goal=fila.rule.target_goal,
                amount=fila.actual_amount, date=_ultimo_dia(mes.year, mes.month),
                member=hogar.active_memberships().order_by("pk").first(),
                origen="cascade",
            )
            aporte.save()

    # El ajuste viaja al mes siguiente: la mesada de este mes ya se gastó.
    if ajustes:
        siguiente = _mes_siguiente(mes)
        for ajuste in ajustes:
            libro = mesada_de_por_id(hogar, ajuste.miembro_id, siguiente)
            libro.adjustment = centavos(libro.adjustment + ajuste.importe)
            libro.save(update_fields=["adjustment"])

    # Y se cierra el libro de este mes.
    for libro in AllowanceLedger.objects.for_household(hogar).filter(budget_month=mes):
        libro.spent = gasto_personal_del_mes(libro.member, mes)
        libro.carried_out = motor_allowance.carried_out(
            libro.saldo(), hogar.allowance_rollover
        )
        libro.save(update_fields=["spent", "carried_out"])

    return ajustes
```

Y engancharlo en `cerrar_mes`. Justo **despues** de `cierre_calculado = motor_closing.cerrar(...)` y **antes** de instanciar el `MonthlyClose`, inserta:

```python
    # El sobrante real del mes es lo que de verdad quedo, SIN el arrastre: el
    # saldo que venia de meses anteriores ya se repartio en su momento, y
    # volver a repartirlo daria mesada dos veces por el mismo dinero.
    sobrante_real = centavos(
        cierre_calculado.ingresos_reales - cierre_calculado.egresos_reales
    )
    aplicar_cascada_al_cierre(mes, sobrante_real)
```

- [x] **Step 4: Ejecutar, correr la suite y commitear**

```bash
.venv/Scripts/python.exe -m pytest tests/budget -q
.venv/Scripts/python.exe -m pytest -q
git add -A
git commit -m "Aplica la cascada al mes real y lleva el libro de la mesada"
```

Cuerpo: al planificar, cada miembro sabe desde el día 1 cuánta mesada tiene, y esa cifra ya no se mueve. Al cerrar, el faltante se absorbe desde la última regla hacia arriba y la parte que le tocaría a la mesada cae como ajuste del mes siguiente (§4.5.3, §13.6). Lo gastado con ámbito personal baja la mesada; el entretenimiento familiar no, porque es un gasto fijo del hogar decidido al configurar (§4.5.5).

---

### Task 14: Pantallas, tanda 1 — configurar el presupuesto

Primer uso real de `@requiere_permiso`. Formularios de Django planos sobre el CSS que ya existe: el Plan 3 rehace la presentación.

**Files:**
- Create: `apps/budget/forms.py`, `apps/budget/views.py`, `apps/budget/urls.py`, `templates/budget/configurar.html`, `templates/budget/formulario.html`
- Modify: `config/urls.py`, `templates/accounts/inicio.html`, `locale/{en,fr}/LC_MESSAGES/django.po`
- Test: `tests/budget/test_views.py`

**Interfaces:**
- Consumes: `HouseholdScopedModelForm`, `requiere_permiso`, los modelos de las Tareas 9-11.
- Produce:
  - `IncomeSourceForm`, `ExpenseRuleForm`, `CategoryForm`, `AllocationRuleForm` — todas `HouseholdScopedModelForm`.
  - Rutas bajo `/budget/`: `configurar`, `ingreso_nuevo`, `gasto_nuevo`, `categoria_nueva`, `reparto_nuevo`.
  - Nombres de URL: `budget:configurar`, `budget:ingreso_nuevo`, `budget:gasto_nuevo`, `budget:categoria_nueva`, `budget:reparto_nuevo`.

- [x] **Step 1: Escribir las pruebas**

`tests/budget/test_views.py`:

```python
"""Las pantallas mínimas, y los permisos que las gobiernan.

Primer uso real de @requiere_permiso: hasta el lote de puertas estaba probado
y no lo llamaba ningún código de producción. Aquí queda ejercitado el
adolescente del §6.2 — registra sus gastos y no ve la hipoteca.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.budget.models import ExpenseRule, IncomeSource
from apps.households.models import Membership
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import CategoryFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_con_hogar():
    user = UserFactory()
    hogar = crear_hogar(user, "Family Thompson", family_size=4)
    return user, hogar


def _miembro(hogar, **permisos):
    base = dict(can_view_budget=False, can_edit_budget=False,
                can_add_transactions=False, can_view_reports=False)
    base.update(permisos)
    return MembershipFactory(household=hogar, role=Membership.MEMBER, **base)


# --- los permisos gobiernan de verdad ----------------------------------------


def test_configurar_exige_can_edit_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    sin_permiso = _miembro(hogar, can_add_transactions=True)
    client.force_login(sin_permiso.user)

    respuesta = client.get(reverse("budget:configurar"))

    assert respuesta.status_code == 403


def test_el_403_de_presupuesto_esta_traducido(client, admin_con_hogar):
    """No una página en blanco: la deuda que el lote de puertas cerró."""
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar).user)

    respuesta = client.get(reverse("budget:configurar"))

    assert "You do not have permission" in respuesta.content.decode()


def test_quien_tiene_el_permiso_entra(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_edit_budget=True).user)

    assert client.get(reverse("budget:configurar")).status_code == 200


def test_un_anonimo_va_al_login(client):
    respuesta = client.get(reverse("budget:configurar"))

    assert respuesta.status_code == 302


# --- los formularios no filtran datos de otras familias ----------------------


def test_el_desplegable_de_categorias_solo_trae_las_del_hogar(client, admin_con_hogar):
    """La fuga del <select> que el lote de puertas cerró, verificada en una
    pantalla real."""
    admin, hogar = admin_con_hogar
    CategoryFactory(household=hogar, name="Hipoteca Thompson", slug="mi-rent")
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    CategoryFactory(household=ajeno, name="Hipoteca García", slug="su-rent")
    client.force_login(admin)

    html = client.get(reverse("budget:gasto_nuevo")).content.decode()

    assert "Hipoteca Thompson" in html
    assert "Hipoteca García" not in html


def test_no_se_puede_crear_un_gasto_contra_una_categoria_ajena(client, admin_con_hogar):
    """El <select> filtrado es cosmético: lo que importa es que el POST con
    un id ajeno tampoco pase."""
    admin, hogar = admin_con_hogar
    ajeno = crear_hogar(UserFactory(), "Family García", family_size=2)
    categoria_ajena = CategoryFactory(household=ajeno, slug="su-rent")
    client.force_login(admin)

    client.post(reverse("budget:gasto_nuevo"), {
        "category": categoria_ajena.pk, "name": "Intento",
        "amount": "100.00", "periodicity": "monthly",
        "effective_from": "2026-01-01", "scope": "household",
        "is_essential": "on",
    })

    assert not ExpenseRule.unscoped.filter(name="Intento").exists()


# --- crear las cosas ----------------------------------------------------------


def test_el_admin_crea_un_gasto_fijo(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent")
    client.force_login(admin)

    respuesta = client.post(reverse("budget:gasto_nuevo"), {
        "category": categoria.pk, "name": "Alquiler",
        "amount": "1800.00", "periodicity": "monthly",
        "effective_from": "2026-01-01", "scope": "household",
        "is_essential": "on",
    })

    assert respuesta.status_code == 302
    regla = ExpenseRule.objects.for_household(hogar).get(name="Alquiler")
    assert regla.amount == Decimal("1800.00")


def test_el_admin_crea_un_ingreso(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    membresia = hogar.active_memberships().first()
    client.force_login(admin)

    client.post(reverse("budget:ingreso_nuevo"), {
        "owner": membresia.pk, "name": "Sueldo", "source_type": "salary",
        "amount_type": "fixed", "amount": "3000.00",
        "periodicity": "monthly", "effective_from": "2026-01-01",
        "scope": "household",
    })

    assert IncomeSource.objects.for_household(hogar).filter(name="Sueldo").exists()


def test_la_pantalla_de_configuracion_lista_lo_creado(client, admin_con_hogar):
    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent")
    from tests.factories_budget import ExpenseRuleFactory

    ExpenseRuleFactory(household=hogar, category=categoria, name="Alquiler")
    client.force_login(admin)

    html = client.get(reverse("budget:configurar")).content.decode()

    assert "Alquiler" in html
```

- [x] **Step 2: Ejecutar y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q`
Expected: FAIL — `NoReverseMatch: 'budget' is not a registered namespace`

- [x] **Step 3: Escribir `apps/budget/forms.py`**

```python
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.households.scoped_forms import HouseholdScopedModelForm

from .models import AllocationRule, Category, ExpenseRule, Goal, IncomeSource, Transaction


class CategoryForm(HouseholdScopedModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "kind"]


class IncomeSourceForm(HouseholdScopedModelForm):
    class Meta:
        model = IncomeSource
        fields = [
            "owner", "name", "source_type", "amount_type",
            "amount", "amount_min", "amount_max",
            "periodicity", "effective_from", "effective_to", "scope",
        ]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `owner` es una Membership, que no hereda de HouseholdScoped, así que
        # la base no lo acota: hay que hacerlo aquí o el <select> traería los
        # miembros de todas las familias.
        self.fields["owner"].queryset = self.household.active_memberships()


class ExpenseRuleForm(HouseholdScopedModelForm):
    class Meta:
        model = ExpenseRule
        fields = [
            "category", "name", "amount", "periodicity",
            "effective_from", "effective_to", "is_essential", "owner", "scope",
        ]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False


class AllocationRuleForm(HouseholdScopedModelForm):
    class Meta:
        model = AllocationRule
        fields = [
            "order", "target_type", "target_goal", "target_category",
            "method", "amount", "percentage", "split", "is_active",
        ]
```

- [x] **Step 4: Escribir `apps/budget/views.py` y `urls.py`**

```python
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.households.permissions import requiere_permiso

from .forms import AllocationRuleForm, CategoryForm, ExpenseRuleForm, IncomeSourceForm
from .models import AllocationRule, Category, ExpenseRule, IncomeSource


@requiere_permiso("can_edit_budget")
def configurar(request, hogar):
    return render(request, "budget/configurar.html", {
        "ingresos": IncomeSource.objects.for_household(hogar).select_related("owner__user"),
        "gastos": ExpenseRule.objects.for_household(hogar).select_related("category"),
        "categorias": Category.objects.for_household(hogar).order_by("parent_id", "slug"),
        "repartos": AllocationRule.objects.for_household(hogar),
    })


def _crear(request, hogar, form_class, titulo):
    """Un formulario de alta, con el hogar acotado por la base segura."""
    form = form_class(request.POST or None, household=hogar)
    if request.method == "POST" and form.is_valid():
        objeto = form.save(commit=False)
        objeto.household = hogar
        objeto.full_clean()
        objeto.save()
        return redirect("budget:configurar")
    return render(request, "budget/formulario.html", {"form": form, "titulo": titulo})


@requiere_permiso("can_edit_budget")
def ingreso_nuevo(request, hogar):
    return _crear(request, hogar, IncomeSourceForm, _("New income"))


@requiere_permiso("can_edit_budget")
def gasto_nuevo(request, hogar):
    return _crear(request, hogar, ExpenseRuleForm, _("New fixed expense"))


@requiere_permiso("can_edit_budget")
def categoria_nueva(request, hogar):
    return _crear(request, hogar, CategoryForm, _("New category"))


@requiere_permiso("can_edit_budget")
def reparto_nuevo(request, hogar):
    return _crear(request, hogar, AllocationRuleForm, _("New split rule"))
```

**Nota:** `objeto.full_clean()` después de fijar el hogar es lo que hace que un POST con el id de una categoría ajena falle — el `clean()` del modelo comprueba el hogar. Si `full_clean` lanza `ValidationError`, hay que capturarlo y añadirlo al formulario:

```python
        from django.core.exceptions import ValidationError
        try:
            objeto.full_clean()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            objeto.save()
            return redirect("budget:configurar")
```

`apps/budget/urls.py`:

```python
from django.urls import path

from . import views

app_name = "budget"

urlpatterns = [
    path("", views.configurar, name="configurar"),
    path("income/new/", views.ingreso_nuevo, name="ingreso_nuevo"),
    path("expense/new/", views.gasto_nuevo, name="gasto_nuevo"),
    path("category/new/", views.categoria_nueva, name="categoria_nueva"),
    path("split/new/", views.reparto_nuevo, name="reparto_nuevo"),
]
```

En `config/urls.py`, antes del `include` de accounts:

```python
    path("budget/", include("apps.budget.urls")),
```

- [x] **Step 5: Escribir las plantillas**

`templates/budget/formulario.html`:

```html
{% extends "base.html" %}{% load i18n %}
{% block title %}{{ titulo }} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <h1>{{ titulo }}</h1>
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button class="btn btn--primary" type="submit">{% translate "Save" %}</button>
    <a href="{% url 'budget:configurar' %}">{% translate "Cancel" %}</a>
  </form>
</section>
{% endblock %}
```

`templates/budget/configurar.html`:

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "Set up the budget" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <h1>{% translate "Set up the budget" %}</h1>

  <h2>{% translate "Income" %}</h2>
  <ul>
    {% for fuente in ingresos %}
      <li>{{ fuente.name }} — {{ fuente.get_amount_type_display }}</li>
    {% empty %}
      <li>{% translate "No income yet." %}</li>
    {% endfor %}
  </ul>
  <a class="btn" href="{% url 'budget:ingreso_nuevo' %}">{% translate "Add income" %}</a>

  <h2>{% translate "Fixed expenses" %}</h2>
  <ul>
    {% for gasto in gastos %}
      <li>{{ gasto.name }} — {{ gasto.amount|money:hogar.currency }} · {{ gasto.get_periodicity_display }}</li>
    {% empty %}
      <li>{% translate "No fixed expenses yet." %}</li>
    {% endfor %}
  </ul>
  <a class="btn" href="{% url 'budget:gasto_nuevo' %}">{% translate "Add a fixed expense" %}</a>

  <h2>{% translate "How the leftover is split" %}</h2>
  <ol>
    {% for regla in repartos %}
      <li>{{ regla.get_target_type_display }} — {{ regla.get_method_display }}</li>
    {% empty %}
      <li>{% translate "No split rules yet." %}</li>
    {% endfor %}
  </ol>
  <a class="btn" href="{% url 'budget:reparto_nuevo' %}">{% translate "Add a split rule" %}</a>

  <h2>{% translate "Categories" %}</h2>
  <ul>
    {% for categoria in categorias %}<li>{{ categoria.etiqueta }}</li>{% endfor %}
  </ul>
  <a class="btn" href="{% url 'budget:categoria_nueva' %}">{% translate "Add a category" %}</a>
</section>
{% endblock %}
```

En `templates/accounts/inicio.html`, añadir el enlace **solo si el miembro puede**:

```html
  {% if perms_presupuesto %}
    <p><a href="{% url 'budget:configurar' %}">{% translate "Set up the budget" %}</a></p>
  {% endif %}
```

y en `apps/accounts/views.py::inicio`, pasar `perms_presupuesto`:

```python
@login_required
def inicio(request):
    from apps.households.permissions import membresia_actual

    try:
        membresia = membresia_actual(request)
    except PermissionDenied:
        membresia = None
    return render(request, "accounts/inicio.html", {
        "perms_presupuesto": bool(membresia and membresia.can_edit_budget),
    })
```

Un 403 al hacer clic es correcto pero grosero: el menú no ofrece lo que el miembro no puede hacer.

- [x] **Step 6: El catálogo bilingüe de esta tanda**

Recoge cada cadena nueva de `apps/budget/models/*.py`, `apps/budget/seeds.py`, `apps/budget/forms.py`, `apps/budget/views.py` y `templates/budget/*.html`, y añádelas a **los dos** `.po`. Son unas 60 cadenas: las etiquetas de las ocho periodicidades, los cinco modos de ingreso, los seis tipos de fuente, los cinco métodos de pago, los diecisiete nombres del árbol de categorías, los `verbose_name` de los trece modelos, y el texto de las plantillas.

Traducciones del árbol de categorías al francés canadiense, que son las que más se ven:

```
Housing → Logement          Rent → Loyer            Mortgage → Hypothèque
Utilities → Services publics    Water → Eau         Gas → Gaz
Electricity → Électricité   Internet → Internet     Subscriptions → Abonnements
Groceries → Épicerie        Transport → Transport   Fuel → Essence
Entertainment → Divertissement                      Bank loans → Prêts bancaires
Financial obligations → Obligations financières
Salary → Salaire            Other income → Autres revenus
```

Compila y comprueba:

```bash
MSGFMT="C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py"
for L in en fr; do .venv/Scripts/python.exe "$MSGFMT" -o "locale/$L/LC_MESSAGES/django.mo" "locale/$L/LC_MESSAGES/django.po"; done
.venv/Scripts/python.exe -m pytest tests/test_catalogo_exhaustivo.py tests/test_traducciones.py -q
```

Expected: PASS. Si falla, el mensaje nombra cada cadena que falta.

- [x] **Step 7: Ejecutar todo y commitear**

```bash
.venv/Scripts/python.exe -m pytest -q
git add -A
git commit -m "Anade la pantalla de configuracion del presupuesto"
```

Cuerpo: primer uso real de `@requiere_permiso`, que hasta el lote de puertas estaba probado y no lo llamaba ningún código de producción. El adolescente del §6.2 queda ejercitado: sin `can_edit_budget` recibe un 403 traducido, y el menú ni siquiera le ofrece el enlace — un 403 al hacer clic es correcto pero grosero. Los formularios heredan de `HouseholdScopedModelForm`, y una prueba comprueba en una pantalla real que el `<select>` de categorías no trae las de otra familia y que un POST con un id ajeno tampoco pasa.

---

### Task 15: Pantallas, tanda 2 — registrar un gasto y ver el mes

**Files:**
- Modify: `apps/budget/forms.py`, `apps/budget/views.py`, `apps/budget/urls.py`, los dos `.po`
- Create: `templates/budget/mes.html`, `templates/budget/gasto.html`
- Test: `tests/budget/test_views.py` (añadir)

**Interfaces:**
- Produce: `TransactionForm`, con `merchant_name` como texto libre y `TransactionForm.comercio()` que reutiliza o crea el `Merchant` por su nombre normalizado; rutas `budget:mes` (`/budget/month/`, y `/budget/month/<int:anio>/<int:numero>/`) y `budget:registrar` (`/budget/spend/`).

- [ ] **Step 1: Escribir las pruebas**

Añadir a `tests/budget/test_views.py`:

```python
# --- registrar un gasto: la acción más frecuente ------------------------------


def test_registrar_exige_can_add_transactions(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    assert client.get(reverse("budget:registrar")).status_code == 403


def test_el_adolescente_registra_su_gasto_sin_ver_la_hipoteca(client, admin_con_hogar):
    """§6.2 completo, en dos afirmaciones."""
    _, hogar = admin_con_hogar
    adolescente = _miembro(hogar, can_add_transactions=True)
    client.force_login(adolescente.user)

    assert client.get(reverse("budget:registrar")).status_code == 200
    assert client.get(reverse("budget:mes")).status_code == 403


def test_registrar_un_gasto_lo_guarda_en_el_mes_corriente(client, admin_con_hogar):
    from apps.budget.models import Transaction

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    respuesta = client.post(reverse("budget:registrar"), {
        "category": categoria.pk, "amount": "45.50",
        "date": "2026-09-05", "payment_method": "debit", "scope": "household",
        "note": "Metro",
    })

    assert respuesta.status_code == 302
    tx = Transaction.objects.for_household(hogar).get()
    assert tx.amount == Decimal("45.50")
    assert tx.member == hogar.active_memberships().get(user=admin)


def test_el_gasto_se_registra_a_nombre_de_quien_lo_teclea(client, admin_con_hogar):
    """`member` no es un campo del formulario: sale de la petición. Si lo
    fuera, cualquiera podría registrar gastos a nombre de otro."""
    from apps.budget.forms import TransactionForm

    assert "member" not in TransactionForm.base_fields


# --- ver el mes ---------------------------------------------------------------


def test_el_mes_exige_can_view_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_add_transactions=True).user)

    assert client.get(reverse("budget:mes")).status_code == 403


def test_el_mes_muestra_lo_planeado_y_lo_real(client, admin_con_hogar):
    from tests.factories_budget import ExpenseRuleFactory

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-rent", name="Alquiler")
    ExpenseRuleFactory(household=hogar, category=categoria, name="Alquiler",
                       amount=Decimal("1800.00"))
    client.force_login(admin)

    html = client.get(reverse("budget:mes")).content.decode()

    assert "1,800.00" in html or "1 800,00" in html


def test_un_mes_futuro_se_puede_consultar_y_no_persiste(client, admin_con_hogar):
    from apps.budget.models import BudgetMonth

    admin, hogar = admin_con_hogar
    client.force_login(admin)

    respuesta = client.get(reverse("budget:mes", args=[2030, 5]))

    assert respuesta.status_code == 200
    assert not BudgetMonth.objects.for_household(hogar).filter(year=2030).exists()


# --- el comercio se teclea, no se elige --------------------------------------


def _gasto(categoria, **extra):
    datos = {"category": categoria.pk, "amount": "45.50", "date": "2026-09-05",
             "payment_method": "debit", "scope": "household"}
    datos.update(extra)
    return datos


def test_teclear_un_comercio_nuevo_lo_crea(client, admin_con_hogar):
    from apps.budget.models import Merchant

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    client.post(reverse("budget:registrar"),
                _gasto(categoria, merchant_name="WALMART #3421"))

    assert Merchant.objects.for_household(hogar).get().normalized_name == "WALMART"


def test_teclear_una_variante_reutiliza_el_comercio_que_ya_existe(client, admin_con_hogar):
    """Para lo que existe engine/merchants.py: WALMART #3421 y walmart son el
    mismo comercio, y sin esto la lista se llenaria de duplicados en un mes."""
    from apps.budget.models import Merchant

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    client.post(reverse("budget:registrar"),
                _gasto(categoria, merchant_name="WALMART #3421"))
    client.post(reverse("budget:registrar"),
                _gasto(categoria, merchant_name="walmart"))

    assert Merchant.objects.for_household(hogar).count() == 1


def test_un_gasto_sin_comercio_se_guarda_igual(client, admin_con_hogar):
    """No todo gasto tiene comercio: una transferencia, un reembolso."""
    from apps.budget.models import Transaction

    admin, hogar = admin_con_hogar
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    client.post(reverse("budget:registrar"), _gasto(categoria, merchant_name=""))

    assert Transaction.objects.for_household(hogar).get().merchant is None


def test_el_comercio_de_otro_hogar_no_se_reutiliza(client, admin_con_hogar):
    """Dos familias que compran en el mismo Walmart tienen cada una su fila:
    fundirlas cruzaria el historial de gasto de dos hogares."""
    from apps.budget.models import Merchant
    from tests.factories_budget import MerchantFactory

    admin, hogar = admin_con_hogar
    ajeno = crear_hogar(UserFactory(), "Family Garcia", family_size=2)
    MerchantFactory(household=ajeno, name="Walmart")
    categoria = CategoryFactory(household=hogar, slug="mi-groceries")
    client.force_login(admin)

    client.post(reverse("budget:registrar"),
                _gasto(categoria, merchant_name="WALMART #3421"))

    assert Merchant.unscoped.count() == 2
```

- [ ] **Step 2: Verificar que falla, luego implementar**

Run: `.venv/Scripts/python.exe -m pytest tests/budget/test_views.py -q` → FAIL (`NoReverseMatch: budget:registrar`).

Añadir a `apps/budget/forms.py`:

```python
class TransactionForm(HouseholdScopedModelForm):
    """`member` y `budget_month` NO son campos: salen de la peticion y del
    ciclo del mes. Si `member` lo fuera, cualquiera podria registrar gastos a
    nombre de otro.

    `merchant` tampoco es un desplegable: nadie da de alta un comercio antes
    de comprar en el. Se teclea el nombre tal como aparece en el recibo y
    `Merchant.normalized_name` decide si es uno que ya existe — que es
    exactamente para lo que existe engine/merchants.py. Un `<select>` de
    comercios estaria vacio el primer dia y sería inservible el centesimo.
    """

    merchant_name = forms.CharField(
        label=_("Where"), max_length=120, required=False,
        help_text=_("Type it as it appears on the receipt."),
    )

    class Meta:
        model = Transaction
        fields = ["category", "income_source", "amount", "date",
                  "payment_method", "scope", "note"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def comercio(self):
        """El comercio tecleado, reutilizando el que ya exista en el hogar."""
        nombre = self.cleaned_data.get("merchant_name", "").strip()
        if not nombre:
            return None
        normalizado = normalizar(nombre)
        existente = Merchant.objects.for_household(self.household).filter(
            normalized_name=normalizado
        ).first()
        if existente is not None:
            return existente
        comercio = Merchant(household=self.household, name=nombre)
        comercio.save()
        return comercio
```

Los imports que esto añade a `apps/budget/forms.py`:

```python
from apps.budget.engine.merchants import normalizar

from .models import Merchant
```

Y `registrar` lo usa al guardar, entre fijar el hogar y fijar el miembro:

```python
        tx.merchant = form.comercio()
```

Añadir a `apps/budget/views.py`:

```python
from django.utils import timezone

from apps.households.permissions import membresia_actual

from . import services
from .forms import TransactionForm


@requiere_permiso("can_add_transactions")
def registrar(request, hogar):
    """La acción más frecuente de la aplicación (§7.1)."""
    hoy = timezone.localdate()
    form = TransactionForm(request.POST or None, household=hogar,
                           initial={"date": hoy})
    if request.method == "POST" and form.is_valid():
        mes = services.obtener_mes(hogar, hoy.year, hoy.month)
        tx = form.save(commit=False)
        tx.household = hogar
        tx.budget_month = mes
        tx.member = membresia_actual(request)
        tx.full_clean()
        tx.save()
        return redirect("budget:registrar")
    return render(request, "budget/gasto.html", {"form": form})


@requiere_permiso("can_view_budget")
def mes(request, hogar, anio=None, numero=None):
    hoy = timezone.localdate()
    anio = anio or hoy.year
    numero = numero or hoy.month
    resultado = services.obtener_mes(hogar, anio, numero)
    return render(request, "budget/mes.html", {
        "resultado": resultado,
        "es_proyeccion": isinstance(resultado, services.ProyeccionDeMes),
        "anio": anio, "numero": numero,
    })
```

Rutas:

```python
    path("spend/", views.registrar, name="registrar"),
    path("month/", views.mes, name="mes"),
    path("month/<int:anio>/<int:numero>/", views.mes, name="mes"),
```

`templates/budget/gasto.html` reutiliza el patrón de `formulario.html` con el título `{% translate "Record a spend" %}`.

`templates/budget/mes.html`:

```html
{% extends "base.html" %}{% load i18n money %}
{% block title %}{% translate "This month" %} · Wealthome{% endblock %}
{% block content %}
<section class="card">
  <h1>{{ anio }}-{{ numero }}</h1>
  {% if es_proyeccion %}
    <p>{% translate "This month has not started yet — these numbers come from your rules." %}</p>
    <table>
      {% for linea in resultado.lineas %}
        <tr><td>{{ linea.nombre }}</td><td>{{ linea.importe|money:hogar.currency }}</td></tr>
      {% endfor %}
    </table>
    <p>{% translate "Left over" %}: {{ resultado.sobrante|money:hogar.currency }}</p>
  {% else %}
    <table>
      <tr><th>{% translate "Category" %}</th><th>{% translate "Planned" %}</th></tr>
      {% for linea in resultado.lineas.all %}
        <tr>
          <td>{{ linea.category.etiqueta }}</td>
          <td>{{ linea.planned_amount|money:hogar.currency }}</td>
        </tr>
      {% endfor %}
    </table>
    <h2>{% translate "What actually happened" %}</h2>
    <table>
      {% for tx in resultado.transacciones.all %}
        <tr><td>{{ tx.date }}</td><td>{{ tx.category.etiqueta }}</td>
            <td>{{ tx.amount|money:hogar.currency }}</td></tr>
      {% empty %}
        <tr><td>{% translate "Nothing recorded yet." %}</td></tr>
      {% endfor %}
    </table>
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 3: El catálogo de esta tanda, la suite y el commit**

Añade las cadenas nuevas a los dos `.po`, compila, y corre:

```bash
.venv/Scripts/python.exe -m pytest -q
git add -A
git commit -m "Anade registrar un gasto y la pantalla del mes"
```

---

### Task 16: Pantallas, tanda 3 — planificar el mes, cerrarlo y las metas

**Files:**
- Modify: `apps/budget/forms.py`, `apps/budget/views.py`, `apps/budget/urls.py`, los dos `.po`
- Create: `templates/budget/planificar.html`, `templates/budget/cerrar.html`, `templates/budget/metas.html`
- Test: `tests/budget/test_views.py` (añadir)

**Interfaces:**
- Produce: `GoalForm`, `GoalContributionForm`; rutas `budget:planificar`, `budget:cerrar`, `budget:metas`, `budget:meta_nueva`, `budget:aportar`.

- [ ] **Step 1: Escribir las pruebas**

Añadir a `tests/budget/test_views.py`:

```python
# --- planificar el mes (§4.5.6) -----------------------------------------------


@pytest.fixture
def hogar_listo_para_planificar(admin_con_hogar):
    from apps.budget.engine.cascade import ALLOWANCE, FIXED, GOAL, REMAINDER
    from tests.factories_budget import (
        AllocationRuleFactory, ExpenseRuleFactory, GoalFactory, IncomeSourceFactory,
    )

    admin, hogar = admin_con_hogar
    membresia = hogar.active_memberships().first()
    IncomeSourceFactory(household=hogar, owner=membresia, amount=Decimal("3000.00"))
    ExpenseRuleFactory(household=hogar, amount=Decimal("1800.00"),
                       category=CategoryFactory(household=hogar, slug="mi-rent"))
    meta = GoalFactory(household=hogar, target_amount=Decimal("10000.00"))
    AllocationRuleFactory(household=hogar, order=1, target_type=GOAL,
                          target_goal=meta, method=FIXED, amount=Decimal("600.00"))
    AllocationRuleFactory(household=hogar, order=2, target_type=ALLOWANCE,
                          method=REMAINDER, target_goal=None)
    return admin, hogar


def test_planificar_muestra_el_sobrante_y_la_mesada(client, hogar_listo_para_planificar):
    """§13.5: la pareja ve su sobrante repartido y cada uno sabe su mesada."""
    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)

    html = client.get(reverse("budget:planificar")).content.decode()

    assert "1,200.00" in html or "1 200,00" in html   # el sobrante proyectado


def test_confirmar_la_planificacion_escribe_las_mesadas(client, hogar_listo_para_planificar):
    from apps.budget.models import AllowanceLedger

    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)

    respuesta = client.post(reverse("budget:planificar"))

    assert respuesta.status_code == 302
    assert AllowanceLedger.objects.for_household(hogar).exists()


def test_planificar_exige_can_edit_budget(client, hogar_listo_para_planificar):
    _, hogar = hogar_listo_para_planificar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    assert client.get(reverse("budget:planificar")).status_code == 403


# --- cerrar el mes ------------------------------------------------------------


def test_cerrar_el_mes_escribe_el_cierre(client, hogar_listo_para_planificar):
    from apps.budget.models import MonthlyClose

    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)
    client.post(reverse("budget:planificar"))

    respuesta = client.post(reverse("budget:cerrar"))

    assert respuesta.status_code == 302
    assert MonthlyClose.objects.for_household(hogar).exists()


def test_un_mes_cerrado_es_de_solo_lectura(client, hogar_listo_para_planificar):
    """§4.3: un mes cerrado no admite nada."""
    admin, hogar = hogar_listo_para_planificar
    client.force_login(admin)
    client.post(reverse("budget:planificar"))
    client.post(reverse("budget:cerrar"))

    respuesta = client.post(reverse("budget:cerrar"))

    assert respuesta.status_code in (302, 409)
    from apps.budget.models import MonthlyClose

    assert MonthlyClose.objects.for_household(hogar).count() == 1


# --- metas --------------------------------------------------------------------


def test_las_metas_muestran_su_dato_derivado(client, admin_con_hogar):
    from apps.budget.engine.goals import BY_TARGET_DATE
    from tests.factories_budget import GoalFactory

    admin, hogar = admin_con_hogar
    GoalFactory(household=hogar, name="Vacaciones",
                contribution_mode=BY_TARGET_DATE,
                target_amount=Decimal("7200.00"),
                target_date=date(2027, 6, 30))
    client.force_login(admin)

    html = client.get(reverse("budget:metas")).content.decode()

    assert "Vacaciones" in html


def test_aportar_a_una_meta_exige_can_edit_budget(client, admin_con_hogar):
    _, hogar = admin_con_hogar
    client.force_login(_miembro(hogar, can_view_budget=True).user)

    assert client.get(reverse("budget:aportar")).status_code == 403
```

(Añade `from datetime import date` al principio del archivo de pruebas.)

- [ ] **Step 2: Implementar**

`apps/budget/views.py`:

```python
@requiere_permiso("can_edit_budget")
def planificar(request, hogar):
    """El asistente del §4.5.6, en una sola pantalla.

    Los tres pasos del spec —ingresos, salidas, reparto— se presentan juntos
    porque el Plan 3 rehará la navegación; lo que importa aquí es que el
    cálculo y la escritura sean los definitivos.
    """
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    proyeccion = services.proyectar(hogar, hoy.year, hoy.month)

    if request.method == "POST":
        services.planificar_mes(hogar, mes_actual, proyeccion.sobrante)
        return redirect("budget:mes")

    reglas = [
        r.a_regla_de_reparto(services.miembros_activos(hogar))
        for r in AllocationRule.objects.for_household(hogar).filter(is_active=True)
    ]
    from apps.budget.engine.cascade import repartir

    return render(request, "budget/planificar.html", {
        "proyeccion": proyeccion,
        "asignaciones": repartir(proyeccion.sobrante, reglas),
        "mes": mes_actual,
    })


@requiere_permiso("can_edit_budget")
def cerrar(request, hogar):
    hoy = timezone.localdate()
    mes_actual = services.obtener_mes(hogar, hoy.year, hoy.month)
    if request.method == "POST":
        from apps.budget.models import MesCerrado

        try:
            services.cerrar_mes(mes_actual)
        except MesCerrado:
            pass   # ya estaba cerrado: idempotente, no un error del usuario
        return redirect("budget:mes")
    return render(request, "budget/cerrar.html", {"mes": mes_actual})


@requiere_permiso("can_view_budget")
def metas(request, hogar):
    from .models import Goal

    filas = []
    for meta in Goal.objects.for_household(hogar):
        aporte, fecha = meta.derivar()
        filas.append({"meta": meta, "aporte": aporte, "fecha": fecha,
                      "acumulado": meta.acumulado()})
    return render(request, "budget/metas.html", {"filas": filas})


@requiere_permiso("can_edit_budget")
def meta_nueva(request, hogar):
    from .forms import GoalForm

    return _crear(request, hogar, GoalForm, _("New goal"))


@requiere_permiso("can_edit_budget")
def aportar(request, hogar):
    from .forms import GoalContributionForm

    form = GoalContributionForm(request.POST or None, household=hogar)
    if request.method == "POST" and form.is_valid():
        aporte = form.save(commit=False)
        aporte.household = hogar
        aporte.member = membresia_actual(request)
        aporte.full_clean()
        aporte.save()
        return redirect("budget:metas")
    return render(request, "budget/formulario.html",
                  {"form": form, "titulo": _("Add to a goal")})
```

Formularios:

```python
class GoalForm(HouseholdScopedModelForm):
    class Meta:
        model = Goal
        fields = ["name", "scope", "owner", "contribution_mode",
                  "target_amount", "target_date", "monthly_amount"]
        widgets = {"target_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = self.household.active_memberships()
        self.fields["owner"].required = False


class GoalContributionForm(HouseholdScopedModelForm):
    class Meta:
        model = GoalContribution
        fields = ["goal", "amount", "date"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}
```

Rutas: `plan/`, `close/`, `goals/`, `goals/new/`, `goals/contribute/`.

`templates/budget/planificar.html` muestra el sobrante proyectado, la cascada aplicada y la mesada resultante por miembro, con un botón `{% translate "Confirm the plan" %}`. `templates/budget/cerrar.html` pide confirmación con `{% translate "Close the month" %}`. `templates/budget/metas.html` lista cada meta con su acumulado, su aporte mensual derivado y su fecha.

- [ ] **Step 3: El catálogo, la suite y el commit**

```bash
.venv/Scripts/python.exe -m pytest -q
git add -A
git commit -m "Anade planificar el mes, cerrarlo y las metas"
```

---

### Task 17: La batería de aislamiento y los criterios de aceptación

**Files:**
- Create: `tests/budget/test_aislamiento.py`, `tests/budget/test_aceptacion.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: todo lo anterior.
- Produce: la evidencia de que los diez criterios de aceptación del spec se cumplen.

- [ ] **Step 1: Escribir la batería de aislamiento**

`tests/budget/test_aislamiento.py`:

```python
"""Ningún endpoint devuelve datos de otro hogar (§9, §13.10).

"Esta es la clase de bug que no se descubre en desarrollo": una familia que
ve las finanzas de otra no lanza ningún error, y quien lo sufre no lo reporta
porque no sabe que está pasando.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.households.services import crear_hogar
from tests.factories import UserFactory
from tests.factories_budget import CategoryFactory, ExpenseRuleFactory, GoalFactory

pytestmark = pytest.mark.django_db

RUTAS_DE_LECTURA = [
    "budget:configurar", "budget:mes", "budget:metas",
    "budget:registrar", "budget:planificar", "budget:ingreso_nuevo",
    "budget:gasto_nuevo", "budget:categoria_nueva", "budget:reparto_nuevo",
    "budget:meta_nueva", "budget:aportar",
]


@pytest.fixture
def dos_hogares():
    thompson = crear_hogar(UserFactory(), "Family Thompson", family_size=4)
    garcia = crear_hogar(UserFactory(), "Family García", family_size=3)

    ExpenseRuleFactory(household=garcia, name="SECRETO-GARCIA",
                       category=CategoryFactory(household=garcia, slug="su-rent"),
                       amount=Decimal("4321.99"))
    GoalFactory(household=garcia, name="META-SECRETA-GARCIA")
    CategoryFactory(household=garcia, name="CATEGORIA-SECRETA-GARCIA", slug="su-cat")
    return thompson, garcia


@pytest.mark.parametrize("nombre", RUTAS_DE_LECTURA)
def test_ninguna_pantalla_filtra_datos_del_otro_hogar(client, dos_hogares, nombre):
    thompson, _ = dos_hogares
    client.force_login(thompson.active_memberships().first().user)

    html = client.get(reverse(nombre)).content.decode()

    assert "SECRETO-GARCIA" not in html
    assert "META-SECRETA-GARCIA" not in html
    assert "CATEGORIA-SECRETA-GARCIA" not in html
    assert "4,321.99" not in html and "4 321,99" not in html


def test_todo_modelo_del_motor_esta_acotado():
    """La guardia del lote de puertas, aplicada a los trece modelos nuevos."""
    from apps.budget import models as m
    from apps.households.scoping import HouseholdScoped

    esperados = [
        m.Category, m.Merchant, m.IncomeSource, m.ExpenseRule, m.BudgetMonth,
        m.BudgetLine, m.MonthlyClose, m.Transaction, m.Goal, m.GoalContribution,
        m.AllocationRule, m.MonthlyAllocation, m.AllowanceLedger,
    ]
    assert len(esperados) == 13
    for modelo in esperados:
        assert issubclass(modelo, HouseholdScoped), modelo.__name__
        assert modelo._meta.base_manager_name == "unscoped", modelo.__name__
        with pytest.raises(RuntimeError):
            list(modelo.objects.all())
```

- [ ] **Step 2: Escribir los criterios de aceptación de punta a punta**

`tests/budget/test_aceptacion.py`: una prueba por cada uno de los diez criterios del §10 del diseño del Plan 2, escritas contra los servicios y el cliente de pruebas. Las que ya están cubiertas por pruebas anteriores se escriben aquí igualmente, en su forma de extremo a extremo, porque son el contrato del plan:

```python
"""Los diez criterios de aceptación del §10 del diseño del Plan 2."""

from datetime import date
from decimal import Decimal

import pytest

from apps.budget import services
from apps.budget.engine.income import RANGE
from apps.budget.models import AllowanceLedger, MonthlyClose
from apps.households.services import crear_hogar
from tests.factories import MembershipFactory, UserFactory
from tests.factories_budget import (
    CategoryFactory, ExpenseRuleFactory, IncomeSourceFactory, TransactionFactory,
)

pytestmark = pytest.mark.django_db


def test_criterio_2_un_ingreso_range_presupuesta_el_minimo_y_el_exceso_es_superavit():
    """§13.4."""
    hogar = crear_hogar(UserFactory(), "Thompson", family_size=2)
    fuente = IncomeSourceFactory(
        household=hogar, owner=hogar.active_memberships().first(),
        amount_type=RANGE, amount_min=Decimal("800.00"), amount_max=Decimal("2400.00"),
        effective_from=date(2026, 1, 1),
    )
    mes = services.obtener_mes(hogar, 2026, 1, hoy=date(2026, 1, 10))
    TransactionFactory(
        household=hogar, budget_month=mes, amount=Decimal("2400.00"),
        date=date(2026, 1, 20), income_source=fuente,
        category=mes.lineas.get(kind="income").category,
        member=hogar.active_memberships().first(),
    )

    cierre = services.cerrar_mes(mes)

    assert cierre.ingresos_presupuestados == Decimal("800.00")
    assert cierre.ingresos_reales == Decimal("2400.00")
    assert cierre.balance == Decimal("2400.00")


def test_criterio_5_editar_el_alquiler_en_marzo_no_altera_enero():
    """§13.7."""
    hogar = crear_hogar(UserFactory(), "Thompson", family_size=2)
    regla = ExpenseRuleFactory(
        household=hogar, amount=Decimal("1800.00"),
        category=CategoryFactory(household=hogar, slug="mi-rent"),
        effective_from=date(2026, 1, 1),
    )
    enero = services.obtener_mes(hogar, 2026, 1, hoy=date(2026, 1, 10))
    cierre_enero = services.cerrar_mes(enero)
    antes = cierre_enero.egresos_presupuestados

    services.reemplazar_regla(regla, Decimal("1950.00"), desde=date(2026, 4, 1))

    cierre_enero.refresh_from_db()
    assert cierre_enero.egresos_presupuestados == antes
    assert services.proyectar(hogar, 2026, 5).total_egresos == Decimal("1950.00")


def test_criterio_9_tres_quincenas_y_un_seguro_anual():
    """La decisión §2.2, de punta a punta."""
    from apps.budget.engine.periodicity import ANNUAL, BIWEEKLY

    hogar = crear_hogar(UserFactory(), "Thompson", family_size=2)
    IncomeSourceFactory(
        household=hogar, owner=hogar.active_memberships().first(),
        amount=Decimal("1400.00"), periodicity=BIWEEKLY,
        effective_from=date(2026, 1, 2),
    )
    ExpenseRuleFactory(
        household=hogar, amount=Decimal("1200.00"), periodicity=ANNUAL,
        category=CategoryFactory(household=hogar, slug="mi-insurance"),
        effective_from=date(2026, 8, 15),
    )

    enero = services.proyectar(hogar, 2026, 1)      # tres quincenas
    julio = services.proyectar(hogar, 2026, 7)
    agosto = services.proyectar(hogar, 2026, 8)     # el seguro

    assert enero.total_ingresos == Decimal("4200.00")
    assert julio.total_egresos == Decimal("0.00")
    assert agosto.total_egresos == Decimal("1200.00")
```

Escribe del mismo modo los criterios 1, 3, 4, 6, 7, 8 y 10 — el 6 (el arrastre entre meses), el 4 (el faltante que ajusta la mesada del mes siguiente sin retirar nada) y el 10 (la aplicación en francés, comprobando que un importe se renderiza `2 847,50 $`) son los que más valor tienen, porque cruzan varias tareas.

- [ ] **Step 3: Correr todo, incluida una corrida limpia**

```bash
.venv/Scripts/python.exe -m pytest -q --create-db
```

Expected: PASS. Una corrida con `--create-db` es la única que demuestra que las migraciones acumuladas del plan construyen el esquema desde cero.

- [ ] **Step 4: Actualizar el README**

Añade al `README.md` una sección "El motor financiero" con: cómo correr solo el motor (`pytest tests/budget/engine -q`), la nota de que `apps/budget/engine/` no importa el ORM y por qué, el comando `cerrar_meses_vencidos` y para qué existe, y las cinco desviaciones del spec de la Fase 1 con un enlace al diseño del Plan 2.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Anade la bateria de aislamiento y los criterios de aceptacion"
```

Cuerpo: la batería recorre cada pantalla nueva con un usuario del hogar Thompson y comprueba que ni un dato del hogar García aparece en el HTML — "esta es la clase de bug que no se descubre en desarrollo", porque una familia que ve las finanzas de otra no lanza ningún error y quien lo sufre no sabe que está pasando. Los diez criterios del §10 quedan escritos como pruebas de punta a punta.

---

## Cierre del plan

Al terminar la Tarea 17:

- Los trece modelos, el motor y seis pantallas funcionan de punta a punta.
- Las pruebas del §9 del diseño de la Fase 1 están todas escritas y en verde.
- La aplicación se puede usar a mano en inglés y en francés.
- Lo que queda para el Plan 3: Stripe y la suscripción (§5), el Overview con gráficas, Balance, Goals con progreso visual, la navegación móvil, htmx, Chart.js, el neomorfismo del §7.3 y la PWA.

**Antes de integrar,** invoca `superpowers:requesting-code-review` sobre la rama completa y `superpowers:finishing-a-development-branch` para decidir cómo integrarla.
