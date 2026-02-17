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
    include=['tasks.etl_tasks', 'tasks.anomaly_tasks']
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
}

if __name__ == '__main__':
    app.start()
