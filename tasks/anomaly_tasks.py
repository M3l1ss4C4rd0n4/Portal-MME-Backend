"""
Tareas Celery para detección de anomalías y envío de alertas automáticas.

- check_anomalies: Cada 30 minutos evalúa el sistema energético.
  SOLO envía notificación cuando detecta anomalías CRÍTICAS realmente urgentes.
  NO envía si la misma alerta ya fue notificada en las últimas 6 horas.
- send_daily_generate: Resumen diario a las 8:30 AM (genera PDF + Telegram, dispara emails).
- send_daily_summary: Alias deprecated → send_daily_generate.

Cuando detecta anomalías críticas, envía por Telegram + email
usando NotificationService.
"""
import json
import logging
import re as _re
import sys
import os
from datetime import datetime, date, timedelta
from celery import shared_task, group, chord

# Asegurar que el directorio raíz del proyecto esté en el path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# Configuración del bot de Oscar
BOT_BROADCAST_URL = "http://localhost:8001/api/broadcast-alert"
BOT_TIMEOUT = 60

# ── Cooldown: no reenviar la misma alerta más de una vez por día ──
ALERT_COOLDOWN_HOURS = 24  # valor de respaldo; en práctica se usa TTL hasta medianoche
DAILY_LOCK_TTL_SECONDS = 72000  # 20 horas — expira antes del próximo informe


def _get_redis():
    """Cliente Redis para locks de idempotencia (DB 1, mismo backend Celery)."""
    import redis as _redis
    return _redis.Redis(host='localhost', port=6379, db=1, socket_timeout=2)


def _informes_dir() -> str:
    return os.path.join(_PROJECT_ROOT, "whatsapp_bot", "informes")


def _daily_gen_lock_key(day: date) -> str:
    return f"daily_summary_gen_{day.isoformat()}"


def _daily_email_lock_key(day: date, dest: str) -> str:
    return f"daily_email_sent_{day.isoformat()}_{dest.lower()}"


def _is_daily_generation_done(day: date) -> bool:
    try:
        return bool(_get_redis().get(_daily_gen_lock_key(day)))
    except Exception as e:
        logger.warning("[RESUMEN DIARIO] No se pudo verificar lock de generación: %s", e)
        return False


def _mark_daily_generation_done(day: date) -> None:
    try:
        _get_redis().setex(_daily_gen_lock_key(day), DAILY_LOCK_TTL_SECONDS, "generated")
    except Exception as e:
        logger.warning("[RESUMEN DIARIO] No se pudo marcar lock de generación: %s", e)


def _is_daily_email_sent(day: date, dest: str) -> bool:
    try:
        return bool(_get_redis().get(_daily_email_lock_key(day, dest)))
    except Exception as e:
        logger.warning("[RESUMEN DIARIO] No se pudo verificar lock email %s: %s", dest, e)
        return False


def _mark_daily_email_sent(day: date, dest: str) -> None:
    try:
        _get_redis().setex(_daily_email_lock_key(day, dest), DAILY_LOCK_TTL_SECONDS, "sent")
    except Exception as e:
        logger.warning("[RESUMEN DIARIO] No se pudo marcar lock email %s: %s", dest, e)


def _clean_markdown_for_telegram(text: str) -> str:
    """Convierte markdown estándar (##, ###, **, -) a Telegram Markdown v1."""
    # Quitar título general si quedó (# INFORME...)
    text = _re.sub(r'^#\s+INFORME.+\n?', '', text)
    text = _re.sub(r'^📅\s*Fecha:.+\n?', '', text, flags=_re.MULTILINE)
    # ## N. Título → *N. Título* (negrita Telegram)
    text = _re.sub(
        r'^##\s*(\d+\.\s*.+)$',
        r'*\1*',
        text,
        flags=_re.MULTILINE,
    )
    # ### N.N Subtítulo → _N.N Subtítulo_ (itálica Telegram)
    text = _re.sub(
        r'^###?\s*(\d+\.\d+\s*.+)$',
        r'_\1_',
        text,
        flags=_re.MULTILINE,
    )
    # **texto** → *texto* (negrita Telegram)
    text = _re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    # - item → ▸ item
    text = _re.sub(r'^-\s+', '▸ ', text, flags=_re.MULTILINE)
    #   - sub-item → · sub-item
    text = _re.sub(r'^\s{2,}-\s+', '  · ', text, flags=_re.MULTILINE)
    return text.strip()


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
            tg_sent = result.get('telegram_sent', 0)
            wa_sent = result.get('sent', 0)
            total = result.get('total_sent', tg_sent + wa_sent)
            logger.info(
                f"✅ Broadcast completado: {total} enviados "
                f"(Telegram={tg_sent}, WhatsApp={wa_sent})"
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
        from core.config import settings
        import psycopg2
        import json

        conn_params = {
            'host': settings.POSTGRES_HOST,
            'port': settings.POSTGRES_PORT,
            'database': settings.POSTGRES_DB,
            'user': settings.POSTGRES_USER
        }
        if settings.POSTGRES_PASSWORD:
            conn_params['password'] = settings.POSTGRES_PASSWORD
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor()

        for alerta in alertas[:5]:
            try:
                # Convertir tipos numpy a Python nativos para que psycopg2 los acepte
                # (pandas devuelve numpy.float64/int64 que psycopg2 no adapta y rompe el INSERT)
                _valor_raw = alerta.get('valor', 0)
                _valor_py = float(_valor_raw) if _valor_raw is not None else 0.0
                # Bug real encontrado (2026-08-25): solo se guardaba `titulo`
                # (un renglón corto tipo "Índice PBP ALTO: 7/7 días sobre PE
                # 667 COP/kWh") y la `descripcion` más explicativa que sí
                # arma cada evaluador de alertas_energeticas.py (ej. "Sistema
                # en modo de compensación hidráulica") se descartaba por
                # completo — nunca llegaba al correo/informe/Telegram, que
                # leen esta columna. Causa real reportada por el usuario de
                # que las alertas "no son legibles". `alertas_historial` no
                # tiene una columna separada para el título corto, así que
                # se concatenan ambos en la misma columna `descripcion` (el
                # HTML del correo ya muestra `metrica` en negrita arriba,
                # esto solo enriquece el texto de abajo).
                _titulo = str(alerta.get('titulo', '')).strip()
                _desc = str(alerta.get('descripcion', '')).strip()
                if _titulo and _desc:
                    _descripcion_completa = f"{_titulo}. {_desc}"
                else:
                    _descripcion_completa = _titulo or _desc
                cur.execute("""
                    INSERT INTO alertas_historial
                    (fecha_evaluacion, metrica, severidad, descripcion,
                     valor_promedio, json_completo,
                     notificacion_whatsapp_enviada)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT ON CONSTRAINT unique_alerta_fecha_metrica DO UPDATE SET
                        notificacion_whatsapp_enviada = GREATEST(
                            alertas_historial.notificacion_whatsapp_enviada,
                            EXCLUDED.notificacion_whatsapp_enviada
                        ),
                        fecha_generacion = CASE
                            WHEN EXCLUDED.notificacion_whatsapp_enviada = TRUE
                            THEN NOW()
                            ELSE alertas_historial.fecha_generacion
                        END
                """, (
                    date.today(),
                    str(alerta.get('categoria', alerta.get('metrica', 'SISTEMA'))),
                    str(alerta.get('severidad', 'ALERTA')),
                    _descripcion_completa,
                    _valor_py,
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
                    -- ROUND a 1 decimal evita falsos positivos por precisión binaria
                    SELECT fecha, ROUND(SUM(valor_gwh)::numeric, 1) AS total
                    FROM metrics
                    WHERE metrica = %s
                      AND fecha >= CURRENT_DATE - INTERVAL '10 days'
                    GROUP BY fecha
                    ORDER BY fecha DESC
                    LIMIT 10
                ),
                ranked AS (
                    SELECT fecha, total,
                           ROW_NUMBER() OVER (ORDER BY fecha DESC) AS rn
                    FROM daily_totals
                ),
                latest AS (
                    SELECT total FROM ranked WHERE rn = 1
                )
                -- Contar solo días CONSECUTIVOS desde el más reciente con igual total.
                -- Si hay un día diferente en el medio, los anteriores no cuentan.
                SELECT COUNT(*)
                FROM ranked r, latest l
                WHERE r.total = l.total
                  AND NOT EXISTS (
                      SELECT 1 FROM ranked r2, latest l2
                      WHERE r2.rn < r.rn
                        AND r2.total <> l2.total
                  )
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


def _alerta_ya_notificada(clave: str, horas: int = ALERT_COOLDOWN_HOURS) -> bool:
    """
    Verifica si una alerta con esta clave ya fue notificada hoy.
    Usa Redis como fuente de verdad (atómico, compartido por todos los workers).
    El TTL se calcula hasta medianoche para garantizar máximo 1 envío por día.

    `clave` debe ser un identificador ESTABLE del tipo de alerta (ej. 'HSIN_CRITICO'),
    nunca el título formateado con valores en vivo (ej. porcentajes) — de lo contrario
    cada ciclo genera una clave distinta y el cooldown nunca hace match.
    """
    try:
        import redis as _redis
        _r = _redis.Redis(host='localhost', port=6379, db=1, socket_timeout=2)
        _key = 'alert_cooldown:' + clave.replace(' ', '_')[:120]
        return bool(_r.get(_key))
    except Exception as e:
        logger.warning(f"Error verificando cooldown de alerta (Redis): {e}")
        return False  # En caso de error, permitir enviar


def _activar_cooldown_alerta(clave: str, horas: int = ALERT_COOLDOWN_HOURS) -> None:
    """Registra en Redis que esta alerta ya fue notificada hoy (TTL hasta medianoche)."""
    try:
        import redis as _redis
        from datetime import datetime
        _r = _redis.Redis(host='localhost', port=6379, db=1, socket_timeout=2)
        _key = 'alert_cooldown:' + clave.replace(' ', '_')[:120]
        # TTL = segundos restantes hasta las 00:00 del día siguiente
        _now = datetime.now()
        _midnight = (_now.replace(hour=0, minute=0, second=0, microsecond=0)
                     + timedelta(days=1))
        _ttl = max(int((_midnight - _now).total_seconds()), 3600)
        _r.setex(_key, _ttl, '1')
        logger.debug(f"Cooldown activado hasta medianoche: {_key} (TTL={_ttl}s)")
    except Exception as e:
        logger.warning(f"Error activando cooldown en Redis: {e}")


@shared_task(name='tasks.anomaly_tasks.check_anomalies', bind=True, max_retries=2)
def check_anomalies(self):
    """
    Tarea periódica: detectar anomalías en el sistema energético.

    POLÍTICA DE NOTIFICACIÓN:
      - Solo se envía notificación por Telegram/email cuando hay anomalías
        de severidad CRÍTICO (urgencias reales que el Viceministro debe conocer).
      - Las alertas de severidad ALERTA se registran en BD y logs pero NO
        se envían como notificación push.
      - Cooldown diario: si la misma alerta ya fue notificada hoy (TTL hasta
        medianoche), no se reenvía — máximo 1 notificación por alerta por día.
      - Métricas evaluadas: demanda (presión), aportes hídricos, embalses (%),
        precio bolsa vs escasez, margen operativo (%), estrés térmico (%).
      - El informe diario (8:30 AM) sí incluye TODAS las anomalías detectadas.
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
            sistema.evaluar_estres_termico(horizonte=7)
        finally:
            sistema.close()

        alertas = sistema.alertas
        alertas_criticas = [a for a in alertas if a.get('severidad') in ('CRÍTICO', 'ALERTA')]

        # ── Detección de datos congelados ──
        staleness_alerts = _check_stale_data()
        if staleness_alerts:
            alertas_criticas.extend(staleness_alerts)
            logger.warning(f"⚠️ [ANOMALÍAS] {len(staleness_alerts)} métricas con datos congelados")

        # ── CU/PNT alertas (Fase 7) ──
        try:
            from core.container import container as _ctnr
            _cu = _ctnr.get_cu_service().get_cu_current()
            if _cu:
                cu_val = _cu.get('cu_total', 0)
                if cu_val > 600:
                    # CU es un indicador ECONÓMICO, no operativo.
                    # Severidad máxima = ALERTA para evitar confusión con riesgo de
                    # desabastecimiento. NUNCA genera CRÍTICO operativo.
                    alertas_criticas.append({
                        'titulo': f'💲 CU elevado: {cu_val:.0f} COP/kWh [indicador económico, umbral criterio propio, no CREG]',
                        'categoria': 'Costo Unitario',
                        'severidad': 'ALERTA',  # Máx ALERTA — no riesgo operativo SIN
                        'descripcion': (
                            f'El Costo Unitario alcanzó {cu_val:.2f} COP/kWh '
                            f'(umbral de seguimiento: >600 — umbral de criterio propio del portal, '
                            f'sin cita normativa CREG que lo respalde). '
                            f'INDICADOR ECONÓMICO — No implica riesgo de desabastecimiento. '
                            f'Refleja presión tarifaria, combustibles o decisiones regulatorias.'
                        ),
                    })
                    logger.warning(f"💲 [ANOMALÍAS] CU elevado (económico): {cu_val:.2f} COP/kWh")
                elif cu_val > 400:
                    alertas_criticas.append({
                        'titulo': f'CU_ELEVADO: {cu_val:.0f} COP/kWh [criterio propio, no CREG]',
                        'categoria': 'Costo Unitario',
                        'severidad': 'ALERTA',
                        'descripcion': (
                            f'El Costo Unitario alcanzó {cu_val:.2f} COP/kWh '
                            f'(umbral alerta: >400 — umbral de criterio propio del portal, '
                            f'sin cita normativa CREG que lo respalde).'
                        ),
                    })
                    logger.info(f"⚠️ [ANOMALÍAS] CU elevado: {cu_val:.2f} COP/kWh")
        except Exception as e:
            logger.warning(f"[ANOMALÍAS] CU check falló (no crítico): {e}")

        try:
            from core.container import container as _ctnr
            from domain.services.losses_nt_service import OPERATOR_PROFILES
            _pnt = _ctnr.losses_nt_service.get_losses_statistics()
            if _pnt:
                pnt_val = _pnt.get('pct_promedio_nt_30d', 0)
                # Umbral nacional agregado (perfil DEFAULT = mix todos OR)
                _perfil_nac = OPERATOR_PROFILES['DEFAULT']
                if pnt_val > _perfil_nac.pnt_crit_pct:
                    alertas_criticas.append({
                        'titulo': f'PNT_CRÍTICA: {pnt_val:.1f}%',
                        'clave': 'PNT_CRITICA',
                        'categoria': 'Pérdidas No Técnicas',
                        'severidad': 'CRÍTICO',
                        'descripcion': (
                            f'P_NT promedio 30d: {pnt_val:.2f}% supera umbral crítico '
                            f'nacional ({_perfil_nac.pnt_crit_pct}%). '
                            f'Posible incremento sistémico de hurto/subfacturación. '
                            f'Fuente del umbral: SSPD Informes de Pérdidas por OR 2023-2024 '
                            f'y Plan de Pérdidas CREG 015 de 2018.'
                        ),
                    })
                    logger.info(f"🔴 [ANOMALÍAS] PNT CRÍTICA: {pnt_val:.2f}%")
                elif pnt_val > _perfil_nac.pnt_warn_pct:
                    alertas_criticas.append({
                        'titulo': f'PNT_ELEVADA: {pnt_val:.1f}%',
                        'categoria': 'Pérdidas No Técnicas',
                        'severidad': 'ALERTA',
                        'descripcion': (
                            f'P_NT promedio 30d: {pnt_val:.2f}% supera umbral de alerta '
                            f'({_perfil_nac.pnt_warn_pct}%). Revisar medición y facturación. '
                            f'Fuente del umbral: SSPD Informes de Pérdidas por OR 2023-2024 '
                            f'y Plan de Pérdidas CREG 015 de 2018.'
                        ),
                    })
                    logger.info(f"⚠️ [ANOMALÍAS] PNT elevada: {pnt_val:.2f}%")
        except Exception as e:
            logger.warning(f"[ANOMALÍAS] PNT check falló (no crítico): {e}")

        # ── FILTRO DE URGENCIA ──
        # Solo notificar las CRÍTICAS (no las de severidad ALERTA)
        alertas_urgentes = [
            a for a in alertas_criticas
            if a.get('severidad') == 'CRÍTICO'
        ]

        # ── FILTRO DE COOLDOWN ──
        # Se evalúa ANTES de registrar en BD para que la búsqueda de cooldown
        # no encuentre la inserción actual (que aún no existe en este ciclo).
        alertas_nuevas = []
        for a in alertas_urgentes:
            titulo = a.get('titulo', a.get('descripcion', ''))
            clave = a.get('clave') or titulo
            if not _alerta_ya_notificada(clave):
                alertas_nuevas.append(a)
            else:
                logger.info(
                    f"⏳ [ANOMALÍAS] Alerta ya notificada recientemente, omitiendo: {titulo}"
                )

        # Registrar TODAS las alertas en BD (para el informe diario)
        if alertas_criticas:
            _registrar_alerta_bd(alertas_criticas, 0)
            logger.info(f"📝 [ANOMALÍAS] {len(alertas_criticas)} anomalías registradas en BD")

        if alertas_nuevas:
            logger.warning(
                f"🚨 [ANOMALÍAS] {len(alertas_nuevas)} anomalías CRÍTICAS NUEVAS → notificando"
            )

            # Construir mensaje
            alert_lines = []
            max_severity = "CRITICAL"
            for a in alertas_nuevas[:5]:
                categoria = a.get('categoria', 'Sistema')
                titulo = a.get('titulo', 'Anomalía detectada')
                icon = '🔴'
                alert_lines.append(f"{icon} *{categoria}*: {titulo}")

            alert_message = (
                f"🚨 *ALERTA URGENTE - SISTEMA ELÉCTRICO* 🚨\n\n"
                f"{chr(10).join(alert_lines)}\n\n"
                f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"📊 Total alertas críticas: {len(alertas_nuevas)}\n\n"
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

            # Actualizar BD con estado de envío (garantizar flag = TRUE)
            _registrar_alerta_bd(alertas_nuevas, max(1, enviados))

            # Activar cooldown Redis para cada alerta enviada (atómico, cross-worker)
            for _a in alertas_nuevas:
                _clave_envio = _a.get('clave') or _a.get('titulo', _a.get('descripcion', ''))
                _activar_cooldown_alerta(_clave_envio)

            logger.info(f"📤 [ANOMALÍAS] Broadcast completado: {enviados} usuarios notificados")
        elif alertas_criticas:
            logger.info(
                f"📋 [ANOMALÍAS] {len(alertas_criticas)} anomalías detectadas "
                f"(ninguna crítica nueva para notificar)"
            )
        else:
            logger.info("✅ [ANOMALÍAS] No se detectaron anomalías críticas")

        return {
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "anomalies_found": len(alertas_criticas) if alertas_criticas else 0,
            "critical_new": len(alertas_nuevas) if alertas_nuevas else 0,
            "notified": len(alertas_nuevas) > 0 if alertas_nuevas else False,
            "total_evaluated": len(alertas)
        }

    except Exception as e:
        logger.error(f"❌ [ANOMALÍAS] Error verificando anomalías: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=120)


@shared_task(
    name='tasks.anomaly_tasks.send_daily_generate',
    time_limit=600,
    soft_time_limit=540,
)
def send_daily_generate():
    """
    Tarea diaria (8:30 AM): genera el informe ejecutivo completo.

    Combina generación de datos, gráficos y PDF; envía Telegram;
    persiste artefactos en disco y dispara envío de emails en subtareas.

    Lock anti-duplicación: se marca solo tras persistir PDF + HTML.
    """
    try:
        today = date.today()
        if _is_daily_generation_done(today):
            logger.info(
                "⏭️ [RESUMEN DIARIO] Informe ya generado hoy (%s). "
                "Omitido por guarda anti-duplicación.",
                today,
            )
            return {
                "status": "skipped",
                "reason": "already_generated_today",
                "date": today.isoformat(),
            }

        logger.info("📊 [RESUMEN DIARIO] Generando informe ejecutivo completo…")

        import requests
        from domain.services.report_service import generar_pdf_informe
        from domain.services.notification_service import (
            broadcast_telegram,
            build_daily_email_html,
        )

        API_BASE = "http://localhost:8000"
        API_KEY = os.getenv('API_KEY')
        HDR = {"Content-Type": "application/json", "X-API-Key": API_KEY}

        def _api_call(intent, params=None, timeout=120):
            """Helper para llamar al orquestador."""
            try:
                r = requests.post(
                    f"{API_BASE}/v1/chatbot/orchestrator",
                    json={
                        "sessionId": f"daily_{intent}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        "intent": intent,
                        "parameters": params or {},
                    },
                    headers=HDR,
                    timeout=timeout,
                )
                if r.status_code == 200:
                    return r.json().get('data', {})
            except Exception as e:
                logger.warning(f"[RESUMEN DIARIO] Error en API {intent}: {e}")
            return {}

        # ══════════════════════════════════════════════
        # 1. Texto narrativo IA (informe_ejecutivo)
        # ══════════════════════════════════════════════
        import time as _time

        informe_texto = None
        generado_con_ia = False
        fecha_generacion = datetime.now().strftime('%Y-%m-%d %H:%M')
        d_informe: dict = {}
        _INFORME_TIMEOUT = 180

        for _attempt in range(2):
            d_informe = _api_call('informe_ejecutivo', timeout=_INFORME_TIMEOUT)
            if d_informe.get('contexto_datos'):
                break
            if _attempt == 0:
                logger.warning(
                    "[RESUMEN DIARIO] informe_ejecutivo sin contexto_datos — "
                    "reintento en 5s (timeout=%ss)",
                    _INFORME_TIMEOUT,
                )
                _time.sleep(5)

        _contexto_datos = d_informe.get('contexto_datos') if d_informe else None
        if not _contexto_datos:
            logger.error(
                "[RESUMEN DIARIO] Sin contexto_datos tras 2 intentos — "
                "abortando sin marcar lock (re-ejecución manual permitida)"
            )
            return {
                "status": "error",
                "error": "informe_ejecutivo_sin_contexto",
                "date": today.isoformat(),
            }

        if d_informe:
            informe_texto = d_informe.get('informe')
            generado_con_ia = d_informe.get('generado_con_ia', False)
            fecha_generacion = d_informe.get('fecha_generacion', fecha_generacion)
            if informe_texto:
                logger.info(
                    f"[RESUMEN DIARIO] Informe IA obtenido "
                    f"({len(informe_texto)} chars, IA={generado_con_ia})"
                )

        if not informe_texto:
            logger.info("[RESUMEN DIARIO] Usando fallback de KPIs básicos")
            informe_texto = _build_kpi_fallback()
            generado_con_ia = False

        # ══════════════════════════════════════════════
        # 2. Datos estructurados reales
        # ══════════════════════════════════════════════
        # 2a. KPIs (estado_actual → fichas)
        fichas = []
        d_estado = _api_call('estado_actual', timeout=60)
        if d_estado:
            fichas = d_estado.get('fichas', [])
            logger.info(f"[RESUMEN DIARIO] KPIs obtenidos: {len(fichas)}")

        # 2b. Predicciones a 30 días — las 3 métricas clave
        predicciones_lista = []
        _PRED_METRICS = [
            ('GENE_TOTAL', 'Generación Total del Sistema'),
            ('PRECIO_BOLSA', 'Precio de Bolsa Nacional'),
            ('EMBALSES_PCT', 'Porcentaje de Embalses'),
        ]
        for metric_id, metric_label in _PRED_METRICS:
            d_pred = _api_call(
                'predicciones',
                {'fuente': metric_id, 'horizonte': 30},
                timeout=60,
            )
            if d_pred and d_pred.get('predicciones'):
                # Enriquecer estadísticas con IC próximos 7 días (rango corto, más preciso)
                _preds = d_pred.get('predicciones', [])
                _estadisticas = d_pred.get('estadisticas', {})
                _preds_sorted = sorted(_preds, key=lambda p: p.get('fecha', ''))
                _near = _preds_sorted[:7] if len(_preds_sorted) >= 7 else _preds_sorted
                _ic_infs = [p['intervalo_inferior'] for p in _near if p.get('intervalo_inferior') is not None]
                _ic_sups = [p['intervalo_superior'] for p in _near if p.get('intervalo_superior') is not None]
                if _ic_infs and _ic_sups:
                    _estadisticas['ic_inferior_gwh'] = round(
                        sum(_ic_infs) / len(_ic_infs), 1)
                    _estadisticas['ic_superior_gwh'] = round(
                        sum(_ic_sups) / len(_ic_sups), 1)
                predicciones_lista.append({
                    'fuente': d_pred.get('fuente', metric_label),
                    'fuente_label': metric_label,
                    'horizonte_dias': d_pred.get('horizonte_dias', 30),
                    'estadisticas': _estadisticas,
                    'modelo': d_pred.get('modelo', ''),
                    'conclusiones': d_pred.get('conclusiones', []),
                    'predicciones': _preds,
                })
                logger.info(
                    f"[RESUMEN DIARIO] Predicciones {metric_id}: "
                    f"{d_pred.get('total_predicciones', 0)} puntos"
                )
        # Compatibilidad: predicciones_data = primera métrica (o vacío)
        predicciones_data = predicciones_lista[0] if predicciones_lista else {}

        # Enriquecer con MAPE ex-post real y fecha_generacion desde BD
        if predicciones_lista:
            try:
                from infrastructure.database.manager import db_manager as _db_mgr
                df_qual = _db_mgr.query_df("""
                    SELECT DISTINCT ON (fuente)
                           fuente, mape_expost, mape_train,
                           fecha_evaluacion::date AS fecha_eval
                    FROM predictions_quality_history
                    WHERE mape_expost IS NOT NULL
                      AND mape_expost < 1.0
                    ORDER BY fuente, fecha_evaluacion DESC
                """)
                if not df_qual.empty:
                    qual_map = df_qual.set_index('fuente').to_dict('index')
                    for _item in predicciones_lista:
                        _fkey = _item.get('fuente', '')
                        if _fkey in qual_map:
                            _item['mape_expost'] = round(
                                float(qual_map[_fkey]['mape_expost']) * 100.0, 2)
                            _item['fecha_mape'] = str(qual_map[_fkey]['fecha_eval'])
                    logger.info("[RESUMEN DIARIO] MAPE ex-post enriquecido en predicciones")
            except Exception as _qe:
                logger.warning(f"[RESUMEN DIARIO] No se pudo obtener quality history: {_qe}")

            # Enriquecer con fecha de última generación del modelo
            try:
                _fuentes = [_i.get('fuente', '') for _i in predicciones_lista if _i.get('fuente')]
                if _fuentes:
                    df_gen = _db_mgr.query_df("""
                        SELECT fuente, MAX(fecha_generacion) AS ultima_gen
                        FROM predictions
                        WHERE fuente = ANY(%s)
                        GROUP BY fuente
                    """, (_fuentes,))
                    if not df_gen.empty:
                        gen_map = df_gen.set_index('fuente')['ultima_gen'].to_dict()
                        for _item in predicciones_lista:
                            _fkey = _item.get('fuente', '')
                            if _fkey in gen_map and gen_map[_fkey] is not None:
                                _item['fecha_generacion_modelo'] = (
                                    gen_map[_fkey].strftime('%d/%m/%Y %H:%M')
                                    if hasattr(gen_map[_fkey], 'strftime')
                                    else str(gen_map[_fkey])[:16]
                                )
                        logger.info("[RESUMEN DIARIO] Fecha generación modelo enriquecida")
            except Exception as _ge:
                logger.warning(f"[RESUMEN DIARIO] No se pudo obtener fecha_generacion: {_ge}")

        # Enriquecer con comparación interanual (mismo período año anterior)
        # AporEner y CapaUtilDiarEner tienen datos desde 2020; se mapean a
        # fuentes APORTES_HIDRICOS y EMBALSES_PCT respectivamente.
        _INTERANUAL_MAP = {
            'EMBALSES_PCT': {
                'metrica': 'CapaUtilDiarEner',
                'entidad': 'Sistema',    # solo total sistema, evita doble conteo con filas por embalse
                'label': 'Embalses año anterior',
                'factor': 1.0,           # mostrar en GWh (valor real, sin conversión falsa a %)
                'unidad': 'GWh',
            },
            'APORTES_HIDRICOS': {
                'metrica': 'AporEner',
                'entidad': None,         # sin filtro por entidad
                'label': 'Aportes año anterior',
                'factor': 1.0,
                'unidad': 'GWh/d',
            },
        }
        if predicciones_lista:
            try:
                from infrastructure.database.manager import db_manager as _db_mgr2
                for _item in predicciones_lista:
                    _fkey = _item.get('fuente', '')
                    if _fkey not in _INTERANUAL_MAP:
                        continue
                    _cfg = _INTERANUAL_MAP[_fkey]
                    _entidad_filter = (
                        "AND entidad = %(entidad)s" if _cfg.get('entidad') else ""
                    )
                    _df_ia = _db_mgr2.query_df(f"""
                        WITH
                        curr AS (
                            SELECT AVG(daily) AS avg_curr
                            FROM (
                                SELECT fecha, SUM(valor_gwh) AS daily
                                FROM metrics
                                WHERE metrica = %(metrica)s
                                  {_entidad_filter}
                                  AND fecha BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE
                                GROUP BY fecha
                            ) t
                        ),
                        prev AS (
                            SELECT AVG(daily) AS avg_prev
                            FROM (
                                SELECT fecha, SUM(valor_gwh) AS daily
                                FROM metrics
                                WHERE metrica = %(metrica)s
                                  {_entidad_filter}
                                  AND fecha BETWEEN CURRENT_DATE - 395 AND CURRENT_DATE - 335
                                GROUP BY fecha
                            ) t
                        )
                        SELECT curr.avg_curr, prev.avg_prev FROM curr, prev
                    """, {'metrica': _cfg['metrica'], 'entidad': _cfg.get('entidad', '')})
                    if not _df_ia.empty:
                        avg_c = _df_ia['avg_curr'].iloc[0]
                        avg_p = _df_ia['avg_prev'].iloc[0]
                        if avg_c and avg_p and float(avg_p) > 0:
                            f = _cfg['factor']
                            var_ia = (float(avg_c) - float(avg_p)) / float(avg_p) * 100.0
                            _item['variacion_interanual'] = round(var_ia, 1)
                            _item['valor_interanual_ref'] = round(float(avg_p) * f, 1)
                            _item['valor_interanual_curr'] = round(float(avg_c) * f, 1)
                            _item['unidad_interanual'] = _cfg.get('unidad', 'GWh')
                logger.info("[RESUMEN DIARIO] Comparación interanual calculada")
            except Exception as _ie:
                logger.warning(f"[RESUMEN DIARIO] No se pudo calcular interanual: {_ie}")

        # 2c. Noticias del sector
        noticias = []
        d_news = _api_call('noticias_sector', timeout=60)
        if d_news:
            noticias = d_news.get('noticias', [])
            logger.info(f"[RESUMEN DIARIO] Noticias obtenidas: {len(noticias)}")

        # 2d. Anomalías recientes - PRIORIZAR orquestador sobre BD
        # NOTA: Las anomalías del orquestador tienen mejor contexto (YoY, valor actual,
        # desviación, impacto operativo). Las de BD son fallback y se filtran para
        # excluir alertas técnicas que no interesan al usuario final.
        anomalias = []
        try:
            # OPCIÓN 1: Usar anomalías del orquestador (preferidas)
            if _contexto_datos:
                _anom_orq = _contexto_datos.get('anomalias', {})
                if isinstance(_anom_orq, dict):
                    _lista_orq = _anom_orq.get('lista', [])
                else:
                    _lista_orq = _anom_orq if isinstance(_anom_orq, list) else []
                
                if _lista_orq:
                    anomalias = _lista_orq[:5]  # Top 5
                    logger.info(
                        f"[RESUMEN DIARIO] Usando {len(anomalias)} anomalías del ORQUESTADOR "
                        f"(con YoY y contexto completo)"
                    )
            
            # OPCIÓN 2: Fallback a BD solo si orquestador no tiene anomalías
            if not anomalias:
                from infrastructure.database.manager import db_manager
                df_anom = db_manager.query_df("""
                    SELECT metrica, severidad, descripcion, valor_promedio,
                           fecha_evaluacion
                    FROM alertas_historial
                    WHERE fecha_evaluacion >= CURRENT_DATE - INTERVAL '1 day'
                    ORDER BY fecha_evaluacion DESC
                """)
                if not df_anom.empty:
                    # FILTRO: Excluir métricas técnicas (mismo filtro que orquestador)
                    _metricas_tecnicas = {
                        'TEST', 'DATOS_CONGELADOS', 'STALENESS', 'DATA_QUALITY',
                        'CONNECTION_ERROR', 'SYNC_ERROR'
                    }
                    
                    # Deduplicar por (metrica, descripcion), conservar mayor severidad
                    _sev_order = {'CRITICA': 3, 'CRITICO': 3, 'CRITICAL': 3,
                                  'ALERTA': 2, 'WARNING': 2,
                                  'NORMAL': 1, 'INFO': 0}
                    seen: dict = {}
                    for rec in df_anom.to_dict('records'):
                        _metrica = str(rec.get('metrica', '')).strip().upper()
                        
                        # Excluir métricas técnicas
                        if any(_tec in _metrica for _tec in _metricas_tecnicas):
                            continue
                        
                        key = (
                            _metrica,
                            str(rec.get('descripcion', '')).strip().upper(),
                        )
                        prev = seen.get(key)
                        if prev is None:
                            seen[key] = rec
                        else:
                            prev_rank = _sev_order.get(
                                str(prev.get('severidad', '')).upper(), 1)
                            cur_rank = _sev_order.get(
                                str(rec.get('severidad', '')).upper(), 1)
                            if cur_rank > prev_rank:
                                seen[key] = rec
                    
                    # Ordenar por severidad desc y tomar top 5
                    deduped = sorted(
                        seen.values(),
                        key=lambda r: _sev_order.get(
                            str(r.get('severidad', '')).upper(), 1),
                        reverse=True,
                    )[:5]
                    
                    # Quitar columna auxiliar antes de pasar a downstream
                    for r in deduped:
                        r.pop('fecha_evaluacion', None)
                    
                    anomalias = deduped
                    _excluidas = len(df_anom) - len([r for r in df_anom.to_dict('records') 
                                                     if not any(_tec in str(r.get('metrica', '')).upper() 
                                                                for _tec in _metricas_tecnicas)])
                    logger.info(
                        f"[RESUMEN DIARIO] Anomalías de BD (filtradas): "
                        f"{len(df_anom)} raw → {len(anomalias)} válidas ({_excluidas} técnicas excluidas)"
                    )
        except Exception as e:
            logger.warning(f"[RESUMEN DIARIO] Error leyendo anomalías: {e}")

        # ══════════════════════════════════════════════
        # 3. Generar gráficos PNG (sector)
        # ══════════════════════════════════════════════
        chart_paths = []
        try:
            from whatsapp_bot.services.informe_charts import generate_all_informe_charts
            charts = generate_all_informe_charts()
            for key in ('generacion', 'embalses', 'precios', 'demanda', 'precio_multi', 'aportes_hidricos',
                        'despacho_termica', 'capacidad_embalse', 'aportes_demanda'):
                path = charts.get(key, (None,))[0]
                if path and os.path.isfile(path):
                    chart_paths.append(path)
            logger.info(f"[RESUMEN DIARIO] Gráficos sector: {len(chart_paths)}")
        except Exception as e:
            logger.warning(f"[RESUMEN DIARIO] Error generando gráficos sector: {e}")

        # ══════════════════════════════════════════════
        # 4. Generar PDF (narrativa + gráficos)
        # ══════════════════════════════════════════════
        pdf_path = None
        try:
            pdf_path = generar_pdf_informe(
                informe_texto, fecha_generacion, generado_con_ia,
                chart_paths=chart_paths,
                fichas=fichas,
                predicciones=predicciones_lista or predicciones_data,
                anomalias=anomalias,
                noticias=noticias,
                contexto_datos=_contexto_datos,
            )
            if pdf_path:
                size_kb = os.path.getsize(pdf_path) / 1024
                logger.info(f"[RESUMEN DIARIO] PDF generado: {pdf_path} ({size_kb:.1f} KB)")
        except Exception as e:
            logger.warning(f"[RESUMEN DIARIO] Error generando PDF: {e}")

        # ══════════════════════════════════════════════
        # 5. Construir mensaje Telegram (KPIs + resumen compacto)
        # El análisis completo va SOLO en el PDF adjunto.
        # ══════════════════════════════════════════════
        tg_message = (
            f"📊 *INFORME EJECUTIVO DIARIO DEL SIN*\n"
            f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"{'─' * 30}\n\n"
        )

        # ── KPIs principales ──
        if fichas:
            for f in fichas[:3]:
                emoji = f.get('emoji', '⚡')
                ind = f.get('indicador', '')
                val = f.get('valor', '')
                uni = f.get('unidad', '')
                ctx = f.get('contexto', {})
                var_pct = ctx.get('variacion_vs_promedio_pct', '')
                etiqueta_var = ctx.get('etiqueta_variacion', 'vs 7d')
                tg_message += f"{emoji} *{ind}:* {val} {uni}"
                if isinstance(var_pct, (int, float)):
                    tg_message += f" ({var_pct:+.1f}% {etiqueta_var})"
                tg_message += "\n"

                # Detalle embalses: media histórica
                if 'embalse' in ind.lower():
                    media_h = ctx.get('media_historica_2020_2025')
                    desv_h = ctx.get('desviacion_pct_media_historica_2020_2025')
                    if media_h is not None and desv_h is not None:
                        dir_txt = "por encima" if desv_h >= 0 else "por debajo"
                        tg_message += (
                            f"   📊 Media 2020-2025: {media_h:.1f}% → "
                            f"*{abs(desv_h):.1f}% {dir_txt}*\n"
                        )
            tg_message += "\n"

        # ── Predicciones compactas (del contexto) ──
        _pred_mes = (_contexto_datos or {}).get('predicciones_mes', {})
        _metricas = _pred_mes.get('metricas_clave', {})
        if _metricas:
            tg_message += "📈 *Proyecciones próximo mes:*\n"
            for clave in ['generacion', 'precio_bolsa', 'embalses']:
                m = _metricas.get(clave, {})
                if m:
                    emoji_m = m.get('emoji', '▸')
                    nom = m.get('indicador', clave)
                    prom = m.get('promedio_periodo', '')
                    uni_m = m.get('unidad', '')
                    tend = m.get('tendencia', '')
                    tg_message += f"  {emoji_m} {nom}: {prom} {uni_m} {tend}\n"
            tg_message += "\n"

        # ── Anomalías (si hay) ──
        if anomalias:
            tg_message += f"⚠️ *Anomalías detectadas ({len(anomalias)}):*\n"
            for a in anomalias[:5]:
                sev = a.get('severidad', 'ALERTA')
                met = a.get('metrica') or a.get('indicador', '')
                desc_short = a.get('descripcion', '')[:80]
                tg_message += f"  {'🔴' if 'CRIT' in sev.upper() else '🟡'} {met}: {desc_short}\n"
            tg_message += "\n"

        # ── Noticias (solo títulos) ──
        if noticias:
            tg_message += "📰 *Noticias del Sector:*\n"
            for i, n in enumerate(noticias[:3], 1):
                titulo = n.get('titulo', '')
                fuente = n.get('fuente', '')
                tg_message += f"  {i}. {titulo}"
                if fuente:
                    tg_message += f" ({fuente})"
                tg_message += "\n"
            tg_message += "\n"

        # ── Cierre ──
        tg_message += (
            "📎 *El análisis completo con gráficas y predicciones "
            "se encuentra en el PDF adjunto.*\n\n"
            "Portal Energético — Ministerio de Minas y Energía"
        )

        # ══════════════════════════════════════════════
        # 6. Construir email HTML, Telegram y persistir artefactos
        # ══════════════════════════════════════════════
        email_html = build_daily_email_html(
            informe_texto,
            noticias=noticias,
            fichas=fichas,
            predicciones=predicciones_lista or predicciones_data or None,
            anomalias=anomalias,
            generado_con_ia=generado_con_ia,
            indices_compuestos=_contexto_datos.get('indices_compuestos') if _contexto_datos else None,
        )

        email_subject = (
            f"📊 Informe Ejecutivo del Sector Eléctrico — "
            f"{datetime.now().strftime('%Y-%m-%d')}"
        )

        tg_result = broadcast_telegram(
            message=tg_message,
            pdf_path=pdf_path,
            parse_mode=None,
        )

        date_str = today.isoformat()
        informes_dir = _informes_dir()
        os.makedirs(informes_dir, exist_ok=True)
        persisted_pdf = os.path.join(
            informes_dir, f"Informe_Ejecutivo_MME_{date_str}.pdf"
        )
        persisted_html = os.path.join(
            informes_dir, f"Informe_Ejecutivo_MME_{date_str}.html"
        )

        if pdf_path and os.path.isfile(pdf_path):
            import shutil
            shutil.copy2(pdf_path, persisted_pdf)
            logger.info("[RESUMEN DIARIO] PDF persistido: %s", persisted_pdf)
        else:
            persisted_pdf = None
            logger.warning("[RESUMEN DIARIO] PDF no disponible para persistir")

        with open(persisted_html, 'w', encoding='utf-8') as html_file:
            html_file.write(email_html)
        logger.info("[RESUMEN DIARIO] HTML persistido: %s", persisted_html)

        _mark_daily_generation_done(today)

        fanout_result = None
        if persisted_pdf and os.path.isfile(persisted_pdf):
            fanout_result = send_daily_emails_fanout.delay(
                date_str, email_subject, persisted_html, persisted_pdf
            )
            logger.info(
                "[RESUMEN DIARIO] Fanout de emails encolado: task_id=%s",
                fanout_result.id if fanout_result else None,
            )
        else:
            logger.error(
                "[RESUMEN DIARIO] No se encoló fanout de emails: PDF persistido ausente"
            )

        logger.info(
            "📤 [RESUMEN DIARIO] Generación completada: Telegram=%s, "
            "emails encolados=%s",
            tg_result.get("sent", 0),
            "sí" if fanout_result else "no",
        )

        # Limpiar archivos temporales
        if pdf_path and os.path.isfile(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        for cp in chart_paths:
            try:
                if cp and os.path.isfile(cp):
                    os.remove(cp)
            except OSError:
                pass

        return {
            "status": "completed",
            "informe_ia": generado_con_ia,
            "telegram_sent": tg_result.get("sent", 0),
            "email_fanout_task_id": fanout_result.id if fanout_result else None,
            "pdf_path": persisted_pdf,
            "html_path": persisted_html,
        }

    except Exception as e:
        logger.error(
            f"❌ [RESUMEN DIARIO] Error: {str(e)}", exc_info=True
        )
        return {"status": "error", "error": str(e)}


@shared_task(name='tasks.anomaly_tasks.send_daily_summary')
def send_daily_summary():
    """Alias deprecated — delega a send_daily_generate."""
    logger.warning(
        "[RESUMEN DIARIO] send_daily_summary está deprecated; "
        "use send_daily_generate"
    )
    return send_daily_generate()


@shared_task(name='tasks.anomaly_tasks.email_batch_complete')
def email_batch_complete(results: list, date_str: str) -> dict:
    """Callback del chord: resume envíos de email del informe diario."""
    sent = 0
    failed = 0
    skipped = 0
    failed_recipients: list[str] = []

    for item in results or []:
        if isinstance(item, Exception):
            failed += 1
            failed_recipients.append("unknown")
            continue
        if not isinstance(item, dict):
            failed += 1
            continue
        status = item.get("status")
        dest = item.get("dest", "unknown")
        if status == "sent":
            sent += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
            failed_recipients.append(dest)

    summary = {
        "date": date_str,
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "failed_recipients": failed_recipients,
    }
    logger.info("[EMAIL] %s", json.dumps({
        "event": "daily_batch_complete",
        **summary,
    }, ensure_ascii=False))

    if failed > 0:
        logger.warning(
            "[RESUMEN DIARIO] %s email(s) fallidos para %s: %s",
            failed,
            date_str,
            ", ".join(failed_recipients),
        )

    return summary


@shared_task(
    name='tasks.anomaly_tasks.send_single_daily_email',
    bind=True,
    time_limit=90,
    soft_time_limit=60,
    max_retries=2,
    default_retry_delay=120,
)
def send_single_daily_email(
    self,
    dest: str,
    subject: str,
    html_path: str,
    pdf_path: str,
    date_str: str,
) -> dict:
    """Envía el informe diario a un único destinatario."""
    from domain.services.notification_service import _send_one_email

    day = date.fromisoformat(date_str)

    if _is_daily_email_sent(day, dest):
        logger.info("[RESUMEN DIARIO] Email ya enviado hoy a %s — omitido", dest)
        return {"status": "skipped", "dest": dest, "reason": "already_sent_today"}

    if not os.path.isfile(html_path):
        err = f"HTML no encontrado: {html_path}"
        logger.error("[RESUMEN DIARIO] %s", err)
        return {"status": "failed", "dest": dest, "error": err}

    if not os.path.isfile(pdf_path):
        err = f"PDF no encontrado: {pdf_path}"
        logger.error("[RESUMEN DIARIO] %s", err)
        return {"status": "failed", "dest": dest, "error": err}

    try:
        with open(html_path, encoding='utf-8') as html_file:
            body_html = html_file.read()
    except OSError as e:
        err = f"No se pudo leer HTML: {e}"
        logger.error("[RESUMEN DIARIO] %s", err)
        return {"status": "failed", "dest": dest, "error": err}

    ok, error, duration_ms = _send_one_email(dest, subject, body_html, pdf_path)
    if ok:
        _mark_daily_email_sent(day, dest)
        return {
            "status": "sent",
            "dest": dest,
            "duration_ms": duration_ms,
        }

    try:
        raise self.retry(exc=RuntimeError(error or "smtp_send_failed"))
    except self.MaxRetriesExceededError:
        return {
            "status": "failed",
            "dest": dest,
            "error": error,
            "duration_ms": duration_ms,
        }


@shared_task(name='tasks.anomaly_tasks.send_daily_emails_fanout')
def send_daily_emails_fanout(
    date_str: str,
    subject: str,
    html_path: str,
    pdf_path: str,
) -> dict:
    """Encola envío paralelo de emails del informe diario (una subtarea por destinatario)."""
    from domain.services.notification_service import get_email_recipients

    recipients = get_email_recipients(diario=True)
    if not recipients:
        logger.info("[RESUMEN DIARIO] No hay destinatarios de email diario")
        return {"status": "no_recipients", "date": date_str}

    emails = [r['correo'] for r in recipients]
    logger.info(
        "[RESUMEN DIARIO] Encolando %s emails para %s",
        len(emails),
        date_str,
    )

    header = group(
        send_single_daily_email.s(dest, subject, html_path, pdf_path, date_str)
        for dest in emails
    )
    workflow = chord(header, email_batch_complete.s(date_str)).apply_async()
    return {
        "status": "fanout_enqueued",
        "date": date_str,
        "recipients": len(emails),
        "chord_id": workflow.id if workflow else None,
    }


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
        df_precio = metrics_service.get_metric_data('PrecBolsNaci', start, end)  # type: ignore[attr-defined]
        if not df_precio.empty:
            col = 'valor' if 'valor' in df_precio.columns else df_precio.columns[-1]
            precio = f"{round(df_precio[col].mean(), 2)} COP/kWh"
    except Exception:
        pass

    embalses = 'N/D'
    try:
        emb_data = hydro_service.get_hydrology_summary(start, end)  # type: ignore[attr-defined]
        if emb_data and 'porcentaje_embalses' in emb_data:
            embalses = f"{round(emb_data['porcentaje_embalses'], 1)}%"
    except Exception:
        pass

    mix_frase = "no se pudo obtener el detalle de la matriz de generación por fuente"
    try:
        df_fuentes = gen_service.get_generation_by_sources(start, end)  # type: ignore[attr-defined]
        if not df_fuentes.empty:
            total = df_fuentes['valor_gwh'].sum()
            if total > 0:
                mix = df_fuentes.groupby('recurso')['valor_gwh'].sum().sort_values(ascending=False)
                partes = [f"{recurso.lower()} con {round((valor / total) * 100, 1)}%" for recurso, valor in mix.items()]
                if len(partes) == 1:
                    mix_frase = f"la matriz de generación estuvo liderada por {partes[0]}"
                else:
                    mix_frase = (
                        "la matriz de generación estuvo liderada por "
                        + partes[0] + ", seguida de " + ", ".join(partes[1:-1] + [f"y {partes[-1]}"] if len(partes) > 2 else [partes[-1]])
                    )
    except Exception:
        pass

    # Fase 39 (2026-08-25): reescrito como prosa en vez de una lista de KPIs
    # cruda estilo "⚡ Generación: X" — hallazgo real del usuario ("parecen
    # simples consultas a la base de datos sin una forma real"), causado
    # porque este texto de respaldo (usado cuando la IA no responde) nunca
    # tuvo redacción narrativa, a diferencia del informe generado con IA que
    # sí reemplaza. Los datos/cálculos no cambian, solo cómo se presentan.
    return (
        "⚠️ Resumen automático (sin análisis de IA disponible en este momento):\n\n"
        f"En las últimas 24 horas el sistema generó un total de {gen_total}, "
        f"con un precio promedio de bolsa de {precio}. "
        f"Los embalses se encuentran al {embalses} de su capacidad. "
        f"En cuanto a la generación por fuente, {mix_frase}."
    )
