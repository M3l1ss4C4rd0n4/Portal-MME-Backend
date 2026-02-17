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
    _METRIC_ICONS = {
        'GENE_TOTAL': '&#9889;',
        'Generaci': '&#9889;',
        'Hidr': '&#128167;',
        'PRECIO': '&#128176;',
        'Precio': '&#128176;',
        'EMBALSES': '&#128167;',
        'Porcentaje': '&#128167;',
    }

    for pred_item in _pred_list:
        if not pred_item or not pred_item.get('estadisticas'):
            continue

        stats = pred_item['estadisticas']
        preds_data_list = pred_item.get('predicciones', [])
        fuente = pred_item.get('fuente', 'General')
        modelo = pred_item.get('modelo', '')
        if modelo and not pred_modelo_label:
            pred_modelo_label = modelo

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
            if sev in ('CRITICA', 'CRITICO', 'CRITICAL'):
                r_color = '#C62828'
                r_bg = '#FFEBEE'
                r_label = 'CR' + chr(205) + 'TICO'
            elif sev == 'ALERTA':
                r_color = '#E65100'
                r_bg = '#FFF3E0'
                r_label = 'ALERTA'
            else:
                r_color = '#F9A825'
                r_bg = '#FFFDE7'
                r_label = 'AVISO'
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

    # ════════ Análisis Ejecutivo (texto narrativo IA) ════════
    # Convertir markdown a HTML simplificado para email
    narrative_html = _markdown_to_email_html(informe_texto)
    if narrative_html:
        analisis_titulo = ('An' + chr(225) + 'lisis Ejecutivo — Generado con IA'
                           if generado_con_ia
                           else 'Resumen Ejecutivo del Sector')
        p.append('<tr><td style="padding:20px 26px 8px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                 'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
        p.append('<tr><td style="background:#F5F7FA;padding:14px 16px;'
                 'font-size:14px;font-weight:700;color:#333;">'
                 '&#128214; ' + analisis_titulo + '</td></tr>')
        p.append('<tr><td style="padding:16px 18px;font-size:13px;color:#333;line-height:1.7;">')
        p.append(narrative_html)
        p.append('</td></tr></table></td></tr>')

    # ════════ Predicciones 1M ════════
    if pred_1m_rows:
        modelo_label = pred_modelo_label
        p.append('<tr><td style="padding:20px 26px 8px;">')
        p.append('<table cellpadding="0" cellspacing="0" border="0" width="100%" '
                 'style="border-radius:10px;overflow:hidden;border:1px solid #e8e8e8;">')
        p.append('<tr><td colspan="4" style="background:#F5F7FA;padding:14px 16px;'
                 'font-size:14px;font-weight:700;color:#333;">'
                 '&#128200; ' + pred_section_title
                 + (' <span style="font-size:11px;color:#888;font-weight:400;">(' + modelo_label + ')</span>' if modelo_label else '')
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

    return '\n'.join(p)
