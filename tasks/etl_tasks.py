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
