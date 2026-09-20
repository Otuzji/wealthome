# Wealthome — Metas: aportar, corregir y cerrar el ciclo

**Fecha:** 2026-09-20
**Estado:** Implementado en la rama `ui/navegacion-y-tiles` (2026-09-20)
**Depende de:** `2026-08-30-wealthome-nucleo-financiero-design.md` (§3.3 Goal y
GoalContribution, §4.5 la cascada), `2026-09-03-wealthome-motor-financiero-design.md`
(§4.6 `engine/goals.py`), y de la rama `ui/navegacion-y-tiles` con el registro
editable (`acciones_registro.html`) y el FAB con selector.

Las metas existen desde el Plan 2 y se pintan desde el Plan 3, pero el ciclo está a
medias: **no hay forma de aportar desde la interfaz** (`aporte_form.html` no lo incluye
nadie), `status` nunca cambia, nada se corrige ni se borra, y la meta no dice nada del
mes en curso. Este diseño cierra ese ciclo sin tocar el esquema.

Todas las referencias con § apuntan al diseño de la Fase 1 salvo que digan otra cosa.

---

## 1. Alcance

**Incluye:**

- Aportar a una meta desde su tarjeta y desde el `[+]` (tercera opción del selector).
- Estados: `reached` automático al cubrir el objetivo; `abandoned` y reactivar a mano.
- Editar y borrar metas; editar y borrar **aportes manuales**. Los de cascada, intocables.
- La tarjeta de la meta: "This month: $X of the $Y suggested", el aviso de qué la
  alimenta (regla de reparto o solo a mano), la fecha derivada legible, la meta alcanzada
  con su celebración, la abandonada atenuada.
- Un módulo de dominio nuevo, `apps/budget/services_goals.py`, con la lógica que hoy no
  existe; `aplicar_cascada_al_cierre` pasa por él.
- Pruebas en archivos nuevos por tema, fuera de `test_views.py`.

**Fuera de alcance (decidido, no olvidado):**

- Metas en el Overview.
- Una línea de "ahorro" planificada en el mes o un aporte automático al abrirlo. El
  único canal automático sigue siendo la cascada del sobrante al cierre (§4.5).
- Crear la regla de reparto sola al crear la meta: se ofrece el enlace, nada más.
- Aportes negativos (un error se corrige editando o borrando el aporte).
- Cambiar el esquema: `Goal.status` y `GoalContribution.origen` ya existen.

---

## 2. Datos y estados

Sin migraciones. Dos ayudas en `Goal`:

- `alcanzada(acumulado)` → `acumulado >= target_amount`.
- `esta_activa` → `status == ACTIVE`.

**Transiciones de `status`:**

| De | A | Quién |
|---|---|---|
| `active` | `reached` | `recalcular_estado`, al guardar un aporte (manual o cascada) o al bajar el objetivo |
| `reached` | `active` | `recalcular_estado`, al borrar o reducir un aporte o subir el objetivo. No hay "Reopen" a mano: sin subir el objetivo, el siguiente recálculo la volvería a dar por alcanzada |
| `active` | `abandoned` | a mano |
| `abandoned` | `active` | a mano; se recalcula por si ya está cubierta |

Una `abandoned` nunca se mueve sola: si recibe cascada (la regla de reparto sigue viva)
el aporte se guarda y la meta sigue abandonada. Es responsabilidad del usuario quitar la
regla; la tarjeta abandonada lo recuerda si `tiene_regla`.

**Borrado.**

- Aporte `manual`: se borra si su mes no está cerrado. Después, `recalcular_estado`.
- Aporte `cascade`: no se edita ni se borra. Pertenece al cierre del mes; la vista
  responde 403 aunque alguien fabrique el POST.
- Meta: `GoalContribution.goal` y `AllocationRule.target_goal` son `CASCADE`, pero
  `MonthlyAllocation.rule` es `RESTRICT`. Una meta que ya recibió cascada participa de
  un mes cerrado y **no se borra: se abandona**. La regla es "sin aportes de origen
  `cascade`"; la UI enseña "Abandon" en vez de "Remove" y el POST de borrar, si llega,
  deja `messages.error` y vuelve. Los aportes manuales se van con la meta; el `confirm`
  del navegador lo dice.

**Edición de meta.** `GoalForm` con `instance`. Tras guardar, `recalcular_estado`.
`scope` y `owner` quedan deshabilitados si la meta tiene aportes: un aporte de meta de
hogar lleva `member` cualquiera; el de una personal debe ser del dueño.

**Formulario de aporte.** `GoalContributionForm`:
- `goal`: metas **activas** del hogar que el miembro puede ver — las de hogar y las
  personales suyas. Acota render y validación.
- `date`: no posterior a hoy.
- `amount`: positivo (lo exige `MoneyField`; se prueba).

---

## 3. `services_goals.py`

Cuatro funciones, acotadas al hogar, `transaction.atomic` donde escriben.

```python
def aportar(hogar, meta, amount, date, member, origen="manual") -> GoalContribution
```
Crea el aporte con `budget_month = services.mes_de_fecha(hogar, date)` (que no crea
meses), `full_clean()` y `save()`. `MesCerrado` sube tal cual. Luego
`recalcular_estado(meta)`. `aplicar_cascada_al_cierre` la llama con
`origen="cascade", member=None`.

```python
def recalcular_estado(meta, acumulado=None) -> bool
```
Solo `active ↔ reached`. Devuelve si cambió. Guarda con `update_fields=["status"]`.

```python
def cambiar_estado(meta, nuevo) -> None
```
Las dos transiciones a mano de la tabla (`active → abandoned`, `abandoned → active`). Otra cosa → `ValueError`.

```python
def resumen(hogar, metas, hoy) -> list[dict]
```
Para la pantalla. `metas` viene con `prefetch_related("contributions__member__user")`;
las reglas activas con `target_goal` se leen en una consulta; el mes de hoy con
`mes_de_fecha` (o `None`, y entonces `este_mes = 0`). Por meta:

| Clave | Contenido |
|---|---|
| `meta` | la fila |
| `acumulado` | suma en Python sobre el prefetch |
| `aporte`, `fecha` | `meta.derivar(desde=hoy, acumulado=acumulado)` |
| `meses_restantes` | meses entre `hoy` y `fecha` (0 si alcanzada) |
| `este_mes` | suma de aportes con `budget_month_id == mes_de_hoy.pk` |
| `porcentaje`, `porcentaje_barra` | entero real / acotado a 100 |
| `tiene_regla` | hay `AllocationRule` activa apuntando a ella |
| `alcanzada_el` | fecha del aporte que la cubrió (solo `reached`) |
| `aportes` | lista de `(aporte, editable)`; `editable` = manual y mes no cerrado |
| `se_puede_borrar` | ningún aporte de cascada |

Tope de consultas: no crece con el número de metas ni de aportes (se fija con 20 metas y
5 aportes cada una).

---

## 4. Vistas y rutas

Todo en `views_goals.py`. Rutas antes de los patrones con `<str:ambito>`.

| Ruta | Vista | Permiso | Comportamiento |
|---|---|---|---|
| `goals/<pk>/` | `meta_editar` | `can_edit_budget` | `GoalForm` + `instance` vía el helper `editar` de setup con `destino="budget:metas"`; tras guardar, `recalcular_estado` |
| `goals/<pk>/delete/` | `meta_borrar` | `can_edit_budget` | POST. Con cascada → `messages.error` "This goal already took part in a closed month — abandon it instead." Sin → borra. Vuelve a `metas` del ámbito de la meta |
| `goals/<pk>/status/<estado>/` | `meta_estado` | `can_edit_budget` | POST. `estado` ∈ {`active`, `abandoned`}; transición inválida → 400 |
| `goals/contribute/` | `aportar` | `can_edit_budget` | `?goal=<pk>` como `initial`. htmx: GET devuelve `aporte_form.html`; POST bueno devuelve el form limpio + **la tarjeta de la meta fuera de banda** (`id="meta-<pk>"`) + `HX-Trigger: gasto-registrado`. Sin htmx: `formulario.html` y redirige a `metas` |
| `goals/contributions/<pk>/` | `aporte_editar` | `can_edit_budget` | `GoalContributionForm` + `instance`; `cascade` → 403; si su mes ya está cerrado → `messages.error` y vuelve (mover la fecha fuera de un mes cerrado reescribiría ese mes); si la fecha nueva cae en un mes cerrado → error en el form; tras guardar, `recalcular_estado` |
| `goals/contributions/<pk>/delete/` | `aporte_borrar` | `can_edit_budget` | POST; `cascade` → 403; mes cerrado → `messages.error`; borra y `recalcular_estado` |
| `<ambito>/goals/` | `metas` | `can_view_budget` | Usa `resumen`; agrupa activas / alcanzadas / abandonadas |

Acotado: todo pk pasa por `for_household(hogar)`, y las metas personales exigen además
ser del dueño (`acotar_por_dueno`). Un pk ajeno es 404, no 403. `aportar` pone
`member = membresia_actual(request)`.

La meta personal de otro miembro no aparece en el `queryset` de `goal` y un POST
fabricado con su id falla la validación del formulario.

`AllocationRuleForm` acepta `initial` desde la query (`?target_type=goal&target_goal=<pk>`)
para el enlace "add a split rule"; la vista `reparto_nuevo` los pasa.

---

## 5. Interfaz

**`metas.html`** se parte en fragmentos, como `mes.html`:

- `_fragmentos/meta_tarjeta.html` — `section.card` con `id="meta-<pk>"`:
  - Cabecera: nombre, chip de estado (`Reached` / `Abandoned`; activa sin chip), acciones
    icono: Edit, y Remove o Abandon según `se_puede_borrar`. Los SVG salen de
    `acciones_registro.html` a `_fragmentos/acciones_icono.html`, parametrizado por URLs
    y texto del `confirm`, y `acciones_registro.html` lo usa.
  - Barra de progreso y "X of Y — N%".
  - Frase derivada según estado:
    - activa por fecha: "Put in $X a month to get there by June 2027."
    - activa por monto: "At this rate you get there in 14 months · March 2028."
    - alcanzada: "You got there on 3 March 2027 🎉"; sin botón de aportar. Para seguir
      ahorrando se sube el objetivo con Edit y el recálculo la reabre.
    - abandonada: `card--apagada`, "Reactivate"; si `tiene_regla`, "A split rule still
      feeds it — remove it in Budget setup."
  - "This month: $X of the $Y suggested" (activas); en verde si `este_mes >= aporte`.
  - Aviso de alimentación (activas): hogar sin regla → "Nothing feeds this goal
    automatically — add a split rule" (enlace a `reparto_nuevo` con `initial`);
    personal → "Personal goal: only manual contributions."
  - "Add to it" (activas, `can_edit_budget` y `nav_puede_escribir`): `<a>` a
    `aportar?goal=pk`; con JS abre el modal del FAB y pide el form por htmx
    (`hx-get`, `hx-target="#modal-gasto-cuerpo"`, `showModal()`), como las opciones del
    selector.
  - Aportes: fecha · quién / "The household" / "From the monthly split" · importe ·
    acciones icono si `editable`. Últimos 5; el resto en `<details>` "Show all".
- `metas.html`: bloques Active, Reached, Abandoned (los dos últimos solo si hay).
  `.rejilla--2` en escritorio. Vacío: tarjeta "No goals yet" con el botón dentro.

**`aporte_form.html`** como `gasto_form.html`: título fuera de banda
(`#modal-gasto-titulo`), `hx-post` a `request.path`, `hx-target="this"`, botón Back →
`abrirSelectorDeRegistro()`. Página entera: `budget/formulario.html`.

**FAB.** Tercera opción del selector, siempre: "A goal contribution" / "Money you set
aside", `hx-get` a `aportar`. Sin metas activas que aportar, el fragmento del formulario
responde con un estado vacío ("No active goals yet" + enlace a New goal) en vez del
`<select>` vacío. Así el menú no paga una consulta por página para saber si hay metas.

**CSS.** `.chip--alcanzada`, `.chip--abandonada`, `.card--apagada`, `.meta__este-mes`,
`.selector__opcion--meta`. Mismos tokens; nada nuevo de layout.

**i18n.** EN y FR en los `.po` a mano; `sw.js` sube de versión.

---

## 6. Pruebas

| Archivo | Cubre |
|---|---|
| `tests/budget/test_services_goals.py` | `aportar` resuelve `budget_month`, sube `MesCerrado`, marca `reached`; `recalcular_estado` en sus cuatro casos; `cambiar_estado` acepta dos transiciones y rechaza el resto; `resumen`: `este_mes` solo el mes de hoy, `tiene_regla`, `meses_restantes`, `editable`, `se_puede_borrar`, `alcanzada_el`; tope de consultas con 20 metas × 5 aportes |
| `tests/budget/test_metas_vistas.py` | lista por ámbito (hogar vs personal); orden por estado; `meta_editar` reabre al subir el objetivo; `meta_borrar` con cascada no borra y avisa; `meta_estado` y su 400; 403 en toda escritura sin `can_edit_budget`; pk ajeno → 404 |
| `tests/budget/test_aportar.py` | htmx: form limpio + tarjeta OOB + `HX-Trigger`; página entera redirige; `?goal=` preselecciona; meta personal ajena fuera del queryset y rechazada por POST; fecha futura rechazada; mes cerrado → error; `aporte_editar`/`aporte_borrar` en cascada → 403; borrar recalcula |
| `tests/budget/test_mes_cerrado.py` | la cascada al cierre pasa por `services_goals.aportar` y marca `reached` |
| `tests/test_navegacion.py`, `tests/test_pwa.py`, `tests/test_presupuesto_consultas.py` | FAB con tres opciones; estado vacío de `aportar` sin metas activas; versión de `sw.js`; tope de consultas de Metas medido de nuevo |

TDD tarea por tarea; la suite entera una vez al final.
