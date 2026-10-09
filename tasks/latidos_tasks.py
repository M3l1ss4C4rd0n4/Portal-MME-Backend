"""
Tarea de latidos: avisa cuando algo del sistema deja de producir.

Ver `domain/services/latidos_service` para el porqué y la lista de fallas que
motivaron este vigilante.
"""

import logging

from tasks import app

logger = logging.getLogger(__name__)


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
    enviado = False
    if mensaje and notificar:
        try:
            from domain.services.notification_service import broadcast_alert
            severidad = "CRITICO" if criticos else "WARNING"
            broadcast_alert(mensaje, severity=severidad, is_daily=False)
            enviado = True
        except Exception as e:
            logger.error(f"[LATIDOS] No se pudo notificar: {e}")

    return {
        'total': len(resultados),
        'fallos': len(fallos),
        'criticos': len(criticos),
        'notificado': enviado,
        'detalle': [
            {'nombre': r.latido.nombre, 'ok': r.ok, 'detalle': r.detalle}
            for r in resultados
        ],
    }


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
