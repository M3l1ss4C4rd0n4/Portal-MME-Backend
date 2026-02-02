"""Tareas Celery para ETL automatizado"""
from celery import shared_task, Task
from datetime import datetime, timedelta
import logging
import os
import glob
from requests.exceptions import RequestException, Timeout, ConnectionError as RequestsConnectionError

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
        from infrastructure.external.xm_service import fetch_metric_from_api
        from infrastructure.database.connection import get_connection
        
        logger.info(f"Iniciando descarga de {metric_code} desde {start_date} hasta {end_date}")
        
        # Descargar datos
        data = fetch_metric_from_api(metric_code, start_date, end_date)
        
        if not data:
            logger.warning(f"No se obtuvieron datos para {metric_code}")
            return {"status": "no_data", "metric": metric_code}
        
        # Guardar en PostgreSQL
        with get_connection() as conn:
            cur = conn.cursor()
            inserted = 0
            
            for record in data:
                try:
                    cur.execute("""
                        INSERT INTO metrics (metrica, fecha, valor, unidad)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (metrica, fecha) DO UPDATE
                        SET valor = EXCLUDED.valor, unidad = EXCLUDED.unidad
                    """, (
                        record.get('metrica', metric_code),
                        record.get('fecha'),
                        record.get('valor'),
                        record.get('unidad', 'kWh')
                    ))
                    inserted += 1
                except Exception as e:
                    logger.error(f"Error insertando registro: {e}")
                    continue
            
            conn.commit()
        
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
            result = fetch_metric_data.delay(metric, start_str, end_str)
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
