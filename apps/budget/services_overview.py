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


def totales(ingresos, egresos, ingresos_real, egresos_real):
    """Las tres cifras de cabecera, planeado y real, las mismas en Overview y
    en This month: una sola funcion para que no diverjan. Lo real sale de los
    registros del mes; el sobrante real es lo que entro menos lo que salio."""
    return {
        "ingresos": ingresos, "egresos": egresos, "sobrante": ingresos - egresos,
        "ingresos_real": ingresos_real, "egresos_real": egresos_real,
        "sobrante_real": ingresos_real - egresos_real,
    }


def real_contra_planeado(lineas, transacciones):
    """Por tipo: lo planeado, lo que de verdad paso y el porcentaje entero
    que la dona pinta. Lo real sale de las transacciones y no de los pagos de
    las lineas: un gasto sin partida tambien salio del bolsillo."""
    donas = {}
    for kind in (INCOME, EXPENSE):
        planeado = sum((l.planned_amount for l in lineas if l.kind == kind), CERO)
        real = sum((t.amount for t in transacciones if t.category.kind == kind), CERO)
        porcentaje = int(real * 100 / planeado) if planeado else 0
        donas[kind] = {"planeado": planeado, "real": real, "porcentaje": porcentaje}
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


def desvios(lineas, transacciones, hoy: date):
    """Las categorias de gasto que se desvian de lo planeado. Solo lineas no
    excepcionales: lo puntual no estaba en el presupuesto.

    Un exceso se muestra siempre, aunque la categoria siga abierta; un ahorro
    solo cuando esta terminada (todas sus lineas pagadas o vencidas), porque a
    mitad de mes "gastar menos" aun no es un ahorro. Primero lo mas grande."""
    por_categoria = {}
    categoria_de_linea = {}
    for l in lineas:
        if l.kind == EXPENSE and not l.is_exceptional:
            por_categoria.setdefault(l.category_id, []).append(l)
            categoria_de_linea[l.pk] = l.category_id
    real_de = {}
    for t in transacciones:
        categoria_id = categoria_de_linea.get(t.budget_line_id)
        if categoria_id is not None and t.category.kind == EXPENSE:
            real_de[categoria_id] = real_de.get(categoria_id, CERO) + t.amount

    resultado = []
    for categoria_id, de_la_categoria in por_categoria.items():
        planeado = sum((l.planned_amount for l in de_la_categoria), CERO)
        real = real_de.get(categoria_id, CERO)
        desvio = Desvio(de_la_categoria[0].category, planeado, real)
        terminada = all(
            l.pagado >= l.planned_amount or (l.due_date is not None and l.due_date < hoy)
            for l in de_la_categoria
        )
        if desvio.diferencia > 0 or (desvio.diferencia < 0 and terminada):
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
        existentes = list(siguiente.lineas.values_list("kind", "due_date", "planned_amount", "scope"))
        if existentes:
            return [(kind, fecha, importe) for kind, fecha, importe, ambito in existentes
                    if ambito == HOUSEHOLD]

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
    return totales(
        sum((l.importe for l in lineas if l.kind == INCOME), CERO),
        sum((l.importe for l in lineas if l.kind == EXPENSE), CERO),
        CERO, CERO,
    )


def alerta_cash_float(hogar, mes, lineas, real_del_mes: Decimal, hoy: date):
    """Si lo que hay en mano alcanza hasta el proximo ingreso.

    `lineas` son las del hogar (con `pagado_total`). En mano = saldo inicial
    del mes (lo que ya habia al empezar, 0 si no se anoto) + lo que el mes ha
    dejado hasta hoy. Pendiente = lo que aun hay que pagar ANTES del proximo
    ingreso: el del mismo dia lo cubre el propio ingreso. Si el mes ya no tiene
    ingresos por cobrar se mira el mes siguiente; si nada planea un ingreso,
    todo lo pendiente cuenta y `sin_ingreso` lo dice."""
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
        (l.restante for l in lineas
         if l.kind == EXPENSE
         and (proximo is None or l.due_date is None or l.due_date < proximo)),
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
