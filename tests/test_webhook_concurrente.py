"""El webhook, entregado DOS VECES A LA VEZ.

Vive en su propio archivo y no en tests/test_webhook.py porque necesita
`transaction=True`: sin transacciones de verdad, los hilos no ven lo que hace el
otro y la prueba pasaria siempre, midiendo nada. Esa fixture es cara y no debe
contagiar al resto del archivo.

Es el criterio de aceptacion 3, la mitad que faltaba. El mecanismo —el unique de
StripeEvent.event_id mas el select_for_update sobre esa fila— existe desde la
Tarea 10, pero solo estaba probado en SECUENCIA: tres entregas una detras de
otra. Stripe reintenta en paralelo, y comprobar processed_at sin bloquear dejaria
pasar dos acreditaciones. Esto es lo que lo comprueba.
"""

import json
import threading

import pytest
from django.db import connections

from apps.subscriptions.models import StripeEvent, Subscription
from apps.subscriptions.services import procesar_evento
from apps.households.services import crear_hogar
from tests.factories import UserFactory


def _evento(hogar_pk, event_id="evt_paralelo"):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": {
            "client_reference_id": str(hogar_pk),
            "id": "cs_test_paralelo",
            "customer": "cus_paralelo",
        }},
    }


@pytest.mark.django_db(transaction=True)
def test_el_mismo_evento_dos_veces_a_la_vez_acredita_una_sola():
    """La fila del evento SE CREA ANTES, y eso es lo que hace util la prueba.

    Con la fila sin crear, los dos hilos chocan en el unique de `event_id` y es
    ESE indice el que los serializa: la prueba pasaba igual quitando el
    select_for_update, o sea que no medía nada. Comprobado quitandolo.

    Creandola de antemano y sin procesar se llega a la carrera de verdad: los dos
    hilos hacen get_or_create y los dos la ENCUENTRAN, los dos leen
    processed_at=None, y sin el bloqueo los dos acreditan.
    """
    hogar = crear_hogar(UserFactory(), "Los Simultaneos", family_size=2)
    evento = _evento(hogar.pk)
    StripeEvent.objects.create(
        event_id="evt_paralelo", type=evento["type"], payload=evento,
    )

    resultados = []
    fallos = []
    listos = threading.Barrier(2, timeout=30)

    def entregar():
        try:
            # Que los dos hilos lleguen JUNTOS al procesamiento: sin la barrera,
            # el primero suele terminar antes de que el segundo empiece y la
            # prueba volveria a medir el caso secuencial.
            listos.wait()
            resultados.append(procesar_evento(json.loads(json.dumps(evento))))
        except Exception as exc:                      # noqa: BLE001
            fallos.append(exc)
        finally:
            # Cada hilo abre su propia conexion; hay que cerrarla o el pooler se
            # queda con sesiones colgadas y la corrida siguiente falla al montar.
            connections.close_all()

    hilos = [threading.Thread(target=entregar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)

    assert not fallos, f"un hilo reventó: {fallos}"
    assert all(not h.is_alive() for h in hilos), "un hilo se quedó bloqueado"

    # Una sola fila de evento: el unique de event_id.
    assert StripeEvent.objects.filter(event_id="evt_paralelo").count() == 1
    # Y UNA sola acreditación: el select_for_update es lo que lo garantiza.
    assert resultados.count(True) == 1, (
        f"se acreditó {resultados.count(True)} veces, deberia ser exactamente 1"
    )

    hogar.refresh_from_db()
    assert hogar.subscription.status == Subscription.ACTIVE
    assert hogar.subscription.paid_at is not None
