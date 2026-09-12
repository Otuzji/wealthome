"""El único módulo que cruza el ORM y el motor.

Lee modelos, llama a apps/budget/engine/ y escribe el resultado. Que la
frontera esté en un solo archivo es lo que la hace auditable de un vistazo.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.budget.engine import allowance as motor_allowance
from apps.budget.engine import cascade as motor_cascade
from apps.budget.engine import closing as motor_closing
from apps.budget.engine import income as motor_income
from apps.budget.engine.money import centavos
from apps.budget.models import (
    DIAS_PARA_EL_CIERRE_AUTOMATICO,
    AllocationRule,
    AllowanceLedger,
    BudgetLine,
    BudgetMonth,
    ExpenseRule,
    GoalContribution,
    IncomeSource,
    MesCerrado,
    MonthlyAllocation,
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
        media = fuente.amount_type == motor_income.ROLLING_AVERAGE
        cifra = fuente.cifra_del_mes(
            historial=historial_de_ingreso(fuente, primero) if media else ()
        )
        if cifra is None:
            # rolling_average sin historia: aún no hay datos, y no se inventa
            # un número. La interfaz lo dice con todas sus letras.
            continue
        lineas.append(
            LineaProyectada(
                categoria_id=categoria_de_ingreso.pk, kind=INCOME,
                # Los otros cuatro modos dan la cifra de UN pago, y hay que
                # multiplicarla por las veces que cae en el mes (§2.2). La
                # media móvil ya es de totales mensuales: multiplicarla
                # presupuestaría el doble en un ingreso quincenal.
                importe=centavos(cifra) if media else centavos(cifra * veces),
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
        # Hallazgo de la revisión previa a esta tarea: BudgetLine.clean()
        # rechaza una línea cuyo kind no coincida con el de su categoría. Sin
        # full_clean() aquí, una ExpenseRule mal configurada (apuntando a una
        # categoría de ingreso) escribiría igual la línea contradictoria, y el
        # error solo aparecería mucho después, dentro de engine.closing.cerrar,
        # señalando una categoría y nada más.
        linea.full_clean()
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
    # El §6 del diseño del Plan 2 lo exige para materializar y para cerrar;
    # materializar ya lo hacia. Sin el, dos peticiones pueden cerrar el mismo
    # mes a la vez y escribir dos MonthlyClose, que son inmutables.
    mes = BudgetMonth.unscoped.select_for_update().get(pk=mes.pk)
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

    # El sobrante real del mes es lo que de verdad quedo, SIN el arrastre: el
    # saldo que venia de meses anteriores ya se repartio en su momento, y
    # volver a repartirlo daria mesada dos veces por el mismo dinero.
    sobrante_real = centavos(
        cierre_calculado.ingresos_reales - cierre_calculado.egresos_reales
    )
    aplicar_cascada_al_cierre(mes, sobrante_real)

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
    """El saldo del último mes cerrado ANTERIOR a este.

    `year__lte` con orden descendente tomaba el último cerrado del año, que
    puede ser posterior: `cerrar_mes` es público y nada obliga a cerrar en
    orden. Cerrar marzo con diciembre ya cerrado se traía el saldo de
    diciembre y lo congelaba en un MonthlyClose inmutable.
    """
    anterior = (
        MonthlyClose.objects.for_household(mes.household)
        .filter(
            Q(budget_month__year__lt=mes.year)
            | Q(budget_month__year=mes.year, budget_month__month__lt=mes.month)
        )
        .order_by("-budget_month__year", "-budget_month__month")
        .first()
    )
    return anterior.arrastre if anterior else Decimal("0.00")


def _esta_vencido(mes, hoy):
    fin = _ultimo_dia(mes.year, mes.month)
    return hoy > fin + timedelta(days=DIAS_PARA_EL_CIERRE_AUTOMATICO)


def _mes_siguiente(anio, mes):
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def cerrar_vencidos(hogar, hoy=None):
    """Cierra en cadena, EN ORDEN, porque cada cierre arrastra su saldo.

    No se limita a las filas ya materializadas: un hogar que faltó dos meses
    puede no haber visitado nunca febrero (ninguna fila `BudgetMonth` para
    él). Por eso, tras cerrar el mes abierto más antiguo, materializa el
    siguiente antes de volver a mirar — así febrero se crea, se comprueba y,
    si también está vencido, se cierra, todo antes de llegar a marzo.
    """
    hoy = hoy or timezone.localdate()
    cerrados = []
    while True:
        mes = (
            BudgetMonth.objects.for_household(hogar)
            .filter(status=BudgetMonth.OPEN)
            .order_by("year", "month")
            .first()
        )
        if mes is None or not _esta_vencido(mes, hoy):
            break
        cerrados.append(cerrar_mes(mes))
        siguiente_anio, siguiente_mes = _mes_siguiente(mes.year, mes.month)
        materializar(hogar, siguiente_anio, siguiente_mes)
    return cerrados


def obtener_mes(hogar, anio, mes, hoy=None):
    """El único punto de entrada al ciclo del mes (§2.3).

    Cierra los vencidos, materializa el corriente y proyecta todo lo demás.

    **Salvo si el hogar no puede escribir** (§5.2): entonces no hace ninguna de
    las tres cosas. Devuelve la fila que ya hubiera, o una proyección si no la
    hay, y no persiste nada. Ver el comentario del cuerpo.

    **Solo el mes corriente se materializa.** Un mes pasado sin fila es un mes
    que el hogar no vivió, y fabricarlo tenía consecuencias que no se pueden
    deshacer: la fila quedaba abierta en el pasado, la siguiente petición la
    cerraba en cadena mes a mes hasta hoy, y cada eslabón escribía un
    `MonthlyClose` que es inmutable por construcción. Historial inventado que
    solo se puede borrar. Los meses intermedios que sí hay que crear los crea
    `cerrar_vencidos`, que es quien conoce la cadena.
    """
    hoy = hoy or timezone.localdate()

    if not hogar.puede_escribir:
        # §5.2: expirar no destruye datos, pero tampoco crea ninguno. El ciclo
        # se dispara al ENTRAR, asi que sin esto un hogar expirado que solo
        # mira su presupuesto provocaria escrituras — y materializar un mes es
        # registrar algo nuevo, que es justo lo prohibido. Se le da lo que ya
        # existe, y el mes corriente se trata como uno futuro: proyectado, sin
        # persistir. Al pagar, cerrar_vencidos se pone al dia solo.
        #
        # Este return se salta a proposito la rama de abajo que re-materializa
        # una fila abierta y vacia: materializar escribe, y aqui no se escribe.
        existente = (
            BudgetMonth.objects.for_household(hogar)
            .filter(year=anio, month=mes).first()
        )
        return existente if existente is not None else proyectar(hogar, anio, mes)

    cerrar_vencidos(hogar, hoy)

    existente = BudgetMonth.objects.for_household(hogar).filter(year=anio, month=mes).first()
    if existente is not None:
        # Una fila abierta puede estar vacía: `aplicar_cascada_al_cierre` crea
        # la del mes siguiente solo para escribir en ella el ajuste de la
        # mesada (§4.5.3). Sin esto se quedaría con presupuesto cero para
        # siempre, porque materializar solo se llamaba cuando no había fila.
        if existente.status == BudgetMonth.OPEN and not existente.lineas.exists():
            return materializar(hogar, anio, mes)
        return existente

    if (anio, mes) != (hoy.year, hoy.month):
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


# ---------------------------------------------------------------------------
# La cascada aplicada a datos reales (§4.5) y el libro mayor de la mesada.
# ---------------------------------------------------------------------------


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


def mes_de_fecha(hogar, fecha):
    """La fila del mes que contiene esa fecha, o None. NO la crea.

    Resolver sin crear es deliberado: quien escribe un aporte con fecha de un
    mes que el hogar nunca vivió no debe fabricar ese mes por el camino. Un
    mes sin fila tampoco puede estar cerrado, así que devolver None deja pasar
    la escritura, que es lo correcto.
    """
    return (
        BudgetMonth.objects.for_household(hogar)
        .filter(year=fecha.year, month=fecha.month)
        .first()
    )


def _fila_del_mes_siguiente(mes):
    """La fila del mes que viene, creándola si el hogar no ha llegado allí.

    Distinta de `_mes_siguiente(anio, mes)`, que solo hace la aritmética del
    calendario: aquí hace falta una fila donde escribir el ajuste de la
    mesada, y el hogar puede no haber entrado nunca a ese mes.
    """
    anio, numero = _mes_siguiente(mes.year, mes.month)
    fila, _ = BudgetMonth.unscoped.get_or_create(
        household=mes.household, year=anio, month=numero,
        defaults={"status": BudgetMonth.OPEN, "opened_at": timezone.now()},
    )
    return fila


def mesada_de_por_id(hogar, membresia_id, mes):
    fila, _ = AllowanceLedger.unscoped.get_or_create(
        household=hogar, member_id=membresia_id, budget_month=mes
    )
    return fila


def mesada_de(membresia, mes):
    return mesada_de_por_id(mes.household, membresia.pk, mes)


def _carried_in(hogar, membresia_id, mes):
    anterior = _mes_anterior(mes)
    if anterior is None:
        return Decimal("0.00")
    libro = AllowanceLedger.objects.for_household(hogar).filter(
        member_id=membresia_id, budget_month=anterior
    ).first()
    return libro.carried_out if libro else Decimal("0.00")


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
    # Bloquea la fila del mes antes de mirar si ya hay reparto: sin esto, dos
    # envios del boton "Confirmar el plan" pasan los dos por el exists() antes
    # de que ninguno escriba, y el hogar acaba con las mesadas por duplicado.
    # El bloqueo es sobre BudgetMonth y no sobre MonthlyAllocation porque no se
    # puede bloquear una fila que aun no existe.
    BudgetMonth.unscoped.select_for_update().get(pk=mes.pk)

    ya = list(MonthlyAllocation.objects.for_household(hogar).filter(budget_month=mes))
    if ya:
        return ya

    reglas_orm = {
        r.order: r
        for r in AllocationRule.objects.for_household(hogar).filter(is_active=True)
    }
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
                # Ahorra el hogar entero, no una persona. Atribuirlo al pk mas
                # bajo era un dato falso en el historial de la meta, y con cero
                # membresias activas reventaba el cierre con IntegrityError.
                member=None,
                budget_month=mes,
                origen="cascade",
            )
            aporte.save()

    # El ajuste viaja al mes siguiente: la mesada de este mes ya se gastó.
    if ajustes:
        siguiente = _fila_del_mes_siguiente(mes)
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
