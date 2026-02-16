"""
Celery Tasks - Tareas asíncronas y programadas
Envía alertas automáticas vía WhatsApp usando el sistema de notificaciones
"""
from celery import Celery
from celery.schedules import crontab
import logging
from datetime import datetime, date, timedelta
import sys
import asyncio
from pathlib import Path

# Agregar path del proyecto
server_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(server_path))

from app.config import settings

logger = logging.getLogger(__name__)

# Crear app Celery
app = Celery(
    'whatsapp_bot',
    broker=f'redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0',
    backend=f'redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0'
)

# Configuración
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Bogota',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutos máximo por tarea
)


def _run_async(coro):
    """Helper para ejecutar coroutines desde Celery (sync)"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=120)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _broadcast_alert_via_bot(message: str, severity: str = "ALERT") -> dict:
    """
    Envía alerta a TODOS los usuarios del bot via el endpoint broadcast.
    El bot de Oscar (puerto 8001) se encarga de enviar a cada usuario
    que alguna vez haya interactuado con el chatbot.
    """
    import httpx
    try:
        url = "http://localhost:8001/api/broadcast-alert"
        payload = {
            "message": message,
            "severity": severity
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload)
            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"✅ Broadcast completado: {result.get('sent', 0)} enviados "
                    f"de {result.get('users_count', 0)} usuarios"
                )
                return result
            else:
                logger.warning(f"⚠️ Bot respondió {response.status_code}: {response.text}")
                return {"status": "error", "code": response.status_code}
    except Exception as e:
        logger.error(f"❌ Error en broadcast via bot: {e}")
        return {"status": "error", "error": str(e)}


@app.task(name='tasks.check_anomalies')
def check_anomalies():
    """
    Tarea periódica: detectar anomalías y enviar alertas automáticas.
    Usa el sistema de alertas energéticas real.
    Envía via broadcast al bot de Oscar: el bot reenvía a TODOS los usuarios
    que alguna vez hayan interactuado con el chatbot.
    """
    try:
        logger.info("🔍 Verificando anomalías en el sistema...")
        
        # Importar el sistema de alertas energéticas real
        from scripts.alertas_energeticas import AlertasEnergeticas
        
        alertas_system = AlertasEnergeticas()
        resultado = alertas_system.ejecutar_evaluacion_completa()
        
        alertas = resultado.get('alertas', [])
        alertas_criticas = [a for a in alertas if a.get('severidad') in ('CRITICAL', 'ALERT', 'critica', 'alerta')]
        
        if alertas_criticas:
            logger.warning(f"⚠️ {len(alertas_criticas)} anomalías detectadas")
            
            # Construir mensaje de alerta
            alert_lines = []
            max_severity = "ALERT"
            for a in alertas_criticas[:5]:  # Max 5 alertas por mensaje
                metrica = a.get('metrica', 'Sistema')
                desc = a.get('descripcion', a.get('mensaje', 'Anomalía detectada'))
                sev = a.get('severidad', 'ALERT')
                if sev == 'CRITICAL':
                    max_severity = 'CRITICAL'
                alert_lines.append(f"{'🔴' if sev == 'CRITICAL' else '🟠'} *{metrica}*: {desc}")
            
            alert_message = f"""⚠️ *ALERTA AUTOMÁTICA - SISTEMA ELÉCTRICO* ⚠️

{chr(10).join(alert_lines)}

📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}
📊 Total alertas: {len(alertas_criticas)}

_Portal Energético - Ministerio de Minas y Energía_
"""
            
            # Enviar via broadcast al bot → el bot reenvía a todos sus usuarios
            broadcast_result = _broadcast_alert_via_bot(alert_message, max_severity)
            enviados = broadcast_result.get('sent', 0)
            
            # Registrar envío en BD
            _registrar_alerta_bd(alertas_criticas, enviados)
            
            logger.info(f"📤 Broadcast completado: {enviados} usuarios notificados")
        else:
            logger.info("✅ No se detectaron anomalías críticas")
        
        return {
            "status": "completed",
            "anomalies_found": len(alertas_criticas),
            "total_evaluated": len(alertas)
        }
    
    except Exception as e:
        logger.error(f"❌ Error verificando anomalías: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}


@app.task(name='tasks.send_daily_summary')
def send_daily_summary():
    """
    Envía resumen diario automático con datos reales del sistema
    """
    try:
        logger.info("📊 Generando resumen diario con datos reales...")
        
        from domain.services.generation_service import GenerationService
        from domain.services.hydrology_service import HydrologyService
        
        gen_service = GenerationService()
        
        # Obtener datos reales de generación
        end = date.today()
        start = end - timedelta(days=1)
        
        df_gen = gen_service.get_daily_generation_system(start, end)
        df_fuentes = gen_service.get_generation_by_sources(start, end)
        
        # Calcular métricas reales
        gen_total = round(df_gen['valor_gwh'].sum(), 1) if not df_gen.empty else 'N/D'
        
        # Mix energético
        mix_text = ""
        if not df_fuentes.empty:
            total = df_fuentes['valor_gwh'].sum()
            if total > 0:
                mix = df_fuentes.groupby('recurso')['valor_gwh'].sum()
                for recurso, valor in mix.sort_values(ascending=False).items():
                    pct = round((valor / total) * 100, 1)
                    icon = {'Hidráulica': '💧', 'Térmica': '🔥', 'Solar': '☀️', 
                            'Eólica': '🌬️', 'Biomasa': '🌿'}.get(recurso, '⚡')
                    mix_text += f"{icon} {recurso}: {pct}%\n"
        
        if not mix_text:
            mix_text = "Datos de mix no disponibles"
        
        message = f"""📊 *RESUMEN DIARIO DEL SIN*

📅 Fecha: {datetime.now().strftime('%Y-%m-%d')}

⚡ Generación Total: {gen_total} GWh

*Mix Energético:*
{mix_text}
_Portal Energético - Ministerio de Minas y Energía_
"""
        
        # Broadcast resumen diario a todos los usuarios del bot
        broadcast_result = _broadcast_alert_via_bot(message, "INFO")
        enviados = broadcast_result.get('sent', 0)
        
        logger.info(f"📤 Resumen diario enviado a {enviados} usuarios")
        return {"status": "completed", "users_notified": enviados}
    
    except Exception as e:
        logger.error(f"❌ Error enviando resumen diario: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}


@app.task(name='tasks.cleanup_old_data')
def cleanup_old_data():
    """
    Limpia datos antiguos (imágenes, logs, etc)
    """
    try:
        logger.info("🧹 Limpiando datos antiguos...")
        
        import os
        from pathlib import Path
        from datetime import timedelta
        
        # Limpiar imágenes antiguas (>7 días)
        charts_dir = settings.DATA_DIR / "charts"
        if charts_dir.exists():
            cutoff_time = datetime.now() - timedelta(days=7)
            deleted_count = 0
            
            for file_path in charts_dir.glob("*.png"):
                if file_path.stat().st_mtime < cutoff_time.timestamp():
                    file_path.unlink()
                    deleted_count += 1
            
            logger.info(f"🗑️ {deleted_count} imágenes antiguas eliminadas")
        
        return {"status": "completed", "files_deleted": deleted_count}
    
    except Exception as e:
        logger.error(f"❌ Error limpiando datos: {str(e)}")
        return {"status": "error", "error": str(e)}


def _registrar_alerta_bd(alertas: list, enviados: int):
    """Registra las alertas enviadas en la tabla alertas_historial"""
    try:
        import psycopg2
        import json
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='portal_energetico',
            user='postgres'
        )
        cur = conn.cursor()
        
        for alerta in alertas[:5]:  # Max 5 registros
            cur.execute("""
                INSERT INTO alertas_historial 
                (metrica, severidad, descripcion, valor_actual, umbral, 
                 notificacion_whatsapp_enviada, destinatarios_notificados)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                alerta.get('metrica', 'sistema'),
                alerta.get('severidad', 'ALERT'),
                alerta.get('descripcion', alerta.get('mensaje', '')),
                alerta.get('valor_actual', 0),
                alerta.get('umbral', ''),
                enviados > 0,
                enviados
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"📝 {len(alertas[:5])} alertas registradas en BD")
    except Exception as e:
        logger.error(f"Error registrando alertas en BD: {e}")


# ═══════════════════════════════════════════════════════════
# Configuración de tareas programadas (Beat Schedule)
# ═══════════════════════════════════════════════════════════

app.conf.beat_schedule = {
    'check-anomalies-every-30-minutes': {
        'task': 'tasks.check_anomalies',
        'schedule': crontab(minute='*/30'),  # Cada 30 minutos
    },
    'send-daily-summary-7am': {
        'task': 'tasks.send_daily_summary',
        'schedule': crontab(hour=7, minute=0),  # Diario a las 7 AM
    },
    'cleanup-old-data-daily': {
        'task': 'tasks.cleanup_old_data',
        'schedule': crontab(hour=2, minute=0),  # Diario a las 2 AM
    },
}

app.conf.timezone = 'America/Bogota'
