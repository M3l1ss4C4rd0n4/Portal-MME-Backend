"""Tareas Celery para ETL automatizado"""
from celery import shared_task, Task
from datetime import datetime, date, timedelta
import logging
import os
import glob
from requests.exceptions import RequestException, Timeout, ConnectionError as RequestsConnectionError

from tasks import app

logger = logging.getLogger(__name__)


class SafeETLTask(Task):
    """
    Clase base para tareas ETL con manejo robusto de errores.
    
    Características:
    - Reintentos automáticos para errores de red/API
    - Backoff exponencial con jitter
    - Logging detallado de fallos
    - Límite de reintentos configurable
    """
    autoretry_for = (RequestException, Timeout, RequestsConnectionError, ConnectionError)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600  # Máximo 10 minutos entre reintentos
    retry_jitter = True
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Callback ejecutado cuando una tarea falla definitivamente.
        Registra información detallada para debugging.
        """
        logger.error(
            f"❌ Task {self.name} [{task_id}] FAILED",
            extra={
                'task_id': task_id,
                'task_name': self.name,
                'task_args': args,
                'task_kwargs': kwargs,
                'exception': str(exc),
                'traceback': str(einfo)
            },
            exc_info=True
        )
        
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """
        Callback ejecutado en cada reintento.
        """
        logger.warning(
            f"⚠️ Task {self.name} [{task_id}] retrying ({self.request.retries}/{self.max_retries})",
            extra={
                'task_id': task_id,
                'retry_count': self.request.retries,
                'max_retries': self.max_retries,
                'exception': str(exc)
            }
        )


@shared_task(bind=True, base=SafeETLTask, max_retries=3)
def fetch_metric_data(self, metric_code: str, start_date: str, end_date: str):
    """
    Descarga datos de una métrica específica desde la API de XM.
    
    Args:
        metric_code: Código de la métrica (ej: 'PrecBolsNaci', 'Gene')
        start_date: Fecha inicio formato 'YYYY-MM-DD'
        end_date: Fecha fin formato 'YYYY-MM-DD'
    """
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from infrastructure.external.xm_service import fetch_metric_data as xm_fetch
        from infrastructure.database.connection import PostgreSQLConnectionManager
        
        logger.info(f"Iniciando descarga de {metric_code} desde {start_date} hasta {end_date}")
        
        # Determinar entidad según la métrica
        entity_map = {
            'Gene': 'Recurso',
            'PrecBolsNaci': 'Sistema',
            'DEM': 'Sistema',
            'DemaReal': 'Sistema',
            'TRAN': 'Sistema',
            'PerdidasEner': 'Sistema',
            'AporEner': 'Recurso',
            'CapaUtilDiarEner': 'Recurso',
            'PorcVoluUtilDiar': 'Recurso',
        }
        entity = entity_map.get(metric_code, 'Sistema')
        
        # Descargar datos usando la función correcta del xm_service
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').date() if isinstance(start_date, str) else start_date
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').date() if isinstance(end_date, str) else end_date
        
        df = xm_fetch(metric_code, entity, start_dt, end_dt)
        
        if df is None or df.empty:
            logger.warning(f"No se obtuvieron datos para {metric_code}")
            return {"status": "no_data", "metric": metric_code}
        
        # Guardar en PostgreSQL
        from core.config import settings
        import psycopg2
        conn_params = {
            'host': settings.POSTGRES_HOST, 'port': settings.POSTGRES_PORT,
            'database': settings.POSTGRES_DB, 'user': settings.POSTGRES_USER
        }
        if settings.POSTGRES_PASSWORD:
            conn_params['password'] = settings.POSTGRES_PASSWORD
        conn = psycopg2.connect(**conn_params)
        
        cur = conn.cursor()
        inserted = 0
        
        for _, row in df.iterrows():
            try:
                cur.execute("""
                    INSERT INTO metrics (metrica, fecha, entidad, recurso, valor_gwh, unidad)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (metrica, fecha, entidad, COALESCE(recurso, '')) DO UPDATE
                    SET valor_gwh = EXCLUDED.valor_gwh, unidad = EXCLUDED.unidad
                """, (
                    metric_code,
                    row.get('Date', row.get('fecha')),
                    entity,
                    row.get('Values_code', row.get('recurso', None)),
                    row.get('Values', row.get('valor_gwh', row.get('valor'))),
                    'kWh' if 'Prec' in metric_code else 'GWh'
                ))
                inserted += 1
            except Exception as e:
                logger.error(f"Error insertando registro: {e}")
                continue
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"✅ {metric_code}: {inserted} registros procesados")
        return {
            "status": "success",
            "metric": metric_code,
            "records": inserted,
            "period": f"{start_date} to {end_date}"
        }
        
    except Exception as exc:
        logger.error(f"Error en fetch_metric_data: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Reintentar en 5 minutos


@shared_task
def etl_incremental_all_metrics():
    """
    Ejecuta ETL incremental para todas las métricas principales.
    Se ejecuta cada 6 horas vía Celery Beat.
    """
    logger.info("🚀 Iniciando ETL incremental automático")
    
    # Métricas a actualizar
    metrics = [
        'PrecBolsNaci',  # Precio bolsa nacional
        'Gene',          # Generación
        'DEM',           # Demanda
        'TRAN',          # Transmisión
        'PerdidasEner'   # Pérdidas
    ]
    
    # Rango: últimos 7 días
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    results = []
    for metric in metrics:
        try:
            result = fetch_metric_data.delay(metric, start_str, end_str)  # type: ignore[union-attr]
            results.append({
                "metric": metric,
                "task_id": result.id,
                "status": "queued"
            })
            logger.info(f"✓ Tarea encolada: {metric} (task_id: {result.id})")
        except Exception as e:
            logger.error(f"✗ Error encolando {metric}: {e}")
            results.append({
                "metric": metric,
                "status": "error",
                "error": str(e)
            })
    
    return {
        "status": "completed",
        "timestamp": datetime.now().isoformat(),
        "metrics_queued": len([r for r in results if r["status"] == "queued"]),
        "results": results
    }


@shared_task
def clean_old_logs(days: int = 30):
    """
    Limpia archivos de log antiguos.
    
    Args:
        days: Número de días de antigüedad para borrar logs
    """
    logger.info(f"🧹 Limpiando logs mayores a {days} días")
    
    log_dir = '/home/admonctrlxm/server/logs'
    cutoff_time = datetime.now() - timedelta(days=days)
    deleted = 0
    
    # Patrones de archivos a limpiar
    patterns = [
        os.path.join(log_dir, '*.log'),
        os.path.join(log_dir, 'etl', '*.log'),
    ]
    
    for pattern in patterns:
        for log_file in glob.glob(pattern):
            try:
                if os.path.getmtime(log_file) < cutoff_time.timestamp():
                    os.remove(log_file)
                    deleted += 1
                    logger.info(f"Borrado: {log_file}")
            except Exception as e:
                logger.error(f"Error borrando {log_file}: {e}")
    
    logger.info(f"✅ Limpieza completada: {deleted} archivos eliminados")
    return {
        "status": "success",
        "deleted_files": deleted,
        "cutoff_days": days
    }


@shared_task
def test_task():
    """Tarea de prueba simple"""
    logger.info("🧪 Test task ejecutada")
    return {
        "status": "success",
        "message": "Test task completed",
        "timestamp": datetime.now().isoformat()
    }


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def calcular_cu_diario(self):
    """
    Calcula el Costo Unitario (CU) diario.
    
    Ejecuta a las 10:00 AM para capturar datos con lag de 2 días.
    Calcula CU para los últimos 7 días (cubre posible lag de RestAliv/PerdidasEner).
    
    Retries: 3 veces con 5 min de delay (por si hay datos no disponibles aún)
    """
    from domain.services.cu_service import CUService

    logger.info("💰 Iniciando cálculo del CU diario")

    try:
        cu_service = CUService()
        hoy = date.today()
        insertados = 0
        errores = 0

        # Calcular últimos 7 días para cubrir el lag
        for i in range(7):
            fecha = hoy - timedelta(days=i)
            try:
                saved = cu_service.save_cu_for_date(fecha)
                if saved:
                    insertados += 1
                    logger.info(f"💰 CU {fecha}: guardado OK")
            except Exception as e:
                errores += 1
                logger.error(f"💰 CU {fecha}: error → {e}")

        result = {
            "status": "success",
            "insertados": insertados,
            "errores": errores,
            "dias_procesados": 7,
            "timestamp": datetime.now().isoformat()
        }
        logger.info(f"💰 CU diario completado: {result}")
        return result

    except Exception as exc:
        logger.error(f"💰 Error en calcular_cu_diario: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=2, default_retry_delay=600, name='tasks.etl_tasks.regenerar_predicciones')
def regenerar_predicciones(self):
    """
    Re-genera predicciones de corto (90d) y largo plazo (365d) con datos frescos.

    Ejecuta los dos scripts ETL de entrenamiento en subproceso y luego regenera
    las predicciones de largo plazo vía PredictionsService.save_long_term_predictions().

    Programado domingos 02:00 AM — el ETL incremental corre */6h y garantiza
    que la BD de métricas está actualizada.
    """
    import subprocess
    inicio = datetime.now()
    logger.info("🔮 [regenerar_predicciones] Iniciando regeneración semanal")

    resumen = {
        'script_sector': None,
        'script_postgres': None,
        'largo_plazo': None,
        'monitor_quality': None,
        'duracion_seg': 0,
    }

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(base_dir, 'venv', 'bin', 'python')
    if not os.path.exists(python_bin):
        python_bin = 'python3'

    # 1. Re-entrena predicciones sectoriales (DEMANDA, PRECIOS, EMBALSES, etc.)
    script_sector = os.path.join(base_dir, 'scripts', 'train_predictions_sector_energetico.py')
    try:
        proc = subprocess.run(
            [python_bin, script_sector],
            capture_output=True, text=True, timeout=1800, cwd=base_dir
        )
        resumen['script_sector'] = 'ok' if proc.returncode == 0 else f'error rc={proc.returncode}'
        if proc.returncode != 0:
            logger.error(f"[regenerar_predicciones] sector stderr: {proc.stderr[-1000:]}")
        else:
            logger.info("[regenerar_predicciones] sector: OK")
    except subprocess.TimeoutExpired:
        resumen['script_sector'] = 'timeout'
        logger.error("[regenerar_predicciones] script_sector excedió 30 min")
    except Exception as e:
        resumen['script_sector'] = f'exception: {e}'
        logger.error(f"[regenerar_predicciones] script_sector: {e}")

    # 2. Re-entrena predicciones de generación por tecnología (Hidráulica, Solar, etc.)
    script_postgres = os.path.join(base_dir, 'scripts', 'train_predictions_postgres.py')
    try:
        proc = subprocess.run(
            [python_bin, script_postgres],
            capture_output=True, text=True, timeout=1800, cwd=base_dir
        )
        resumen['script_postgres'] = 'ok' if proc.returncode == 0 else f'error rc={proc.returncode}'
        if proc.returncode != 0:
            logger.error(f"[regenerar_predicciones] postgres stderr: {proc.stderr[-1000:]}")
        else:
            logger.info("[regenerar_predicciones] postgres: OK")
    except subprocess.TimeoutExpired:
        resumen['script_postgres'] = 'timeout'
        logger.error("[regenerar_predicciones] script_postgres excedió 30 min")
    except Exception as e:
        resumen['script_postgres'] = f'exception: {e}'
        logger.error(f"[regenerar_predicciones] script_postgres: {e}")

    # 3. Re-genera predicciones de largo plazo (Prophet 365d) con PredictionsService
    try:
        from domain.services.predictions_service_extended import PredictionsService
        svc = PredictionsService()
        largo_resumen = svc.save_long_term_predictions()
        ok_count = sum(1 for v in largo_resumen.values() if v > 0)
        resumen['largo_plazo'] = f'ok {ok_count}/{len(largo_resumen)} fuentes'
        logger.info(f"[regenerar_predicciones] largo_plazo: {resumen['largo_plazo']}")
    except Exception as e:
        resumen['largo_plazo'] = f'exception: {e}'
        logger.error(f"[regenerar_predicciones] largo_plazo: {e}")

    # 4. Actualiza métricas de calidad ex-post
    script_quality = os.path.join(base_dir, 'scripts', 'monitor_predictions_quality.py')
    try:
        proc = subprocess.run(
            [python_bin, script_quality],
            capture_output=True, text=True, timeout=300, cwd=base_dir
        )
        resumen['monitor_quality'] = 'ok' if proc.returncode == 0 else f'error rc={proc.returncode}'
        logger.info(f"[regenerar_predicciones] monitor_quality: {resumen['monitor_quality']}")
    except Exception as e:
        resumen['monitor_quality'] = f'exception: {e}'
        logger.error(f"[regenerar_predicciones] monitor_quality: {e}")

    resumen['duracion_seg'] = round((datetime.now() - inicio).total_seconds())
    logger.info(f"🔮 [regenerar_predicciones] Completado en {resumen['duracion_seg']}s: {resumen}")
    return resumen


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def sync_sharepoint_xlsx(self, nombres: list = None, forzar: bool = False):
    """
    Descarga los archivos Excel desde SharePoint del Ministerio,
    detecta cambios por hash SHA-256 y actualiza la base de datos PostgreSQL
    con la información de los archivos que hayan cambiado.

    Archivos configurados (ver etl/etl_sharepoint_sync.py):
      - Matriz_Subsidios_DEE     → tablas subsidios_pagos / empresas / mapa
      - Matriz_Ejecucion_2026    → schema presupuesto
      - Matriz_Subsidios_KPIs    → schema subsidios_kpis
      - Seguimiento_Contratos_CE → schema contratos_or

    Args:
        nombres: Lista de nombres específicos a sincronizar (None = todos los activos).
        forzar:  Si True, ejecuta el ETL aunque el archivo no haya cambiado en disco.
    """
    logger.info("📥 [sync_sharepoint_xlsx] Iniciando sincronización SharePoint → BD")
    try:
        import sys
        import os
        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _base not in sys.path:
            sys.path.insert(0, _base)

        from etl.etl_sharepoint_sync import run_sync

        resultados = run_sync(nombres=nombres, forzar=forzar)

        exitosos = sum(1 for r in resultados if r["error"] is None)
        etl_ejecutados = sum(1 for r in resultados if r["etl_ejecutado"])
        fallidos = [r for r in resultados if r["error"]]

        resumen = {
            "status": "success" if not fallidos else "partial",
            "timestamp": datetime.now().isoformat(),
            "archivos_procesados": len(resultados),
            "exitosos": exitosos,
            "etl_ejecutados": etl_ejecutados,
            "fallidos": [{"nombre": r["nombre"], "error": r["error"]} for r in fallidos],
        }
        logger.info("📥 [sync_sharepoint_xlsx] Completado: %s", resumen)
        return resumen

    except Exception as exc:
        logger.error("❌ [sync_sharepoint_xlsx] Error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


# ── Actualización programada de noticias ──────────────────────────────────
# Se ejecuta 3 veces al día (7 AM, 12 PM, 7 PM) para garantizar que el
# slider de noticias del portal siempre muestre titulares frescos.
# ──────────────────────────────────────────────────────────────────────────

@app.task(
    name='tasks.etl_tasks.refresh_news_cache',
    bind=True,
    base=SafeETLTask,
)
def refresh_news_cache(self):
    """
    Invalida el caché de noticias en Redis para forzar una recarga fresca
    en la próxima visita al portal. Se ejecuta 3 veces al día vía Celery Beat.
    """
    try:
        from infrastructure.cache.redis_client import get_redis_client
        client = get_redis_client()
        deleted = client.delete("news:enriched_news")
        logger.info(
            "[REFRESH_NEWS] Cache de noticias invalidado (%s). "
            "Próxima visita recargará noticias frescas.",
            "clave eliminada" if deleted else "clave no existía",
        )
        return {"status": "success", "cache_invalidated": bool(deleted)}
    except Exception as exc:
        logger.error("[REFRESH_NEWS] Error invalidando cache: %s", exc)
        raise self.retry(exc=exc)
