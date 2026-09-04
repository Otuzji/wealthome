# Wealthome — Plan 2: el motor financiero

**Fecha:** 2026-09-03
**Estado:** Diseño aprobado, pendiente de plan de implementación
**Depende de:** `2026-08-30-wealthome-nucleo-financiero-design.md` (el diseño de toda la
Fase 1, aprobado), y del lote de puertas cerrado en los commits `193c7e6` y `1f36f66`.

Este documento no reemplaza al diseño de la Fase 1: lo *aterriza*. Aquel fija el **qué**
—§3.2, §3.3 y §4 completas—; este fija el **cómo**, y resuelve por escrito las decisiones
que aquel dejó abiertas y que, sin decidir, cada tarea del plan resolvería de una forma
distinta.

Todas las referencias con § apuntan al diseño de la Fase 1 salvo que digan otra cosa.

---

## 1. Alcance

**Incluye:** los trece modelos de §3.2 y §3.3, el motor de presupuesto completo de §4
—las ocho periodicidades, los cinco modos de ingreso variable, el ciclo de vida del mes,
el cierre y el arrastre, las metas y **el reparto en cascada del sobrante** de §4.5—, los
servicios que los unen, y **seis pantallas mínimas** que permiten ejercitar todo eso a
mano de punta a punta.

**No incluye:** Stripe y la suscripción (§5), el Overview con gráficas, Balance, la
navegación móvil, htmx, Chart.js, el neomorfismo del §7.3 y la PWA. Todo eso es el
Plan 3. Las pantallas de este plan son formularios de Django planos sobre el CSS que ya
existe: feas a propósito, para que el Plan 3 rehaga la presentación sobre un motor que ya
se usó a mano y no sobre uno que solo pasó pruebas.

**Estado de partida:** el Plan 1 está integrado y las tres puertas están cerradas. Existe
la barrera de aislamiento (`HouseholdScoped` con manager estricto,
`HouseholdScopedModelForm`, `HouseholdScopedAdmin`, `HouseholdScopedFactory`), la capa
central de autorización (`hogar_actual`, `@con_hogar`, `@solo_admin`,
`@requiere_permiso`), `MoneyField`, y las plantillas 403/404. **Nada del motor financiero
existe.** 139 pruebas en verde.

---

## 2. Las siete decisiones de este plan

Cada una se tomó explícitamente. Las razones importan tanto como las decisiones, porque
son lo que impide que la siguiente persona las deshaga por parecerle arbitrarias.

### 2.1 La aritmética vive en funciones puras, no en los modelos

`apps/budget/engine/` **no importa el ORM**. Ni `django.db`, ni `apps.*.models`, ni una
línea. Recibe `Decimal`, fechas y listas; devuelve `Decimal`, fechas y listas.
`services.py` es quien lee el ORM, llama al motor y escribe el resultado.

La razón está en §9: los casos que el diseño exige cubrir —cada periodicidad, cada modo
de ingreso, la cascada con reglas reordenadas, el faltante absorbido de abajo arriba, el
acumulado de mesada a lo largo de varios meses, el arrastre que cuadra al centavo— son
**aritmética, no persistencia**. Probarlos contra el pooler de Supabase los haría lentos
y frágiles justo donde más pruebas hacen falta y donde más caro es un error.

Se sostiene con una prueba que recorre el AST de cada módulo de `engine/` y falla si
aparece un import prohibido. Sin ella, la pureza se erosiona en la tercera tarea.

### 2.2 Las reglas aterrizan por calendario real, no prorrateadas

Se cuentan las **ocurrencias reales** de la regla dentro del mes, ancladas en
`effective_from`. Un mes con tres quincenas presupuesta tres sueldos; el seguro anual cae
entero en su mes de aniversario.

La alternativa —promediar todo— produce doce meses idénticos y cómodos de leer, y luego
el seguro de $1.200 llega en agosto contra un presupuesto que decía $100: once meses
cuadran y uno se descuadra por $1.100 sin que el plan lo hubiera anunciado nunca. El
presupuesto tiene que predecir **cuándo** sale el dinero, o §4.4 (balance = real contra
presupuestado) no significa nada.

El efecto secundario es una función del producto, no un defecto: el mes de tres sueldos
aparece como sobrante de verdad y la cascada de §4.5 lo reparte, que es exactamente el
ritual del que nació la aplicación.

### 2.3 El ciclo del mes es perezoso, con un comando de reserva

El disparador es **entrar**. Al pedir un mes, el motor cierra en cadena los meses vencidos
—en orden, porque cada cierre arrastra su saldo al siguiente— y materializa el corriente.
Cero infraestructura nueva: no hay Celery ni cron en el stack, y desarrollo y producción
se comportan igual.

Además se escribe `manage.py cerrar_meses_vencidos` con la **misma** lógica, sin usar
todavía, para que el Plan 3 pueda enchufarle un cron o un correo de aviso sin extraer esa
lógica de dentro de una vista.

Un `manage.py` programado como único disparador se descartó: en desarrollo nadie lo lanza,
así que los meses no se materializarían y las pruebas manuales fallarían por una razón que
no es el código.

### 2.4 `Transaction` gana una clave foránea a `IncomeSource`

Hueco del diseño de la Fase 1: §4.1 exige que `rolling_average` promedie los seis meses
reales **de una fuente concreta**, y §3.3 define `Transaction` sin ningún vínculo con
`IncomeSource`. Tal como estaba escrito, ese modo no se podía calcular.

`Transaction.income_source` (anulable) lo resuelve con exactitud aunque dos fuentes
compartan categoría — el caso normal: dos sueldos en la casa, o dos clientes de freelance.
Derivarlo de `budget_line` habría dejado el historial a merced de que el usuario vincule
cada ingreso a su línea, cosa que §3.3 declara opcional: la media se calcularía sobre
menos meses de los que el usuario cree, en silencio. Promediar por categoría habría hecho
que un sueldo fijo inflara la media de un freelance, que es justo el optimismo que §4.1
prohíbe.

### 2.5 Una sola app, con `models/` y `engine/` como paquetes

Los trece modelos son un subsistema cohesionado y se referencian en todas direcciones
(`Transaction`→`BudgetLine`, `AllowanceLedger`→`BudgetMonth`, `AllocationRule`→`Goal`).
Repartirlos en tres apps solo produce cadenas de dependencias entre migraciones a cambio
de nada.

`models/` es un paquete y no un `models.py` de ~500 líneas porque el plan lo ejecutan
agentes tarea por tarea, y un archivo que seis tareas distintas editan es un problema de
contexto y de conflictos. `__init__.py` reexporta todo, así que
`from apps.budget.models import Transaction` sigue funcionando y ninguna migración se
entera.

### 2.6 Todos los modelos financieros son `HouseholdScoped`, sin excepciones

Incluidos los alcanzables por su padre (`BudgetLine` a través de `BudgetMonth`).
Denormalizar la columna `household` compra que **todos** respondan a `for_household`, que
las consultas entre meses no necesiten un join, y —lo que más importa— que no haya ni una
excepción que recordar cuando alguien añada el modelo catorce.

El precio es que `linea.household` podría desviarse de `linea.budget_month.household`. Se
valida en `save()` y tiene su prueba: un `CheckConstraint` no cruza tablas.

### 2.7 Redondeo en un solo punto, y el residuo cae donde el faltante

§3.4 exige que el redondeo sea explícito, a dos decimales, y siempre en el mismo punto del
cálculo. Una sola función, `engine/money.py::centavos()`, redondea con `ROUND_HALF_UP`, y
ninguna otra parte del motor redondea.

Tres invariantes, que son lo que las pruebas comprueban:

- La suma de las asignaciones **nunca excede** el sobrante.
- **Dentro** de una regla, la suma de las partes es **exactamente** el importe de la regla:
  una mesada de $100 entre tres miembros da 33,34 / 33,33 / 33,33 y no 33,33 tres veces.
  Lo garantiza `repartir_proporcional()`, que reparte los centavos sobrantes de uno en uno
  por orden de miembro.
- Si el juego de reglas incluye una de método `remainder`, la suma es **exactamente** el
  sobrante.

Lo que **no** se hace: forzar que la suma iguale el sobrante cuando las reglas no lo
agotan. Una familia cuyas reglas reparten $600 de un sobrante de $800 deja $200 sin
asignar a propósito, y esos $200 se quedan en el balance y se arrastran. Empujarlos a la
última regla sería inventarle a la familia una decisión que no tomó.

---

## 3. Estructura de archivos

```
apps/budget/
  __init__.py
  apps.py
  models/
    __init__.py        # reexporta los trece
    catalog.py         # Category, Merchant
    rules.py           # IncomeSource, ExpenseRule
    months.py          # BudgetMonth, BudgetLine, MonthlyClose
    ledger.py          # Transaction
    goals.py           # Goal, GoalContribution
    allocation.py      # AllocationRule, MonthlyAllocation, AllowanceLedger
  engine/
    __init__.py
    periodicity.py     # ocurrencias de una regla dentro de un mes
    income.py          # los cinco modos -> la cifra conservadora
    cascade.py         # el reparto del sobrante, el faltante, el redondeo
    closing.py         # totales, varianza, balance, arrastre
    allowance.py       # el libro mayor de la mesada
    goals.py           # las dos formas de expresar una meta
    merchants.py       # normalización de nombres de comercio
  services.py          # lee ORM -> llama al motor -> escribe ORM
  seeds.py             # el árbol de categorías precargado
  forms.py  views.py  urls.py  admin.py
  management/commands/cerrar_meses_vencidos.py
  migrations/
templates/budget/      # las seis pantallas
tests/budget/
  test_periodicity.py  test_income.py  test_cascade.py
  test_closing.py      test_allowance.py  test_goals.py     # puras, sin django_db
  test_pureza.py       # el AST de engine/ no importa el ORM
  test_models.py  test_services.py  test_month_cycle.py
  test_views.py   test_aislamiento.py
```

---

## 4. El motor

Ninguna función guarda estado. Todas reciben y devuelven valores. Los tipos de entrada son
`dataclass` congeladas definidas en el propio `engine/`, no modelos.

### 4.1 `periodicity.py`

```python
def ocurrencias(periodicidad, ancla: date, anio: int, mes: int,
                hasta: date | None = None) -> list[date]
def importe_del_mes(importe: Decimal, periodicidad, ancla: date, anio: int, mes: int,
                    hasta: date | None = None) -> Decimal
```

`ancla` es `effective_from`; `hasta` es `effective_to` y corta. El importe del mes es
`importe × len(ocurrencias)`.

Las ocho periodicidades, con sus valores de columna en inglés como el resto del esquema:

| Valor | Dispara |
|---|---|
| `weekly` | cada 7 días desde el ancla |
| `biweekly` | cada 14 días desde el ancla |
| `semimonthly` | el día del ancla y ese día + 15 |
| `monthly` | el día del ancla, cada mes |
| `bimonthly` | el día del ancla, en los meses a distancia múltiplo de 2 |
| `quarterly` | ídem, múltiplo de 3 |
| `semiannual` | ídem, múltiplo de 6 |
| `annual` | ídem, múltiplo de 12 |

**Dos reglas de borde, fijadas aquí porque son dinero:**

- Una regla anclada el día 29, 30 o 31 dispara el **último día** de los meses más cortos.
  Nunca se salta un mes: el alquiler de febrero se paga en febrero.
- `semimonthly` aplica el mismo recorte a su segunda fecha (ancla el 20 → 20 y último día).

### 4.2 `income.py`

```python
def cifra_conservadora(amount_type, *, amount=None, amount_min=None,
                       amount_max=None, historial: Sequence[Decimal] = ()) -> Decimal | None
```

Los cinco modos de §4.1:

| Modo | Devuelve |
|---|---|
| `fixed` | `amount` |
| `estimated` | `amount` (la estimación del usuario, ajustable mes a mes) |
| `range` | `amount_min` — **el mínimo**; lo que exceda es superávit |
| `rolling_average` | la media de los meses **con datos** de los últimos seis; `None` si hay menos de tres |
| `irregular` | `Decimal("0.00")` |

`historial` son los totales mensuales reales de esa fuente, del más antiguo al más
reciente, ya filtrados a los últimos seis meses por `services.py`.

`None` significa **"aún no hay datos"**, y la interfaz lo dice con todas sus letras en vez
de inventar un número. La regla que gobierna todo el motor (§4.1) es que el presupuesto
usa siempre la cifra conservadora: el optimismo va en la proyección, nunca en el plan.

### 4.3 `cascade.py`

```python
@dataclass(frozen=True)
class ReglaReparto:
    orden: int
    destino: str                       # "goal" | "allowance" | "category"
    metodo: str                        # "fixed" | "percentage" | "remainder"
    importe: Decimal | None            # para "fixed"
    porcentaje: Decimal | None         # para "percentage"
    destino_id: int | None
    miembros: tuple[int, ...] = ()     # solo para "allowance"
    pesos: tuple[Decimal, ...] | None = None   # None = partes iguales

@dataclass(frozen=True)
class Asignacion:
    orden: int
    importe: Decimal
    miembro_id: int | None             # solo en las de mesada

@dataclass(frozen=True)
class Ajuste:
    miembro_id: int
    importe: Decimal                   # negativo: se descuenta del mes siguiente

def repartir(sobrante: Decimal, reglas: Sequence[ReglaReparto]) -> list[Asignacion]
def absorber_faltante(planeado: Sequence[Asignacion], reglas: Sequence[ReglaReparto],
                      sobrante_real: Decimal) -> tuple[list[Asignacion], list[Ajuste]]
```

**Cómo cae el sobrante.** Las reglas se recorren por `orden`. Cada una toma:

- `fixed` → `min(importe, disponible)`
- `percentage` → `sobrante × porcentaje`, redondeado, limitado por `disponible`. **El
  porcentaje es sobre el sobrante que entró a la cascada**, no sobre lo que va quedando:
  "10% al fondo de vacaciones" significa el 10% del sobrante, que es como lo dice una
  familia.
- `remainder` → todo lo disponible

**El redondeo.** Un solo punto: `engine/money.py::centavos()`. Cada asignación se limita
además por lo que quede disponible, así que la suma nunca excede el sobrante. Lo que las
reglas no agoten se queda sin asignar y se arrastra en el balance — ver §2.7.

**El reparto de la mesada cuadra al centavo.** `equal` entre tres miembros y $100 da
33,34 / 33,33 / 33,33: los centavos sobrantes se reparten de uno en uno por orden de `pk`
de la membresía, siempre igual, para que dos ejecuciones den lo mismo.

**Sobrante negativo.** No reparte nada, devuelve la lista vacía y no genera mesada.

**El faltante (§4.5.3).** Cuando el sobrante real queda por debajo del proyectado, la
diferencia se absorbe **desde la última regla hacia arriba**, y si no alcanza, la
penúltima. Eso es lo que significa una cascada y lo que hace que el orden importe: con el
ahorro arriba y las mesadas abajo, un mes flojo se come la diversión y no el ahorro.

**Pero la mesada ya asignada nunca se retira.** Se fija al planificar y no se mueve
durante el mes — de nada sirve enterarse el día 30 de que tenías $100 para gastar. La
parte del faltante que le habría tocado a una regla de mesada se devuelve como `Ajuste`
negativo, que `services.py` escribe en el `AllowanceLedger` **del mes siguiente**.

Ejemplo canónico del §4.5.3, que debe quedar como prueba literal: sobrante proyectado
$800 → $600 al ahorro, $100 a cada uno. Sobrante real $720. El ahorro recibe sus $600
íntegros; el faltante de $80 se descuenta de las mesadas del mes siguiente, $40 a cada uno.
Nadie pierde dinero que ya gastó.

### 4.4 `closing.py`

```python
@dataclass(frozen=True)
class Renglon:
    categoria_id: int
    kind: str                 # "income" | "expense"
    presupuestado: Decimal
    real: Decimal

@dataclass(frozen=True)
class Cierre:
    ingresos_presupuestados: Decimal
    ingresos_reales: Decimal
    egresos_presupuestados: Decimal
    egresos_reales: Decimal
    varianza_por_categoria: dict[int, Decimal]
    balance: Decimal
    arrastre: Decimal

def cerrar(renglones: Sequence[Renglon], saldo_arrastrado: Decimal) -> Cierre
```

§4.4: `balance = saldo_arrastrado + ingresos_reales − egresos_reales`, y ese balance es el
`arrastre` del mes siguiente. El superávit **y el déficit** se arrastran igual.

### 4.5 `allowance.py`

```python
def saldo(carried_in, granted, adjustment, spent) -> Decimal
def carried_out(saldo: Decimal, rollover: bool) -> Decimal
```

`saldo = carried_in + granted + adjustment − spent`. `carried_out` es el saldo si
`Household.allowance_rollover` está activo (por defecto lo está, §4.5.4) y cero si no —
con la opción desactivada, lo no gastado vuelve al hogar al cerrar.

Es un libro mayor y no un campo mutable: cada mes es una fila y el saldo se deriva sumando,
para que *"¿por qué tengo $145 este mes?"* siempre tenga respuesta.

### 4.6 `goals.py`

```python
def derivar(modo, objetivo: Decimal, acumulado: Decimal, desde: date,
            fecha_objetivo: date | None = None,
            aporte_mensual: Decimal | None = None) -> tuple[Decimal, date]
```

Las dos formas de §3.3 son la misma cosa vista al revés: el usuario da dos datos y la
aplicación deriva el tercero. `by_target_date` recibe objetivo y fecha y devuelve el aporte
mensual necesario; `by_monthly_amount` recibe objetivo y aporte y devuelve la fecha de
llegada. El tercer dato **nunca se guarda**: se deriva al mostrarlo, o quedaría obsoleto en
cuanto cambie el acumulado.

### 4.7 `merchants.py`

```python
def normalizar(nombre: str) -> str
```

Mayúsculas, sin acentos, sin puntuación, espacios colapsados, y sin el número de sucursal
final (`WALMART #3421` → `WALMART`). Es lo que hace que `WALMART #3421` y
`Walmart Supercentre` sean el mismo comercio, que es la base de las consultas de la Fase 2.

---

## 5. Los modelos

Los trece heredan de `HouseholdScoped`. Todo importe es `MoneyField`. Todo texto visible
pasa por `gettext`.

### 5.1 `catalog.py`

**`Category`** — `slug`, `name`, `is_system`, `parent` (autorreferencial), `kind`
(`income`|`expense`), `tax_category` (anulable, sin usar en la Fase 1, sembrado desde ya
porque etiquetar dos años de gastos retroactivamente es un trabajo que nadie hace nunca).

**Desviación 1 — se siembra por hogar.** §3.2 dice `household = nulo para las del
sistema`, pero `HouseholdScoped.household` no admite nulo, y ablandarlo destriparía la
barrera. Al crear un hogar se copia el árbol precargado (~25 filas, `seeds.py`): `slug`
puesto, `name` vacío, `is_system=True`. Se muestra traducido desde el `slug` mientras
`name` esté vacío; renombrar solo escribe `name`. Esto hace cierto sin trabajo extra el
*"el hogar puede añadir **y renombrar**"* de §3.2, que con un árbol global habría exigido
una tabla de anulaciones por hogar.

El árbol de §3.2: Vivienda (alquiler, hipoteca), Servicios (agua, gas, electricidad,
internet), Suscripciones, Alimentos, Transporte, Gasolina, Entretenimiento, Obligaciones
financieras, Préstamos bancarios.

**`Merchant`** — `name`, `normalized_name`, único por hogar sobre `normalized_name`.

### 5.2 `rules.py`

**`IncomeSource`** — `owner`, `name`, `source_type`, `amount_type`, `amount`,
`amount_min`, `amount_max`, `periodicity`, `effective_from`, `effective_to`, `scope`.

**`ExpenseRule`** — `category`, `name`, `amount`, `periodicity`, `effective_from`,
`effective_to`, `is_essential`, `owner` (anulable), `scope`.

**Desviación 3 — los dueños son `Membership`, no `User`.** §3.2 dice "el miembro", que es
ambiguo. Con FK a `User` se puede asignar el sueldo de una casa a alguien que no vive en
ella; con FK a `Membership` eso es **irrepresentable**, porque la membresía ya está atada
al hogar. Un miembro que se va queda con `is_active=False` y su histórico intacto
(`on_delete=PROTECT`). Aplica igual a `Transaction.member`, `Goal.owner` y
`AllowanceLedger.member`.

**Las reglas nunca se mutan** (§3.2). Subir el alquiler cierra la regla vieja con
`effective_to` y crea una nueva con `effective_from`. Es un servicio,
`services.reemplazar_regla(regla, nuevo_importe, desde)`, no una edición.

### 5.3 `months.py`

**`BudgetMonth`** — `year`, `month`, `status` (`future`|`open`|`closed`), `opened_at`,
`closed_at`. `UniqueConstraint(household, year, month)`.

**`BudgetLine`** — `budget_month`, `category`, `kind`, `planned_amount`, `is_exceptional`,
`owner`, `scope`, `note`.

**Desviación 2 — `source_rule` se parte en dos.** `source_income` y `source_expense_rule`,
ambas anulables, con un `CheckConstraint` que exige como máximo una y que concuerde con
`kind`. Una regla es o una `IncomeSource` o una `ExpenseRule`; una FK genérica arrastraría
`contenttypes` a cambio de nada. Las dos nulas significan línea excepcional.

**`MonthlyClose`** — `budget_month` (uno a uno), los cuatro totales,
`varianza_por_categoria` (JSON), `balance`, `arrastre`. **Inmutable:** `save()` lanza si el
objeto ya tiene `pk`. Inmutable de verdad, no por convención.

### 5.4 `ledger.py`

**`Transaction`** — `budget_month`, `category`, `merchant` (anulable), `income_source`
(anulable, **desviación 4**), `amount`, `date`, `member`, `payment_method`, `scope`,
`note`, `budget_line` (anulable), `receipt_image` (**desviación 5**: entra anulable y sin
usar, como dice §3.3, aunque el destino real —Supabase Storage— siga sin decidirse).

### 5.5 `goals.py`

**`Goal`** — `name`, `scope`, `owner`, `status`, `contribution_mode`, `target_amount`,
`target_date`, `monthly_amount`. **`GoalContribution`** — `goal`, `amount`, `date`,
`member`, `origen` (`manual`|`cascade`).

### 5.6 `allocation.py`

**`AllocationRule`** — `order`, `target_type`, `target_goal`, `target_category`, `method`,
`amount`, `percentage`, `split`, `is_active`.

**`MonthlyAllocation`** — `budget_month`, `rule`, `planned_amount`, `actual_amount`,
`member` (solo mesadas). Se escribe al confirmar la planificación y se ajusta al cerrar.

**`AllowanceLedger`** — `member`, `budget_month`, `granted`, `spent`, `adjustment`,
`carried_in`, `carried_out`. `spent` son las transacciones de ámbito `personal` de ese
miembro en ese mes.

### 5.7 Escrituras contra un mes cerrado

Un mes cerrado rechaza toda escritura (§9) en **dos** capas: el servicio la rechaza, y
`BudgetLine.save`, `Transaction.save`, `GoalContribution.save` y `MonthlyAllocation.save`
lanzan si su mes está cerrado. Dos capas porque el Plan 3 añadirá caminos de escritura que
hoy no existen, y la capa de modelo es la que no se puede rodear.

---

## 6. El ciclo del mes

Un solo punto de entrada:

```python
services.obtener_mes(hogar, anio, mes) -> BudgetMonth | ProyeccionDeMes
```

`ProyeccionDeMes` es una `dataclass` congelada de `services.py` —no un modelo y no una
fila— con los mismos campos que consumiría una plantilla (`anio`, `mes`, `lineas`,
`total_ingresos`, `total_egresos`, `sobrante`). Existe para que las pantallas traten un mes
futuro y uno abierto con el mismo código sin que el futuro toque la base de datos.

1. **Cierra en cadena los meses vencidos**, en orden, porque cada cierre arrastra su saldo
   al siguiente. Vencido = terminado hace más de 5 días (§4.2).
2. Si el mes pedido es el corriente y no tiene fila, **lo materializa** desde las reglas
   vigentes.
3. Si es futuro, **lo proyecta sin persistir** — §2.3 exige que cambiar el alquiler se
   refleje al instante en todos los meses futuros. Los meses `future` no existen como
   filas.
4. Si está cerrado, devuelve el `MonthlyClose` congelado.

**Concurrencia:** `select_for_update` sobre la fila de `BudgetMonth` al materializar y al
cerrar, más el `UniqueConstraint`. Dos pestañas abiertas el día 1 es el caso normal, no el
raro.

**Editar sin romper el historial** (§4.3): la vista anual toca la regla y afecta a los
meses futuros; la vista mensual de un mes abierto toca sus `BudgetLine` y afecta solo a ese
mes; un mes cerrado es de solo lectura.

---

## 7. Las pantallas

Formularios de Django planos sobre el CSS que ya existe. Todo formulario hereda de
`HouseholdScopedModelForm`; toda vista lleva uno de los tres decoradores. Household y
Personal (§2.4) son la misma vista con un parámetro de filtro, no vistas duplicadas.

| Pantalla | Decorador |
|---|---|
| Configurar presupuesto: categorías, ingresos, gastos fijos, reglas de reparto | `@requiere_permiso("can_edit_budget")` |
| Planificar el mes — los tres pasos de §4.5.6 | `@requiere_permiso("can_edit_budget")` |
| El mes: planeado contra real, varianza | `@requiere_permiso("can_view_budget")` |
| **Registrar un gasto** — la acción más frecuente | `@requiere_permiso("can_add_transactions")` |
| Cerrar el mes | `@requiere_permiso("can_edit_budget")` |
| Metas: lista y aportar | `can_view_budget` / `can_edit_budget` |

Este es el primer uso real de `@requiere_permiso`, y con él el adolescente de §6.2 queda
ejercitado de verdad: registra sus gastos y no ve la hipoteca. Los enlaces del menú se
ocultan según el permiso — un 403 al hacer clic es correcto pero grosero.

---

## 8. Pruebas

**Las pruebas del motor no llevan `django_db`.** Es el rendimiento que se compra con §2.1.

Los casos que §9 exige cubrir, cada uno mapeado a su prueba:

| Caso de §9 | Dónde |
|---|---|
| Cada periodicidad genera las líneas correctas en cada mes | `test_periodicity.py` |
| Cada modo de ingreso presupuesta la cifra conservadora correcta | `test_income.py` |
| Cerrar una regla y crear su sucesora no altera ningún mes cerrado | `test_services.py` |
| El arrastre entre cierres consecutivos cuadra al centavo | `test_closing.py` |
| Un mes cerrado rechaza toda escritura | `test_models.py`, `test_services.py` |
| La cascada con cada combinación de métodos y reglas reordenadas | `test_cascade.py` |
| El faltante se absorbe desde la última regla hacia arriba | `test_cascade.py` |
| Una mesada ya asignada nunca se reduce dentro del mes | `test_cascade.py`, `test_allowance.py` |
| El acumulado de mesada cuadra al centavo a lo largo de varios meses, con acumulación activada y desactivada | `test_allowance.py` |
| Un sobrante negativo no reparte nada y no genera mesada | `test_cascade.py` |
| Ningún endpoint devuelve datos de otro hogar | `test_aislamiento.py` |

Más dos guardias propias de este plan:

- `test_pureza.py` — el AST de cada módulo de `engine/` no importa `django.db` ni
  `apps.*.models`.
- La consistencia `linea.household == linea.budget_month.household`, y su equivalente en
  cada modelo con dos caminos al hogar.

Las pruebas de base de datos se marcan (`@pytest.mark.db`) para poder correr el motor solo,
en un segundo, durante el desarrollo.

---

## 9. Riesgos conocidos

**El catálogo bilingüe es el riesgo real.** Este plan añade muchísimo texto visible:
nombres de categoría del sistema, etiquetas de trece formularios, la copia del asistente de
tres pasos. No hay cadena GNU gettext en esta máquina, así que todo se escribe a mano en
los dos `.po` y se compila con `Tools/i18n/msgfmt.py`. `tests/test_catalogo_exhaustivo.py`
lo atrapa, pero atraparlo al final de un plan grande es un día perdido: el plan dedica una
tarea al catálogo **por cada tanda de pantallas**, no una sola al final.

**La suite contra el pooler de Supabase.** Hoy 139 pruebas tardan 3,5 minutos. El motor
puro no empeora eso, pero los servicios, las vistas y trece modelos sí. El *"no hay CI"*
del traspaso empieza a doler aquí de verdad.

**Trampas del entorno, heredadas** (documento de traspaso §5): tras añadir una migración
hay que correr una vez con `--create-db` o la base reutilizada conserva el esquema viejo y
las pruebas mienten; el pooler deja sesiones abiertas y un reintento limpia los errores de
arranque espurios; y las pruebas se corren **en primer plano**, esperando el resultado.

**El tamaño.** Son unas 14-16 tareas: el plan más grande de los tres. Lleva un punto de
control usable a mitad —motor y modelos completos, con el comando de gestión y las pruebas
de §9 en verde— para que si hay que parar, se pare en un sitio con sentido y no a medio
formulario.

---

## 10. Criterios de aceptación

1. Un administrador configura ingresos, gastos fijos y reglas de reparto, y ve el
   presupuesto de un mes futuro calculado desde las reglas, sin filas persistidas.
2. Un ingreso en modo `range` presupuesta el mínimo, y el exceso aparece como superávit al
   cierre (§13.4).
3. Una pareja planifica el mes en tres pasos, ve su sobrante repartido según sus reglas, y
   cada uno sabe desde el día 1 cuánta mesada tiene (§13.5).
4. Un mes que cierra por debajo de lo estimado deja el ahorro intacto y ajusta la mesada
   del mes siguiente, sin retirar nada ya gastado (§13.6).
5. Editar el alquiler en marzo no altera ningún cierre de enero ni febrero (§13.7).
6. Se registran gastos durante un mes, se cierra, y el mes siguiente arranca con el saldo
   arrastrado correcto (§13.3).
7. Un miembro con solo `can_add_transactions` registra un gasto y recibe 403 traducido en
   las pantallas de presupuesto.
8. Ninguna consulta devuelve datos de otro hogar, verificado por pruebas (§13.10).
9. Un mes con tres quincenas presupuesta tres sueldos; un seguro anual cae entero en su mes
   de aniversario.
10. La aplicación funciona completa en francés, con los montos formateados `2 847,50 $`.
