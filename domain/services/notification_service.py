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

logger = logging.getLogger(__name__)


# ─────────────────── Configuración ───────────────────

def _pg_params() -> dict:
    """Obtiene parámetros de conexión PostgreSQL."""
    try:
        from infrastructure.database.connection import PostgreSQLConnectionManager
        mgr = PostgreSQLConnectionManager()
        params = {
            'host': mgr.host,
            'port': mgr.port,
            'database': mgr.database,
            'user': mgr.user,
        }
        if mgr.password:
            params['password'] = mgr.password
        return params
    except Exception:
        # Fallback directo
        return {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'portal_energetico'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', ''),
        }


def _get_telegram_token() -> str:
    """Obtiene el token del bot de Telegram."""
    # 1. Variable de entorno directa
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    if token:
        return token
    # 2. Intentar leer del .env del bot
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'whatsapp_bot', '.env'
    )
    try:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith('TELEGRAM_BOT_TOKEN='):
                        return line.strip().split('=', 1)[1].strip()
    except Exception:
        pass
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
    parse_mode: str = "Markdown",
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
                # Enviar texto
                resp = client.post(
                    f"{base}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        f"Telegram sendMessage {chat_id}: {resp.status_code}"
                    )
                    failed += 1
                    continue

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
) -> Dict[str, int]:
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


def build_daily_email_html(informe_texto: str) -> str:
    """
    Construye HTML premium del email diario.
    Parsea el informe real del orquestador y lo renderiza en una
    plantilla corporativa moderna con tarjetas KPI, semáforos de
    riesgo y diseño responsivo.
    """
    fecha = datetime.now().strftime('%Y-%m-%d')
    hora = datetime.now().strftime('%H:%M')

    # ── Parsear datos reales del informe ──
    data = _parse_informe_sections(informe_texto)

    # ── Construir tarjetas KPI ──
    kpi_cards = ''
    colors = ['#1565C0', '#2E7D32', '#E65100']
    bg_colors = ['#E3F2FD', '#E8F5E9', '#FFF3E0']
    for i, kpi in enumerate(data['kpis'][:3]):
        color = colors[i % len(colors)]
        bg = bg_colors[i % len(bg_colors)]
        var_html = ''
        if 'variacion' in kpi:
            var_val = kpi['variacion']
            is_neg = var_val.startswith('-')
            var_color = '#C62828' if is_neg else '#2E7D32'
            var_arrow = '&#9660;' if is_neg else '&#9650;'
            var_html = (
                '<span style="font-size:12px;color:' + var_color + ';">'
                + var_arrow + ' ' + var_val + ' vs 7d</span>'
            )
        kpi_cards += (
            '<td style="width:33.33%;padding:6px;">'
            '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
            'style="background:' + bg + ';border-radius:10px;border-left:4px solid ' + color + ';">'
            '<tr><td style="padding:16px 14px;">'
            '<div style="font-size:13px;color:#555;margin-bottom:4px;">'
            + kpi['icon'] + ' ' + kpi['label'] + '</div>'
            '<div style="font-size:24px;font-weight:700;color:' + color + ';margin-bottom:2px;">'
            + kpi['value'] + '</div>'
            + var_html
            + '</td></tr></table></td>'
        )

    # ── Construir predicciones ──
    def _pred_row(pred):
        tend = pred.get('tendencia', 'Estable')
        if tend == 'Creciente':
            arrow = '&#9650;'
            t_color = '#2E7D32'
            t_bg = '#E8F5E9'
        elif tend == 'Decreciente':
            arrow = '&#9660;'
            t_color = '#C62828'
            t_bg = '#FFEBEE'
        else:
            arrow = '&#9654;'
            t_color = '#1565C0'
            t_bg = '#E3F2FD'
        return (
            '<tr>'
            '<td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#555;">'
            + pred['icon'] + ' ' + pred['label'] + '</td>'
            '<td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;font-size:14px;font-weight:600;color:#222;">'
            + pred['value'] + '</td>'
            '<td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;color:' + t_color + ';">'
            + pred['cambio'] + '</td>'
            '<td style="padding:10px 14px;border-bottom:1px solid #f0f0f0;">'
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:11px;font-weight:600;color:' + t_color + ';background:' + t_bg + ';">'
            + arrow + ' ' + tend + '</span></td></tr>'
        )

    pred_1m_rows = ''.join([_pred_row(p) for p in data['predicciones_1m']])
    pred_6m_rows = ''.join([_pred_row(p) for p in data['predicciones_6m']])

    # ── Riesgos ──
    risk_items = ''
    for r in data['riesgos']:
        if r['severity'] == 'critical':
            r_color = '#C62828'
            r_bg = '#FFEBEE'
            r_icon = '&#128308;'
            r_label = 'CRITICO'
        elif r['severity'] == 'alert':
            r_color = '#E65100'
            r_bg = '#FFF3E0'
            r_icon = '&#128992;'
            r_label = 'ALERTA'
        else:
            r_color = '#F9A825'
            r_bg = '#FFFDE7'
            r_icon = '&#128993;'
            r_label = 'AVISO'
        risk_items += (
            '<tr><td style="padding:12px 14px;border-bottom:1px solid #f5f5f5;">'
            '<table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>'
            '<td style="width:70px;vertical-align:top;">'
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'font-size:10px;font-weight:700;color:#fff;background:' + r_color + ';">'
            + r_label + '</span></td>'
            '<td style="padding-left:8px;">'
            '<div style="font-size:14px;font-weight:600;color:#333;">' + r['label'] + '</div>'
            '<div style="font-size:12px;color:#666;margin-top:2px;">' + r['desc'] + '</div>'
            '</td></tr></table></td></tr>'
        )
    if not risk_items:
        risk_items = (
            '<tr><td style="padding:16px;text-align:center;color:#2E7D32;font-size:14px;">'
            '&#9989; No se detectaron riesgos significativos hoy</td></tr>'
        )

    # ── Recomendaciones ──
    rec_items = ''
    for i, rec in enumerate(data['recomendaciones']):
        rec_items += (
            '<tr><td style="padding:8px 14px;border-bottom:1px solid #f5f5f5;font-size:13px;'
            'color:#333;line-height:1.5;">'
            '<span style="display:inline-block;width:22px;height:22px;border-radius:50%;'
            'background:#1565C0;color:#fff;text-align:center;line-height:22px;font-size:11px;'
            'font-weight:700;margin-right:8px;">' + str(i + 1) + '</span>'
            + rec + '</td></tr>'
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

    # ════════ Header con gradiente ════════
    p.append('<tr><td style="background:linear-gradient(135deg,#0D1B4A 0%,#1A3A7A 50%,#2856A3 100%);'
             'padding:0;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%">')
    p.append('<tr><td style="padding:28px 32px 12px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%"><tr>')
    p.append('<td style="vertical-align:middle;">')
    p.append('<div style="font-size:10px;letter-spacing:3px;color:rgba(255,255,255,0.6);'
             'text-transform:uppercase;margin-bottom:6px;">Rep' + chr(250) + 'blica de Colombia</div>')
    p.append('<div style="font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">'
             'Informe Ejecutivo del<br>Sector Energ' + chr(233) + 'tico</div>')
    p.append('</td>')
    p.append('<td style="text-align:right;vertical-align:middle;">')
    p.append('<div style="width:52px;height:52px;border-radius:50%;'
             'background:rgba(255,255,255,0.15);text-align:center;line-height:52px;'
             'font-size:26px;display:inline-block;">&#9889;</div>')
    p.append('</td></tr></table></td></tr>')
    # Sub-header bar
    p.append('<tr><td style="padding:0 32px 20px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" '
             'style="background:rgba(255,255,255,0.12);border-radius:8px;width:100%;">')
    p.append('<tr>')
    p.append('<td style="padding:10px 16px;color:rgba(255,255,255,0.9);font-size:13px;">'
             '&#128197; ' + fecha + '</td>')
    p.append('<td style="padding:10px 16px;color:rgba(255,255,255,0.9);font-size:13px;">'
             '&#128337; ' + hora + '</td>')
    p.append('<td style="padding:10px 16px;color:rgba(255,255,255,0.9);font-size:13px;'
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

    # ════════ Predicciones 1M ════════
    if pred_1m_rows:
        p.append('<tr><td style="padding:20px 26px 8px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                 'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
        p.append('<tr><td colspan="4" style="background:#F5F7FA;padding:14px 16px;'
                 'font-size:14px;font-weight:700;color:#333;">'
                 '&#128200; Proyecciones a 1 Mes</td></tr>')
        p.append('<tr style="background:#FAFAFA;">')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">INDICADOR</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">VALOR</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">CAMBIO</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">TENDENCIA</td>')
        p.append('</tr>')
        p.append(pred_1m_rows)
        p.append('</table></td></tr>')

    # ════════ Predicciones 6M ════════
    if pred_6m_rows:
        p.append('<tr><td style="padding:12px 26px 8px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                 'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
        p.append('<tr><td colspan="4" style="background:#F5F7FA;padding:14px 16px;'
                 'font-size:14px;font-weight:700;color:#333;">'
                 '&#128202; Proyecciones a 6 Meses</td></tr>')
        p.append('<tr style="background:#FAFAFA;">')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">INDICADOR</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">VALOR</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">CAMBIO</td>')
        p.append('<td style="padding:8px 14px;font-size:11px;color:#888;font-weight:600;">TENDENCIA</td>')
        p.append('</tr>')
        p.append(pred_6m_rows)
        p.append('</table></td></tr>')

    # ════════ Riesgos ════════
    p.append('<tr><td style="padding:20px 26px 8px;">')
    p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
             'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
    p.append('<tr><td style="background:#FFF8E1;padding:14px 16px;'
             'font-size:14px;font-weight:700;color:#E65100;">'
             '&#9888;&#65039; Riesgos y Alertas</td></tr>')
    p.append(risk_items)
    p.append('</table></td></tr>')

    # ════════ Recomendaciones ════════
    if rec_items:
        p.append('<tr><td style="padding:16px 26px 8px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                 'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
        p.append('<tr><td style="background:#E8F5E9;padding:14px 16px;'
                 'font-size:14px;font-weight:700;color:#2E7D32;">'
                 '&#9989; Recomendaciones T' + chr(233) + 'cnicas</td></tr>')
        p.append(rec_items)
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
    p.append('&#128206; <b>PDF adjunto:</b> Encuentre el informe completo con gr' + chr(225)
             + 'ficos, predicciones detalladas y an' + chr(225) + 'lisis estad' + chr(237)
             + 'stico en el archivo adjunto a este correo.')
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
