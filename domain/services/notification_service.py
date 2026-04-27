"""
Servicio unificado de notificaciones.

Gestiona el envío de mensajes a través de dos canales:
  1. Telegram broadcast (a todos los usuarios registrados en PostgreSQL)
  2. Email (a destinatarios de la tabla alert_recipients)

Usado por:
  - Celery tasks (check_anomalies, send_daily_summary)
  - Endpoint /api/broadcast-alert (bot uvicorn)
"""

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
from typing import Optional, List, Dict, Any

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from core.constants import MODEL_DISPLAY_NAMES, MAPE_THRESHOLDS, mape_quality, ANOMALY_SEVERITY_EMOJIS, ANOMALY_SEVERITY_COLORS, METRIC_ICONS_HTML

# Cargar .env para que os.getenv() encuentre SMTP y otras vars
# (en producción las vars vienen del EnvironmentFile de systemd; en terminal/tests
# necesitan cargarse explícitamente desde el archivo .env)
load_dotenv()

logger = logging.getLogger(__name__)


# ─────────────────── Configuración ───────────────────

def _pg_params() -> dict:
    """Obtiene parámetros de conexión PostgreSQL."""
    _SP = (
        "sector_energetico,subsidios,supervision,"
        "comunidades,presupuesto,contratos_or,public"
    )
    try:
        from core.config import settings
        params = {
            'host': settings.POSTGRES_HOST,
            'port': settings.POSTGRES_PORT,
            'database': settings.POSTGRES_DB,
            'user': settings.POSTGRES_USER,
            'options': f'-c search_path={_SP}',
        }
        if settings.POSTGRES_PASSWORD:
            params['password'] = settings.POSTGRES_PASSWORD
        return params
    except Exception as e:
        logger.warning("Error leyendo config DB para notificaciones: %s", e)
        # Fallback directo
        return {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'portal_energetico'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', ''),
            'options': f'-c search_path={_SP}',
        }


def _get_telegram_token() -> str:
    """Obtiene el token del bot de Telegram."""
    # 1. Variable de entorno directa
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    if token:
        return token
    # 2. Intentar leer del .env del bot
    # __file__ = .../server/domain/services/notification_service.py
    # Se necesitan 3 niveles de dirname para llegar a .../server/
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'whatsapp_bot', '.env'
    )
    try:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith('TELEGRAM_BOT_TOKEN='):
                        return line.strip().split('=', 1)[1].strip()
    except Exception as e:
        logger.debug("Error leyendo token Telegram del .env: %s", e)
    return ''

# ─────────────────── Telegram ───────────────────

def get_telegram_users() -> List[Dict[str, Any]]:
    """Devuelve usuarios activos de la tabla telegram_users."""
    try:
        conn = psycopg2.connect(**_pg_params())
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT chat_id, username, nombre FROM telegram_users WHERE activo = TRUE"
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error leyendo telegram_users: {e}")
        return []


def broadcast_telegram(
    message: str,
    pdf_path: Optional[str] = None,
    parse_mode: Optional[str] = None,
) -> Dict[str, int]:
    """
    Envía un mensaje (y opcionalmente un PDF) a todos los usuarios
    de Telegram registrados en PostgreSQL.

    Retorna {"sent": N, "failed": M}.
    """
    token = _get_telegram_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN no configurado — broadcast cancelado")
        return {"sent": 0, "failed": 0}

    users = get_telegram_users()
    if not users:
        logger.warning("No hay usuarios de Telegram para broadcast")
        return {"sent": 0, "failed": 0}

    sent = 0
    failed = 0
    base = f"https://api.telegram.org/bot{token}"

    with httpx.Client(timeout=15.0) as client:
        for u in users:
            chat_id = u['chat_id']
            try:
                # Enviar texto (con fallback si Markdown falla)
                resp = client.post(
                    f"{base}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                    },
                )
                if resp.status_code != 200:
                    # Log detallado del error
                    try:
                        err_body = resp.json().get('description', resp.text[:200])
                    except Exception as e:
                        err_body = resp.text[:200]
                    logger.warning(
                        f"Telegram sendMessage {chat_id}: {resp.status_code} → {err_body}"
                    )
                    # Fallback: reintentar sin parse_mode (texto plano)
                    resp2 = client.post(
                        f"{base}/sendMessage",
                        json={"chat_id": chat_id, "text": message},
                    )
                    if resp2.status_code != 200:
                        logger.warning(
                            f"Telegram sendMessage {chat_id} (plain): {resp2.status_code}"
                        )
                        failed += 1
                        continue
                    logger.info(f"Telegram {chat_id}: enviado como texto plano (fallback)")

                # Enviar PDF si existe
                if pdf_path and os.path.isfile(pdf_path):
                    with open(pdf_path, 'rb') as f:
                        resp_doc = client.post(
                            f"{base}/sendDocument",
                            data={
                                "chat_id": str(chat_id),
                                "caption": "📎 Informe Ejecutivo del Sector Eléctrico",
                            },
                            files={"document": (os.path.basename(pdf_path), f, "application/pdf")},
                        )
                        if resp_doc.status_code != 200:
                            logger.warning(
                                f"Telegram sendDocument {chat_id}: "
                                f"{resp_doc.status_code}"
                            )

                sent += 1
            except Exception as e:
                failed += 1
                logger.error(f"Error broadcast Telegram {chat_id}: {e}")

    logger.info(
        f"📤 Telegram broadcast: {sent} enviados, {failed} fallidos "
        f"(PDF: {'sí' if pdf_path else 'no'})"
    )
    return {"sent": sent, "failed": failed}


# ─────────────────── Email ───────────────────

def _smtp_config():
    """Lee configuración SMTP de env vars (cada vez que se invoca)."""
    return {
        'server': os.getenv('SMTP_SERVER', 'smtp.office365.com'),
        'port': int(os.getenv('SMTP_PORT', 587)),
        'user': os.getenv('SMTP_USER', ''),
        'password': os.getenv('SMTP_PASSWORD', ''),
        'from_name': os.getenv('EMAIL_FROM_NAME', 'Portal Energético MME'),
    }


def get_email_recipients(
    alertas: bool = False,
    diario: bool = False,
) -> List[Dict[str, Any]]:
    """
    Devuelve destinatarios de email activos de la tabla alert_recipients.

    Args:
        alertas: Si True, filtra quienes reciben alertas de anomalías.
        diario: Si True, filtra quienes reciben el informe diario.
    """
    try:
        conn = psycopg2.connect(**_pg_params())
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        conditions = ["activo = TRUE", "canal_email = TRUE"]
        if alertas:
            conditions.append("recibir_alertas = TRUE")
        if diario:
            conditions.append("recibir_diario = TRUE")

        cur.execute(
            f"SELECT nombre, correo, rol FROM alert_recipients "
            f"WHERE {' AND '.join(conditions)}"
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Error leyendo alert_recipients: {e}")
        return []


def send_email(
    to_list: List[str],
    subject: str,
    body_html: str,
    pdf_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envía un email HTML (opcionalmente con PDF adjunto) a una lista de direcciones.

    Retorna {"sent": N, "failed": M}.
    """
    cfg = _smtp_config()
    if not cfg['user'] or not cfg['password']:
        logger.warning(
            "SMTP_USER / SMTP_PASSWORD no configurados — email no enviado. "
            f"SMTP_USER='{cfg['user']}', SMTP_SERVER='{cfg['server']}'. "
            "Configure las variables de entorno para habilitar emails."
        )
        return {"sent": 0, "failed": 0, "reason": "smtp_not_configured"}

    sent = 0
    failed = 0

    for dest in to_list:
        try:
            msg = MIMEMultipart()
            msg['From'] = f"{cfg['from_name']} <{cfg['user']}>"
            msg['To'] = dest
            msg['Subject'] = subject
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))

            # Adjuntar PDF si existe
            if pdf_path and os.path.isfile(pdf_path):
                with open(pdf_path, 'rb') as f:
                    part = MIMEApplication(f.read(), _subtype='pdf')
                    part.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=os.path.basename(pdf_path),
                    )
                    msg.attach(part)

            # Enviar
            context = ssl.create_default_context()
            with smtplib.SMTP(cfg['server'], cfg['port']) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(cfg['user'], cfg['password'])
                server.sendmail(cfg['user'], dest, msg.as_string())

            sent += 1
            logger.info(f"✅ Email enviado a {dest}")
        except Exception as e:
            failed += 1
            logger.error(f"❌ Error enviando email a {dest}: {e}")

    logger.info(f"📧 Email broadcast: {sent} enviados, {failed} fallidos")
    return {"sent": sent, "failed": failed}


def broadcast_email_alert(
    subject: str,
    body_html: str,
    pdf_path: Optional[str] = None,
    alertas: bool = False,
    diario: bool = False,
) -> Dict[str, int]:
    """
    Envía un email a los destinatarios configurados en alert_recipients.
    Filtra por tipo: alertas (anomalías) o diario (informe ejecutivo).
    """
    recipients = get_email_recipients(alertas=alertas, diario=diario)
    if not recipients:
        logger.info("No hay destinatarios de email para este tipo de notificación")
        return {"sent": 0, "failed": 0}

    emails = [r['correo'] for r in recipients]
    logger.info(
        f"📧 Enviando a {len(emails)} destinatarios "
        f"(alertas={alertas}, diario={diario})"
    )
    return send_email(emails, subject, body_html, pdf_path)


# ─────────────────── Persistencia Telegram ───────────────────

def persist_telegram_user(
    chat_id: int,
    username: Optional[str] = None,
    nombre: Optional[str] = None,
) -> bool:
    """
    Upsert de un usuario de Telegram en PostgreSQL.
    Llamado desde track_telegram_user() en telegram_polling.py.
    """
    try:
        conn = psycopg2.connect(**_pg_params())
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO telegram_users (chat_id, username, nombre, ultima_interaccion)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (chat_id) DO UPDATE SET
                username   = COALESCE(EXCLUDED.username, telegram_users.username),
                nombre     = COALESCE(EXCLUDED.nombre, telegram_users.nombre),
                ultima_interaccion = NOW()
            """,
            (chat_id, username, nombre),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error persistiendo telegram_user {chat_id}: {e}")
        return False


# ─────────────────── Orquestador de alto nivel ───────────────────

def broadcast_alert(
    message: str,
    severity: str = "INFO",
    pdf_path: Optional[str] = None,
    email_subject: Optional[str] = None,
    email_body_html: Optional[str] = None,
    is_daily: bool = False,
) -> Dict[str, Any]:
    """
    Punto de entrada principal para enviar notificaciones por todos los canales.

    Args:
        message: Texto Markdown para Telegram.
        severity: CRITICAL / ALERT / WARNING / INFO.
        pdf_path: Ruta a PDF adjunto (opcional).
        email_subject: Asunto del email (si omitido, se genera automáticamente).
        email_body_html: Cuerpo HTML del email (si omitido, se genera del message).
        is_daily: True para informe diario, False para alertas.

    Returns:
        Resumen de envíos por canal.
    """
    result = {
        "timestamp": datetime.now().isoformat(),
        "severity": severity,
        "telegram": {"sent": 0, "failed": 0},
        "email": {"sent": 0, "failed": 0},
    }

    # ── Telegram ──
    try:
        tg = broadcast_telegram(message, pdf_path=pdf_path)
        result["telegram"] = tg
    except Exception as e:
        logger.error(f"Error en broadcast Telegram: {e}")

    # ── Email ──
    try:
        subj = email_subject or (
            f"⚡ Informe Ejecutivo Diario — {datetime.now().strftime('%Y-%m-%d')}"
            if is_daily
            else f"⚠️ Alerta Energética [{severity}] — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        html = email_body_html or _plain_to_html(message)

        em = broadcast_email_alert(
            subject=subj,
            body_html=html,
            pdf_path=pdf_path,
            alertas=not is_daily,
            diario=is_daily,
        )
        result["email"] = em
    except Exception as e:
        logger.error(f"Error en broadcast email: {e}")

    total_sent = result["telegram"]["sent"] + result["email"]["sent"]
    logger.info(
        f"📣 Broadcast completo: {total_sent} notificaciones enviadas "
        f"(TG={result['telegram']['sent']}, Email={result['email']['sent']})"
    )
    return result


# ─────────────────── Helpers ───────────────────

def _plain_to_html(text: str) -> str:
    """Convierte texto plano/Markdown sencillo a HTML para emails."""
    import re as _re

    html = text
    # Bold **text** → <b>text</b>
    html = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
    # Bold *text* → <b>text</b>  (Telegram Markdown uses single *)
    html = _re.sub(r'\*(.+?)\*', r'<b>\1</b>', html)
    # _italic_ → <i>italic</i>
    html = _re.sub(r'_(.+?)_', r'<i>\1</i>', html)
    # Line breaks
    html = html.replace('\n', '<br>\n')

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: auto;
                padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <div style="background: #1a237e; color: white; padding: 15px 20px;
                    border-radius: 6px 6px 0 0; text-align: center;">
            <h2 style="margin:0;">Portal Energético MME</h2>
            <p style="margin:4px 0 0; font-size:13px;">
                Ministerio de Minas y Energía — República de Colombia
            </p>
        </div>
        <div style="padding: 20px; line-height: 1.6;">
            {html}
        </div>
        <div style="border-top: 1px solid #e0e0e0; padding: 10px 20px;
                    font-size: 11px; color: #888; text-align: center;">
            Sistema automatizado de notificaciones del Portal Energético.
            Este correo se generó el {datetime.now().strftime('%Y-%m-%d %H:%M')}.
        </div>
    </div>
    """


def _parse_informe_sections(informe_texto: str) -> dict:
    """
    Parsea el texto Markdown del informe ejecutivo y extrae secciones
    estructuradas: KPIs, predicciones, riesgos, recomendaciones.
    """
    import re as _re

    result = {
        'kpis': [],
        'predicciones_1m': [],
        'predicciones_6m': [],
        'riesgos': [],
        'recomendaciones': [],
        'nota': '',
    }

    lines = informe_texto.strip().split('\n')
    current_section = ''
    current_pred = ''

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect sections
        if '1. Situación actual' in stripped or 'Situación actual' in stripped:
            current_section = 'kpis'
            continue
        if '2. Tendencias' in stripped or 'proyecciones' in stripped.lower():
            current_section = 'predicciones'
            continue
        if '3. Riesgos' in stripped or 'oportunidades' in stripped.lower():
            current_section = 'riesgos'
            continue
        if '4. Recomendaciones' in stripped or 'técnicas' in stripped.lower():
            current_section = 'recomendaciones'
            continue

        # Sub-section for predictions
        if 'Próximo mes' in stripped:
            current_pred = '1m'
            continue
        if 'Próximos 6 meses' in stripped or '6 meses' in stripped:
            current_pred = '6m'
            continue

        # Parse KPIs: lines like "⚡ Generación Total: *247.41 GWh* (2026-02-13)"
        if current_section == 'kpis':
            # Skip variation lines — we handle them separately below
            if 'Variación' in stripped or 'variación' in stripped:
                var_match = _re.search(r'Variaci[oó]n\s+vs\s+\S+:\s*([-\d.]+%)', stripped)
                if var_match and result['kpis']:
                    result['kpis'][-1]['variacion'] = var_match.group(1)
                continue

            kpi_match = _re.match(
                r'^\s*(.+?):\s*\*?([\d.,]+\s*[A-Za-z/%]+(?:/[A-Za-z]+)*)\*?\s*(?:\(([^)]+)\))?',
                stripped
            )
            if kpi_match:
                label = kpi_match.group(1).strip()
                value = kpi_match.group(2).strip().rstrip('*')
                date_str = kpi_match.group(3) or ''
                # Remove emojis from label for clean display
                label_clean = _re.sub(r'[^\w\s./%-áéíóúñÁÉÍÓÚÑ]', '', label).strip()
                # Determine icon
                icon = '⚡'
                if 'Precio' in label or 'precio' in label:
                    icon = '💰'
                elif 'Embalse' in label or 'embalse' in label:
                    icon = '💧'
                elif 'Demanda' in label or 'demanda' in label:
                    icon = '📊'

                result['kpis'].append({
                    'icon': icon,
                    'label': label_clean,
                    'value': value,
                    'date': date_str,
                })

        # Parse predictions
        if current_section == 'predicciones':
            pred_match = _re.match(
                r'^\s*(.+?):\s*([\d.,]+\s*\S+)\s*\(.*?cambio:\s*([-\d.]+%)\)\s*(.*)',
                stripped
            )
            if pred_match:
                label = pred_match.group(1).strip()
                label_clean = _re.sub(r'[^\w\s./%-áéíóúñÁÉÍÓÚÑ]', '', label).strip()
                value = pred_match.group(2).strip()
                cambio = pred_match.group(3).strip()
                tendencia_raw = pred_match.group(4).strip()
                tendencia = 'Estable'
                if 'Creciente' in tendencia_raw:
                    tendencia = 'Creciente'
                elif 'Decreciente' in tendencia_raw:
                    tendencia = 'Decreciente'

                icon = '⚡'
                if 'Precio' in label or 'precio' in label:
                    icon = '💰'
                elif 'Embalse' in label or 'embalse' in label:
                    icon = '💧'

                entry = {
                    'icon': icon,
                    'label': label_clean,
                    'value': value,
                    'cambio': cambio,
                    'tendencia': tendencia,
                }
                if current_pred == '6m':
                    result['predicciones_6m'].append(entry)
                else:
                    result['predicciones_1m'].append(entry)

        # Parse risks
        if current_section == 'riesgos':
            risk_match = _re.match(r'^\s*(.+?):\s*(.+)', stripped)
            if risk_match:
                label = risk_match.group(1).strip()
                label_clean = _re.sub(r'[^\w\s./%-áéíóúñÁÉÍÓÚÑ]', '', label).strip()
                desc = risk_match.group(2).strip()
                severity = 'warning'
                if 'alerta' in desc.lower() or 'ALERTA' in stripped:
                    severity = 'alert'
                if 'crítico' in desc.lower() or 'CRÍTICO' in stripped:
                    severity = 'critical'
                result['riesgos'].append({
                    'label': label_clean,
                    'desc': desc,
                    'severity': severity,
                })

        # Parse recommendations
        if current_section == 'recomendaciones':
            rec_match = _re.match(r'^\s*[•\-]\s*(.+)', stripped)
            if rec_match:
                result['recomendaciones'].append(rec_match.group(1).strip())

        # Note/fallback
        if 'sin IA' in stripped or 'fallback' in stripped.lower():
            result['nota'] = _re.sub(r'[_*]', '', stripped).strip()

    return result


def _markdown_to_email_html(md_text: str) -> str:
    """Convierte markdown simplificado del informe IA a HTML inline para email."""
    import re as _re2

    if not md_text:
        return ''

    lines = md_text.strip().split('\n')
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append('<br>')
            continue

        # Headers
        h3 = _re2.match(r'^###\s+(.+)', stripped)
        h2 = _re2.match(r'^##\s+(.+)', stripped)
        h1 = _re2.match(r'^#\s+(.+)', stripped)
        if h1:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(
                '<div style="font-size:16px;font-weight:700;color:#0D1B4A;'
                'margin:14px 0 6px;border-bottom:1px solid #e0e0e0;padding-bottom:4px;">'
                + _inline_md(h1.group(1)) + '</div>'
            )
            continue
        if h2:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(
                '<div style="font-size:14px;font-weight:700;color:#1A3A7A;'
                'margin:12px 0 4px;">'
                + _inline_md(h2.group(1)) + '</div>'
            )
            continue
        if h3:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(
                '<div style="font-size:13px;font-weight:600;color:#333;'
                'margin:10px 0 4px;">'
                + _inline_md(h3.group(1)) + '</div>'
            )
            continue

        # List items
        li = _re2.match(r'^[\-\*•]\s+(.+)', stripped)
        if li:
            if not in_list:
                html_parts.append(
                    '<ul style="margin:4px 0;padding-left:20px;'
                    'font-size:13px;color:#444;line-height:1.6;">'
                )
                in_list = True
            html_parts.append('<li>' + _inline_md(li.group(1)) + '</li>')
            continue

        # Numbered lists
        nli = _re2.match(r'^\d+[\.\)]\s+(.+)', stripped)
        if nli:
            if not in_list:
                html_parts.append(
                    '<ul style="margin:4px 0;padding-left:20px;'
                    'font-size:13px;color:#444;line-height:1.6;">'
                )
                in_list = True
            html_parts.append('<li>' + _inline_md(nli.group(1)) + '</li>')
            continue

        # Regular paragraph
        if in_list:
            html_parts.append('</ul>')
            in_list = False
        html_parts.append(
            '<p style="margin:4px 0;font-size:13px;color:#444;line-height:1.6;">'
            + _inline_md(stripped) + '</p>'
        )

    if in_list:
        html_parts.append('</ul>')

    return '\n'.join(html_parts)


def _inline_md(text: str) -> str:
    """Aplica formato inline markdown (bold, italic) a texto."""
    import re as _re3
    # Bold: **text** or __text__
    text = _re3.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = _re3.sub(r'__(.+?)__', r'<b>\1</b>', text)
    # Italic: *text* or _text_
    text = _re3.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    # Inline code
    text = _re3.sub(r'`(.+?)`', r'<code style="background:#f5f5f5;padding:1px 4px;border-radius:3px;font-size:12px;">\1</code>', text)
    return text


def build_daily_email_html(
    informe_texto: str,
    noticias: list | None = None,
    fichas: list | None = None,
    predicciones: dict | None = None,
    anomalias: list | None = None,
    generado_con_ia: bool = True,
    indices_compuestos: dict | None = None,
) -> str:
    """
    Construye HTML premium del email diario combinando:
      - Datos estructurados reales (KPIs, predicciones, anomalías)
      - Texto narrativo de IA (análisis ejecutivo)
      - Noticias del sector

    Plantilla corporativa moderna con tarjetas KPI, tabla de predicciones,
    semáforos de riesgo y diseño responsivo compatible con Outlook.
    """
    fecha = datetime.now().strftime('%Y-%m-%d')
    hora = datetime.now().strftime('%H:%M')

    # ── Construir tarjetas KPI desde datos estructurados ──
    kpi_cards = ''
    if fichas:
        colors = ['#1565C0', '#2E7D32', '#E65100']
        bg_colors = ['#E3F2FD', '#E8F5E9', '#FFF3E0']
        icon_map = {'⚡': '&#9889;', '💰': '&#128176;', '💧': '&#128167;', '📊': '&#128202;'}
        for i, ficha in enumerate(fichas[:3]):
            color = colors[i % len(colors)]
            bg = bg_colors[i % len(bg_colors)]
            emoji = ficha.get('emoji', '⚡')
            icon_html = icon_map.get(emoji, '&#9889;')
            label = ficha.get('indicador', 'Indicador')
            valor = ficha.get('valor', '')
            unidad = ficha.get('unidad', '')
            ctx = ficha.get('contexto', {})
            var_pct = ctx.get('variacion_vs_promedio_pct', None)
            fecha_dato = ficha.get('fecha', '')

            # Valor formateado
            if isinstance(valor, float):
                value_str = f"{valor:,.2f} {unidad}"
            else:
                value_str = f"{valor} {unidad}"

            # Variación
            var_html = ''
            if var_pct is not None:
                is_neg = float(var_pct) < 0
                var_color = '#C62828' if is_neg else '#2E7D32'
                var_arrow = '&#9660;' if is_neg else '&#9650;'
                # Usar etiqueta personalizada si está (ej: "vs Media 2020-2025")
                etiqueta_var = ctx.get('etiqueta_variacion', 'vs 7d')
                var_html = (
                    '<div style="font-size:11px;color:' + var_color + ';margin-top:2px;">'
                    + var_arrow + ' ' + f"{var_pct:+.1f}%" + ' ' + etiqueta_var + '</div>'
                )

            # Fecha del dato
            date_html = ''
            if fecha_dato:
                date_html = (
                    '<div style="font-size:10px;color:#999;margin-top:2px;">'
                    'Dato: ' + str(fecha_dato) + '</div>'
                )

            kpi_cards += (
                '<td style="width:33.33%;padding:6px;">'
                '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                'style="background:' + bg + ';border-radius:10px;border-left:4px solid ' + color + ';">'
                '<tr><td style="padding:16px 14px;">'
                '<div style="font-size:13px;color:#555;margin-bottom:4px;">'
                + icon_html + ' ' + label + '</div>'
                '<div style="font-size:22px;font-weight:700;color:' + color + ';margin-bottom:2px;">'
                + value_str + '</div>'
                + var_html + date_html
                + '</td></tr></table></td>'
            )

    # ── Construir tabla de predicciones 1 mes ──
    pred_1m_rows = ''
    pred_section_title = 'Proyecciones a 1 Mes'  # default, se actualiza abajo
    pred_modelo_label = ''

    def _modelo_legible(modelo_bd: str) -> str:
        """Convierte nombre interno de BD a nombre legible para el usuario."""
        return MODEL_DISPLAY_NAMES.get(modelo_bd, modelo_bd)

    # Normalizar: aceptar un dict (legacy) o una lista de dicts (multi-métrica)
    _pred_list = []
    if isinstance(predicciones, list):
        _pred_list = predicciones
    elif isinstance(predicciones, dict) and predicciones.get('estadisticas'):
        _pred_list = [predicciones]

    def _make_pred_row(label, icon_ent, value, cambio, tendencia, t_color_r, t_bg_r, arrow_r):
        return (
            '<tr>'
            '<td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#555;">'
            + icon_ent + ' ' + label + '</td>'
            '<td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;font-size:14px;font-weight:600;color:#222;">'
            + value + '</td>'
            '<td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;color:' + t_color_r + ';">'
            + cambio + '</td>'
            '<td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;">'
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:11px;font-weight:600;color:' + t_color_r + ';background:' + t_bg_r + ';">'
            + arrow_r + ' ' + tendencia + '</span></td></tr>'
        )

    # Iconos y unidades por tipo de métrica
    # Iconos de métricas — centralizados en core.constants
    _METRIC_ICONS = METRIC_ICONS_HTML

    for pred_item in _pred_list:
        if not pred_item or not pred_item.get('estadisticas'):
            continue

        stats = pred_item['estadisticas']
        preds_data_list = pred_item.get('predicciones', [])
        fuente = pred_item.get('fuente', 'General')
        modelo = pred_item.get('modelo', '')
        if modelo and not pred_modelo_label:
            pred_modelo_label = _modelo_legible(modelo)

        # Calcular tendencia comparando primera semana vs última semana
        if len(preds_data_list) >= 14:
            avg_first = sum(p['valor_gwh'] for p in preds_data_list[:7]) / 7
            avg_last = sum(p['valor_gwh'] for p in preds_data_list[-7:]) / 7
            cambio_pct = ((avg_last - avg_first) / avg_first * 100) if avg_first else 0
        elif len(preds_data_list) >= 2:
            avg_first = preds_data_list[0]['valor_gwh']
            avg_last = preds_data_list[-1]['valor_gwh']
            cambio_pct = ((avg_last - avg_first) / avg_first * 100) if avg_first else 0
        else:
            cambio_pct = 0

        if cambio_pct > 1:
            tend = 'Creciente'
            t_color = '#2E7D32'
            t_bg = '#E8F5E9'
            arrow = '&#9650;'
        elif cambio_pct < -1:
            tend = 'Decreciente'
            t_color = '#C62828'
            t_bg = '#FFEBEE'
            arrow = '&#9660;'
        else:
            tend = 'Estable'
            t_color = '#1565C0'
            t_bg = '#E3F2FD'
            arrow = '&#9654;'

        # Determinar label y unidad según tipo de fuente
        fuente_label = pred_item.get('fuente_label', fuente)
        fuente_lower = fuente.lower() if fuente else ''
        if fuente_lower in ('hidráulica', 'hidraulica', 'térmica', 'termica',
                            'solar', 'eólica', 'eolica'):
            fuente_label = f'Generaci' + chr(243) + 'n {fuente}'

        # Determinar unidad según métrica
        if 'precio' in fuente_lower or 'bolsa' in fuente_lower or 'PRECIO' in fuente:
            unidad = 'COP/kWh'
            valor_fmt = f"{stats.get('promedio_gwh', 0):,.1f} {unidad}"
            max_fmt = f"{stats.get('maximo_gwh', 0):,.1f} {unidad}"
            min_fmt = f"{stats.get('minimo_gwh', 0):,.1f} {unidad}"
        elif 'embalse' in fuente_lower or 'EMBALSES' in fuente:
            unidad = '%'
            valor_fmt = f"{stats.get('promedio_gwh', 0):.1f}{unidad}"
            max_fmt = f"{stats.get('maximo_gwh', 0):.1f}{unidad}"
            min_fmt = f"{stats.get('minimo_gwh', 0):.1f}{unidad}"
        else:
            unidad = 'GWh/d' + chr(237) + 'a'
            valor_fmt = f"{stats.get('promedio_gwh', 0):.1f} {unidad}"
            max_fmt = f"{stats.get('maximo_gwh', 0):.1f} {unidad}"
            min_fmt = f"{stats.get('minimo_gwh', 0):.1f} {unidad}"

        # Icono
        icon = '&#9889;'
        for prefix, ico in _METRIC_ICONS.items():
            if fuente.startswith(prefix) or fuente_label.startswith(prefix):
                icon = ico
                break

        # Fila principal: promedio del mes
        pred_1m_rows += _make_pred_row(
            f'{fuente_label} (prom.)',
            icon,
            valor_fmt,
            f"{cambio_pct:+.1f}%",
            tend, t_color, t_bg, arrow,
        )

        # Fila de intervalo de confianza (próximos 7 días, ~86% confianza)
        ic_inf = stats.get('ic_inferior_gwh')
        ic_sup = stats.get('ic_superior_gwh')
        if ic_inf is not None and ic_sup is not None:
            if 'precio' in fuente_lower or 'bolsa' in fuente_lower:
                ic_inf_fmt = f"{ic_inf:,.1f} COP/kWh"
                ic_sup_fmt = f"{ic_sup:,.1f} COP/kWh"
            elif 'embalse' in fuente_lower or 'EMBALSES' in fuente:
                ic_inf_fmt = f"{ic_inf:.1f}%"
                ic_sup_fmt = f"{ic_sup:.1f}%"
            else:
                ic_inf_fmt = f"{ic_inf:.1f} GWh"
                ic_sup_fmt = f"{ic_sup:.1f} GWh"
            pred_1m_rows += (
                '<tr>'
                '<td style="padding:4px 14px 6px;font-size:11px;color:#888;" colspan="2">'
                '&#127919; Rango pr&oacute;x. 7 d&iacute;as (IC ~86%)</td>'
                '<td style="padding:4px 14px 6px;" colspan="2">'
                '<span style="font-size:11px;color:#546E7A;font-weight:500;">'
                + ic_inf_fmt + ' &ndash; ' + ic_sup_fmt
                + '</span></td></tr>'
            )

        # Fila de calidad del modelo (MAPE ex-post real)
        mape_expost = pred_item.get('mape_expost')
        if mape_expost is not None:
            mape_label, mape_color, mape_bg = mape_quality(mape_expost)
            fecha_mape = pred_item.get('fecha_mape', '')
            fecha_mape_html = (
                f' <span style="font-size:10px;color:#999;">({fecha_mape})</span>'
                if fecha_mape else ''
            )
            pred_1m_rows += (
                '<tr>'
                '<td style="padding:4px 14px 10px;border-bottom:1px solid #f0f0f0;'
                'font-size:11px;color:#888;" colspan="2">'
                '&#128202; Precisi&oacute;n del modelo' + fecha_mape_html + '</td>'
                '<td style="padding:4px 14px 10px;border-bottom:1px solid #f0f0f0;" colspan="2">'
                '<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
                'font-size:11px;font-weight:600;color:' + mape_color + ';background:' + mape_bg + ';">'
                'Error real: ' + f'{mape_expost:.2f}%' + ' &mdash; ' + mape_label
                + '</span></td></tr>'
            )

        # Fila de fecha de generación del modelo
        fecha_gen_modelo = pred_item.get('fecha_generacion_modelo')
        if fecha_gen_modelo:
            _modelo_nombre = _modelo_legible(modelo) if modelo else ''
            _modelo_suffix = (' &mdash; ' + _modelo_nombre) if _modelo_nombre else ''
            pred_1m_rows += (
                '<tr>'
                '<td style="padding:2px 14px 8px;border-bottom:1px solid #f0f0f0;'
                'font-size:10px;color:#bbb;" colspan="4">'
                '&#128336; Modelo entrenado el: '
                '<span style="color:#999;font-weight:500;">' + fecha_gen_modelo + _modelo_suffix + '</span>'
                '</td></tr>'
            )
    # Título de sección
    if len(_pred_list) >= 3:
        pred_section_title = 'Proyecciones a 1 Mes — 3 M' + chr(233) + 'tricas Clave'
    elif len(_pred_list) == 1 and _pred_list[0]:
        fuente = _pred_list[0].get('fuente', '')
        fl = _pred_list[0].get('fuente_label', fuente)
        pred_section_title = f'Proyecciones a 1 Mes — {fl}'

    # ── Si no hay datos estructurados, intentar parsear del texto ──
    if not kpi_cards or not pred_1m_rows:
        parsed = _parse_informe_sections(informe_texto)
        if not kpi_cards and parsed['kpis']:
            # Fallback desde texto parseado
            colors = ['#1565C0', '#2E7D32', '#E65100']
            bg_colors = ['#E3F2FD', '#E8F5E9', '#FFF3E0']
            for i, kpi in enumerate(parsed['kpis'][:3]):
                color = colors[i % len(colors)]
                bg = bg_colors[i % len(bg_colors)]
                kpi_cards += (
                    '<td style="width:33.33%;padding:6px;">'
                    '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                    'style="background:' + bg + ';border-radius:10px;border-left:4px solid ' + color + ';">'
                    '<tr><td style="padding:16px 14px;">'
                    '<div style="font-size:13px;color:#555;margin-bottom:4px;">'
                    + kpi['icon'] + ' ' + kpi['label'] + '</div>'
                    '<div style="font-size:24px;font-weight:700;color:' + color + ';margin-bottom:2px;">'
                    + kpi['value'] + '</div>'
                    '</td></tr></table></td>'
                )

    # ── Anomalías / Riesgos ──
    risk_items = ''
    if anomalias:
        for anom in anomalias[:5]:
            sev = anom.get('severidad', 'ALERTA')
            desc = anom.get('descripcion', '')
            metrica = anom.get('metrica', '')
            r_color, r_bg = ANOMALY_SEVERITY_COLORS.get(sev, ('#F9A825', '#FFFDE7'))
            r_label = (
                'CR' + chr(205) + 'TICO' if sev in ('CRITICA', 'CRITICO', 'CRITICAL')
                else sev.upper() if sev.upper() in ('ALERTA',)
                else 'AVISO'
            )
            risk_items += (
                '<tr><td style="padding:12px 14px;border-bottom:1px solid #f5f5f5;">'
                '<table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>'
                '<td style="width:70px;vertical-align:top;">'
                '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
                'font-size:10px;font-weight:700;color:#fff;background:' + r_color + ';">'
                + r_label + '</span></td>'
                '<td style="padding-left:8px;">'
                '<div style="font-size:14px;font-weight:600;color:#333;">' + metrica + '</div>'
                '<div style="font-size:12px;color:#666;margin-top:2px;">' + desc + '</div>'
                '</td></tr></table></td></tr>'
            )
    if not risk_items:
        risk_items = (
            '<tr><td style="padding:16px;text-align:center;color:#2E7D32;font-size:14px;">'
            '&#9989; No se detectaron riesgos significativos hoy</td></tr>'
        )

    # ── Construir HTML completo ──
    p = []
    p.append('<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">')
    p.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    p.append('<title>Informe Ejecutivo - ' + fecha + '</title></head>')
    p.append('<body style="margin:0;padding:0;background:#f0f2f5;'
             'font-family:Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif;">')

    # Outer wrapper
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
             'style="background:#f0f2f5;padding:20px 0;">')
    p.append('<tr><td align="center">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="680" '
             'style="max-width:680px;background:#ffffff;border-radius:12px;'
             'overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">')

    # ════════ Header con color sólido (Outlook-safe) ════════
    p.append('<tr><td style="background-color:#0D1B4A;padding:0;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%">')
    p.append('<tr><td style="padding:28px 32px 12px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>')
    p.append('<td style="vertical-align:middle;">')
    p.append('<div style="font-size:10px;letter-spacing:3px;color:#8FAAD4;'
             'text-transform:uppercase;margin-bottom:6px;">Rep' + chr(250) + 'blica de Colombia</div>')
    p.append('<div style="font-size:22px;font-weight:700;color:#FFFFFF;line-height:1.3;">'
             'Informe Ejecutivo del<br>Sector Energ' + chr(233) + 'tico</div>')
    p.append('</td>')
    p.append('<td style="text-align:right;vertical-align:middle;">')
    p.append('<div style="width:52px;height:52px;border-radius:50%;'
             'background-color:#1A3A7A;text-align:center;line-height:52px;'
             'font-size:26px;display:inline-block;">&#9889;</div>')
    p.append('</td></tr></table></td></tr>')
    # Sub-header bar
    p.append('<tr><td style="padding:0 32px 20px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" '
             'style="background-color:#1A3A7A;border-radius:8px;width:100%;">')
    p.append('<tr>')
    p.append('<td style="padding:10px 16px;color:#B8D0F0;font-size:13px;">'
             '&#128197; ' + fecha + '</td>')
    p.append('<td style="padding:10px 16px;color:#B8D0F0;font-size:13px;">'
             '&#128337; ' + hora + '</td>')
    p.append('<td style="padding:10px 16px;color:#B8D0F0;font-size:13px;'
             'text-align:right;">Despacho del Viceministro</td>')
    p.append('</tr></table></td></tr>')
    p.append('</table></td></tr>')

    # ════════ KPI Cards ════════
    if kpi_cards:
        p.append('<tr><td style="padding:24px 26px 8px;">')
        p.append('<div style="font-size:11px;letter-spacing:2px;color:#999;'
                 'text-transform:uppercase;margin-bottom:12px;font-weight:600;">'
                 'Indicadores Clave del D' + chr(237) + 'a</div>')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%">')
        p.append('<tr>' + kpi_cards + '</tr>')
        p.append('</table></td></tr>')

    # ════════ Análisis Ejecutivo REMOVIDO del email ════════
    # El análisis completo ahora se incluye SOLO en el PDF adjunto.
    # El email muestra únicamente KPIs, predicciones, anomalías y noticias.

    # ════════ Predicciones 1M ════════
    if pred_1m_rows:
        modelo_label = pred_modelo_label
        p.append('<tr><td style="padding:20px 26px 8px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                 'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
        p.append('<tr><td colspan="4" style="background:#F5F7FA;padding:14px 16px;'
                 'font-size:14px;font-weight:700;color:#333;">'
                 '&#128200; ' + pred_section_title
                 + '</td></tr>')
        p.append('<tr style="background:#FAFAFA;">')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">INDICADOR</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">VALOR</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">CAMBIO</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">TENDENCIA</td>')
        p.append('</tr>')
        p.append(pred_1m_rows)
        p.append('</table></td></tr>')

    # ════════ Riesgos y Anomalías ════════
    p.append('<tr><td style="padding:20px 26px 8px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
             'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
    p.append('<tr><td style="background:#FFF8E1;padding:14px 16px;'
             'font-size:14px;font-weight:700;color:#E65100;">'
             '&#9888;&#65039; Riesgos y Anomal' + chr(237) + 'as</td></tr>')
    p.append(risk_items)
    p.append('</table></td></tr>')

    # ════════ Índices Compuestos del Sistema ════════
    if indices_compuestos:
        _IDX_COLORS = {
            'ÓPTIMO': '#1B5E20', 'ADECUADO': '#2E7D32', 'NORMAL': '#2E7D32', 'ESTABLE': '#2E7D32',
            'LEVE': '#7CB342', 'BAJO': '#E65100', 'MODERADO': '#E65100', 'VIGILANCIA': '#E65100',
            'PREOCUPANTE': '#BF360C', 'ALTO ESTR\u00c9S': '#B71C1C',
            'CR\u00cdTICO': '#B71C1C',
        }
        _IDX_BG = {
            'ÓPTIMO': '#C8E6C9', 'ADECUADO': '#E8F5E9', 'NORMAL': '#E8F5E9', 'ESTABLE': '#E8F5E9',
            'LEVE': '#F9FBE7', 'BAJO': '#FFF3E0', 'MODERADO': '#FFF3E0', 'VIGILANCIA': '#FFF3E0',
            'PREOCUPANTE': '#FBE9E7', 'ALTO ESTR\u00c9S': '#FFEBEE',
            'CR\u00cdTICO': '#FFEBEE',
        }
        # (sigla, qué mide, textos por nivel {nivel: (descripción, impacto, acción)})
        _IDX_META = {
            'ISH': {
                'titulo': 'Disponibilidad de agua en embalses para generaci\u00f3n el\u00e9ctrica',
                'niveles': {
                    '\u00d3PTIMO':      ('Los embalses est\u00e1n en niveles hist\u00f3ricamente altos. Hay amplia reserva h\u00eddrica.',
                                         'El sistema opera con gran margen de seguridad. La hidroenerg\u00eda puede cubrir la demanda sin apoyos t\u00e9rmicos.',
                                         'Mantener la gesti\u00f3n actual. Aprovechar excedentes para optimizar costos.'),
                    'ADECUADO':         ('Los embalses tienen reservas suficientes para cubrir la demanda en el corto plazo.',
                                         'Bajo riesgo operativo. Los precios de bolsa se mantienen estables.',
                                         'Monitorear la tendencia. Si los aportes h\u00eddricos bajan, revisar despacho t\u00e9rmico.'),
                    'BAJO':             ('Los embalses est\u00e1n por debajo de niveles normales. La reserva h\u00eddrica es insuficiente.',
                                         'Presi\u00f3n al alza en precios de bolsa. Mayor dependencia de generaci\u00f3n t\u00e9rmica costosa.',
                                         'Activar planes de contingencia t\u00e9rmica. Revisar restricciones de exportaci\u00f3n de energ\u00eda.'),
                    'CR\u00cdTICO':     ('Los embalses est\u00e1n en niveles cr\u00edticos. Riesgo real de racionamiento.',
                                         'El sistema enfrenta riesgo de desabastecimiento. Los precios de bolsa pueden dispararse.',
                                         'Declarar alerta de escasez. Activar protocolos de emergencia y coordinaci\u00f3n con el regulador.'),
                },
            },
            'IPM': {
                'titulo': 'Presi\u00f3n que ejercen los precios del mercado el\u00e9ctrico mayorista',
                'niveles': {
                    'NORMAL':           ('Los precios de bolsa est\u00e1n dentro de rangos hist\u00f3ricos normales. No hay presi\u00f3n econ\u00f3mica.',
                                         'Costos de generaci\u00f3n estables. Los usuarios regulados no enfrentar\u00e1n incrementos abruptos.',
                                         'Sin acci\u00f3n inmediata. Continuar monitoreo de aportes h\u00eddricos y oferta t\u00e9rmica.'),
                    'LEVE':             ('Los precios muestran una tendencia al alza moderada, a\u00fan dentro de rangos manejables.',
                                         'Leve incremento en el costo de prestaci\u00f3n del servicio. M\u00e1rgenes comercializadores bajo presi\u00f3n.',
                                         'Verificar causas (deficits h\u00eddricos, mantenimientos). Preparar alertas a agentes del mercado.'),
                    'MODERADO':         ('Los precios de bolsa est\u00e1n por encima de lo normal. El mercado muestra tensi\u00f3n.',
                                         'Efecto directo en tarifas reguladas si persiste. Riesgo de incumplimiento en contratos a precio fijo.',
                                         'Emitir circular a comercializadores. Revisar opciones de gesti\u00f3n de demanda y respuesta activa.'),
                    'ALTO ESTR\u00c9S': ('Los precios de bolsa est\u00e1n en niveles excepcionalmente altos. Crisis de precios en el mercado.',
                                         'Impacto directo en tarifas a usuarios. Riesgo de crisis financiera en comercializadores deficitarios.',
                                         'Intervenci\u00f3n regulatoria urgente. Activar mecanismos de precio l\u00edmite y mesas de trabajo con CREG.'),
                },
            },
            'IES': {
                'titulo': 'Nivel de estr\u00e9s operativo del sistema el\u00e9ctrico nacional',
                'niveles': {
                    'NORMAL':           ('El sistema opera con normalidad. No hay indicios de sobrecarga o vulnerabilidades cr\u00edticas.',
                                         'La confiabilidad del servicio es alta. El riesgo de fallas en cascada es m\u00ednimo.',
                                         'Mantener vigilancia rutinaria. Sin acciones especiales requeridas.'),
                    'LEVE':             ('El sistema presenta algunas se\u00f1ales de estr\u00e9s: anomal\u00edas aisladas o m\u00e1rgenes ajustados.',
                                         'La confiabilidad se mantiene, pero con menor margen de maniobra ante imprevistos.',
                                         'Revisar planes de mantenimiento preventivo. Identificar los indicadores que est\u00e1n generando el estr\u00e9s.'),
                    'MODERADO':         ('El sistema acumula m\u00faltiples indicadores en estado de alerta. La presi\u00f3n operativa es significativa.',
                                         'Riesgo elevado ante eventos imprevistos (salida de una planta grande, ola de calor). Menor resiliencia.',
                                         'Activar coordinaci\u00f3n operativa entre XM y generadores. Diferir mantenimientos no urgentes.'),
                    'ALTO ESTR\u00c9S': ('El sistema est\u00e1 bajo estr\u00e9s severo con m\u00faltiples indicadores cr\u00edticos simult\u00e1neos.',
                                         'Alta probabilidad de fallas si ocurre cualquier contingencia adicional. Estabilidad del sistema en riesgo.',
                                         'Activar sala de crisis operativa. Notificar al MinMinas y a la CREG. Preparar protocolos de carga controlada.'),
                },
            },
            'CIS': {
                'titulo': 'Calificaci\u00f3n integral que resume el estado general del sistema el\u00e9ctrico',
                'niveles': {
                    'ESTABLE':          ('Todos los indicadores principales est\u00e1n en verde. El sistema opera con condiciones \u00f3ptimas.',
                                         'Bajo riesgo en todas las dimensiones: h\u00eddrica, econ\u00f3mica y operativa.',
                                         'Sin acciones urgentes. Aprovechar la coyuntura para planear mantenimientos mayores.'),
                    'VIGILANCIA':       ('El sistema es estable pero uno o m\u00e1s indicadores muestran tendencias a monitorear.',
                                         'Riesgo moderado. La situaci\u00f3n puede evolucionar negativamente si no se gestiona.',
                                         'Aumentar frecuencia de monitoreo. Identificar el indicador que jala el \u00edndice hacia abajo.'),
                    'PREOCUPANTE':      ('Varios indicadores est\u00e1n deteriorados. El sistema se acerca a condiciones de riesgo alto.',
                                         'El deterioro combinado puede amplificar los efectos negativos. Tarifa, confiabilidad y reservas en tensi\u00f3n.',
                                         'Escalar a nivel directivo. Convocar comit\u00e9 de seguimiento y preparar nota t\u00e9cnica para el despacho ministerial.'),
                    'CR\u00cdTICO':     ('El sistema enfrenta una crisis multidimensional con varios indicadores en rojo simult\u00e1neamente.',
                                         'Riesgo real de afectaci\u00f3n masiva del servicio. Impacto econ\u00f3mico y reputacional alto para el sector.',
                                         'Activar el Comit\u00e9 de Crisis del Sector Energ\u00e9tico. Coordinaci\u00f3n inmediata con Presidencia de la Rep\u00fablica.'),
                },
            },
        }
        _idx_defs = [
            ('ish', 'ISH', 'Disponibilidad H\u00eddrica', '&#128167;'),
            ('ipm', 'IPM', 'Presi\u00f3n de Mercado', '&#128176;'),
            ('ies', 'IES', 'Estr\u00e9s del Sistema', '&#9888;&#65039;'),
            ('cis', 'CIS', 'Estado General', '&#127775;'),
        ]
        idx_cards = ''
        for key, sigla, nombre_corto, icon in _idx_defs:
            entry = indices_compuestos.get(key, {})
            valor = entry.get('valor', 0)
            nivel = str(entry.get('nivel', 'NORMAL')).upper()
            color = _IDX_COLORS.get(nivel, '#555555')
            bg = _IDX_BG.get(nivel, '#F5F5F5')
            meta = _IDX_META.get(sigla, {})
            titulo_largo = meta.get('titulo', nombre_corto)
            textos = meta.get('niveles', {}).get(nivel, ('', '', ''))
            descripcion_str, impacto_str, accion_str = textos if len(textos) == 3 else ('', '', '')
            idx_cards += (
                '<td style="width:25%;padding:5px;vertical-align:top;">'
                '<div style="background:' + bg + ';border-radius:10px;'
                'border:2px solid ' + color + ';padding:14px 10px;">'
                # Valor + sigla
                '<div style="text-align:center;margin-bottom:8px;">'
                '<div style="font-size:18px;margin-bottom:2px;">' + icon + '</div>'
                '<div style="font-size:22px;font-weight:700;color:' + color + ';line-height:1;">' + f'{valor:.0f}' + '</div>'
                '<div style="font-size:10px;font-weight:700;color:#333;margin:2px 0;">' + sigla + '</div>'
                '<div style="padding:2px 8px;border-radius:4px;display:inline-block;'
                'background:' + color + ';color:#fff;font-size:9px;font-weight:600;">' + nivel + '</div>'
                '</div>'
                # Qué mide
                '<div style="font-size:9px;font-weight:600;color:#333;border-top:1px solid ' + color + '20;padding-top:6px;margin-top:2px;">'
                '\u00bfQu\u00e9 mide?</div>'
                '<div style="font-size:9px;color:#444;margin-bottom:6px;line-height:1.3;">' + titulo_largo + '</div>'
                # Situación actual
                '<div style="font-size:9px;font-weight:600;color:#333;">'
                'Situaci\u00f3n actual:</div>'
                '<div style="font-size:9px;color:#444;margin-bottom:6px;line-height:1.3;">' + descripcion_str + '</div>'
                # Impacto
                '<div style="font-size:9px;font-weight:600;color:#333;">'
                'Impacto en el sistema:</div>'
                '<div style="font-size:9px;color:#444;margin-bottom:6px;line-height:1.3;">' + impacto_str + '</div>'
                # Acción recomendada
                '<div style="font-size:9px;font-weight:600;color:' + color + ';background:' + color + '15;'
                'border-radius:4px;padding:4px 6px;line-height:1.3;">'
                '&#128204; Acci\u00f3n: ' + accion_str + '</div>'
                '</div></td>'
            )
        p.append('<tr><td style="padding:20px 26px 8px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                 'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
        p.append('<tr><td style="background:#EDE7F6;padding:14px 16px;'
                 'font-size:14px;font-weight:700;color:#4527A0;">'
                 '&#128201; \u00cdndices del Sistema El\u00e9ctrico Nacional</td></tr>')
        p.append('<tr><td style="padding:12px 10px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%">')
        p.append('<tr>' + idx_cards + '</tr>')
        _comp = indices_compuestos.get('componentes', {})
        _n_crit = _comp.get('anomalias_criticas', 0)
        _n_alert = _comp.get('anomalias_alertas', 0)
        p.append(
            '</table>'
            '<div style="font-size:10px;color:#666;margin-top:8px;text-align:center;">'
            'Cada indicador tiene escala 0&#8211;100 (mayor = mejor condici\u00f3n) &middot; '
            + str(_n_crit) + ' alerta(s) cr\u00edtica(s) + '
            + str(_n_alert) + ' alerta(s) moderada(s) computadas'
            '</div>'
        )
        p.append('</td></tr></table></td></tr>')

    # ════════ Noticias del sector ════════
    if noticias:
        p.append('<tr><td style="padding:20px 26px 8px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                 'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
        p.append('<tr><td style="background-color:#E3F2FD;padding:14px 16px;'
                 'font-size:14px;font-weight:700;color:#1565C0;">'
                 '&#128240; Noticias del Sector Energ' + chr(233) + 'tico</td></tr>')
        for n in noticias[:3]:
            titulo = n.get('titulo', 'Sin t' + chr(237) + 'tulo')
            resumen = n.get('resumen', n.get('resumen_corto', ''))
            fuente = n.get('fuente', '')
            fecha_n = n.get('fecha', n.get('fecha_publicacion', ''))
            url = n.get('url', '')
            if len(resumen) > 140:
                resumen = resumen[:137] + '...'
            link_html = ''
            if url:
                link_html = (
                    ' <a href="' + url + '" '
                    'style="color:#1565C0;font-size:12px;text-decoration:none;'
                    'font-weight:600;">Leer m' + chr(225) + 's &rarr;</a>'
                )
            meta = ''
            if fuente or fecha_n:
                parts = []
                if fuente:
                    parts.append(fuente)
                if fecha_n:
                    parts.append(str(fecha_n))
                meta = (
                    '<div style="font-size:11px;color:#888;margin-top:4px;">'
                    + ' &middot; '.join(parts) + '</div>'
                )
            p.append(
                '<tr><td style="padding:14px 16px;border-bottom:1px solid #f0f0f0;">'
                '<div style="font-size:14px;font-weight:600;color:#222;margin-bottom:4px;">'
                + titulo + '</div>'
                '<div style="font-size:12px;color:#555;line-height:1.5;">'
                + resumen + link_html + '</div>'
                + meta
                + '</td></tr>'
            )
        p.append('</table></td></tr>')

    # ════════ Canales de consulta ════════
    p.append('<tr><td style="padding:20px 26px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
             'style="background:#F5F7FA;border-radius:10px;overflow:hidden;">')
    p.append('<tr><td style="padding:20px 24px;">')
    p.append('<div style="font-size:14px;font-weight:700;color:#333;margin-bottom:12px;">'
             '&#128204; Canales de Consulta</div>')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%">')
    # Chatbot button
    p.append('<tr><td style="padding:4px 0;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0"><tr>')
    p.append('<td style="background:#0088cc;border-radius:6px;padding:10px 20px;">')
    p.append('<a href="https://t.me/MinEnergiaColombia_bot" '
             'style="color:#ffffff;text-decoration:none;font-size:13px;font-weight:600;">'
             '&#128172; Chatbot Telegram</a>')
    p.append('</td>')
    p.append('<td style="padding-left:12px;">')
    p.append('<a href="https://t.me/MinEnergiaColombia_bot" '
             'style="color:#0088cc;font-size:12px;">t.me/MinEnergiaColombia_bot</a>')
    p.append('</td></tr></table></td></tr>')
    # Portal button
    p.append('<tr><td style="padding:4px 0;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0"><tr>')
    p.append('<td style="background:#1565C0;border-radius:6px;padding:10px 20px;">')
    p.append('<a href="https://portalenergetico.minenergia.gov.co/" '
             'style="color:#ffffff;text-decoration:none;font-size:13px;font-weight:600;">'
             '&#127760; Portal Energ' + chr(233) + 'tico</a>')
    p.append('</td>')
    p.append('<td style="padding-left:12px;">')
    p.append('<a href="https://portalenergetico.minenergia.gov.co/" '
             'style="color:#1565C0;font-size:12px;">portalenergetico.minenergia.gov.co</a>')
    p.append('</td></tr></table></td></tr>')
    p.append('</table></td></tr></table></td></tr>')

    # ════════ PDF notice ════════
    p.append('<tr><td style="padding:0 26px 16px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
             'style="background:#EDE7F6;border-radius:8px;">')
    p.append('<tr><td style="padding:14px 18px;font-size:13px;color:#4527A0;line-height:1.6;">')
    p.append('&#128206; <b>Informe PDF adjunto:</b> Consulte el an' + chr(225)
             + 'lisis ejecutivo completo con gr' + chr(225)
             + 'ficos, predicciones detalladas por m' + chr(233)
             + 'trica y an' + chr(225) + 'lisis de IA en el archivo PDF adjunto a este correo.')
    p.append('</td></tr></table></td></tr>')

    # ════════ Footer ════════
    p.append('<tr><td style="background:#1A1A2E;padding:24px 32px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%">')
    p.append('<tr><td style="text-align:center;">')
    p.append('<div style="font-size:13px;color:rgba(255,255,255,0.7);margin-bottom:8px;">'
             'Ministerio de Minas y Energ' + chr(237) + 'a</div>')
    p.append('<div style="font-size:11px;color:rgba(255,255,255,0.4);margin-bottom:12px;">'
             'Sistema automatizado de informes del Portal Energ' + chr(233)
             + 'tico &mdash; Generado el ' + fecha + ' a las ' + hora + '</div>')
    p.append('<div style="border-top:1px solid rgba(255,255,255,0.1);'
             'padding-top:12px;font-size:11px;color:rgba(255,255,255,0.3);">'
             'Este mensaje es informativo. Para consultas, utilice los canales de contacto indicados.</div>')
    p.append('</td></tr></table></td></tr>')

    p.append('</table></td></tr></table></body></html>')

    return '\n'.join(p)
