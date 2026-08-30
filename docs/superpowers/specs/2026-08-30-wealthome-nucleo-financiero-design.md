# Wealthome — Fase 1: Núcleo financiero

**Fecha:** 2026-08-30
**Estado:** Diseño aprobado, pendiente de plan de implementación

---

## 1. Qué es Wealthome

Una aplicación de presupuesto familiar para hogares canadienses. Un administrador crea el
hogar, invita hasta cinco miembros más, configura los ingresos y gastos fijos de la casa, y
a partir de ahí la familia lleva su presupuesto mes a mes: registra lo que gasta, compara
contra lo planeado, cierra el mes y avanza al siguiente.

Se vende por **CAD $25 de pago único, de por vida**, con 14 días de prueba gratuita.

### Alcance de la Fase 1

Este documento cubre únicamente el núcleo financiero. Es un producto vendible por sí solo.

**Incluye:** autenticación, hogares y membresías con permisos, suscripción por Stripe,
configuración inicial del presupuesto (ingresos incluidos los variables, gastos fijos),
presupuesto anual y mensual editable, **planificación mensual con reparto en cascada del
sobrante y mesada personal**, registro manual de transacciones, Overview con gráficas,
Balance con cierres mensuales, Goals, Settings y Profile, los tres temas visuales, y
bilingüismo inglés/francés.

**No incluye** (ver sección 12): OCR de recibos, reportes ad-hoc, machine learning,
simulador de compras, gestión de deudas, módulo fiscal de la CRA, registro sin conexión.

El esquema de datos de la Fase 1 se diseña deliberadamente para soportar esas fases
posteriores sin migraciones dolorosas.

---

## 2. Decisiones de arquitectura

Cada decisión aquí se tomó explícitamente durante el diseño. Las razones importan tanto
como las decisiones.

### 2.1 Plataforma: PWA ahora, nativo después

Django sirve HTML responsive; la aplicación se instala en el teléfono desde el navegador
(`manifest.json`, ícono, pantalla de inicio, service worker que cachea la interfaz). Un solo
código base para iOS, Android y escritorio.

Si el producto se valida, se envuelve el mismo frontend en **Capacitor** para publicar en
App Store y Play Store, sin reescribir nada. La decisión cara —desarrollar apps nativas— se
difiere hasta tener evidencia de que vale la pena.

### 2.2 Django es dueño de toda la lógica; Supabase es Postgres + Storage

Supabase aporta **únicamente** la base de datos Postgres gestionada y el almacenamiento de
archivos (imágenes de recibos, a partir de la Fase 2). No usamos Supabase Auth ni sus
políticas RLS.

La razón: los permisos de esta aplicación son no triviales (seis miembros, cuatro permisos
granulares, dos ámbitos de visibilidad). Repartidos entre políticas SQL y código Django,
tendríamos dos fuentes de verdad que se contradicen en silencio — una fuente clásica de
fugas de datos entre hogares. Un solo lugar que auditar.

### 2.3 El presupuesto: reglas + materialización al cierre

La decisión central del sistema. Se evaluaron tres opciones:

- **Filas materializadas** (generar las 12 filas de cada regla al configurar): consultas
  triviales, pero cambiar el alquiler "de aquí en adelante" exige actualizar N filas.
- **Reglas puras** (calcular todo al vuelo): sin nada que regenerar, pero un mes ya cerrado
  cambiaría retroactivamente al editar una regla vieja. Inaceptable para un balance.
- **Reglas + materialización al cierre** — la elegida.

Las reglas son la fuente de verdad de los meses futuros. Al abrir un mes se materializa su
presupuesto como filas editables. Al cerrarlo, esas filas se congelan en un histórico
inmutable. Los meses futuros siguen siendo reglas hasta que les toque.

Esto resuelve exactamente los tres comportamientos requeridos: editar el presupuesto anual
(tocas la regla), editar un mes concreto (tocas sus filas), y consultar cierres pasados
(histórico congelado, inmune a cambios posteriores).

### 2.4 Hogar y personal: un solo modelo, un eje de visibilidad

No hay dos subsistemas. Cada transacción, meta y regla de gasto tiene un **dueño** (el
miembro) y un **ámbito**: `household` (por defecto) o `personal`.

- La vista **Household** agrega únicamente lo de ámbito `household`.
- La vista **Personal** muestra todo lo del miembro que consulta —sus ingresos, los gastos
  que registró, sus metas— sin importar el ámbito.

Así "mi porción del hogar" y "mi espacio privado" son la misma pantalla con un filtro
distinto, no dos modelos duplicados.

### 2.5 Frontend sin build step

Plantillas de Django + **htmx** (intercambio de fragmentos HTML sin recargar) + **Alpine.js**
(estado local pequeño: modales, acordeones). Gráficas con **Chart.js** por CDN.

Sin React, sin `npm`, sin compilación. Esto mantiene la premisa de "principalmente Python"
de forma real, y hace que envolver en Capacitor más adelante sea trivial.

---

## 3. Modelo de datos

### 3.1 Cuentas y acceso

**`Household`**
Nombre visible ("Family Thompson"), moneda (`CAD`), zona horaria, mes de inicio del año
presupuestario, `family_size`, `allowance_rollover` (§4.5.4) y marca de tiempo de creación.

`family_size` es cuántas personas viven en la casa, que **no** es lo mismo que cuántas
usan la aplicación: un hogar de cinco puede tener dos cuentas. Se usa para métricas per
cápita y como referencia en las recomendaciones de la Fase 3, nunca como límite de acceso —
el límite de acceso son las 6 membresías.

**`Membership`** — une usuario ↔ hogar
- `role`: `admin` | `member`
- Permisos booleanos: `can_view_budget`, `can_edit_budget`, `can_add_transactions`,
  `can_view_reports`
- `joined_at`, `is_active`

Quien registra el hogar es `admin`. Puede invitar hasta **5 miembros adicionales** (6 en
total). El límite se valida en el modelo, no solo en la interfaz.

**`Invitation`**
Hogar, correo del invitado, token firmado, `expires_at` (7 días), `accepted_at`,
`invited_by`, `language` (idioma en que se envía el correo).

**`Subscription`** — una por hogar
`stripe_customer_id`, `stripe_checkout_session_id`, `status` (`trialing` | `active` |
`expired`), `trial_ends_at`, `paid_at`.

**`StripeEvent`**
`event_id` de Stripe, tipo, `processed_at`. Existe únicamente para garantizar idempotencia
de los webhooks.

**`Profile`** — uno por usuario
Avatar, nombre visible, `theme` (`sereno` | `nocturno` | `accesible`), `language`
(`en` | `fr`).

### 3.2 Las reglas — fuente de verdad de los meses futuros

**`Category`** — árbol jerárquico (`parent` autorreferencial)
- `slug` — identificador estable para las categorías del sistema (`rent`, `groceries`,
  `hydro`…). Es lo que permite mostrarlas traducidas.
- `name` — solo se usa para las categorías que crea el usuario, guardadas en su idioma.
- `is_system` — distingue las precargadas de las creadas por el hogar.
- `household` — nulo para las del sistema.
- `tax_category` — nulo en la Fase 1. Reservado para la Fase 4 (CRA): `medical`,
  `donations`, `childcare`, `rrsp`, etc.
- `kind`: `income` | `expense`

Árbol precargado: Vivienda (alquiler, hipoteca), Servicios (agua, gas, electricidad,
internet), Suscripciones, Alimentos, Transporte, Gasolina, Entretenimiento, Obligaciones
financieras, Préstamos bancarios. El hogar puede añadir y renombrar.

**`IncomeSource`**
- `owner` (miembro), `household`, `name`
- `source_type`: `salary` | `freelance` | `rental` | `pension` | `benefits` | `other`
- `amount_type`: `fixed` | `estimated` | `range` | `rolling_average` | `irregular`
- `amount`, `amount_min`, `amount_max` (según el modo — ver §4.1)
- `periodicity`, `effective_from`, `effective_to`
- `scope`: `household` | `personal`

**`ExpenseRule`**
- `household`, `category`, `name`, `amount`
- `periodicity`, `effective_from`, `effective_to`
- `is_essential` (esencial vs. prescindible — alimenta las recomendaciones de la Fase 3)
- `owner` (opcional, para gastos fijos personales), `scope`

**Periodicidades soportadas** (compartidas por ingresos y gastos): semanal, quincenal,
bimensual (dos veces al mes), mensual, bimestral, trimestral, semestral, anual.

**Las reglas nunca se mutan.** Subir el alquiler de $1800 a $1950 cierra la regla vieja con
`effective_to = 31 de marzo` y crea una nueva con `effective_from = 1 de abril`. El
historial queda intacto sin un modelo adicional, y "¿desde cuándo pagamos más?" es una
consulta, no una investigación.

### 3.3 Lo mensual

**`BudgetMonth`**
`household`, `year`, `month`, `status` (`future` | `open` | `closed`), `opened_at`,
`closed_at`.

Los meses `future` **no existen como filas**: se calculan desde las reglas al consultarlos.

**`BudgetLine`** — las filas materializadas de un mes abierto
`budget_month`, `category`, `source_rule` (nulo si es excepcional), `kind`
(`income`|`expense`), `planned_amount`, `is_exceptional`, `owner`, `scope`, `note`.

Lo excepcional vive aquí: el viaje, la matrícula, los regalos de Navidad. Se agregan al mes
abierto y no afectan a ningún otro mes.

**`Transaction`** — lo que realmente pasó
`household`, `budget_month`, `category`, `merchant`, `amount`, `date`, `member`,
`payment_method`, `scope`, `receipt_image` (nulo en Fase 1), `note`, `budget_line` (opcional,
si se vincula a una línea concreta).

**`Merchant`**
`household`, `name`, `normalized_name`. Entidad propia con normalización, para que
`WALMART #3421` y `Walmart Supercentre` sean el mismo comercio. Es la base de las consultas
tipo "¿cuánto gastamos en Walmart este año?" que llegan en la Fase 2.

**`Goal`** y **`GoalContribution`**
Meta con `name`, `scope` (hogar o personal), `owner`, `status`, y **dos formas de
expresarse** (`contribution_mode`):

- `by_target_date` — "$7,200 para el 30 de junio de 2027". La aplicación calcula el aporte
  mensual necesario.
- `by_monthly_amount` — "$600 cada mes". La aplicación calcula la fecha de llegada.

Son la misma cosa vista al revés: el usuario da dos datos y la aplicación deriva el tercero.
Ambas formas deben existir, porque las familias piensan de las dos maneras. Las
contribuciones registran aportes con fecha, miembro y origen (manual o automática desde la
cascada).

**`AllocationRule`** — las reglas de reparto del sobrante (§4.5)
- `household`, `order` (entero, define la prioridad en la cascada)
- `target_type`: `goal` | `allowance` | `category`
- `target_goal` / `target_category` (según el tipo)
- `method`: `fixed` | `percentage` | `remainder`
- `amount` (para `fixed`) o `percentage` (para `percentage`)
- `split`: para `allowance`, cómo se divide entre miembros — `equal` o pesos explícitos
- `is_active`

**`MonthlyAllocation`** — el reparto materializado de un mes
`budget_month`, `rule`, `planned_amount`, `actual_amount`, `member` (solo para mesadas). Se
escribe al confirmar la planificación y se ajusta al cerrar el mes.

**`AllowanceLedger`** — el saldo de mesada de cada miembro
`member`, `household`, `budget_month`, `granted` (lo asignado por la cascada), `spent` (lo
gastado con ámbito `personal` contra la mesada), `adjustment` (correcciones arrastradas de
un cierre anterior), `carried_in`, `carried_out`.

Es un libro mayor, no un campo mutable: cada mes es una fila y el saldo se deriva sumando.
Así "¿por qué tengo $145 este mes?" siempre tiene respuesta.

**`MonthlyClose`** — la foto congelada
`budget_month`, totales de ingresos y egresos presupuestados y reales, varianza por
categoría (JSON), balance final, saldo arrastrado al mes siguiente. **Inmutable una vez
escrito.**

### 3.4 Dinero

Todos los montos son **`DecimalField(max_digits=12, decimal_places=2)`**. Nunca `float`.

En coma flotante, `0.1 + 0.2 != 0.3`. En una aplicación financiera eso produce balances que
no cuadran por centavos, y un usuario que ve eso deja de confiar en la aplicación entera.
El redondeo es explícito, a 2 decimales, y siempre en el mismo punto del cálculo.

---

## 4. El motor de presupuesto

### 4.1 Ingresos que no son un monto fijo

Cinco modos, uno por fuente de ingreso:

| Modo | Para quién | Qué presupuesta |
|---|---|---|
| `fixed` | Sueldo estable | El monto declarado |
| `estimated` | Freelance con idea aproximada | La estimación del usuario, ajustable mes a mes |
| `range` | Comisiones, propinas | El **mínimo**; lo que exceda es superávit |
| `rolling_average` | Quien ya tiene 3+ meses registrados | Media móvil de los últimos 6 meses reales (mínimo 3 para habilitarse) |
| `irregular` | Trabajos esporádicos, bonos | **Cero**; cuando entra, es ingreso excepcional |

**Regla que gobierna todo el motor: el presupuesto siempre usa la cifra conservadora.** Un
hogar que presupuesta el mejor mes de un ingreso variable se endeuda en el peor. El
optimismo va en la proyección; nunca en el plan.

El modo `rolling_average` solo se ofrece cuando existe historia suficiente. Antes de eso la
interfaz dice explícitamente que aún no hay datos, en lugar de inventar un número.

### 4.2 Ciclo de vida del mes

```
FUTURO ──────────► ABIERTO ──────────► CERRADO
(proyección        (filas reales,       (foto congelada,
 desde reglas)      editables)           inmutable)
```

- **Futuro** → no persistido. Se calcula desde las reglas vigentes en cada consulta. Cambiar
  el alquiler se refleja al instante en todos los meses futuros.
- **Abierto** → se materializa el día 1 del mes (o al entrar por primera vez, lo que ocurra
  antes). Aquí se registran transacciones y se agregan las líneas excepcionales.
- **Cerrado** → lo cierra el usuario, o se cierra automáticamente a los 5 días de terminado
  el mes. Se escribe `MonthlyClose` y el saldo pasa al mes siguiente. **Nada posterior puede
  alterarlo.**

### 4.3 Editar sin romper el historial

| Dónde edita el usuario | Qué toca | A qué afecta |
|---|---|---|
| Vista **anual** | La regla (cierra una, crea otra) | Meses futuros |
| Vista **mensual** de un mes abierto | Las `BudgetLine` de ese mes | Solo ese mes |
| Mes **cerrado** | Nada — solo lectura | — |

### 4.4 Balance y arrastre

El balance de un mes es: saldo arrastrado del cierre anterior + ingresos reales − egresos
reales. El superávit o déficit se arrastra al mes siguiente al cerrar.

### 4.5 Reparto en cascada del sobrante

La función que distingue a Wealthome. Nace de un ritual real: una pareja se sienta cada mes,
estima el ingreso variable, agrega los gastos excepcionales de ese mes, y reparte lo que
sobra entre el ahorro y una mesada personal para cada uno. Casi ninguna aplicación de
presupuesto lo modela, porque todas asumen que el sobrante "se queda ahí".

#### 4.5.1 Además, cierra el diseño

Es el puente que faltaba entre Household y Personal. Un miembro que aporta todo su sueldo a
la casa no tenía, hasta ahora, ninguna fuente de dinero propio en el módulo Personal.

**La mesada es un gasto del hogar y un ingreso personal del miembro** — la misma cantidad,
vista desde los dos lados. Con eso, Personal › Budget deja de ser una vista filtrada y pasa
a tener presupuesto propio.

#### 4.5.2 La cascada

Al planificar el mes:

```
Ingresos estimados del mes
− Gastos fijos (incluido el entretenimiento familiar)
− Gastos excepcionales del mes
──────────────────────────────
  SOBRANTE PROYECTADO
        │
        ├─ Regla 1 (prioridad más alta)
        ├─ Regla 2
        └─ Regla N
```

Cada `AllocationRule` tiene un destino (una meta de ahorro, la mesada de los miembros, una
categoría o fondo) y un método (monto fijo, porcentaje del sobrante, o todo el resto). Las
reglas se ordenan por prioridad y el sobrante cae por ellas en cascada.

Ejemplo canónico: (1) Ahorro familiar, monto fijo $600. (2) Mesada personal, el resto,
repartido en partes iguales. Otra familia puede poner $50 a cada hijo, 10% al fondo de
vacaciones, y el resto a reserva de emergencia. Es el mismo mecanismo.

#### 4.5.3 Qué pasa cuando el sobrante real es menor al proyectado

Pasa constantemente: un ingreso por horas cierra por debajo de lo estimado.

**El faltante lo absorbe la última regla de la cascada**, y si no alcanza, la penúltima. Eso
es lo que significa una cascada, y hace que el orden importe de verdad: con el ahorro arriba
y las mesadas abajo, un mes flojo se come la diversión, no el ahorro. Una familia que
prefiera lo contrario solo reordena las reglas.

**Pero la mesada ya asignada nunca se retira.** Se fija al planificar y no se mueve durante
el mes — de nada sirve enterarse el día 30 de que tenías $100 para gastar. Si el cierre real
deja un faltante, se registra como `adjustment` negativo contra la mesada **del mes
siguiente**.

Ejemplo: sobrante proyectado $800 → $600 al ahorro, $100 a cada uno. Sobrante real $720. El
ahorro recibe sus $600 íntegros; el faltante de $80 se descuenta de las mesadas de octubre,
$40 a cada uno. Nadie pierde dinero que ya gastó.

#### 4.5.4 Acumulación de la mesada

`Household.allowance_rollover` (por defecto **activado**): la mesada no gastada se acumula al
mes siguiente. Guardar $100 durante tres meses para comprar algo de $300 es exactamente lo
que hace que se sienta dinero propio y no una asignación que caduca.

Con la opción desactivada, el saldo no gastado vuelve al hogar al cerrar el mes.

#### 4.5.5 Entretenimiento familiar ≠ mesada personal

Son cosas distintas y la interfaz debe decirlo con claridad:

| | Entretenimiento familiar | Mesada personal |
|---|---|---|
| Qué es | Salidas, comidas, ocio compartido | Dinero individual, sin justificación |
| Dónde vive | `ExpenseRule`, gasto fijo del hogar | `AllocationRule` sobre el sobrante |
| Quién decide | El hogar, al configurar | Cada miembro, al gastarlo |
| Cuándo se fija | Antes del sobrante | Después del sobrante |

Confundirlas es lo que hace que las parejas discutan por dinero.

#### 4.5.6 El flujo "Planificar el mes"

Un asistente de tres pasos, al abrir cada mes:

1. **Ingresos** — los fijos vienen precargados; los variables piden confirmar o ajustar la
   estimación del mes. Es el único dato que la familia teclea de verdad cada mes.
2. **Salidas** — gastos fijos precargados y editables, más las partidas excepcionales de
   ese mes (inscripciones, viajes, regalos).
3. **Reparto** — muestra el sobrante proyectado, la cascada aplicada y la mesada resultante
   por miembro (con el acumulado del mes anterior). Las reglas se reordenan arrastrando.

Al confirmar, el mes pasa a `open` y se escriben las `MonthlyAllocation` y el
`AllowanceLedger` del mes.

---

## 5. Suscripción y pagos

### 5.1 El trial con pago único

**Stripe no ofrece períodos de prueba para pagos únicos** — `trial_period_days` es una
función de las suscripciones recurrentes, y este producto no recurre. El trial lo gestiona
la aplicación:

1. El administrador se registra → se crea el hogar con `trial_ends_at = hoy + 14 días`,
   acceso completo, **sin pedir tarjeta**.
2. En cualquier momento (o al día 14) → Stripe Checkout en modo `payment`, CAD $25, una vez.
3. El webhook `checkout.session.completed` marca la suscripción `active`, de por vida.

No pedir tarjeta al inicio reduce la fricción para un producto de $25 y evita almacenar
datos de pago de gente que quizá nunca compre. La contrapartida asumida: algunos usuarios
prueban y no vuelven.

### 5.2 Reglas de correctitud, no negociables

- **El webhook es la única fuente de verdad.** Nunca la URL de retorno: cualquiera puede
  visitar `/success/` sin haber pagado.
- **Idempotencia.** Se guarda el `event_id` de cada evento procesado (`StripeEvent`). Stripe
  reintenta los webhooks; sin esto un hogar puede quedar en estado inconsistente.
- **Expirar no destruye datos.** Al día 15 sin pago el hogar pasa a **solo lectura**: se ven
  todos los datos históricos, no se puede registrar nada nuevo. Borrar las finanzas de una
  familia por no pagar $25 es indefendible.
- **La moneda es CAD.** El precio se define en dólares canadienses porque el mercado es
  Canadá.

### 5.3 Checkout localizado

Se pasa el parámetro `locale` a Stripe Checkout, para que la pasarela aparezca en el idioma
del usuario.

---

## 6. Permisos y seguridad

### 6.1 La regla que no se negocia

**Toda consulta se filtra por el hogar del usuario autenticado, sin excepción.**

En una aplicación financiera multi-inquilino, un solo `filter()` olvidado le muestra a una
familia las finanzas de otra. Por eso los permisos viven en una **capa central de
autorización** que las vistas invocan, y no repartidos a mano vista por vista, donde tarde o
temprano uno se olvida.

Mecanismo: un `manager` por defecto en los modelos con ámbito de hogar que exige el hogar
como parámetro, más comprobaciones de permiso a nivel de objeto en la capa de servicio.

### 6.2 Los cuatro permisos

`can_view_budget`, `can_edit_budget`, `can_add_transactions`, `can_view_reports` — el
administrador los ajusta por miembro. Un adolescente puede registrar sus gastos sin ver la
hipoteca.

### 6.3 Invitaciones

Enlace firmado, expira a los 7 días. El límite de 5 miembros adicionales se valida **al
crear la invitación y otra vez al aceptarla** — de lo contrario, seis invitaciones
pendientes se aceptan todas a la vez y el hogar termina con más miembros de los permitidos.

---

## 7. Interfaz

### 7.1 Navegación

Dos ámbitos de primer nivel —**Household** y **Personal**— con los mismos submódulos
(Overview, Budget, Balance, Goals; Reports solo en Household, desde la Fase 2), más
**Settings** y **Profile**.

En móvil, barra inferior fija. La acción más frecuente de la aplicación —**registrar un
gasto**— ocupa el centro, siempre a un toque. La quinta pestaña queda reservada para
Reportes en la Fase 2; en la Fase 1 ese espacio lo ocupa Metas:

```
┌────────────────────────────────────────────────┐
│  Hogar   Personal   [ + ]   Metas    Ajustes   │
└────────────────────────────────────────────────┘
```

En escritorio, barra lateral con el árbol completo. El mismo HTML, distinta hoja de estilos.

### 7.2 Pantallas de la Fase 1

- **Onboarding** (asistente): crear hogar → miembros → ingresos por miembro → gastos fijos →
  meta de ahorro → reglas de reparto
- **Planificar el mes** (asistente de 3 pasos, §4.5.6): ingresos → salidas → reparto
- **Household › Overview**: presupuesto del mes vs. gasto real, flujo de caja, movimientos
  recientes, gráficas, filtros, botón de registrar
- **Household › Budget**: vista anual y mensual, edición de reglas y de líneas del mes
- **Household › Balance**: balance actual y cierres de meses anteriores
- **Household › Goals**: metas de ahorro con progreso y fecha objetivo
- **Personal › Overview / Budget / Balance / Goals**: las mismas vistas, filtradas al miembro
- **Personal › Budget**: incluye la mesada del mes, su acumulado y en qué se ha ido
- **Settings**: miembros y permisos, suscripción, tema, idioma, categorías, reglas de
  reparto y acumulación de mesada
- **Profile**: avatar, nombre, tema, idioma

### 7.3 Estilo visual

Dirección elegida: **skeuomorfismo suave (neomorfismo)**. Superficies que parecen talladas
en un mismo material, relieve sutil, paleta financiera sobria en verdes y grises azulados.

### 7.4 Los tres temas

| Tema | Para quién |
|---|---|
| **Sereno** (por defecto) | Todos. Gris perla, relieve suave, texto 15 px, verde discreto. |
| **Nocturno** | Preferencia personal. El mismo Sereno invertido: idénticas formas y tamaños, solo cambian los colores. |
| **Accesible** | Tercera edad y vista cansada. Texto 20 px, contraste 14:1 (supera WCAG AAA), **bordes sólidos en lugar de sombras**, botones de 56 px de alto. |

El tema Accesible no es "Sereno con letra grande". El neomorfismo comunica profundidad
mediante sombras delicadas, y esa es precisamente la señal que primero se pierde con la
vista cansada o una pantalla con reflejo. Ahí se sustituye por bordes, que son inequívocos.

**Implementación:** `data-theme="sereno|nocturno|accesible"` en el elemento raíz;
`tokens.css` define los tres juegos de variables. Los componentes se escriben **una sola
vez**. El tema se guarda en el perfil, así que cada miembro elige el suyo sin afectar a los
demás.

### 7.5 Organización del CSS

CSS puro, sin preprocesadores. Cuatro archivos que se editan por separado y se sirven como
una sola hoja:

```
tokens.css      → colores, sombras, tipografía, espaciado (los tres temas)
base.css        → reset y elementos HTML
components.css  → botones, tarjetas, formularios, tablas
modules.css     → lo específico de cada pantalla
```

---

## 8. Internacionalización (EN / FR)

Inglés por defecto, francés como segunda opción. Se implementa **desde la primera línea de
código**: retrofitear i18n a una aplicación ya escrita obliga a revisar cada plantilla y
cada mensaje de error a mano; hacerlo desde el inicio no cuesta casi nada.

- **Django i18n**: cada texto visible envuelto en `{% trans %}` / `gettext()`. Traducciones
  en `locale/en/` y `locale/fr/`.
- **El idioma se guarda en el perfil de cada miembro**, no en el navegador ni en el hogar.
  Un miembro en inglés y otro en francés, en la misma familia, sobre los mismos datos.
- **Formato de números y fechas** — crítico en una aplicación de dinero:

| | Inglés (en-CA) | Francés (fr-CA) |
|---|---|---|
| Monto | `$2,847.50` | `2 847,50 $` |
| Fecha | `August 30, 2026` | `30 août 2026` |

  En francés canadiense el signo va **después**, el decimal es **coma** y los miles se
  separan con **espacio**. Se formatea siempre a través de la localización de Django
  (`USE_L10N`), nunca con interpolación manual tipo `f"${amount}"`.

- **Categorías del sistema**: se muestran traducidas a partir de su `slug`. Las que crea el
  usuario se guardan tal cual las escribió.
- **Correos** (invitación, aviso de fin de prueba) en el idioma del destinatario. Como el
  invitado aún no tiene perfil, quien invita elige el idioma de la invitación.

---

## 9. Pruebas

**El motor de presupuesto concentra casi toda la lógica real** — regla → materialización del
mes → cierre → arrastre de saldo. Ahí van las pruebas a fondo, con `pytest` +
`pytest-django` + `factory_boy`.

Casos que deben quedar cubiertos explícitamente:

- Cada periodicidad genera las líneas correctas en cada mes
- Cada uno de los cinco modos de ingreso variable presupuesta la cifra conservadora correcta
- Cerrar una regla y crear su sucesora no altera ningún mes ya cerrado
- El arrastre de saldo entre cierres consecutivos cuadra al centavo
- Un mes cerrado rechaza toda escritura
- La cascada reparte correctamente con cada combinación de métodos (`fixed`, `percentage`,
  `remainder`) y con reglas reordenadas
- Un sobrante real menor al proyectado se absorbe desde la última regla hacia arriba, sin
  tocar las de prioridad alta
- Una mesada ya asignada nunca se reduce dentro del mes; el ajuste aparece en el mes
  siguiente
- El acumulado de mesada cuadra al centavo a lo largo de varios meses, con la opción de
  acumulación activada y desactivada
- Un sobrante negativo (mes deficitario) no reparte nada y no genera mesada

**Aislamiento entre hogares:** una batería de pruebas que verifica que ningún endpoint
devuelve datos de otro hogar. Esta es la clase de bug que no se descubre en desarrollo.

**Extremo a extremo** con Playwright, para los tres flujos que no pueden romperse:
registro → onboarding → pago; invitar y aceptar miembro; registrar un gasto.

---

## 10. PWA

`manifest.json`, íconos, pantalla de inicio, y service worker que cachea la interfaz para
que abra rápido y permita **consultar** sin señal.

Registrar gastos estando sin conexión (en el supermercado, sin datos) es un caso de uso
real, pero exige cola de sincronización y resolución de conflictos. Va a la Fase 2.

---

## 11. Stack

| Capa | Elección |
|---|---|
| Backend | Python + Django |
| Base de datos | Postgres (Supabase) |
| Archivos | Supabase Storage |
| Pagos | Stripe (Checkout, modo `payment`) |
| Frontend | Plantillas Django + htmx + Alpine.js |
| Gráficas | Chart.js (CDN) |
| Estilos | CSS puro, 4 archivos |
| Pruebas | pytest, pytest-django, factory_boy, Playwright |
| Móvil | PWA; Capacitor en fase posterior |

---

## 12. Fuera de alcance (fases posteriores)

Cada fase tendrá su propio ciclo de diseño → plan → implementación.

**Fase 2 — Captura y reportes**
OCR de recibos por foto (Google Vision o AWS Textract), reportes ad-hoc (por categoría, por
comercio, por miembro, por período), registro sin conexión con sincronización.

**Fase 3 — Inteligencia**
Aprendizaje de hábitos de gasto, recomendaciones, alertas anticipadas, simulador de compras
("si compro este teléfono, ¿cómo afecta mis finanzas?").

Esta fase se construye **después**, deliberadamente: un modelo sin histórico de
transacciones no puede recomendar nada. Requiere meses de datos reales. El esquema de la
Fase 1 ya captura todo lo que necesitará —categoría, comercio, miembro, fecha, esencial vs.
prescindible, presupuestado vs. real— para que llegado el momento no haya que migrar nada.

**Fase 4 — Deudas e impuestos**
Seguimiento y proyección de deudas, estrategias de amortización, y módulo de apoyo a la
declaración de impuestos de la **CRA**.

El campo `tax_category` se siembra desde la Fase 1 aunque no se use, porque etiquetar dos
años de gastos retroactivamente es un trabajo que nadie hace nunca. La terminología fiscal
usará los **términos oficiales de la CRA en francés**, no traducciones propias: el usuario
los compara contra sus formularios reales.

---

## 13. Criterios de éxito de la Fase 1

1. Un administrador se registra, completa el onboarding y ve su presupuesto anual en menos
   de 10 minutos.
2. Invita a un miembro con permisos limitados; ese miembro entra y ve exactamente lo que le
   corresponde, ni más ni menos.
3. Registra gastos durante un mes, cierra el mes, y el balance del mes siguiente arranca con
   el saldo arrastrado correcto.
4. Un ingreso variable en modo `range` presupuesta el mínimo, y el exceso aparece como
   superávit al cierre.
5. Una pareja planifica el mes en tres pasos, ve su sobrante repartido según sus reglas, y
   cada uno sabe desde el día 1 cuánta mesada tiene.
6. Un mes que cierra por debajo de lo estimado deja el ahorro intacto y ajusta la mesada del
   mes siguiente, sin retirar nada ya gastado.
7. Editar el alquiler en marzo no altera ningún cierre de enero ni febrero.
8. La aplicación funciona completa en francés, con montos formateados `2 847,50 $`.
9. Los tres temas se aplican sin ningún componente duplicado.
10. Ninguna consulta devuelve datos de otro hogar, verificado por pruebas.
11. El pago por Stripe activa el hogar de por vida vía webhook, y un webhook repetido no
   produce ningún efecto adicional.
