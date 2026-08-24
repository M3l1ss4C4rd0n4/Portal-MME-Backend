"""
Tarea Celery — sanador liviano de vistas materializadas de ontología (Fase 13/14).

El refresh completo (scripts/ontologia/refresh_ontologia.py) corre 1 vez al día
vía cron de sistema (4:30 AM) y hace trabajo costoso (re-resolver alias,
re-indexar embeddings, llamar a SharePoint). Pero un ETL externo puede tumbar
las vistas materializadas en cualquier momento del día — DROP TABLE ... CASCADE
es necesario ahí para que las tablas se adapten a columnas nuevas/eliminadas
del Excel origen (ver etl/etl_sharepoint_sync.py), así que no se puede evitar
el CASCADE sin romper esa lógica. Si eso ocurre después de las 4:30 AM, la
ontología queda rota (endpoints con error 500) hasta el cron del día siguiente
— hasta 24 h de exposición, confirmado en vivo el 2026-08-03.

Esta tarea solo hace la verificación/reparación barata (¿existen las 9 vistas?
si no, reaplica las migraciones) — nunca el pipeline completo — para poder
correr con mucha más frecuencia sin el costo de las otras tareas.
"""
from __future__ import annotations

import logging

from tasks import app as celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.ontologia_tasks.verificar_vistas_ontologia",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
)
def verificar_vistas_ontologia(self):
    """Verifica que las 9 vistas materializadas de ontología existan; recrea las que falten."""
    try:
        from scripts.ontologia.refresh_ontologia import _recrear_vistas_faltantes
        _recrear_vistas_faltantes()
        return {"status": "ok"}
    except Exception as exc:
        logger.error(f"[ONTOLOGIA_HEALER] Error verificando/recreando vistas: {exc}", exc_info=True)
        raise self.retry(exc=exc)
