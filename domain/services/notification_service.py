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

# Configuración SMTP (env vars)
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'Portal Energético MME')


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
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(
            "SMTP_USER / SMTP_PASSWORD no configurados — email no enviado. "
            "Configure las variables de entorno para habilitar emails."
        )
        return {"sent": 0, "failed": 0, "reason": "smtp_not_configured"}

    sent = 0
    failed = 0

    for dest in to_list:
        try:
            msg = MIMEMultipart()
            msg['From'] = f"{EMAIL_FROM_NAME} <{SMTP_USER}>"
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
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, dest, msg.as_string())

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


def build_daily_email_html(informe_texto: str) -> str:
    """
    Construye el cuerpo HTML del email diario del informe ejecutivo.
    Recibe el texto Markdown del informe y lo envuelve en una plantilla
    corporativa para el Despacho del Viceministro.
    """
    import re as _re

    # Convertir Markdown básico a HTML
    html = informe_texto
    html = _re.sub(r'#{3}\s*(.+)', r'<h3 style="color:#1a237e;margin:15px 0 5px;">\1</h3>', html)
    html = _re.sub(r'#{2}\s*(.+)', r'<h2 style="color:#1a237e;border-bottom:2px solid #1a237e;'
                   r'padding-bottom:4px;margin:20px 0 8px;">\1</h2>', html)
    html = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
    html = _re.sub(r'\*(.+?)\*', r'<b>\1</b>', html)
    html = _re.sub(r'_(.+?)_', r'<i>\1</i>', html)
    html = _re.sub(r'^[-•]\s+(.+)$', r'<li>\1</li>', html, flags=_re.MULTILINE)
    html = html.replace('\n', '<br>\n')

    fecha = datetime.now().strftime('%Y-%m-%d')
    hora = datetime.now().strftime('%H:%M')

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5;
             margin: 0; padding: 20px;">
  <div style="max-width: 750px; margin: auto; background: white;
              border-radius: 10px; overflow: hidden;
              box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
    <!-- Header -->
    <div style="background: linear-gradient(135deg, #1a237e, #283593);
                color: white; padding: 25px 30px; text-align: center;">
      <h1 style="margin:0; font-size:22px;">
        📊 Informe Ejecutivo del Sector Eléctrico
      </h1>
      <p style="margin:6px 0 0; font-size:14px; opacity:0.9;">
        República de Colombia — Ministerio de Minas y Energía
      </p>
    </div>

    <!-- Metadata -->
    <div style="background: #e8eaf6; padding: 10px 30px; font-size: 13px;
                color: #333; display: flex; gap: 20px;">
      <span>📅 Fecha: {fecha}</span>
      <span>⏰ Hora: {hora}</span>
      <span>📋 Despacho del Viceministro</span>
    </div>

    <!-- Body -->
    <div style="padding: 25px 30px; line-height: 1.7; color: #222;">
      {html}
    </div>

    <!-- Footer -->
    <div style="border-top: 2px solid #1a237e; padding: 15px 30px;
                font-size: 11px; color: #777; text-align: center;
                background: #fafafa;">
      <p style="margin:0;">
        Documento generado automáticamente por el Portal Energético MME.<br>
        Los datos provienen de XM, SIMEM y fuentes oficiales del sector.<br>
        Las predicciones utilizan modelos ENSEMBLE con validación holdout.
      </p>
      <p style="margin:8px 0 0; font-size:10px; color:#aaa;">
        📎 El informe ejecutivo en formato PDF se adjunta a este correo.
      </p>
    </div>
  </div>
</body>
</html>"""
