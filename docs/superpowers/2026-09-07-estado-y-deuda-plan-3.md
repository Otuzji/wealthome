# Wealthome — Estado al cerrar el Plan 2, y la deuda que hereda el Plan 3

**Fecha:** 2026-09-07
**Rama:** `main`, commit de integración `4c31bdf`
**Pruebas:** 413 en verde (264 en `tests/budget`, 149 en el resto), verificadas sobre el
resultado ya mergeado y sobre un esquema construido desde cero con `--create-db`.

Este documento existe por la misma razón que el del Plan 1: el espacio de trabajo del
Plan 2 se retiró al integrarlo. Lo que hay aquí son decisiones y hallazgos que **no se
deducen leyendo el código**. La deuda de la sección 3 sale de una revisión de rama
completa hecha antes de integrar; sus tres fallos Críticos ya están arreglados y no
aparecen aquí, salvo como lección.

---

## 1. Qué está construido

El **Plan 2 (el motor financiero)** completo: 17 tareas, 30 commits.

- `apps/budget/engine/` — **cálculo puro, sin ORM.** `money.py` (el único punto de
  redondeo), `periodicity.py` (ocho periodicidades por calendario real), `income.py`
  (cinco modos de ingreso variable), `cascade.py` (reparto del sobrante y absorción del
  faltante), `closing.py`, `allowance.py`, `goals.py`, `merchants.py`.
- `apps/budget/models/` — los trece modelos, todos `HouseholdScoped`, en cuatro
  migraciones.
- `apps/budget/services.py` — **el único módulo que cruza ORM y motor.** Ciclo del mes
  (proyectar → materializar → cerrar en cadena con arrastre), `reemplazar_regla`, la
  cascada aplicada a datos reales y el libro mayor de la mesada.
- `apps/budget/{forms,views,urls}.py` y `templates/budget/` — seis pantallas:
  configurar, el mes, registrar un gasto, planificar, cerrar y metas.
- `apps/budget/management/commands/cerrar_meses_vencidos.py` — existe para quien pueda
  programarlo; **no** es el disparador principal, que es entrar.
- Catálogos `en`/`fr` al día, escritos a mano y compilados con `Tools/i18n/msgfmt.py`.

**Lo que NO existe todavía:** Stripe y la suscripción (§5 del spec), el Overview con
gráficas, la pantalla de Balance, el progreso visual de las metas, la navegación móvil,
htmx, Chart.js, el neomorfismo del §7.3 y la PWA. Eso es el Plan 3.

### Cómo arrancarlo

```
cd C:\Users\otton\OneDrive\Documents\Wealthome
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

`.env` está en la raíz, ignorado por git, con la cadena del pooler de Supabase.

---

## 2. Las tres decisiones del Plan 2 que hay que respetar

No son deuda: son las que sostienen todo lo demás, y romperlas por comodidad en el
Plan 3 costaría caro.

1. **`apps/budget/engine/` no importa Django.** Es lo que permite probar la aritmética
   del dinero sin base de datos, en segundos en vez de minutos.
   `tests/budget/engine/test_pureza.py` lo vigila, e incluye una prueba de la prueba.
2. **El aislamiento por hogar es una barrera, no una convención.**
   `Modelo.objects.all()` lanza `RuntimeError`; la única entrada es
   `.objects.for_household(hogar)`, y `unscoped` es la salida de emergencia explícita.
   Los formularios heredan de `HouseholdScopedModelForm`, que acota **el render y la
   validación**: filtrar solo el render sería cosmético.
3. **Las reglas nunca se mutan.** Subir el alquiler cierra la regla vieja con
   `effective_to` y crea su sucesora (`services.reemplazar_regla`). Por eso editar el
   alquiler en marzo no altera ningún cierre de enero. Y `MonthlyClose` lanza si ya
   tiene `pk`: un balance que se puede reescribir no es un balance.

---

## 3. La deuda que hereda el Plan 3

Ordenada por lo que cuesta dejarla sin hacer. Nada de esto bloquea el uso de la
aplicación hoy, y nada de esto se arregló al integrar porque ampliar el alcance sin
decirlo no toca.

### 3.1 Datos que salen mal o pueden reventar

- **Los aportes de la cascada se atribuyen a un miembro arbitrario.**
  `services.py::aplicar_cascada_al_cierre` escribe `GoalContribution` con
  `member=hogar.active_memberships().order_by("pk").first()`. Un ahorro **del hogar**
  queda a nombre de quien tenga el `pk` más bajo: un dato falso en el historial de
  metas. Y si no hay membresías activas, `member=None` sobre una FK no anulable revienta
  con `IntegrityError` en medio del cierre. Lo correcto es que `GoalContribution.member`
  sea anulable para el origen `cascade`.
- **Faltan dos de las cuatro guardias de mes cerrado del §5.7.** Solo `BudgetLine` y
  `Transaction` heredan `EscrituraAcotadaAlMes`. `MonthlyAllocation` tiene mes y no la
  hereda; `GoalContribution` ni siquiera tiene mes, así que **`budget:aportar` escribe
  contra un mes cerrado sin que nada lo impida**. Es una desviación no declarada del
  diseño.
- **`repartir_proporcional` da un centavo a un miembro con peso cero.** Verificado:
  `repartir_proporcional(Decimal("0.03"), [0, 1, 1])` → `[0.01, 0.01, 0.01]`. El bucle
  de sobrantes reparte por índice sin mirar el peso. La prueba que existe no lo detecta
  porque su caso no deja centavos sueltos.
- **`planificar_mes` no está protegido contra doble envío.** Comprueba `exists()` y
  escribe, sin `select_for_update` ni restricción única sobre
  `(budget_month, rule, member)`. Dos clics en «Confirmar el plan» pueden duplicar
  mesadas. `cerrar_mes` tampoco toma el `select_for_update` que el §6 exige;
  `materializar` sí.
- **`reemplazar_regla` solo sirve para `ExpenseRule`** pese a su nombre y a la firma
  genérica del §5.2: pasarle un `IncomeSource` da `AttributeError`. Además se salta
  `full_clean()`, así que un `desde <= effective_from` deja la regla vieja con
  `effective_to < effective_from`, y `ocurrencias()` la hace desaparecer de **todos** los
  meses.
- **No hay migración de datos que siembre el catálogo en hogares preexistentes.**
  `sembrar()` solo corre dentro de `crear_hogar`. Cualquier hogar creado antes del Plan 2
  hará estallar `_categoria_de_ingreso` con su `LookupError`. Si la base ya tiene hogares,
  hace falta un `RunPython`.

### 3.2 Rendimiento

- **N+1 en la pantalla del mes y en metas.** `templates/budget/mes.html` recorre las
  líneas y las transacciones accediendo a `categoria.etiqueta` sin `select_related`: un
  mes con 120 transacciones son 120 consultas contra el pooler de Supabase. `views.metas`
  llama a `meta.acumulado()` dos veces por meta.
- **`planificar` proyecta el mes dos veces** (`obtener_mes` y luego `proyectar`).
- Un presupuesto de consultas (`django_assertNumQueries`) sobre `budget:mes` con 50
  transacciones convertiría esto en una regresión detectable en vez de en un
  descubrimiento de producción.

### 3.3 Alcance del §7 que quedó fuera, y no estaba escrito en ningún sitio

- **El menú enlaza 1 de las 6 pantallas.** Solo `budget:configurar`, y solo bajo
  `can_edit_budget`. El adolescente del §6.2 —con solo `can_add_transactions`— **no tiene
  ningún camino a «registrar un gasto»**, que el propio diseño llama la acción más
  frecuente. Las pruebas llegan por `reverse()`, no navegando. El Plan 3 debería tratar la
  navegación como entregable con nombre propio, no como una frase dentro de una tabla.
- **La varianza no se ve.** Los cuatro totales y `varianza_por_categoria` se calculan y se
  guardan; la pantalla del mes muestra líneas planeadas y transacciones sueltas, sin
  compararlas. Un mes cerrado tampoco enseña su `MonthlyClose`.
- **Las líneas excepcionales no existen en la interfaz.** No hay formulario de
  `BudgetLine` en toda la aplicación, así que `is_exceptional` es un campo que nadie puede
  poner. El paso 2 del asistente del §4.5.6 («agregar los gastos excepcionales») no está.
- **El asistente de tres pasos es una sola pantalla.** Lo autorizó el plan
  explícitamente, pero el §4.5.6 sigue sin cumplirse.
- **`AllocationRule.pesos` y `split=weighted` no son alcanzables:** el motor los soporta y
  están probados, pero `AllocationRuleForm` no incluye el campo.

### 3.4 Detalles pequeños, todos verificados

- **La guardia de pureza no cubre `django.utils`.** `PROHIBIDOS` es
  `("django.db", "django.conf", "django.contrib")`, aunque el README y el docstring de
  `periodicity.py` afirman que el motor tampoco importa `django.utils`. Añadir `"django."`
  a secas lo cierra.
- **El README promete más de lo que el esquema hace:** dice que el `CheckConstraint` de
  `BudgetLine` exige que la fuente concuerde con el tipo de línea; el constraint real solo
  exige como máximo una fuente. La concordancia vive en `clean()`.
- **`Goal.clean` no comprueba el hogar de `owner`,** a diferencia de `IncomeSource` y
  `ExpenseRule`. Hoy lo tapa el queryset acotado del formulario, que es la única defensa.
- **`_categoria_de_ingreso` usa `.first()` sin `order_by`:** no determinista, y aplana
  toda la varianza de ingresos en una sola categoría.
- **`varianza_por_categoria` se guarda como `{str: str}`**; quien lo consuma tendrá que
  reconstruir los `Decimal`.
- **Cascadas de borrado discutibles:** `GoalContribution.goal` es `CASCADE`, así que
  borrar una meta destruye su historial de aportes.
- **Pruebas que envejecen:** `test_criterio_1` y `test_criterio_10` usan 2030-05 como «mes
  futuro» (fallarán ruidosamente en junio de 2030);
  `test_las_metas_muestran_su_dato_derivado` solo afirma que el nombre aparece en el HTML,
  no el dato derivado que promete su nombre.

---

## 4. Lo que la revisión de rama enseñó, y conviene repetir

Los tres fallos Críticos que encontró estaban **en el mismo sitio**: `obtener_mes`, el
único punto de entrada al ciclo del mes, aceptaba cualquier entrada, materializaba
cualquier pasado y devolvía filas a medio construir. Ninguno lo habrían cazado las
pruebas de su tarea, porque cada tarea probaba su camino feliz.

El peor —entrar a un mes pasado que el hogar nunca vivió lo materializaba, y la siguiente
petición lo cerraba en cadena hasta hoy escribiendo `MonthlyClose` **inmutables**—
fabricaba historial financiero que solo se puede borrar, no corregir, y se disparaba desde
la barra de direcciones.

La lección para el Plan 3: **las funciones que son "el único punto de entrada" merecen
pruebas de entrada hostil**, no solo del camino previsto.

---

## 5. Trampas del entorno (cuestan tiempo si no se saben)

- **La suite completa tarda ~19 minutos** contra el pooler de Supabase y **supera el
  límite de 600 s** de una sola llamada de herramienta. Córrela en dos mitades en primer
  plano:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/budget -q              # ~11-15 min
  .venv/Scripts/python.exe -m pytest -q --ignore=tests/budget     # ~5-7 min
  ```
  Solo el motor puro es rápido de verdad: `pytest tests/budget/engine -q`.
- **Tras añadir una migración hay que correr una vez con `--create-db`**, o la base
  reutilizada conserva el esquema viejo y las pruebas mienten.
- **El pooler deja sesiones abiertas.** Dos corridas seguidas pueden dar un error de
  arranque espurio (`There is 1 other session using the database`) que un reintento
  limpia. Pasó en la corrida limpia del Plan 2: 3 errores de arranque que al reintentar
  pasaron.
- **La base `test_postgres` no es basura:** es la que reutiliza `--reuse-db`.
- **No hay cadena GNU gettext en esta máquina.** Los catálogos se escriben a mano y se
  compilan así:
  ```bash
  MSGFMT="C:/Users/otton/AppData/Local/Programs/Python/Python311/Tools/i18n/msgfmt.py"
  for L in en fr; do .venv/Scripts/python.exe "$MSGFMT" -o "locale/$L/LC_MESSAGES/django.mo" "locale/$L/LC_MESSAGES/django.po"; done
  ```
  `tests/test_catalogo_exhaustivo.py` nombra cada cadena que falte.
- **Los heredocs de shell con contenido largo y acentuado fallan a veces** en este
  entorno; escribir el archivo con la herramienta de escritura y luego insertarlo con un
  script corto es más fiable.
- **Restos en disco del worktree del Plan 2.** Al retirarlo, Windows denegó el permiso
  sobre varios archivos (OneDrive sincronizando, o el `.venv` de dentro). Git ya no lo
  registra y la rama está borrada, pero quedan ~3,2 MB en
  `.worktrees/plan-2-motor-financiero/` y dos carpetas de metadatos en `.git/worktrees/`
  (una, `fundacion`, sobra desde el Plan 1). Son inertes; borrarlos a mano es seguro.

---

## 6. Estado de publicación

`main` tiene **34 commits sin publicar** en `origin/main`
(`github.com/Otuzji/wealthome`). El Plan 2 entero está integrado localmente y **sin
empujar**.

---

## 7. Prompt para arrancar el Plan 3

Para pegar tal cual en una sesión nueva:

> Vamos con el Plan 3 de Wealthome, en `C:\Users\otton\OneDrive\Documents\Wealthome`.
>
> Contexto: los Planes 1 (fundación: auth, hogares, permisos, temas, i18n) y 2 (el motor
> financiero: trece modelos, motor puro, servicios y seis pantallas) están terminados e
> integrados en `main`, con 413 pruebas en verde. Antes de proponer nada, lee estos tres
> documentos, en este orden:
>
> - `docs/superpowers/2026-09-07-estado-y-deuda-plan-3.md` — el estado al cerrar el
>   Plan 2, las tres decisiones que hay que respetar, la deuda heredada y las trampas del
>   entorno. **Empieza por aquí.**
> - `docs/superpowers/specs/2026-09-03-wealthome-motor-financiero-design.md` — el diseño
>   del Plan 2, para entender el modelo de datos y el ciclo del mes.
> - `docs/superpowers/plans/2026-09-03-wealthome-motor-financiero.md` — el plan ejecutado,
>   con sus 97 pasos marcados.
>
> El Plan 3 cubre, según el cierre del Plan 2: Stripe y la suscripción (§5 del spec
> original), el Overview con gráficas, la pantalla de Balance, las metas con progreso
> visual, la navegación móvil, htmx, Chart.js, el neomorfismo del §7.3 y la PWA.
>
> Además hay deuda heredada que quiero valorar contigo antes de decidir el alcance —está
> en la sección 3 del documento de estado—. Me importan especialmente tres cosas: que el
> menú hoy enlaza 1 de las 6 pantallas y el miembro con solo `can_add_transactions` no
> tiene ningún camino a registrar un gasto; que `budget:aportar` puede escribir contra un
> mes cerrado porque faltan dos de las cuatro guardias del §5.7; y que la varianza se
> calcula y se guarda pero no se ve en ninguna pantalla.
>
> Empieza por una sesión de brainstorming para fijar el alcance del Plan 3 —qué entra,
> qué se queda fuera y en qué orden—, y no escribas código hasta que el alcance esté
> acordado. Cuando lo esté, quiero un diseño y luego un plan por tareas, como en los dos
> planes anteriores.
>
> Trabajamos en español. Las pruebas se corren en primer plano y en dos mitades: la suite
> completa tarda unos 19 minutos y no cabe en una sola llamada.
