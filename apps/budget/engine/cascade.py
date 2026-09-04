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
