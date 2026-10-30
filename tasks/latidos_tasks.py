"""
Tarea de latidos: avisa cuando algo del sistema deja de producir.

Ver `domain/services/latidos_service` para el porqué y la lista de fallas que
motivaron este vigilante.

Dos reglas de envío, ambas de una queja real de los destinatarios (2026-10-29):

1. **Solo a quien desarrolla.** Un latido dice "celery-worker corre código
   viejo" o "la Senda CREG se agota en 29 días". Nadie más que quien mantiene
   el portal puede actuar sobre eso, y llegaba a los 5 destinatarios con el
   mismo asunto que una alerta real del SIN.

2. **Solo cuando la foto cambia.** La tarea corre a las 06:10, 14:10 y 22:10.
   Antes notificaba en las tres, aunque los seis latidos en rojo fueran
   exactamente los mismos de la corrida anterior y de la de ayer. Ahora se
   compara una huella del conjunto en rojo: si no cambió, se calla hasta que
   venza la ventana de recordatorio. Si aparece un latido nuevo, la huella
   cambia y avisa de inmediato, sin esperar.
"""

import hashlib
import logging

from tasks import app

logger = logging.getLogger(__name__)

# Recordatorio de una situación que no ha cambiado. Un día: lo suficiente para
# que no se olvide, poco para que no sature.
HORAS_RECORDATORIO = 24
CLAVE_HUELLA = 'latidos:huella'


@app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=600,
    name='tasks.latidos_tasks.revisar_latidos',
)
def revisar_latidos(self, notificar: bool = True):
    """
    Revisa todos los latidos y avisa si algo dejó de producir.

    Deja constancia en `ontologia.etl_lineage` SIEMPRE, incluso cuando todo
    está sano: así el propio vigilante tiene un latido que otros pueden mirar.
    Un vigilante que muere en silencio es el mismo problema que vino a
    resolver, y en este sistema ya pasó con todo lo demás.
    """
    from domain.services.latidos_service import revisar_todo, construir_mensaje

    resultados = revisar_todo()
    fallos = [r for r in resultados if not r.ok]
    criticos = [r for r in fallos if r.latido.critico]

    for r in fallos:
        nivel = logger.error if r.latido.critico else logger.warning
        nivel(f"[LATIDOS] {r.latido.que_vigila}: {r.detalle}")

    resumen = (
        f"{len(resultados) - len(fallos)}/{len(resultados)} sanos, "
        f"{len(fallos)} en rojo ({len(criticos)} crítico(s))"
    )
    logger.info(f"[LATIDOS] {resumen}")

    _registrar_lineage(
        'exito' if not criticos else 'error',
        len(fallos),
        f"{resumen} | fallos: {', '.join(r.latido.nombre for r in fallos) or 'ninguno'}",
    )

    mensaje = construir_mensaje(resultados)
    huella = _huella(fallos)
    enviado = False
    omitido = False

    if mensaje and notificar:
        if _misma_situacion(huella):
            omitido = True
            logger.info(
                "[LATIDOS] Mismos %d latidos en rojo que la corrida anterior: "
                "no se repite el aviso (recordatorio cada %dh)",
                len(fallos), HORAS_RECORDATORIO,
            )
        else:
            try:
                from domain.services.notification_service import broadcast_alert
                severidad = "CRITICO" if criticos else "WARNING"
                broadcast_alert(
                    mensaje, severity=severidad, is_daily=False, tecnica=True
                )
                enviado = True
            except Exception as e:
                logger.error(f"[LATIDOS] No se pudo notificar: {e}")

            # La huella se graba solo si el aviso salió. Si el envío falla, la
            # próxima corrida reintenta en vez de darlo por avisado.
            if enviado:
                _recordar_situacion(huella)

    return {
        'total': len(resultados),
        'fallos': len(fallos),
        'criticos': len(criticos),
        'notificado': enviado,
        'omitido_por_repetido': omitido,
        'detalle': [
            {'nombre': r.latido.nombre, 'ok': r.ok, 'detalle': r.detalle}
            for r in resultados
        ],
    }


def _huella(fallos) -> str:
    """Identifica el CONJUNTO de latidos en rojo, no su redacción.

    Se usa el nombre de cada latido y no su detalle: el detalle lleva cifras
    vivas ("quedan 29 días", "arrancó hace 6d") que cambian en cada corrida y
    harían que dos fotos idénticas se vieran distintas.
    """
    nombres = sorted(r.latido.nombre for r in fallos)
    criticos = sorted(r.latido.nombre for r in fallos if r.latido.critico)
    return hashlib.sha256(
        ('|'.join(nombres) + '#' + '|'.join(criticos)).encode('utf-8')
    ).hexdigest()[:32]


def _redis():
    import redis as _redis_mod

    return _redis_mod.Redis(host='localhost', port=6379, db=1, socket_timeout=2)


def _misma_situacion(huella: str) -> bool:
    """True si ya se avisó de esta misma foto dentro de la ventana."""
    try:
        previa = _redis().get(CLAVE_HUELLA)
    except Exception as e:
        # Sin Redis se avisa: perder un aviso es peor que repetirlo.
        logger.warning("[LATIDOS] No se pudo leer la huella previa: %s", e)
        return False
    return previa is not None and previa.decode('utf-8') == huella


def _recordar_situacion(huella: str) -> None:
    try:
        _redis().setex(CLAVE_HUELLA, HORAS_RECORDATORIO * 3600, huella)
    except Exception as e:
        logger.warning("[LATIDOS] No se pudo guardar la huella: %s", e)


def _registrar_lineage(estado: str, filas: int, detalle: str) -> None:
    try:
        from infrastructure.database.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ontologia.etl_lineage
                        (pipeline, paso, iniciado_en, finalizado_en,
                         filas_afectadas, estado, detalle)
                    VALUES ('latidos', 'revision', now(), now(), %s, %s, %s)
                    """,
                    (filas, estado, detalle[:1000]),
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"[LATIDOS] No se pudo registrar el propio latido: {e}")
