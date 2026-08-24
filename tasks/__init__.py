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
    include=['tasks.etl_tasks', 'tasks.anomaly_tasks', 'tasks.push_tasks', 'tasks.homeslider_diagnosticos_tasks', 'tasks.ontologia_tasks']
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
    # Resumen diario a las 8:30 AM (hora Colombia)
    # XM publica cambios entre 7:00–8:00 AM; 30 min de margen para datos frescos.
    'send-daily-summary-830am': {
        'task': 'tasks.anomaly_tasks.send_daily_generate',
        'schedule': crontab(hour=8, minute=30),
    },
    # Informe EnergIA app: push FCM 5 min después del resumen
    'energia-app-informe-830am': {
        'task': 'tasks.push_tasks.enviar_informe_diario_push',
        'schedule': crontab(hour=8, minute=35),
    },
    # Cálculo del Costo Unitario (CU) diario a las 10:00 AM
    # (espera a que RestAliv y PerdidasEner estén disponibles — lag ~2 días)
    'calcular-cu-diario': {
        'task': 'tasks.etl_tasks.calcular_cu_diario',
        'schedule': crontab(hour=10, minute=0),  # Diario a las 10 AM
    },
    # Actualización ONI (NOAA CPC) — semanal, antes del reentrenamiento de modelos
    # NOAA actualiza ONI mensualmente; bajarlo semanalmente garantiza datos frescos.
    # Corre a las 01:30 AM del lunes, 30 min antes del reentrenamiento.
    'actualizar-oni-semanal': {
        'task': 'tasks.etl_tasks.actualizar_oni',
        'schedule': crontab(hour=1, minute=30, day_of_week='1'),  # Lunes 01:30 AM
    },
    # Actualización PDO + SOI (NOAA) — semanal junto con ONI
    # PDO actualiza ~mensual; SOI actualiza ~mensual. Corre 45 min antes del reentrenamiento.
    'actualizar-pdo-soi-semanal': {
        'task': 'tasks.etl_tasks.actualizar_pdo_soi',
        'schedule': crontab(hour=1, minute=15, day_of_week='1'),  # Lunes 01:15 AM
    },
    # Re-entrenamiento cada 3 días (lunes/jueves/domingo) a las 02:00 AM
    # Corre DESPUÉS del ETL incremental (*/6h) para garantizar datos frescos en BD.
    # Ejecuta: train_predictions_sector + train_predictions_postgres + largo_plazo Prophet + monitor_quality
    # Cambiado de semanal (domingo) a cada 3 días para aprovechar el histórico 2000-2019 extendido.
    'regenerar-predicciones-cada-3-dias': {
        'task': 'tasks.etl_tasks.regenerar_predicciones',
        'schedule': crontab(hour=2, minute=0, day_of_week='0,3,6'),  # Dom/Mié/Sáb 02:00 AM
    },
    # Sincronización SharePoint: cron 4:00 AM + watcher cada 5 min (no Celery).
    # (ver etl/etl_sharepoint_watcher.py y crontab del servidor).
    # La tarea Celery duplicada sync-sharepoint-xlsx-diario fue retirada para evitar
    # descargas redundantes a las 7:00 AM.
    # Actualización de noticias del portal 3 veces al día
    # Mañana (7:00), mediodía (12:00) y noche (19:00)
    'refresh-news-3x-dia': {
        'task': 'tasks.etl_tasks.refresh_news_cache',
        'schedule': crontab(hour='7,12,19', minute=0),
    },
    # Senda de Referencia CREG — verificar/refrescar valores oficiales semanalmente
    # XM publica la senda al inicio de cada estación (mayo y diciembre).
    # Esta tarea re-aplica los valores semilla y alerta si XM no ha publicado.
    'refresh-senda-referencia-semanal': {
        'task': 'tasks.etl_tasks.refresh_senda_referencia',
        'schedule': crontab(hour=2, minute=15, day_of_week='1'),  # Lunes 02:15 AM
    },
    # Precios de Escasez (PEI/PE/PES) — refrescar mensualmente día 1
    # CREG publica los nuevos precios al inicio de cada mes.
    # Esta tarea infiere PEI/PE/PES desde PrecEsca XM si no hay carga manual.
    'refresh-precios-escasez-mensual': {
        'task': 'tasks.etl_tasks.refresh_precios_escasez',
        'schedule': crontab(hour=3, minute=0, day_of_month='1'),  # Día 1 de cada mes 03:00 AM
    },
    # Diagnósticos de HomeSlider generados por IA (Fase 11) — 8:45 AM, 10 min
    # después del informe ejecutivo (8:35 AM) para asegurar datos frescos del día.
    'generar-diagnosticos-homeslider-diario': {
        'task': 'tasks.homeslider_diagnosticos_tasks.generar_diagnosticos_homeslider',
        'schedule': crontab(hour=8, minute=45),
    },
    # Sanador liviano de vistas materializadas de ontología (Fase 13/14/18) —
    # cada 5 min (antes: 1h; originalmente hasta 24h), igualando la cadencia
    # del propio culpable (etl_sharepoint_watcher.py, cron */5) para que el
    # sanador nunca quede más de un ciclo de watcher detrás. Solo es seguro
    # correrlo tan seguido desde la Fase 18: el sanador pasó de reaplicar la
    # cadena histórica de migraciones (minutos por corrida) a un único script
    # canónico (sql/ontologia_vistas_canonicas.sql, segundos por corrida) —
    # ver scripts/ontologia/refresh_ontologia.py::_recrear_vistas_faltantes().
    # Complementa, no reemplaza, el refresh completo diario (cron de sistema
    # 4:30 AM) — ver tasks/ontologia_tasks.py.
    'verificar-vistas-ontologia-cada-5-min': {
        'task': 'tasks.ontologia_tasks.verificar_vistas_ontologia',
        'schedule': crontab(minute='*/5'),
    },
}

if __name__ == '__main__':
    app.start()
