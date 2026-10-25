"""Las cifras del Overview: Forecast, Real y Expenses. Sin HTTP.

Salen de las MISMAS funciones que This month: `totales` y
`real_contra_planeado` viven aqui y `views_month.mes` las importa, de modo que
las dos pantallas no pueden divergir. El reparto del sobrante es el de
`services.cash_float` y "Plan the month": `motor_cascade.repartir` sobre
`services._reglas_del_motor`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from . import services
from .engine import cascade as motor_cascade
from .models import AllowanceLedger, BudgetMonth, ExpenseRule, IncomeSource, MonthlyClose
from .models.catalog import EXPENSE, HOUSEHOLD, INCOME, Category
from .scopes import acotar, acotar_por_dueno

CERO = Decimal("0.00")


def totales(ingresos, egresos, ingresos_real, egresos_real,
            ingresos_pendiente=CERO, egresos_pendiente=CERO):
    """Las tres cifras de cabecera, planeado y real, las mismas en Overview y
    en This month: una sola funcion para que no diverjan. Lo real sale de los
    registros del mes; el sobrante real es lo que entro menos lo que salio.

    Lo pendiente llega ya calculado (la suma de lo que le falta a cada linea
    planificada, sin compensar). Esperado = lo real + lo pendiente: donde
    acabara el mes si se paga todo lo que falta. Desvio = esperado - planeado:
    positivo, mas que lo planeado."""
    return {
        "ingresos": ingresos, "egresos": egresos, "sobrante": ingresos - egresos,
        "ingresos_real": ingresos_real, "egresos_real": egresos_real,
        "sobrante_real": ingresos_real - egresos_real,
        "ingresos_pendiente": ingresos_pendiente, "egresos_pendiente": egresos_pendiente,
        "ingresos_esperado": ingresos_real + ingresos_pendiente,
        "egresos_esperado": egresos_real + egresos_pendiente,
        "ingresos_desvio": ingresos_real + ingresos_pendiente - ingresos,
        "egresos_desvio": egresos_real + egresos_pendiente - egresos,
    }


def real_contra_planeado(lineas, transacciones):
    """Por tipo: lo planeado, lo que de verdad paso, lo que aun falta y el
    porcentaje entero que la dona pinta. Lo real sale de las transacciones y no
    de los pagos de las lineas: un gasto sin partida tambien salio del bolsillo.
    Lo planeado es solo lo planificado: las partidas no planeadas (nacidas de un
    registro) no cuentan, porque nadie las planeo.

    Lo pendiente es la suma de lo que le falta a CADA linea planificada, sin
    compensar: pagar de mas una linea no reduce lo que otra aun debe."""
    donas = {}
    for kind in (INCOME, EXPENSE):
        planificadas = [l for l in lineas if l.kind == kind and not l.no_planeada]
        planeado = sum((l.planned_amount for l in planificadas), CERO)
        pendiente = sum((l.restante for l in planificadas), CERO)
        real = sum((t.amount for t in transacciones if t.category.kind == kind), CERO)
        porcentaje = int(real * 100 / planeado) if planeado else 0
        donas[kind] = {
            "planeado": planeado, "real": real, "pendiente": pendiente,
            "porcentaje": porcentaje,
        }
    return donas


def hay_presupuesto(hogar, mes, hoy: date) -> bool:
    """Si el hogar tiene algo con que mostrar un Overview: una fuente de
    ingreso o una regla de gasto vigentes, o un mes que ya trae lineas. Sin
    ninguna de las tres, la pantalla invita a montar el presupuesto.

    `mes` es la fila o la proyeccion que devolvio `obtener_mes`; de la
    proyeccion basta mirar si trae lineas. Es del hogar entero: en Personal
    tambien decide el presupuesto comun."""
    vigentes = Q(effective_to__isnull=True) | Q(effective_to__gte=hoy)
    if IncomeSource.objects.for_household(hogar).filter(vigentes).exists():
        return True
    if ExpenseRule.objects.for_household(hogar).filter(vigentes).exists():
        return True
    if isinstance(mes, services.ProyeccionDeMes):
        return bool(mes.lineas)
    return mes.lineas.exists()


def lineas_del_ambito(mes, ambito, membresia):
    """Las lineas del mes en ese ambito, con lo que la plantilla lee ya
    cargado: la categoria y la regla de origen (`linea.nombre`) y los pagos
    (`pagado_total`), o cada fila seria una consulta. Un QuerySet, no una
    lista: This month le encadena lo suyo."""
    return acotar_por_dueno(
        mes.lineas.select_related("category", "source_income", "source_expense_rule")
        .annotate(pagado_total=Sum("transacciones__amount"))
        .order_by("due_date", "pk"),
        ambito, membresia,
    )


def transacciones_del_ambito(mes, ambito, membresia):
    """Los registros del mes en ese ambito. Un QuerySet: This month le anade
    su anotacion y su orden."""
    return acotar(
        mes.transacciones.select_related("category", "budget_line"),
        ambito, membresia,
    )


def forecast_hogar(hogar, totales_dict):
    """Lo planeado del hogar y como lo reparte la cascada: lo mismo que
    "Plan the month", sobre el sobrante planeado. Sin sobrante no se reparte.

    `ahorro` es lo que cae en reglas sin miembro (metas, categorias); `mesada`,
    la suma de las partes de cada miembro; `sin_asignar`, lo que ninguna regla
    agota."""
    sobrante = totales_dict["sobrante"]
    asignaciones = []
    if sobrante > 0:
        asignaciones = motor_cascade.repartir(sobrante, services._reglas_del_motor(hogar))
    ahorro = sum((a.importe for a in asignaciones if a.miembro_id is None), CERO)
    mesada = sum((a.importe for a in asignaciones if a.miembro_id is not None), CERO)
    return {
        "ingresos": services.centavos(totales_dict["ingresos"]),
        "egresos": services.centavos(totales_dict["egresos"]),
        "sobrante": services.centavos(sobrante),
        "ahorro": services.centavos(ahorro),
        "mesada": services.centavos(mesada),
        "sin_asignar": services.centavos(max(sobrante, CERO) - ahorro - mesada),
    }


def forecast_personal(hogar, mes, membresia, totales_dict):
    """Lo planeado de este miembro. `totales_dict` es el del ambito personal.

    Su mesada es SU parte del reparto del sobrante del HOGAR: se calcula aqui
    con las lineas del ambito household, que son las mismas que reparte
    `forecast_hogar`. El libro de la mesada solo se lee: si aun no hay fila,
    arrastre y ajuste son 0 y NO se crea (un GET no escribe)."""
    lineas_hogar = lineas_del_ambito(mes, HOUSEHOLD, membresia)
    donas = real_contra_planeado(lineas_hogar, [])
    del_hogar = totales(
        donas[INCOME]["planeado"], donas[EXPENSE]["planeado"], CERO, CERO,
    )
    asignaciones = []
    if del_hogar["sobrante"] > 0:
        asignaciones = motor_cascade.repartir(
            del_hogar["sobrante"], services._reglas_del_motor(hogar),
        )
    mesada = sum((a.importe for a in asignaciones if a.miembro_id == membresia.pk), CERO)

    libro = (
        AllowanceLedger.objects.for_household(hogar)
        .filter(member=membresia, budget_month=mes).first()
    )
    arrastre = libro.carried_in if libro else CERO
    ajuste = libro.adjustment if libro else CERO
    disponible = mesada + arrastre + ajuste
    return {
        "ingresos": services.centavos(totales_dict["ingresos"]),
        "egresos": services.centavos(totales_dict["egresos"]),
        "mesada": services.centavos(mesada),
        "arrastre": services.centavos(arrastre),
        "ajuste": services.centavos(ajuste),
        "disponible": services.centavos(disponible),
        "queda": services.centavos(disponible - services.gasto_personal_del_mes(membresia, mes)),
    }


def expenses(transacciones):
    """Lo gastado, partido en lo que estaba en el presupuesto y lo puntual
    (sin partida, o contra una partida excepcional). Solo gastos."""
    budget = puntual = CERO
    for t in transacciones:
        if t.category.kind != EXPENSE:
            continue
        if t.budget_line_id is None or t.budget_line.is_exceptional:
            puntual += t.amount
        else:
            budget += t.amount
    return {"budget": services.centavos(budget), "one_off": services.centavos(puntual)}


@dataclass(frozen=True)
class Desvio:
    """Una categoria de gasto cuyo real se aparta de lo planeado."""

    categoria: Category
    planeado: Decimal
    real: Decimal

    @property
    def diferencia(self):
        return self.real - self.planeado

    @property
    def exceso(self):
        return self.diferencia > 0

    @property
    def magnitud(self):
        """Cuanto se aparta, sin signo: la plantilla pone el signo y el "over
        plan"/"under plan" por su cuenta."""
        return abs(self.diferencia)


def desvios(lineas, transacciones, cerrado: bool):
    """Las categorias de gasto que se desvian de lo planeado.

    Planificado: las lineas de gasto planificadas (reglas y partidas de Plan
    the month). Lo no planeado (registros sueltos o contra una partida no
    planeada) es siempre exceso de su categoria.

    Con el mes abierto, lo que una linea no ha pagado aun se debe, no se
    ahorro: solo cuentan los excesos, linea a linea y sin compensar, y lo no
    planeado. Con el mes cerrado ya no se debe nada: `real` es todo lo gastado
    en la categoria y tambien se ensena lo gastado de menos. Primero lo mas
    grande."""
    planeado_de, categorias = {}, {}
    exceso_de_lineas = {}
    for l in lineas:
        if l.kind != EXPENSE or l.no_planeada:
            continue
        categorias[l.category_id] = l.category
        planeado_de[l.category_id] = planeado_de.get(l.category_id, CERO) + l.planned_amount
        exceso_de_lineas[l.category_id] = (
            exceso_de_lineas.get(l.category_id, CERO) + max(l.pagado - l.planned_amount, CERO)
        )
    no_planeado_de, gastado_de = {}, {}
    for t in transacciones:
        if t.category.kind != EXPENSE:
            continue
        categorias.setdefault(t.category_id, t.category)
        gastado_de[t.category_id] = gastado_de.get(t.category_id, CERO) + t.amount
        if t.budget_line_id is None or t.budget_line.no_planeada:
            no_planeado_de[t.category_id] = no_planeado_de.get(t.category_id, CERO) + t.amount

    resultado = []
    for categoria_id, categoria in categorias.items():
        planeado = planeado_de.get(categoria_id, CERO)
        if cerrado:
            real = gastado_de.get(categoria_id, CERO)
        else:
            real = (planeado + exceso_de_lineas.get(categoria_id, CERO)
                    + no_planeado_de.get(categoria_id, CERO))
        desvio = Desvio(categoria, planeado, real)
        se_ensena = desvio.diferencia != 0 if cerrado else desvio.diferencia > 0
        if se_ensena:
            resultado.append(desvio)
    resultado.sort(key=lambda d: (-abs(d.diferencia), d.categoria.etiqueta().casefold()))
    return resultado


def _proximos_del_mes_siguiente(hogar, mes):
    """Lo que el mes siguiente tiene del hogar, como `(kind, fecha, importe)`,
    SIN escribir nada: un GET no crea el mes.

    Si el mes ya existe y tiene lineas, valen esas (solo las del hogar). Si no
    existe o esta vacio, se proyecta desde las reglas del hogar: `proyectar`
    lee todas las reglas, asi que aqui se descartan las personales."""
    anio, num = services.mes_siguiente(mes.year, mes.month)
    siguiente = BudgetMonth.objects.for_household(hogar).filter(year=anio, month=num).first()
    if siguiente is not None:
        existentes = list(siguiente.lineas.values_list(
            "kind", "due_date", "planned_amount", "scope", "no_planeada",
        ))
        if existentes:
            # Una partida no planeada que se pospuso ya esta pagada: no se debe.
            return [(kind, fecha, importe) for kind, fecha, importe, ambito, no_planeada in existentes
                    if ambito == HOUSEHOLD and not no_planeada]

    proyeccion = services.proyectar(hogar, anio, num)
    return [(l.kind, l.fecha, l.importe) for l in lineas_proyectadas_del_hogar(hogar, proyeccion)]


def lineas_proyectadas_del_hogar(hogar, proyeccion):
    """Las lineas de una proyeccion cuya regla es del hogar. `proyectar` lee
    todas las reglas, tambien las personales de cada miembro; en una cifra del
    hogar esas no cuentan. No toca `proyectar`: This month sigue como estaba."""
    del_hogar = {
        "income": set(IncomeSource.objects.for_household(hogar).filter(
            scope=HOUSEHOLD, pk__in={l.origen_id for l in proyeccion.lineas if l.origen == "income"},
        ).values_list("pk", flat=True)),
        "expense": set(ExpenseRule.objects.for_household(hogar).filter(
            scope=HOUSEHOLD, pk__in={l.origen_id for l in proyeccion.lineas if l.origen == "expense"},
        ).values_list("pk", flat=True)),
    }
    return [l for l in proyeccion.lineas if l.origen_id in del_hogar[l.origen]]


def totales_proyectados_del_hogar(hogar, proyeccion):
    """`totales` de una proyeccion, solo con lo del hogar y sin nada real."""
    lineas = lineas_proyectadas_del_hogar(hogar, proyeccion)
    ingresos = sum((l.importe for l in lineas if l.kind == INCOME), CERO)
    egresos = sum((l.importe for l in lineas if l.kind == EXPENSE), CERO)
    # Nada pagado todavia: todo lo planeado esta pendiente, y el esperado es
    # el plan (sin desvio que ensenar).
    return totales(ingresos, egresos, CERO, CERO, ingresos, egresos)


def alerta_cash_float(hogar, mes, lineas, real_del_mes: Decimal, hoy: date):
    """Si lo que hay en mano alcanza para pagar lo que falta.

    `lineas` son las del hogar (con `pagado_total`). En mano = saldo inicial
    del mes (lo que ya habia al empezar, 0 si no se anoto) + lo que el mes ha
    dejado hasta hoy. Pendiente = lo que le falta a TODA linea de gasto
    planificada del mes, venza cuando venza (sin corte por fecha: lo que no se
    ha pagado se debe, y las partidas no planeadas ya estan pagadas). Si el
    proximo ingreso cae el mes siguiente, ese mes aporta ademas sus gastos que
    vencen antes de que entre. `proximo` solo se ensena: si nada planea un
    ingreso, `sin_ingreso` lo dice."""
    lineas = list(lineas)
    por_cobrar = [
        l.due_date for l in lineas
        if l.kind == INCOME and l.due_date is not None and l.due_date >= hoy
        and l.pagado < l.planned_amount
    ]
    proximo = min(por_cobrar) if por_cobrar else None

    del_siguiente = []
    if proximo is None:
        del_siguiente = _proximos_del_mes_siguiente(hogar, mes)
        fechas = [fecha for kind, fecha, _ in del_siguiente if kind == INCOME and fecha is not None]
        proximo = min(fechas) if fechas else None

    pendiente = sum(
        (l.restante for l in lineas if l.kind == EXPENSE and not l.no_planeada),
        CERO,
    )
    if proximo is not None:
        pendiente += sum(
            (importe for kind, fecha, importe in del_siguiente
             if kind == EXPENSE and fecha is not None and fecha < proximo),
            CERO,
        )

    saldo = mes.opening_balance
    en_mano = (saldo or CERO) + real_del_mes
    margen = en_mano - pendiente
    return {
        "saldo_inicial": saldo,
        "real_del_mes": services.centavos(real_del_mes),
        "en_mano": services.centavos(en_mano),
        "proximo_ingreso": proximo,
        "pendiente": services.centavos(pendiente),
        "margen": services.centavos(margen),
        # Lo que falta, sin signo: la plantilla no sabe restar ni negar.
        "faltante": services.centavos(max(-margen, CERO)),
        "cubierto": margen >= 0,
        "sin_ingreso": proximo is None,
        "falta_saldo": saldo is None,
    }


def sugerencia_saldo_inicial(mes):
    """El saldo con el que el mes ANTERIOR cerro, para sugerirlo como saldo
    inicial. Solo el del mes inmediato: el anterior se cierra solo 5 dias
    despues de acabar, y en esos dias un cierre mas viejo contradiria el "last
    month closed at" de la tarjeta. Sin ese cierre no hay nada que sugerir."""
    anio, num = services.mes_previo(mes.year, mes.month)
    cierre = MonthlyClose.objects.for_household(mes.household).filter(
        budget_month__year=anio, budget_month__month=num,
    ).first()
    return services.centavos(cierre.arrastre) if cierre else None
