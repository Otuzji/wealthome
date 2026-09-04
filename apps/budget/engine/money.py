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
