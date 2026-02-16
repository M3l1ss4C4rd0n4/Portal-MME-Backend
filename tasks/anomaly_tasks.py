"""
Tareas Celery para detección de anomalías y envío de alertas automáticas.

- check_anomalies: Cada 30 minutos evalúa el sistema energético
- send_daily_summary: Resumen diario a las 7:00 AM

Cuando detecta anomalías, envía un POST al bot de Oscar (puerto 8001)
en /api/broadcast-alert para que reenvíe a todos los usuarios del chatbot.
"""
import logging
import sys
import os
from datetime import datetime, date, timedelta
from celery import shared_task

# Asegurar que el directorio raíz del proyecto esté en el path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# Configuración del bot de Oscar
BOT_BROADCAST_URL = "http://localhost:8001/api/broadcast-alert"
BOT_TIMEOUT = 60


def _broadcast_alert_via_bot(message: str, severity: str = "ALERT") -> dict:
    """
    Envía alerta a TODOS los usuarios del bot via el endpoint broadcast.
    El bot de Oscar (puerto 8001) se encarga de enviar a cada usuario
    que alguna vez haya interactuado con el chatbot.
    """
    import requests
    try:
        payload = {
            "message": message,
            "severity": severity
        }
        response = requests.post(
            BOT_BROADCAST_URL,
            json=payload,
            timeout=BOT_TIMEOUT
        )
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
    except requests.exceptions.ConnectionError:
        logger.warning("⚠️ Bot de WhatsApp no disponible (puerto 8001). Alerta registrada pero no enviada.")
        return {"status": "bot_unavailable", "sent": 0}
    except Exception as e:
        logger.error(f"❌ Error en broadcast via bot: {e}")
        return {"status": "error", "error": str(e)}


def _registrar_alerta_bd(alertas: list, enviados: int):
    """Registra las alertas enviadas en la tabla alertas_historial"""
    try:
        from infrastructure.database.connection import PostgreSQLConnectionManager
        import psycopg2
        import json

        manager = PostgreSQLConnectionManager()
        conn_params = {
            'host': manager.host,
            'port': manager.port,
            'database': manager.database,
            'user': manager.user
        }
        if manager.password:
            conn_params['password'] = manager.password
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor()

        for alerta in alertas[:5]:
            try:
                cur.execute("""
                    INSERT INTO alertas_historial 
                    (fecha_evaluacion, metrica, severidad, descripcion, 
                     valor_promedio, json_completo,
                     notificacion_whatsapp_enviada)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    date.today(),
                    alerta.get('categoria', alerta.get('metrica', 'SISTEMA')),
                    alerta.get('severidad', 'ALERTA'),
                    alerta.get('titulo', alerta.get('descripcion', '')),
                    alerta.get('valor', 0),
                    json.dumps(alerta, ensure_ascii=False, default=str),
                    enviados > 0
                ))
            except Exception as e:
                logger.warning(f"No se pudo insertar alerta individual: {e}")
                conn.rollback()
                continue

        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"📝 {len(alertas[:5])} alertas registradas en BD")
    except Exception as e:
        logger.error(f"Error registrando alertas en BD: {e}")


def _check_stale_data():
    """
    Detecta métricas con datos congelados (mismos valores repetidos N días).
    Retorna lista de alertas para métricas potencialmente estancadas.
    """
    stale_alerts = []
    try:
        from infrastructure.database.connection import PostgreSQLConnectionManager
        import psycopg2

        manager = PostgreSQLConnectionManager()
        conn_params = {
            'host': manager.host, 'port': manager.port,
            'database': manager.database, 'user': manager.user
        }
        if manager.password:
            conn_params['password'] = manager.password
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor()

        # Métricas críticas a monitorear por datos congelados
        metricas_criticas = [
            ('CapaUtilDiarEner', 3),   # Alertar si 3+ días idénticos
            ('PorcVoluUtilDiar', 3),
            ('AporEner', 5),
            ('DemaReal', 2),
            ('Gene', 2),
        ]

        for metrica, max_dias_repetidos in metricas_criticas:
            cur.execute("""
                WITH daily_totals AS (
                    SELECT fecha, SUM(valor_gwh) as total
                    FROM metrics 
                    WHERE metrica = %s 
                    AND fecha >= CURRENT_DATE - INTERVAL '10 days'
                    GROUP BY fecha
                    ORDER BY fecha DESC
                    LIMIT 10
                )
                SELECT COUNT(*) as dias_iguales
                FROM daily_totals
                WHERE total = (SELECT total FROM daily_totals ORDER BY fecha DESC LIMIT 1)
            """, (metrica,))

            row = cur.fetchone()
            if row and row[0] > max_dias_repetidos:
                dias_frozen = row[0]
                stale_alerts.append({
                    'categoria': f'DATOS_CONGELADOS',
                    'metrica': metrica,
                    'severidad': 'ALERTA',
                    'titulo': f'{metrica}: datos idénticos {dias_frozen} días consecutivos',
                    'descripcion': f'La métrica {metrica} muestra el mismo valor total '
                                   f'durante {dias_frozen} días seguidos. Posible problema '
                                   f'con la API XM o el ETL.',
                    'valor': dias_frozen
                })
                logger.warning(
                    f"⚠️ {metrica}: datos congelados {dias_frozen} días "
                    f"(umbral: {max_dias_repetidos})"
                )

        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error en detección de datos congelados: {e}")
    
    return stale_alerts


@shared_task(name='tasks.anomaly_tasks.check_anomalies', bind=True, max_retries=2)
def check_anomalies(self):
    """
    Tarea periódica: detectar anomalías y enviar alertas automáticas.
    Usa el sistema de alertas energéticas real (scripts/alertas_energeticas.py).
    Envía via broadcast al bot de Oscar → el bot reenvía a TODOS los usuarios.
    """
    try:
        logger.info("🔍 [ANOMALÍAS] Verificando anomalías en el sistema...")

        from scripts.alertas_energeticas import SistemaAlertasEnergeticas

        sistema = SistemaAlertasEnergeticas()
        try:
            # Evaluar todas las métricas
            sistema.evaluar_demanda(horizonte=7)
            sistema.evaluar_aportes_hidricos(horizonte=7)
            sistema.evaluar_embalses(horizonte=7)
            sistema.evaluar_precio_bolsa(horizonte=7)
            sistema.evaluar_balance_energetico(horizonte=7)
        finally:
            sistema.close()

        alertas = sistema.alertas
        alertas_criticas = [a for a in alertas if a.get('severidad') in ('CRÍTICO', 'ALERTA')]

        # ── Detección de datos congelados ──
        staleness_alerts = _check_stale_data()
        if staleness_alerts:
            alertas_criticas.extend(staleness_alerts)
            logger.warning(f"⚠️ [ANOMALÍAS] {len(staleness_alerts)} métricas con datos congelados")

        if alertas_criticas:
            logger.warning(f"⚠️ [ANOMALÍAS] {len(alertas_criticas)} anomalías detectadas")

            # Construir mensaje
            alert_lines = []
            max_severity = "ALERT"
            for a in alertas_criticas[:5]:
                categoria = a.get('categoria', 'Sistema')
                titulo = a.get('titulo', 'Anomalía detectada')
                sev = a.get('severidad', 'ALERTA')
                if sev == 'CRÍTICO':
                    max_severity = 'CRITICAL'
                icon = '🔴' if sev == 'CRÍTICO' else '🟠'
                alert_lines.append(f"{icon} *{categoria}*: {titulo}")

            alert_message = (
                f"⚠️ *ALERTA AUTOMÁTICA - SISTEMA ELÉCTRICO* ⚠️\n\n"
                f"{chr(10).join(alert_lines)}\n\n"
                f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"📊 Total alertas: {len(alertas_criticas)}\n\n"
                f"_Portal Energético - Ministerio de Minas y Energía_"
            )

            # Enviar broadcast (Telegram + email)
            from domain.services.notification_service import broadcast_alert as ns_broadcast

            broadcast_result = ns_broadcast(
                message=alert_message,
                severity=max_severity,
                is_daily=False,
            )
            enviados = (
                broadcast_result.get('telegram', {}).get('sent', 0)
                + broadcast_result.get('email', {}).get('sent', 0)
            )

            # Registrar en BD
            _registrar_alerta_bd(alertas_criticas, enviados)

            logger.info(f"📤 [ANOMALÍAS] Broadcast completado: {enviados} usuarios notificados")
        else:
            logger.info("✅ [ANOMALÍAS] No se detectaron anomalías críticas")

        return {
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "anomalies_found": len(alertas_criticas) if alertas_criticas else 0,
            "total_evaluated": len(alertas)
        }

    except Exception as e:
        logger.error(f"❌ [ANOMALÍAS] Error verificando anomalías: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=120)


@shared_task(name='tasks.anomaly_tasks.send_daily_summary')
def send_daily_summary():
    """
    Tarea diaria (7:00 AM): genera el informe ejecutivo completo con IA,
    crea un PDF y lo envía a todos los usuarios vía Telegram + email.

    Flujo:
       1. Llama al orquestador (HTTP) para obtener el informe ejecutivo.
       2. Genera el PDF con report_service.
       3. Envía por Telegram (texto + PDF adjunto) y email (HTML + PDF adjunto)
          usando NotificationService.
    """
    try:
        logger.info("📊 [RESUMEN DIARIO] Generando informe ejecutivo completo…")

        import requests
        from domain.services.report_service import generar_pdf_informe
        from domain.services.notification_service import (
            broadcast_alert as ns_broadcast,
            build_daily_email_html,
        )

        # ── 1. Obtener el informe ejecutivo del orquestador ──
        API_BASE = "http://localhost:8000"
        API_KEY = os.getenv(
            'API_KEY', 'mme-portal-energetico-2026-secret-key'
        )

        informe_texto = None
        generado_con_ia = False
        fecha_generacion = datetime.now().strftime('%Y-%m-%d %H:%M')

        try:
            resp = requests.post(
                f"{API_BASE}/v1/chatbot/orchestrator",
                json={
                    "sessionId": f"daily_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "intent": "informe_ejecutivo",
                    "parameters": {},
                },
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": API_KEY,
                },
                timeout=120,
            )
            if resp.status_code == 200:
                body = resp.json()
                data = body.get('data', {})
                informe_texto = data.get('informe')
                generado_con_ia = data.get('generado_con_ia', False)
                fecha_generacion = data.get(
                    'fecha_generacion', fecha_generacion
                )
                if informe_texto:
                    logger.info(
                        f"[RESUMEN DIARIO] Informe obtenido del orquestador "
                        f"(IA={generado_con_ia}, {len(informe_texto)} chars)"
                    )
            else:
                logger.warning(
                    f"[RESUMEN DIARIO] Orquestador respondió "
                    f"{resp.status_code}: {resp.text[:200]}"
                )
        except Exception as e:
            logger.warning(f"[RESUMEN DIARIO] Error llamando orquestador: {e}")

        # ── Fallback: KPIs básicos si el orquestador no responde ──
        if not informe_texto:
            logger.info("[RESUMEN DIARIO] Usando fallback de KPIs básicos")
            informe_texto = _build_kpi_fallback()
            generado_con_ia = False

        # ── 2. Generar PDF ──
        pdf_path = None
        try:
            pdf_path = generar_pdf_informe(
                informe_texto, fecha_generacion, generado_con_ia
            )
            if pdf_path:
                logger.info(f"[RESUMEN DIARIO] PDF generado: {pdf_path}")
        except Exception as e:
            logger.warning(f"[RESUMEN DIARIO] Error generando PDF: {e}")

        # ── 3. Construir mensaje Telegram ──
        tg_message = (
            f"📊 *INFORME EJECUTIVO DIARIO DEL SIN*\n\n"
            f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"{informe_texto}\n\n"
            f"_Portal Energético — Ministerio de Minas y Energía_"
        )

        # Telegram tiene límite de 4096 caracteres
        if len(tg_message) > 4000:
            # Recortar y poner nota de que el PDF tiene el informe completo
            tg_message = (
                tg_message[:3900] + "\n\n"
                "_(Informe recortado — consulte el PDF adjunto para "
                "la versión completa)_"
            )

        # ── 4. Enviar por todos los canales ──
        email_html = build_daily_email_html(informe_texto)

        result = ns_broadcast(
            message=tg_message,
            severity="INFO",
            pdf_path=pdf_path,
            email_subject=(
                f"📊 Informe Ejecutivo del Sector Eléctrico — "
                f"{datetime.now().strftime('%Y-%m-%d')}"
            ),
            email_body_html=email_html,
            is_daily=True,
        )

        total_sent = (
            result.get("telegram", {}).get("sent", 0)
            + result.get("email", {}).get("sent", 0)
        )
        logger.info(
            f"📤 [RESUMEN DIARIO] Completado: {total_sent} notificaciones "
            f"(TG={result['telegram']['sent']}, "
            f"Email={result['email']['sent']})"
        )

        # Limpiar PDF temporal
        if pdf_path and os.path.isfile(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass

        return {
            "status": "completed",
            "informe_ia": generado_con_ia,
            "telegram_sent": result["telegram"]["sent"],
            "email_sent": result["email"]["sent"],
        }

    except Exception as e:
        logger.error(
            f"❌ [RESUMEN DIARIO] Error: {str(e)}", exc_info=True
        )
        return {"status": "error", "error": str(e)}


def _build_kpi_fallback() -> str:
    """Genera un resumen básico con 3 KPIs cuando el orquestador no responde."""
    from domain.services.generation_service import GenerationService
    from domain.services.hydrology_service import HydrologyService
    from domain.services.metrics_service import MetricsService

    gen_service = GenerationService()
    hydro_service = HydrologyService()
    metrics_service = MetricsService()

    end = date.today()
    start = end - timedelta(days=1)

    gen_total = 'N/D'
    try:
        df_gen = gen_service.get_daily_generation_system(start, end)
        if not df_gen.empty:
            gen_total = f"{round(df_gen['valor_gwh'].sum(), 1)} GWh"
    except Exception:
        pass

    precio = 'N/D'
    try:
        df_precio = metrics_service.get_metric_data('PrecBolsNaci', start, end)
        if not df_precio.empty:
            col = 'valor' if 'valor' in df_precio.columns else df_precio.columns[-1]
            precio = f"{round(df_precio[col].mean(), 2)} COP/kWh"
    except Exception:
        pass

    embalses = 'N/D'
    try:
        emb_data = hydro_service.get_hydrology_summary(start, end)
        if emb_data and 'porcentaje_embalses' in emb_data:
            embalses = f"{round(emb_data['porcentaje_embalses'], 1)}%"
    except Exception:
        pass

    mix_text = ""
    try:
        df_fuentes = gen_service.get_generation_by_sources(start, end)
        if not df_fuentes.empty:
            total = df_fuentes['valor_gwh'].sum()
            if total > 0:
                mix = df_fuentes.groupby('recurso')['valor_gwh'].sum()
                icons = {
                    'Hidráulica': '💧', 'Térmica': '🔥', 'Solar': '☀️',
                    'Eólica': '🌬️', 'Biomasa': '🌿',
                }
                for recurso, valor in mix.sort_values(ascending=False).items():
                    pct = round((valor / total) * 100, 1)
                    icon = icons.get(recurso, '⚡')
                    mix_text += f"  {icon} {recurso}: {pct}%\n"
    except Exception:
        pass

    if not mix_text:
        mix_text = "  Datos de mix no disponibles\n"

    return (
        f"⚡ *Generación Total:* {gen_total}\n"
        f"💰 *Precio de Bolsa:* {precio}\n"
        f"💧 *Embalses:* {embalses}\n\n"
        f"*Mix Energético:*\n{mix_text}"
    )
