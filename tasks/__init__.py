"""
Celery Application Configuration
"""
from celery import Celery
from celery.schedules import crontab
import os

# Configuración de Celery
app = Celery(
    'portal_mme',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1',
    include=['tasks.etl_tasks']
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
}

if __name__ == '__main__':
    app.start()
