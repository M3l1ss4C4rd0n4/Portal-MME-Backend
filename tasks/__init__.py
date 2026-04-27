"""
Celery Application Configuration
"""
from celery import Celery
from celery.schedules import crontab
import os
import sys

# Asegurar que el directorio raíz del proyecto esté en sys.path
# para que los workers puedan importar scripts, infrastructure, etc.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Cargar variables de entorno desde .env para que SMTP_*, TELEGRAM_BOT_TOKEN, etc.
# estén disponibles en los workers y el beat scheduler.
# override=True porque systemd EnvironmentFile puede fallar con caracteres especiales
# como @, *, espacios, dejando variables vacías que load_dotenv no sobreescribiría.
try:
    from dotenv import load_dotenv
    _env_file = os.path.join(_PROJECT_ROOT, '.env')
    if os.path.isfile(_env_file):
        load_dotenv(_env_file, override=True)
except ImportError:
    pass  # python-dotenv no instalado; se depende de EnvironmentFile en systemd

# Configuración de Celery
app = Celery(
    'portal_mme',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1',
    include=['tasks.etl_tasks', 'tasks.anomaly_tasks', 'tasks.push_tasks']
)

# Configuración adicional
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Bogota',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hora máximo por tarea
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    broker_connection_retry_on_startup=True,  # Celery 6.x deprecation fix
)

# Tareas programadas
app.conf.beat_schedule = {
    'etl-incremental-cada-6-horas': {
        'task': 'tasks.etl_tasks.etl_incremental_all_metrics',
        'schedule': crontab(hour='*/6', minute=0),  # Cada 6 horas
    },
    'limpieza-logs-diaria': {
        'task': 'tasks.etl_tasks.clean_old_logs',
        'schedule': crontab(hour=3, minute=0),  # 3:00 AM diario
    },
    # Detección de anomalías cada 30 minutos
    'check-anomalies-every-30-minutes': {
        'task': 'tasks.anomaly_tasks.check_anomalies',
        'schedule': crontab(minute='*/30'),  # Cada 30 minutos
    },
    # Resumen diario a las 8:00 AM (hora Colombia)
    'send-daily-summary-8am': {
        'task': 'tasks.anomaly_tasks.send_daily_summary',
        'schedule': crontab(hour=8, minute=0),  # Diario a las 8 AM
    },
    # Informe EnergIA app: push FCM a las 8:05 AM (5 min después del resumen)
    'energia-app-informe-8am': {
        'task': 'tasks.push_tasks.enviar_informe_diario_push',
        'schedule': crontab(hour=8, minute=5),  # Diario a las 8:05 AM
    },
    # Cálculo del Costo Unitario (CU) diario a las 10:00 AM
    # (espera a que RestAliv y PerdidasEner estén disponibles — lag ~2 días)
    'calcular-cu-diario': {
        'task': 'tasks.etl_tasks.calcular_cu_diario',
        'schedule': crontab(hour=10, minute=0),  # Diario a las 10 AM
    },
    # Re-entrenamiento cada 3 días (lunes/jueves/domingo) a las 02:00 AM
    # Corre DESPUÉS del ETL incremental (*/6h) para garantizar datos frescos en BD.
    # Ejecuta: train_predictions_sector + train_predictions_postgres + largo_plazo Prophet + monitor_quality
    # Cambiado de semanal (domingo) a cada 3 días para aprovechar el histórico 2000-2019 extendido.
    'regenerar-predicciones-cada-3-dias': {
        'task': 'tasks.etl_tasks.regenerar_predicciones',
        'schedule': crontab(hour=2, minute=0, day_of_week='0,3,6'),  # Dom/Mié/Sáb 02:00 AM
    },
    # Sincronización automática Excel SharePoint → data/ → PostgreSQL
    # Descarga archivos, detecta cambios por hash y actualiza la BD.
    # Horario: 7:00 AM diario (laboral, antes del inicio de la jornada).
    'sync-sharepoint-xlsx-diario': {
        'task': 'tasks.etl_tasks.sync_sharepoint_xlsx',
        'schedule': crontab(hour=7, minute=0),  # Diario 7:00 AM
    },
    # Actualización de noticias del portal 3 veces al día
    # Mañana (7:00), mediodía (12:00) y noche (19:00)
    'refresh-news-3x-dia': {
        'task': 'tasks.etl_tasks.refresh_news_cache',
        'schedule': crontab(hour='7,12,19', minute=0),
    },
}

if __name__ == '__main__':
    app.start()
