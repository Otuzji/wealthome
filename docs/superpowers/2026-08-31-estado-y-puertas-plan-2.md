# Wealthome — Estado al cerrar el Plan 1, y qué resolver antes del Plan 2

**Fecha:** 2026-08-31
**Rama:** `main`, commit de integración `1e7147f`, publicado en `github.com/Otuzji/wealthome`

Este documento existe porque el espacio de trabajo del Plan 1 se borró al terminar.
Todo lo que hay aquí son decisiones y hallazgos que no se deducen leyendo el código.

---

## 1. Qué está construido

El **Plan 1 (Fundación)** completo: 17 commits, 88 pruebas contra Postgres real, revisión
final de rama limpia.

- `apps/accounts/` — `User` (correo como identificador, unicidad insensible a mayúsculas
  con `UniqueConstraint(Lower("email"))`), `Profile` (tema e idioma), registro, sesión,
  `PerfilLocaleMiddleware`, `UserAdmin` que hashea correctamente.
- `apps/households/` — `Household`, `Membership` (4 permisos, máximo 6 miembros),
  `Invitation`; `scoping.py` (`HouseholdScoped`, `.for_user()`, `.for_household()`);
  `permissions.py` (`get_membership`, `require_permission`); `services.py`
  (`crear_hogar`, `invitar`, `aceptar_invitacion`).
- `apps/core/templatetags/money.py` — `format_money` y el filtro `{{ x|money }}`.
- `templates/`, `static/css/` — los tres temas (`sereno`, `nocturno`, `accesible`) por
  variables CSS; los componentes se escriben una sola vez.
- `locale/{en,fr}/` — catálogos completos, **escritos a mano** (no hay cadena de
  herramientas GNU gettext en esta máquina) y compilados con `Tools/i18n/msgfmt.py`.

**Nada del motor financiero existe todavía.** Ni categorías, ni ingresos, ni gastos, ni
presupuestos, ni transacciones, ni metas, ni la cascada de reparto.

### Cómo arrancarlo

```
cd C:\Users\otton\OneDrive\Documents\Wealthome
.venv\Scripts\python.exe manage.py migrate      # crea las tablas reales, aún no se hizo
.venv\Scripts\python.exe manage.py runserver
```

`.env` está en la raíz, ignorado por git, con la cadena del pooler de Supabase.

---

## 2. Las tres puertas — resolver ANTES del primer modelo financiero

La revisión final las marcó como condición de entrada al Plan 2. Las tres son baratas hoy
y caras después: cada una es una línea o un archivo pequeño contra **cero** modelos con
ámbito de hogar, y se convierte en una refactorización a través de una docena de modelos,
sus migraciones y sus plantillas en cuanto el Plan 2 avance.

### Puerta 1 — El aislamiento es una convención, no una barrera

`apps/households/scoping.py`. El spec §6.1 pide *"un manager por defecto en los modelos con
ámbito de hogar **que exige el hogar como parámetro**"*. Lo que hay es un `Manager` normal
con dos métodos de conveniencia: `Modelo.objects.all()` y `.filter()` siguen disponibles y
son lo primero que escribe cualquier desarrollador de Django.

La única defensa es una prueba que busca `.objects.` por texto en los módulos de vistas
(`tests/test_scoping.py`), cuyos puntos ciegos están documentados encima de ella. Los dos
graves:

- **Accesores inversos.** `hogar.transaccions.all()` nunca escribe `Modelo.objects`.
- **`get_object_or_404(Transaccion, pk=pk)`** tampoco — y es el estilo que ya usa
  `apps/households/views.py`, así que copiarlo olvidando el filtro de hogar pasa inadvertido.

Y uno que el revisor final añadió y que es el peor: **`ModelForm` y `ModelChoiceField`**.
Un formulario con clave foránea a `Category` renderiza por defecto `Category.objects.all()`
en un `<select>` — los nombres de categoría de **todas** las familias, en el HTML, sin que
ninguna vista contenga `.objects.`. El Plan 2 está lleno de formularios.

Forma propuesta:

```python
class HouseholdScopedManager(models.Manager.from_queryset(HouseholdScopedQuerySet)):
    def get_queryset(self):
        raise RuntimeError("Usa .for_user(user) o .for_household(hogar).")
    # for_user / for_household llaman a super().get_queryset() internamente

class HouseholdScoped(models.Model):
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    objects = HouseholdScopedManager()
    unscoped = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "unscoped"   # el admin, los descriptores y select_related lo necesitan
```

Más una base `HouseholdScopedModelForm` que exija el hogar en `__init__` y vuelva a
consultar cada `ModelChoiceField.queryset` a través de `for_household`.

### Puerta 2 — `for_user` y `_hogar_activo` responden distinto a "¿qué hogar?"

`apps/households/scoping.py` devuelve filas de **todos** los hogares activos del usuario.
`apps/households/views.py::_hogar_activo` devuelve **el primero**. Hoy coinciden porque cada
usuario tiene un hogar.

El día que no coincidan, el Plan 2 sumaría el dinero de dos familias en un solo presupuesto
**sin lanzar ningún error**. Nadie ve una traza: ven un número equivocado y plausible, que
es el peor modo de fallo posible en software financiero.

Hay que decidir cuál es "el hogar" antes de que existan modelos con dinero. La recomendación
del revisor: quedarse con `for_household(hogar)`, resolviendo el hogar una vez por petición,
y retirar `for_user` — coincide con la realidad de un hogar por usuario y saca la costura a
la luz en vez de esconderla.

Cuando esté decidido, escribir la prueba del usuario en dos hogares (hoy ausente a
propósito: escribirla antes solo fijaría el comportamiento accidental).

### Puerta 3 — Los cuatro permisos no gobiernan nada

`apps/households/permissions.py::require_permission` está probado y **no lo llama ningún
código de producción** — solo las pruebas. Las dos vistas que controlan algo comprueban el
rol a mano (`get_membership(...).role != Membership.ADMIN`).

Es defendible en el Plan 1, porque no hay nada que proteger. Pero significa que la
ergonomía de esa API nunca se ha usado, y el Plan 2 la necesitará en una docena de sitios.
Si no se resuelve antes, sus autores copiarán la comprobación en línea — que es exactamente
el *"permisos repartidos a mano vista por vista"* que el spec §6.1 nombra como lo que hay
que evitar.

Falta un decorador y su primer uso real:

```python
@requiere_permiso("can_edit_budget")   # resuelve el hogar y lanza PermissionDenied
def editar_presupuesto(request, hogar): ...
```

---

## 3. Dos costuras más que conviene colocar mientras son gratis

- **`MoneyField`** — un `partial(DecimalField, max_digits=12, decimal_places=2)` en
  `apps/core`, para que la restricción del spec §3.4 se exprese una vez en lugar de
  vigilarse por revisión en doce modelos.
- **Moneda del hogar** — `money.py` lee `settings.DEFAULT_CURRENCY` e ignora la columna
  `Household.currency`, que existe. Solo CAD es una decisión de producto legítima, pero la
  contradicción está ahí y alguien la "arreglará" mal dentro de dos planes.

---

## 4. Deudas menores conocidas (ninguna bloquea)

Veinte hallazgos menores se triaron en la revisión final; dos se arreglaron (unicidad de
correo, alta insegura desde `/admin/`). De los demás, los que vale la pena recordar:

- No hay **CI**. La suite solo corre en una máquina contra el Supabase real, con
  `--reuse-db` y el riesgo de esquema viejo. Un job contra un Postgres desechable se paga
  solo en cuanto el Plan 2 multiplique las migraciones, y resolvería de paso la flakiness
  del pooler.
- **Cuatro dialectos para "no puedes hacer eso"**: `PermissionDenied`,
  `HttpResponseForbidden()` con cuerpo vacío (el usuario ve una página en blanco, sin texto
  traducido), `get_object_or_404`, y `require_permission` sin usar. Unificar antes de que
  crezcan las vistas, con plantillas `403.html` y `404.html`.
- **Las invitaciones pendientes consumen puestos y no se pueden ver ni revocar.** Un
  administrador que teclee mal cinco correos bloquea su hogar siete días sin explicación.
  Hueco del plan, no de la implementación.
- **URLs en español** (`/registro/`, `/hogar/ajustes/`) en un producto inglés/francés. Todo
  el texto visible está traducido y luego la barra de direcciones está en español. Cambiarlo
  cuesta nada ahora y más con cada ruta que añada el Plan 2.
- `Invitation.language` sin `choices`: añadirlo **cuando** el Plan 3 conecte plantillas de
  correo con ese campo, no después.
- `Profile.avatar` es un `ImageField` con `MEDIA_ROOT` local; un despliegue real necesita
  Supabase Storage.

---

## 5. Trampas del entorno (cuestan tiempo si no se saben)

- **El pooler de Supabase** (puerto 6543) deja sesiones abiertas: el teardown avisa que
  `test_postgres` está en uso y dos corridas seguidas pueden dar errores de arranque que un
  reintento limpia. `pytest.ini` ya lleva `--reuse-db`.
- **Tras añadir una migración hay que correr una vez con `--create-db`**, o la base
  reutilizada conserva el esquema viejo y las pruebas mienten.
- **No hay cadena GNU gettext** en esta máquina: `makemessages` y `compilemessages` no
  funcionan. Los catálogos se mantienen a mano y se compilan con `Tools/i18n/msgfmt.py`.
  `tests/test_catalogo_exhaustivo.py` es lo que impide que una cadena nueva se quede fuera.
- **Los agentes se cuelgan** si lanzan pruebas en segundo plano y esperan un aviso: hay que
  ordenarles explícitamente que corran la suite en primer plano y esperen. Pasó tres veces.
- La base `test_postgres` **no es basura**: es la que reutiliza `--reuse-db`.
- El panel de Supabase solo muestra la base `postgres`. Las demás se listan con
  `SELECT datname FROM pg_database WHERE NOT datistemplate;` en el SQL Editor.

---

## 6. Qué cubre el Plan 2

Del spec `docs/superpowers/specs/2026-08-30-wealthome-nucleo-financiero-design.md`,
secciones §3.2, §3.3 y §4 completas:

categorías jerárquicas con `tax_category`; `IncomeSource` con los cinco modos de ingreso
variable; `ExpenseRule` y las ocho periodicidades; el ciclo de vida del mes
(futuro → abierto → cerrado); `BudgetLine`, `Transaction`, `Merchant` con normalización;
`MonthlyClose` inmutable; `Goal` en sus dos formas; y **el reparto en cascada del sobrante**
(§4.5) con `AllocationRule`, `MonthlyAllocation` y `AllowanceLedger`.

La cascada es la función que distingue al producto y nació del ritual mensual real del
dueño del proyecto. Su parte delicada está en §4.5.3: cuando el sobrante real queda por
debajo del proyectado, el faltante lo absorbe la última regla, pero **la mesada ya asignada
nunca se retira** — el ajuste cae en el mes siguiente.
