#!/usr/bin/env python3
"""
Telegram Bot - Modo Polling v2
Conecta con el orquestador del Portal Energético (API puerto 8000)
usando la misma estructura de intents y menú que el sistema central.

Modo polling: el bot se conecta A Telegram (bypassa firewall del Ministerio).
"""
import asyncio
import logging
import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

import httpx
import redis

# ═══════════════════════════════════════════════════════════
# Path setup — whatsapp_bot PRIMERO para que app.config no choque con server/app.py
# ═══════════════════════════════════════════════════════════
WHATSAPP_BOT_DIR = str(Path(__file__).parent)
SERVER_DIR = str(Path(__file__).parent.parent)
if WHATSAPP_BOT_DIR not in sys.path:
    sys.path.insert(0, WHATSAPP_BOT_DIR)
if SERVER_DIR not in sys.path:
    sys.path.append(SERVER_DIR)
os.chdir(WHATSAPP_BOT_DIR)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode

from app.config import settings

# ═══════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════
LOG_DIR = Path(WHATSAPP_BOT_DIR) / 'logs'
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_DIR / 'telegram_polling.log'))
    ]
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Configuración
# ═══════════════════════════════════════════════════════════
PORTAL_API_URL = getattr(settings, 'PORTAL_API_URL', 'http://localhost:8000')
PORTAL_API_KEY = "mme-portal-energetico-2026-secret-key"
ORCHESTRATOR_ENDPOINT = f"{PORTAL_API_URL}/api/v1/chatbot/orchestrator"

# Redis para tracking de usuarios de Telegram
_redis = redis.Redis(
    host=getattr(settings, 'REDIS_HOST', 'localhost'),
    port=getattr(settings, 'REDIS_PORT', 6379),
    db=3,
    password=getattr(settings, 'REDIS_PASSWORD', None) or None,
    decode_responses=True
)


# ═══════════════════════════════════════════════════════════
# User tracking (para broadcast de alertas)
# ═══════════════════════════════════════════════════════════

def track_telegram_user(user_id: int, username: str = None, first_name: str = None):
    """Registra usuario de Telegram en Redis (rápido) + PostgreSQL (persistente)"""
    try:
        _redis.sadd('bot:known_telegram_users', str(user_id))
        _redis.hset(f'telegram_user:{user_id}', mapping={
            'user_id': str(user_id),
            'username': username or '',
            'first_name': first_name or '',
            'last_interaction': datetime.now().isoformat(),
            'platform': 'telegram'
        })
    except Exception as e:
        logger.error(f"Error tracking usuario Telegram {user_id} en Redis: {e}")

    # Persistir en PostgreSQL (best-effort, no bloquea)
    try:
        from domain.services.notification_service import persist_telegram_user
        persist_telegram_user(user_id, username, first_name)
    except Exception as e:
        logger.debug(f"Error persistiendo usuario {user_id} en PostgreSQL: {e}")


# ═══════════════════════════════════════════════════════════
# Orquestador del portal (HTTP)
# ═══════════════════════════════════════════════════════════

async def call_orchestrator(session_id: str, intent: str, parameters: dict = None) -> dict:
    """Llama al orquestador del Portal Energético via HTTP"""
    payload = {
        "sessionId": session_id,
        "intent": intent,
        "parameters": parameters or {}
    }
    logger.info(f"[ORCH] → intent={intent} params={parameters or {}}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                ORCHESTRATOR_ENDPOINT,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": PORTAL_API_KEY
                }
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info(f"[ORCH] ← status={result.get('status')}")
            return result
    except httpx.TimeoutException:
        logger.error("[ORCH] Timeout llamando al orquestador")
        return {"status": "ERROR", "data": {}, "message": "Timeout del servicio"}
    except Exception as e:
        logger.error(f"[ORCH] Error: {e}")
        return {"status": "ERROR", "data": {}, "message": str(e)}


def get_session_id(user_id: int) -> str:
    return f"telegram_{user_id}"


# ═══════════════════════════════════════════════════════════
# Renderizado de respuestas
# ═══════════════════════════════════════════════════════════

# ── FASE A: Helper de redondeo compacto para móvil ────────
def _r(val, dec=1):
    """Redondear valor numérico para display compacto."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if dec == 0:
            return str(int(round(v)))
        return f"{round(v, dec)}"
    except (ValueError, TypeError):
        return str(val)


def render_menu(data: dict) -> tuple:
    """Renderiza el menú principal (4 opciones + submenús)"""
    bienvenida = data.get("mensaje_bienvenida", "¡Bienvenido! 👋")
    indicadores = data.get("indicadores_clave", [])
    menu_items = data.get("menu_principal", [])

    text = bienvenida
    if indicadores:
        text += "\n\n📊 *Indicadores clave:*\n"
        for ind in indicadores:
            text += f"• {ind}\n"

    keyboard = []
    for item in menu_items:
        emoji = item.get("emoji", "")
        titulo = item.get("titulo", "")
        item_id = item.get("id", "")
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {titulo}", callback_data=f"intent:{item_id}"
        )])

    return text, InlineKeyboardMarkup(keyboard)


def render_fichas(data: dict) -> tuple:
    """Renderiza fichas de estado_actual — FASE A: formato compacto para móvil"""
    fichas = data.get("fichas", [])
    fecha = data.get("fecha_consulta", "")

    text = "📊 *Estado Actual del Sector Energético*\n"
    text += f"_{fecha[:10] if fecha else 'Actualizado'}_\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for ficha in fichas:
        emoji = ficha.get("emoji", "📊")
        indicador = ficha.get("indicador", "")
        valor = ficha.get("valor", "N/A")
        unidad = ficha.get("unidad", "")
        fecha_dato = ficha.get("fecha", "")
        contexto = ficha.get("contexto", {})

        # FASE A: Línea 1 — Indicador
        text += f"{emoji} *{indicador}*\n"

        # FASE A: Línea 2 — Valor + fecha compactos
        fecha_str = f" (dato al {fecha_dato})" if fecha_dato else ""
        text += f"   Valor: *{valor} {unidad}*{fecha_str}\n"

        # FASE A: Línea 3 — Prom 7d · Variación · Tendencia en una sola línea
        if contexto:
            promedio = contexto.get("promedio_7_dias")
            variacion = contexto.get("variacion_vs_promedio_pct")
            tendencia = contexto.get("tendencia", "")

            if promedio is not None:
                # Indicadores con promedio 7d (Generación, Precio)
                parts = []
                parts.append(f"Prom 7d: {_r(promedio)} {unidad}")
                if variacion is not None:
                    signo = "+" if variacion > 0 else ""
                    parts.append(f"Var: {signo}{_r(variacion, 1)}%")
                if tendencia:
                    parts.append(tendencia)
                text += f"   {' · '.join(parts)}\n"

            # Embalses: estado + referencia histórica (2020-presente)
            estado_emb = contexto.get("estado")
            ref_hist = contexto.get("referencia_historica")
            if estado_emb:
                text += f"   {estado_emb}\n"
            if ref_hist:
                text += f"   _{ref_hist}_\n"

        text += "\n"

    regresar = data.get("opcion_regresar", {})
    keyboard = [[InlineKeyboardButton(
        regresar.get("titulo", "🔙 Menú principal"), callback_data="intent:menu"
    )]]
    return text, InlineKeyboardMarkup(keyboard)


def render_predicciones_submenu() -> tuple:
    """Submenú de horizontes de predicción"""
    text = "🔮 *Predicciones del Sector Energético*\n\n¿Para qué periodo deseas las predicciones?\n"
    keyboard = [
        [InlineKeyboardButton("📅 Una semana", callback_data="pred:1_semana")],
        [InlineKeyboardButton("📅 Un mes", callback_data="pred:1_mes")],
        [InlineKeyboardButton("📅 6 meses", callback_data="pred:6_meses")],
        [InlineKeyboardButton("📅 Próximo año", callback_data="pred:1_ano")],
        [InlineKeyboardButton("✏️ Fecha personalizada", callback_data="pred:personalizado")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


def render_predicciones_resultado(data: dict, current_horizonte: str = None) -> tuple:
    """Renderiza predicciones — FASE A/B: compacto, horizon selector inline"""
    predicciones = data.get("predicciones", data.get("fichas_prediccion", data.get("fichas", [])))
    horizonte_titulo = data.get("horizonte_titulo", data.get("horizonte", ""))

    text = "🔮 *Predicciones del Sector*"
    if horizonte_titulo:
        if isinstance(horizonte_titulo, dict):
            text += f" — _{horizonte_titulo.get('titulo', '')}_"
        else:
            text += f" — _{horizonte_titulo}_"

    fecha_ini = data.get("fecha_inicio", "")[:10]
    fecha_end = data.get("fecha_fin", "")[:10]
    if fecha_ini and fecha_end:
        text += f"\n📅 _{fecha_ini} → {fecha_end}_"
    text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

    # FASE A: Intro de confianza — una sola línea arriba
    has_experimental = False
    if isinstance(predicciones, list):
        for pred in predicciones:
            if isinstance(pred, dict) and pred.get("nivel_confianza") == "EXPERIMENTAL":
                has_experimental = True
                break
    if has_experimental:
        text += "_Generación y Embalses: alta confianza. Precio de Bolsa: modelo experimental._\n"
    text += "\n"

    if isinstance(predicciones, list):
        for pred in predicciones:
            if isinstance(pred, dict):
                emoji = pred.get("emoji", "📈")
                indicador = pred.get("indicador", pred.get("titulo", ""))
                unidad = pred.get("unidad", "")
                confiable = pred.get("confiable", True)
                error = pred.get("error")
                nivel_conf = pred.get("nivel_confianza", "")

                # FASE A: Etiqueta (experimental) junto al nombre
                exp_tag = " _(experimental)_" if nivel_conf == "EXPERIMENTAL" else ""
                text += f"{emoji} *{indicador}*{exp_tag}\n"

                if error and not confiable:
                    text += f"   ⚠️ _{error}_\n\n"
                    continue
                if error:
                    text += f"   ❌ {error}\n\n"
                    continue

                resumen = pred.get("resumen", {})
                tendencia = pred.get("tendencia", "")

                # FASE A: Línea 1 — Promedio · Rango (números redondeados)
                avg_periodo = resumen.get("promedio_periodo", pred.get("valor_predicho"))
                min_p = resumen.get("minimo_periodo")
                max_p = resumen.get("maximo_periodo")
                rango_conf = resumen.get("rango_confianza")

                line1 = []
                if avg_periodo is not None:
                    line1.append(f"Promedio: *{_r(avg_periodo)} {unidad}*")
                if min_p is not None and max_p is not None:
                    line1.append(f"Rango: {_r(min_p, 0)}–{_r(max_p, 0)} {unidad}")
                elif rango_conf:
                    inf = rango_conf.get('inferior', '?')
                    sup = rango_conf.get('superior', '?')
                    line1.append(f"IC: {_r(inf, 0)}–{_r(sup, 0)}")
                if line1:
                    text += f"   {' · '.join(line1)}\n"

                # FASE A: Línea 2 — Últimos 30d · Tendencia · Días
                avg_hist = resumen.get("promedio_30d_historico")
                cambio = resumen.get("cambio_pct")
                dias_pred = pred.get("total_dias_prediccion")

                line2 = []
                if avg_hist is not None:
                    hist_str = f"Últ 30d: {_r(avg_hist)} {unidad}"
                    if cambio is not None:
                        signo = "+" if cambio > 0 else ""
                        hist_str += f" ({signo}{_r(cambio, 1)}%)"
                    line2.append(hist_str)
                else:
                    nota_hist = resumen.get("nota_historico")
                    if nota_hist:
                        line2.append(nota_hist)
                if tendencia:
                    line2.append(f"Tend: {tendencia}")
                if dias_pred:
                    line2.append(f"{dias_pred} días")
                if line2:
                    text += f"   {' · '.join(line2)}\n"

                text += "\n"
    elif isinstance(predicciones, str):
        text += predicciones

    # FASE A: Disclaimer agrupado al final — una sola vez
    if has_experimental:
        text += "⚠️ _Nota sobre precios: el modelo de Precio de Bolsa es "
        text += "EXPERIMENTAL (sin validación holdout). Úselo solo como "
        text += "referencia direccional, no para decisiones críticas._\n"

    if "mensaje" in data:
        text += f"\n{data['mensaje']}\n"

    # FASE B: Inline horizon selector — switch sin enviar nuevo mensaje
    hor_map = [
        ("📅 1 sem", "1_semana"),
        ("📅 1 mes", "1_mes"),
        ("📅 6 meses", "6_meses"),
        ("📅 1 año", "1_ano"),
    ]
    hor_btns = []
    for label, code in hor_map:
        display = f"▸ {label}" if current_horizonte == code else label
        hor_btns.append(InlineKeyboardButton(display, callback_data=f"pred:{code}"))
    keyboard = [
        hor_btns[:2],
        hor_btns[2:],
        [InlineKeyboardButton("✏️ Personalizado", callback_data="pred:personalizado")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


def render_anomalias(data: dict) -> tuple:
    """Renderiza anomalías — FASE A: compacto, 2-3 líneas por indicador"""
    anomalias = data.get("anomalias", [])
    fecha_analisis = data.get("fecha_analisis", "")

    text = "🔍 *Anomalías del Sector*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if fecha_analisis:
        text += f"📅 _{fecha_analisis}_\n"
    text += "\n"

    if not anomalias:
        text += "✅ *Todo normal* — sin anomalías significativas.\n"
        text += "Generación, precio y embalses dentro de rangos esperados.\n"
    else:
        sev_emoji = {'crítico': '🔴', 'alerta': '🟠', 'normal': '🟢'}

        for a in anomalias:
            emoji_ind = a.get('emoji', '📊')
            nombre = a.get('indicador', '?')
            sev = a.get('severidad', 'normal')
            valor = a.get('valor_actual')
            unidad = a.get('unidad', '')
            avg_hist = a.get('promedio_hist_30d')
            desv = a.get('desviacion_pct', 0)
            predicho = a.get('valor_predicho')
            pred_excluida = a.get('prediccion_excluida', False)

            # FASE A: Línea 1 — Indicador + severidad
            sev_txt = sev.upper() if sev != 'normal' else 'Normal'
            text += f"{sev_emoji.get(sev, '⚪')} {emoji_ind} *{nombre}* — {sev_txt}\n"

            # FASE A: Línea 2 — Actual vs promedio compacto
            if valor is not None and avg_hist is not None:
                delta_h = a.get('delta_hist_pct', 0)
                text += (f"▸ Actual: *{_r(valor)} {unidad}*\n"
                         f"▸ Prom 30d: {_r(avg_hist)} {unidad} "
                         f"(desvío *{_r(desv, 1)}%*)\n")
            elif valor is not None:
                fecha = a.get('fecha_dato', '')
                text += f"▸ Actual: *{_r(valor)} {unidad}* ({fecha})\n"

            # FASE A: Línea 3 — Predicción o motivo de exclusión
            if predicho is not None and not pred_excluida:
                delta_p = a.get('delta_pred_pct', '?')
                text += f"▸ Predicción: {_r(predicho)} {unidad} (desvío {delta_p}%)\n"
            elif pred_excluida:
                comentario_conf = a.get('comentario_confianza', '')
                if comentario_conf:
                    text += f"▸ _{comentario_conf}_\n"
                else:
                    text += "▸ _Predicción excluida por baja confianza_\n"

            text += "\n"

    if "resumen" in data:
        text += f"📋 _{data['resumen']}_\n"

    # FASE B: Detail buttons per indicator
    detalle_completo = data.get("detalle_completo", [])
    if detalle_completo:
        detail_row = []
        for i, det in enumerate(detalle_completo):
            ind = det.get("indicador", "?")
            sev = det.get("severidad", "normal")
            sev_e = {'crítico': '🔴', 'alerta': '🟠', 'normal': '🟢'}.get(sev, '⚪')
            short = (ind.replace("Precio de Bolsa", "Precio")
                     .replace("Generación Total", "Generación")
                     .replace("Porcentaje de Embalses", "Embalses"))
            detail_row.append(InlineKeyboardButton(
                f"{sev_e} {short}", callback_data=f"anom_det:{i}"
            ))
        keyboard = [
            detail_row,
            [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]
        ]
    else:
        keyboard = [[InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]]
    return text, InlineKeyboardMarkup(keyboard)


def render_anomalia_detalle(det: dict) -> tuple:
    """FASE B: Render detalle expandido de una anomalía individual"""
    nombre = det.get("indicador", "?")
    emoji = det.get("emoji", "📊")
    sev = det.get("severidad", "normal")
    valor = det.get("valor_actual")
    unidad = det.get("unidad", "")
    fecha = det.get("fecha_dato", "")
    avg_hist = det.get("promedio_hist_30d")
    delta_h = det.get("delta_hist_pct", 0)
    predicho = det.get("valor_predicho")
    delta_p = det.get("delta_pred_pct")
    desv = det.get("desviacion_pct", 0)
    pred_excluida = det.get("prediccion_excluida", False)
    nivel_pred = det.get("nivel_confianza_prediccion", "").replace("_", " ")
    motivo = det.get("motivo_exclusion", "")
    comentario = det.get("comentario_confianza", "")

    sev_emoji = {'crítico': '🔴', 'alerta': '🟠', 'normal': '🟢'}
    sev_txt = sev.upper() if sev != "normal" else "Normal"

    text = f"{sev_emoji.get(sev, '⚪')} {emoji} *{nombre}* — {sev_txt}\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if valor is not None:
        text += f"▸ Valor actual: *{_r(valor)} {unidad}* ({fecha})\n"
    if avg_hist is not None:
        text += f"▸ Promedio 30d: {_r(avg_hist)} {unidad}\n"
        text += f"▸ Desvío vs histórico: *{_r(delta_h, 1)}%*\n"
    text += "\n"

    if predicho is not None and not pred_excluida:
        text += f"▸ Predicción: {_r(predicho)} {unidad}\n"
        if delta_p is not None:
            text += f"▸ Desvío vs predicción: {_r(delta_p, 1)}%\n"
        text += f"▸ Confianza modelo: {nivel_pred}\n"
    elif pred_excluida:
        text += "▸ Predicción excluida de severidad\n"
        if motivo:
            text += f"▸ Motivo: {motivo}\n"
        if comentario:
            text += f"▸ {comentario}\n"
        text += f"▸ Nivel modelo: {nivel_pred}\n"
    else:
        text += "▸ Predicción: no disponible\n"
    text += "\n"

    text += f"▸ Desvío máximo: *{_r(desv, 1)}%*\n"
    text += f"▸ Severidad: *{sev_txt}*\n"

    keyboard = [
        [InlineKeyboardButton("← Volver a resumen", callback_data="anom_back")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ── FASE C: Helpers para informe ejecutivo interactivo ────

def _parse_informe_sections(informe: str) -> dict:
    """Parse IA informe text into numbered sections.
    
    Soporta dos formatos:
      - IA:       ## 1. Título de sección
      - Fallback: *1. Título de sección*
    """
    import re as _re
    sections = {}

    # Intentar formato IA primero (## headers)
    markers = list(_re.finditer(r'^##\s*(\d+)\.\s*(.+)$', informe, flags=_re.MULTILINE))

    # Si no hay ## headers, intentar formato fallback (*N. Titulo*)
    if not markers:
        markers = list(_re.finditer(
            r'^\*?(\d+)\.\s*(.+?)\*?$',
            informe,
            flags=_re.MULTILINE,
        ))
        # Filtrar solo las que realmente parecen títulos de sección (1-4)
        markers = [m for m in markers if 1 <= int(m.group(1)) <= 5]

    for i, m in enumerate(markers):
        num = int(m.group(1))
        title = m.group(2).strip().rstrip('*')
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(informe)
        content = informe[start:end].strip()
        sections[num] = {'title': title, 'content': content}
    return sections


def render_informe_ejecutivo(data: dict) -> tuple:
    """
    FASE C: Render cabecera del informe con botones de sección.
    El usuario navega por secciones en vez de recibir todo el texto de golpe.
    """
    fecha_gen = data.get("fecha_generacion", "")
    con_ia = data.get("generado_con_ia", False)
    informe = data.get("informe", "")

    text = "📊 *Informe Ejecutivo del Sector Eléctrico*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if fecha_gen:
        text += f"🕐 {fecha_gen}"
        if con_ia:
            text += "  •  Asistido por IA"
        text += "\n"
    text += "\n"

    if informe:
        text += "Selecciona una sección para ver el detalle:\n"
    else:
        text += "No se pudo generar el informe.\n"

    if data.get("nota_fallback"):
        text += f"\n⚠️ _{data['nota_fallback']}_\n"

    keyboard = [
        [InlineKeyboardButton("1️⃣ Contexto", callback_data="inf_sec:1"),
         InlineKeyboardButton("2️⃣ Señales", callback_data="inf_sec:2"),
         InlineKeyboardButton("3️⃣ Riesgos", callback_data="inf_sec:3")],
        [InlineKeyboardButton("4️⃣ Recomend.", callback_data="inf_sec:4"),
         InlineKeyboardButton("5️⃣ Cierre", callback_data="inf_sec:5")],
        [InlineKeyboardButton("📄 Ver informe completo", callback_data="inf_sec:full"),
         InlineKeyboardButton("📥 Descargar PDF", callback_data="inf_pdf")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


def render_informe_seccion(sections: dict, num: int) -> tuple:
    """FASE C: Render una sección individual con navegación"""
    import re as _re
    section = sections.get(num, {})
    title = section.get('title', f'Sección {num}')
    content = section.get('content', 'No disponible.')

    # Limpiar markdown para Telegram
    content_clean = _re.sub(r'\*\*(.+?)\*\*', r'*\1*', content)
    content_clean = _re.sub(r'^###\s*(.+)$', r'_\1_', content_clean, flags=_re.MULTILINE)

    text = f"📊 *{num}. {title}*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += content_clean + "\n"

    # Navegación: Anterior / Siguiente
    nav_row = []
    if num > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"inf_sec:{num - 1}"))
    if num < 5:
        nav_row.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"inf_sec:{num + 1}"))

    # Selector de secciones
    sec_btns = []
    for i in range(1, 6):
        label = f"▸{i}" if i == num else str(i)
        sec_btns.append(InlineKeyboardButton(label, callback_data=f"inf_sec:{i}"))

    keyboard = []
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append(sec_btns)
    keyboard.append([InlineKeyboardButton("📄 Completo", callback_data="inf_sec:full")])
    keyboard.append([InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")])
    return text, InlineKeyboardMarkup(keyboard)


def render_informe_completo(data: dict) -> tuple:
    """FASE C: Informe completo — LEGACY, redirige a cards"""
    # Mantener por compatibilidad; cmd_informe ahora usa render_informe_cards
    cards = render_informe_cards(data)
    if cards:
        # Unir todas las cards en un solo texto (fallback)
        text = "\n\n".join(c[0] for c in cards)
        keyboard = cards[-1][1]
        return text, keyboard
    return "No se pudo generar el informe.", InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]]
    )


def render_informe_cards(data: dict) -> list:
    """
    Render informe ejecutivo como lista de tarjetas (mensajes separados).
    Retorna: list of (text, keyboard_or_None)
    Cada elemento es un mensaje independiente para enviar en secuencia.
    """
    import re as _re
    informe = data.get("informe", "")
    fecha_gen = data.get("fecha_generacion", "")
    con_ia = data.get("generado_con_ia", False)

    if not informe:
        text = "❌ No se pudo generar el informe.\n"
        if data.get("nota_fallback"):
            text += f"\n⚠️ _{data['nota_fallback']}_\n"
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]]
        )
        return [(text, kb)]

    # Parsear secciones del informe de IA
    sections = _parse_informe_sections(informe)
    cards = []

    # ── Card 0: Header ──
    header = "📊 *Informe Ejecutivo del Sector Eléctrico*\n"
    header += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if fecha_gen:
        header += f"🕐 {fecha_gen}"
        if con_ia:
            header += "  •  Asistido por IA"
        header += "\n"
    header += "\n"
    header += "📋 Informe completo en 5 secciones:\n"
    header += "▸ 1️⃣ Contexto general\n"
    header += "▸ 2️⃣ Señales clave\n"
    header += "▸ 3️⃣ Riesgos y oportunidades\n"
    header += "▸ 4️⃣ Recomendaciones técnicas\n"
    header += "▸ 5️⃣ Cierre ejecutivo\n"
    if data.get("nota_fallback"):
        header += f"\n⚠️ _{data['nota_fallback']}_\n"
    cards.append((header, None))

    # Emojis y decoración por sección
    sec_config = {
        1: {"emoji": "📍", "title_fallback": "Contexto general del sistema"},
        2: {"emoji": "📈", "title_fallback": "Señales clave y evolución reciente"},
        3: {"emoji": "⚠️", "title_fallback": "Riesgos y oportunidades"},
        4: {"emoji": "✅", "title_fallback": "Recomendaciones técnicas"},
        5: {"emoji": "🎯", "title_fallback": "Cierre ejecutivo"},
    }

    for num in range(1, 6):
        cfg = sec_config.get(num, {"emoji": "📌", "title_fallback": f"Sección {num}"})
        sec = sections.get(num)
        if sec:
            title = sec["title"]
            content = sec["content"]
        else:
            title = cfg["title_fallback"]
            content = "Información no disponible."

        # Limpiar markdown de IA → Telegram Markdown v1
        content_clean = _re.sub(r'\*\*(.+?)\*\*', r'*\1*', content)
        # ### subtítulos → emoji + negrita
        content_clean = _re.sub(
            r'^###?\s*\d*\.?\d*\s*(.+)$',
            lambda m: f"\n{'─' * 20}\n{cfg['emoji']} *{m.group(1).strip()}*",
            content_clean,
            flags=_re.MULTILINE,
        )
        # Reemplazar guiones de lista con ▸ 
        content_clean = _re.sub(
            r'^[\-•]\s*',
            '▸ ',
            content_clean,
            flags=_re.MULTILINE,
        )
        # Limpiar underscores en nombres tipo MUY_CONFIABLE
        content_clean = content_clean.replace("MUY_CONFIABLE", "MUY CONFIABLE")
        content_clean = content_clean.replace("PRECIO_BOLSA", "PRECIO DE BOLSA")

        # Construir la tarjeta
        card = f"{cfg['emoji']} *{num}. {title}*\n"
        card += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        card += content_clean.strip() + "\n"

        cards.append((card, None))

    # ── Card final: Botones ──
    final = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    final += "📊 _Fin del informe ejecutivo_\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Descargar PDF", callback_data="inf_pdf")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")],
    ])
    cards.append((final, kb))

    return cards


def render_mas_informacion_submenu() -> tuple:
    """Submenú de 'Más información'"""
    text = "📋 *Más Información del Sector*\n\n¿Qué información necesitas?\n"
    keyboard = [
        [InlineKeyboardButton("📊 Informe ejecutivo completo", callback_data="intent:informe_ejecutivo")],
        [InlineKeyboardButton("❓ Hacer una pregunta libre", callback_data="action:pregunta_libre_prompt")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ── Emojis rotativos para noticias (variedad visual) ──
_NEWS_EMOJIS = ["⚡", "🌞", "🔥", "💡", "🏭", "🌊"]


def render_noticias(data: dict) -> tuple:
    """
    Renderiza noticias del sector energético – formato profesional
    orientado al Viceministro/Ministro.

    Cada noticia: emoji + título negrita, resumen itálica (≤180 chars),
    fuente/fecha, y botón URL individual "Leer la noticia".
    Incluye resumen IA si disponible y botón "Ver más" si hay extras.
    """
    noticias = data.get("noticias", [])
    otras = data.get("otras_noticias", [])
    resumen_ia = data.get("resumen_general")
    nota = data.get("nota", "")

    text = "📰 *Noticias clave del sector energético*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if not noticias:
        text += (
            nota
            or "Hoy no se encontraron noticias relevantes "
               "sobre el sector energético.\n"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Actualizar", callback_data="news_refresh")],
            [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")],
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # Resumen ejecutivo IA (si disponible)
    if resumen_ia:
        text += "🧠 *Panorama del día*\n"
        text += f"_{resumen_ia}_\n\n"
        text += "─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n\n"

    keyboard = []
    for i, noticia in enumerate(noticias, 1):
        titulo = noticia.get("titulo", "Sin título")
        resumen = noticia.get("resumen", noticia.get("resumen_corto", ""))
        fuente = noticia.get("fuente", "")
        fecha = noticia.get("fecha", noticia.get("fecha_publicacion", ""))
        url = noticia.get("url", "")

        # Emoji rotativo por posición
        emoji = _NEWS_EMOJIS[(i - 1) % len(_NEWS_EMOJIS)]

        # Título en negrita con emoji
        text += f"{i}) {emoji} *{titulo}*\n"

        # Resumen en itálica (máx 180 chars)
        if resumen:
            if len(resumen) > 180:
                resumen = resumen[:177].rstrip() + "…"
            text += f"_{resumen}_\n"

        # Fuente y fecha
        meta = []
        if fuente:
            meta.append(f"🏷 {fuente}")
        if fecha:
            # Normalizar fecha ISO → YYYY-MM-DD
            fecha_fmt = fecha[:10] if len(fecha) >= 10 else fecha
            meta.append(f"📅 {fecha_fmt}")
        if meta:
            text += f"{'  ·  '.join(meta)}\n"

        text += "\n"

        # Botón URL individual para cada noticia
        if url:
            keyboard.append([InlineKeyboardButton(
                f"🔗 Leer noticia {i}",
                url=url
            )])

    # Botones de acción al final
    action_row = [
        InlineKeyboardButton("🔄 Actualizar", callback_data="news_refresh"),
    ]
    if otras:
        action_row.insert(0, InlineKeyboardButton(
            f"📚 Ver más ({len(otras)})",
            callback_data="news_more",
        ))
    keyboard.append(action_row)
    keyboard.append([
        InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu"),
    ])
    return text, InlineKeyboardMarkup(keyboard)


def render_noticias_extra(data: dict) -> tuple:
    """
    Renderiza la lista extendida de noticias ("otras_noticias").
    Formato compacto: número + título + fuente, con botones URL.
    """
    otras = data.get("otras_noticias", [])

    text = "📚 *Más noticias del sector energético*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if not otras:
        text += "No hay noticias adicionales disponibles.\n"
        keyboard = [[InlineKeyboardButton(
            "⬅ Volver a principales", callback_data="news_back"
        )]]
        return text, InlineKeyboardMarkup(keyboard)

    keyboard = []
    for i, noticia in enumerate(otras, 1):
        titulo = noticia.get("titulo", "Sin título")
        fuente = noticia.get("fuente", "")
        fecha = noticia.get("fecha", noticia.get("fecha_publicacion", ""))
        url = noticia.get("url", "")

        emoji = _NEWS_EMOJIS[(i - 1) % len(_NEWS_EMOJIS)]
        text += f"{i}) {emoji} *{titulo}*\n"

        meta = []
        if fuente:
            meta.append(f"🏷 {fuente}")
        if fecha:
            fecha_fmt = fecha[:10] if len(fecha) >= 10 else fecha
            meta.append(f"📅 {fecha_fmt}")
        if meta:
            text += f"{'  ·  '.join(meta)}\n"
        text += "\n"

        if url:
            keyboard.append([InlineKeyboardButton(
                f"🔗 Leer noticia {i}", url=url
            )])

    keyboard.append([
        InlineKeyboardButton("⬅ Volver a principales", callback_data="news_back"),
        InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu"),
    ])
    return text, InlineKeyboardMarkup(keyboard)


# ── FASE D: Pregunta libre guiada ────────────────────────

def render_pregunta_datos(data: dict) -> tuple:
    """FASE D: Render datos estructurados de pregunta_libre con botón IA"""
    pregunta = data.get("pregunta", "")
    datos = data.get("datos_consultados", {})

    text = "📋 *Datos del Sistema Energético*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    if pregunta:
        text += f'_"{pregunta}"_\n\n'

    if not datos:
        text += "No se encontraron datos relevantes para tu pregunta.\n"
    else:
        for tema, valores in datos.items():
            nombre = tema.replace('_', ' ').replace('prediccion ', '📈 Pred. ').title()
            text += f"▸ *{nombre}*\n"
            if isinstance(valores, dict):
                for k, v in valores.items():
                    if v is None:
                        continue
                    clave = (k.replace('_', ' ')
                              .replace('cop kwh', 'COP/kWh')
                              .replace('gwh', 'GWh')
                              .replace('pct', '%')
                              .title())
                    text += f"   {clave}: {v}\n"
            text += "\n"

    keyboard = [
        [InlineKeyboardButton("🧠 Ver análisis con IA", callback_data="qa_ia")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


def render_pregunta_ia(data: dict) -> tuple:
    """FASE D: Render análisis IA de pregunta_libre con botón volver"""
    import re as _re
    analisis = data.get("analisis_ia", "")
    pregunta = data.get("pregunta", "")

    text = "🧠 *Análisis con IA*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    if pregunta:
        text += f'_"{pregunta}"_\n\n'

    if analisis:
        analisis_clean = _re.sub(r'\*\*(.+?)\*\*', r'*\1*', analisis)
        analisis_clean = _re.sub(r'^###\s*(.+)$', r'_\1_', analisis_clean, flags=_re.MULTILINE)
        text += analisis_clean + "\n"
    else:
        text += "No se pudo generar el análisis. Intenta de nuevo.\n"

    keyboard = [
        [InlineKeyboardButton("⬅ Volver a datos", callback_data="qa_datos")],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


def render_generic(data: dict, intent: str) -> tuple:
    """Renderizado genérico para intents sin renderizador propio"""
    text = ""
    if isinstance(data, dict):
        for key in ["mensaje", "body", "texto", "message", "resumen", "contenido", "informe"]:
            if key in data and isinstance(data[key], str):
                text = data[key]
                break
        if not text:
            text = f"📋 *Resultado: {intent}*\n\n"
            for k, v in data.items():
                if k in ("opcion_regresar", "fecha_consulta", "timestamp"):
                    continue
                if isinstance(v, str) and len(v) < 500:
                    text += f"▸ *{k}*: {v}\n"
                elif isinstance(v, (int, float)):
                    text += f"▸ *{k}*: {v}\n"
                elif isinstance(v, list):
                    text += f"\n*{k}:*\n"
                    for item in v[:10]:
                        if isinstance(item, dict):
                            parts = [f"{ik}: {iv}" for ik, iv in list(item.items())[:3]
                                     if ik != "opcion_regresar"]
                            text += f"  • {', '.join(parts)}\n"
                        else:
                            text += f"  • {item}\n"
    else:
        text = str(data)

    if not text.strip():
        text = "Respuesta recibida del orquestador."

    regresar = data.get("opcion_regresar", {}) if isinstance(data, dict) else {}
    keyboard = [[InlineKeyboardButton(
        regresar.get("titulo", "🔙 Menú principal"), callback_data="intent:menu"
    )]]
    return text, InlineKeyboardMarkup(keyboard)


def render_response(intent: str, result: dict) -> tuple:
    """Dispatch de renderizado según intent"""
    if result.get("status") != "SUCCESS":
        error_msg = result.get("message", "Error desconocido")
        text = f"❌ Error: {error_msg}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")
        ]])
        return text, keyboard

    data = result.get("data", {})

    if intent in ("menu", "ayuda", "help", "start", "inicio"):
        return render_menu(data)
    elif intent == "estado_actual":
        return render_fichas(data)
    elif intent == "predicciones_sector":
        # Si tiene resultados de predicción, renderizar; sino submenú
        if any(k in data for k in ("predicciones", "fichas_prediccion", "fichas")):
            return render_predicciones_resultado(data)
        return render_predicciones_submenu()
    elif intent in ("anomalias_sector", "anomalias_detectadas", "alertas"):
        return render_anomalias(data)
    elif intent in ("noticias_sector", "noticias", "news"):
        return render_noticias(data)
    elif intent in ("informe_ejecutivo", "generar_informe", "informe_completo", "reporte_ejecutivo"):
        return render_informe_ejecutivo(data)
    elif intent == "mas_informacion":
        return render_mas_informacion_submenu()
    else:
        return render_generic(data, intent)


# ═══════════════════════════════════════════════════════════
# Telegram Handlers
# ═══════════════════════════════════════════════════════════

async def _safe_send(chat, text: str, keyboard=None):
    """Envía mensaje con fallback a sin-markdown si falla el parse"""
    if len(text) > 4096:
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for i, chunk in enumerate(chunks):
            kb = keyboard if i == len(chunks) - 1 else None
            try:
                await chat.send_message(chunk, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            except Exception:
                await chat.send_message(chunk, reply_markup=kb)
    else:
        try:
            await chat.send_message(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception:
            await chat.send_message(text, reply_markup=keyboard)


async def send_orchestrated(chat, user, intent: str, parameters: dict = None):
    """Llama al orquestador y envía la respuesta renderizada"""
    track_telegram_user(user.id, user.username, user.first_name)
    await chat.send_action("typing")
    result = await call_orchestrator(get_session_id(user.id), intent, parameters)
    text, keyboard = render_response(intent, result)
    await _safe_send(chat, text, keyboard)


# ── Comandos ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_orchestrated(update.effective_chat, update.effective_user, "menu")

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_orchestrated(update.effective_chat, update.effective_user, "menu")

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_orchestrated(update.effective_chat, update.effective_user, "estado_actual")

async def cmd_predicciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_telegram_user(update.effective_user.id, update.effective_user.username, update.effective_user.first_name)
    text, kb = render_predicciones_submenu()
    await _safe_send(update.effective_chat, text, kb)

async def cmd_anomalias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # FASE B: Cache anomalías for inline detail buttons
    user = update.effective_user
    chat = update.effective_chat
    track_telegram_user(user.id, user.username, user.first_name)
    await chat.send_action("typing")
    result = await call_orchestrator(get_session_id(user.id), "anomalias_sector")
    if result.get("status") == "SUCCESS":
        result_data = result.get("data", {})
        context.user_data["anomalias_cache"] = result_data
        text, kb = render_anomalias(result_data)
    else:
        text, kb = render_response("anomalias_sector", result)
    await _safe_send(chat, text, kb)

async def _send_informe_with_charts(chat, result_data: dict):
    """
    Envía el informe ejecutivo como tarjetas + gráficos intercalados.
    Genera los 3 charts en paralelo con la renderización de cards.

    Orden de envío:
      Card 0  (header)
      Card 1  (sec. 1 — Situación actual)
      ─── 📊 Pie Generación ───
      ─── 🗺️ Mapa Embalses  ───
      ─── 💰 Precio Evolución ───
      Card 2  (sec. 2 — Tendencias)
      Card 3  (sec. 3 — Riesgos)
      Card 4  (sec. 4 — Recomendaciones)
      Card 5  (footer + botones)

    Los 3 gráficos se envían juntos justo después de la
    sección 1 (Situación actual) para mantener coherencia visual.
    """
    import os as _os

    cards = render_informe_cards(result_data)

    # Generar gráficos en hilo aparte (Plotly + kaleido son sync)
    charts = {}
    try:
        from services.informe_charts import generate_all_informe_charts
        charts = await asyncio.to_thread(generate_all_informe_charts)
    except Exception as e:
        logger.warning(f"[INFORME] No se pudieron generar gráficos: {e}")

    # Orden de gráficos a enviar después de la sección 1 (card index 1)
    chart_order = ['generacion', 'embalses', 'precios']

    for idx, (card_text, card_kb) in enumerate(cards):
        await _safe_send(chat, card_text, card_kb)

        # Después de card 1 (Sección 1: Situación actual) → enviar los 3 gráficos
        if idx == 1 and charts:
            for chart_key in chart_order:
                if chart_key in charts:
                    filepath, caption, _ = charts[chart_key]
                    if filepath and _os.path.exists(filepath):
                        try:
                            with open(filepath, 'rb') as img:
                                await chat.send_photo(photo=img, caption=caption)
                        except Exception as e:
                            logger.warning(f"[INFORME] Error enviando gráfico {chart_key}: {e}")


async def cmd_informe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mostrar informe como tarjetas + gráficos
    user = update.effective_user
    chat = update.effective_chat
    track_telegram_user(user.id, user.username, user.first_name)
    await chat.send_action("typing")
    result = await call_orchestrator(get_session_id(user.id), "informe_ejecutivo")
    if result.get("status") == "SUCCESS":
        result_data = result.get("data", {})
        context.user_data["informe_data"] = result_data
        await _send_informe_with_charts(chat, result_data)
    else:
        text, kb = render_response("informe_ejecutivo", result)
        await _safe_send(chat, text, kb)

async def cmd_noticias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_orchestrated(update.effective_chat, update.effective_user, "noticias_sector")

async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_telegram_user(update.effective_user.id, update.effective_user.username, update.effective_user.first_name)
    help_text = """❓ *Ayuda del Bot — Portal Energético MME*

*Comandos:*
📊 /estado — Estado actual del sector
🔮 /predicciones — Predicciones del sector
🚨 /anomalias — Anomalías detectadas
📰 /noticias — Noticias clave del sector
📋 /informe — Informe ejecutivo completo
🔙 /menu — Menú principal
❓ /ayuda — Esta ayuda

*También puedes:*
• Tocar los botones interactivos
• Escribir tu pregunta en lenguaje natural

_Ejemplo: "¿Cómo está la generación hoy?"_"""
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]])
    await _safe_send(update.effective_chat, help_text, kb)


# ── Callbacks de botones ──────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user
    chat = query.message.chat

    logger.info(f"[CB] {user.id} (@{user.username}): {data}")

    if data.startswith("intent:"):
        intent = data.split(":", 1)[1]

        # Submenús que no necesitan llamar al orquestador
        if intent == "predicciones_sector":
            track_telegram_user(user.id, user.username, user.first_name)
            text, kb = render_predicciones_submenu()
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)
            return

        if intent == "mas_informacion":
            track_telegram_user(user.id, user.username, user.first_name)
            text, kb = render_mas_informacion_submenu()
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)
            return

        # Informe ejecutivo — mostrar como tarjetas + gráficos
        if intent in ("informe_ejecutivo", "generar_informe", "informe_completo", "reporte_ejecutivo"):
            track_telegram_user(user.id, user.username, user.first_name)
            await chat.send_action("typing")
            result = await call_orchestrator(get_session_id(user.id), intent)
            if result.get("status") == "SUCCESS":
                result_data = result.get("data", {})
                context.user_data["informe_data"] = result_data
                await _send_informe_with_charts(chat, result_data)
            else:
                text = f"❌ {result.get('message', 'Error desconocido')}"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔙 Menú", callback_data="intent:menu"
                )]])
                await _safe_send(chat, text, kb)
            return

        # Noticias del sector — editMessageText para que 🔄 Actualizar funcione in-place
        if intent in ("noticias_sector", "noticias", "news"):
            track_telegram_user(user.id, user.username, user.first_name)
            await chat.send_action("typing")
            result = await call_orchestrator(get_session_id(user.id), "noticias_sector")
            if result.get("status") == "SUCCESS":
                news_data = result.get("data", {})
                context.user_data["news_cache"] = news_data
                text, kb = render_noticias(news_data)
            else:
                text = f"❌ {result.get('message', 'Error al obtener noticias')}"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔙 Menú", callback_data="intent:menu"
                )]])
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)
            return

        # FASE B: Anomalías con cache para detalle inline
        if intent in ("anomalias_sector", "anomalias_detectadas", "alertas"):
            track_telegram_user(user.id, user.username, user.first_name)
            await chat.send_action("typing")
            result = await call_orchestrator(get_session_id(user.id), intent)
            if result.get("status") == "SUCCESS":
                result_data = result.get("data", {})
                context.user_data["anomalias_cache"] = result_data
                text, kb = render_anomalias(result_data)
            else:
                text = f"❌ {result.get('message', 'Error desconocido')}"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔙 Menú", callback_data="intent:menu"
                )]])
            await _safe_send(chat, text, kb)
            return

        # Enviar al orquestador
        await send_orchestrated(chat, user, intent)

    elif data.startswith("pred:"):
        horizonte = data.split(":", 1)[1]

        if horizonte == "personalizado":
            track_telegram_user(user.id, user.username, user.first_name)
            context.user_data["awaiting_custom_date"] = True
            text = (
                "📅 *Fecha Personalizada*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Escribe la fecha objetivo en formato *DD-MM-AAAA*\n\n"
                "*Ejemplos:*\n"
                "• _15-03-2026_ → predicción a 1 mes\n"
                "• _01-08-2026_ → predicción a 6 meses\n"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancelar", callback_data="intent:predicciones_sector")]])
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)
            return

        # FASE B: Call orchestrator and edit message in-place
        track_telegram_user(user.id, user.username, user.first_name)
        await chat.send_action("typing")
        result = await call_orchestrator(
            get_session_id(user.id), "predicciones_sector", {"horizonte": horizonte}
        )
        if result.get("status") == "SUCCESS":
            text, kb = render_predicciones_resultado(
                result.get("data", {}), current_horizonte=horizonte
            )
        else:
            text = f"❌ Error: {result.get('message', 'Error desconocido')}"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                "🔙 Menú principal", callback_data="intent:menu"
            )]])
        try:
            await query.edit_message_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb
            )
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    elif data.startswith("action:"):
        action = data.split(":", 1)[1]

        if action == "pregunta_libre_prompt":
            track_telegram_user(user.id, user.username, user.first_name)
            text = (
                "❓ *Pregunta Libre*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Escribe tu pregunta y te mostraré datos reales "
                "del sistema energético.\n\n"
                "*Ejemplos:*\n"
                "• _¿Cómo ha variado el precio de bolsa esta semana?_\n"
                "• _¿Cuánta energía solar se generó ayer?_\n"
                "• _¿Cuál es el nivel actual de embalses?_\n"
                "• _¿Qué predicciones hay para la demanda?_\n"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menú principal", callback_data="intent:menu")]])
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    # FASE B: Anomalías — detalle inline y volver a resumen
    elif data.startswith("anom_det:"):
        idx = int(data.split(":", 1)[1])
        track_telegram_user(user.id, user.username, user.first_name)
        cached = context.user_data.get("anomalias_cache")
        if not cached:
            await chat.send_action("typing")
            result = await call_orchestrator(get_session_id(user.id), "anomalias_sector")
            cached = result.get("data", {}) if result.get("status") == "SUCCESS" else {}
            context.user_data["anomalias_cache"] = cached
        detalle = cached.get("detalle_completo", [])
        det = detalle[idx] if idx < len(detalle) else None
        if det:
            text, kb = render_anomalia_detalle(det)
        else:
            text = "No se encontró el detalle solicitado."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("← Volver", callback_data="anom_back")]])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    elif data == "anom_back":
        track_telegram_user(user.id, user.username, user.first_name)
        cached = context.user_data.get("anomalias_cache")
        if not cached:
            await chat.send_action("typing")
            result = await call_orchestrator(get_session_id(user.id), "anomalias_sector")
            cached = result.get("data", {}) if result.get("status") == "SUCCESS" else {}
            context.user_data["anomalias_cache"] = cached
        text, kb = render_anomalias(cached)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    # FASE C: Informe ejecutivo — descargar PDF
    elif data == "inf_pdf":
        track_telegram_user(user.id, user.username, user.first_name)
        informe_data = context.user_data.get("informe_data", {})
        informe_texto = informe_data.get("informe", "")
        if not informe_texto:
            await _safe_send(chat, "No hay informe en cache. Genera uno nuevo con /informe", None)
            return

        await chat.send_action("upload_document")
        try:
            # Generar gráficos para incrustar en el PDF
            chart_paths = []
            try:
                from services.informe_charts import generate_all_informe_charts
                charts = await asyncio.to_thread(generate_all_informe_charts)
                for key in ['generacion', 'embalses', 'precios']:
                    if key in charts:
                        filepath = charts[key][0]
                        if filepath:
                            chart_paths.append(filepath)
            except Exception as ce:
                logger.warning(f"[PDF] No se pudieron generar gráficos para PDF: {ce}")

            # Extraer datos estructurados del contexto para PDF completo
            ctx = informe_data.get("contexto_datos", {})
            _fichas = ctx.get("estado_actual", {}).get("fichas", [])
            _noticias = ctx.get("noticias", {}).get("noticias", []) if isinstance(ctx.get("noticias"), dict) else []
            _anomalias_raw = ctx.get("anomalias", {})
            _anomalias = _anomalias_raw.get("lista", []) if isinstance(_anomalias_raw, dict) else []

            # Extraer predicciones multi-métrica del contexto
            # El contexto tiene fichas (resumen), no el formato API (estadisticas/predicciones[])
            # Transformar fichas → formato esperado por el PDF
            _predicciones_list = []
            pred_ctx = ctx.get("predicciones", {})
            if isinstance(pred_ctx, dict):
                mes_data = pred_ctx.get("1_mes", {})
                if isinstance(mes_data, dict):
                    for ind in mes_data.get("indicadores", []):
                        if not isinstance(ind, dict) or not ind.get("confiable"):
                            continue
                        resumen = ind.get("resumen", {})
                        if not resumen:
                            continue
                        _predicciones_list.append({
                            "fuente": ind.get("indicador", "General"),
                            "fuente_label": ind.get("indicador", "General"),
                            "estadisticas": {
                                "promedio_gwh": resumen.get("promedio_periodo", 0),
                                "minimo_gwh": resumen.get("minimo_periodo", 0),
                                "maximo_gwh": resumen.get("maximo_periodo", 0),
                            },
                            "total_predicciones": ind.get("total_dias_prediccion", 0),
                            "modelo": "ENSEMBLE_v1.0",
                            "predicciones": [],  # No day-by-day data available from fichas
                        })
            _predicciones = _predicciones_list if _predicciones_list else None

            from domain.services.report_service import generar_pdf_informe
            pdf_path = generar_pdf_informe(
                informe_texto,
                fecha_generacion=informe_data.get("fecha_generacion", ""),
                generado_con_ia=informe_data.get("generado_con_ia", True),
                chart_paths=chart_paths,
                fichas=_fichas or None,
                predicciones=_predicciones,
                anomalias=_anomalias or None,
                noticias=_noticias or None,
                contexto_datos=ctx or None,
            )
            if pdf_path:
                import os
                from datetime import date as _date
                filename = f"Informe_Ejecutivo_MME_{_date.today().isoformat()}.pdf"
                with open(pdf_path, "rb") as pdf_file:
                    await chat.send_document(
                        document=pdf_file,
                        filename=filename,
                        caption="📊 Informe Ejecutivo del Sector Eléctrico — MME",
                    )
                # Limpiar archivo temporal
                try:
                    os.remove(pdf_path)
                except OSError:
                    pass
                logger.info(f"[PDF] Enviado a {user.id} (@{user.username})")
            else:
                await _safe_send(
                    chat,
                    "❌ Error al generar el PDF. Intenta de nuevo.",
                    InlineKeyboardMarkup([[InlineKeyboardButton(
                        "🔙 Menú", callback_data="intent:menu"
                    )]]),
                )
        except Exception as e:
            logger.error(f"[PDF] Error: {e}", exc_info=True)
            await _safe_send(
                chat,
                "❌ No se pudo generar el PDF.",
                InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔙 Menú", callback_data="intent:menu"
                )]]),
            )

    # FASE C: Informe ejecutivo — navegación por secciones
    elif data.startswith("inf_sec:"):
        section = data.split(":", 1)[1]
        track_telegram_user(user.id, user.username, user.first_name)

        if section == "full":
            informe_data = context.user_data.get("informe_data", {})
            if informe_data:
                text, kb = render_informe_completo(informe_data)
            else:
                text = "Informe no disponible. Genera uno nuevo con /informe"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔙 Menú", callback_data="intent:menu"
                )]])
        elif section.isdigit():
            num = int(section)
            sections = context.user_data.get("informe_sections", {})
            if sections:
                text, kb = render_informe_seccion(sections, num)
            else:
                text = "Secciones no disponibles. Genera un informe con /informe"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔙 Menú", callback_data="intent:menu"
                )]])
        else:
            return

        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    # Noticias — botón "🔄 Actualizar" refresca en el mismo mensaje
    elif data == "news_refresh":
        track_telegram_user(user.id, user.username, user.first_name)
        await chat.send_action("typing")
        result = await call_orchestrator(get_session_id(user.id), "noticias_sector")
        if result.get("status") == "SUCCESS":
            news_data = result.get("data", {})
            context.user_data["news_cache"] = news_data
            text, kb = render_noticias(news_data)
        else:
            text = "❌ No se pudieron actualizar las noticias."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                "🔙 Menú", callback_data="intent:menu"
            )]])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    # Noticias — botón "📚 Ver más" muestra lista extendida
    elif data == "news_more":
        track_telegram_user(user.id, user.username, user.first_name)
        cached = context.user_data.get("news_cache", {})
        text, kb = render_noticias_extra(cached)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    # Noticias — botón "⬅ Volver a principales"
    elif data == "news_back":
        track_telegram_user(user.id, user.username, user.first_name)
        cached = context.user_data.get("news_cache", {})
        if cached:
            text, kb = render_noticias(cached)
        else:
            # Si no hay cache, recarga desde API
            await chat.send_action("typing")
            result = await call_orchestrator(get_session_id(user.id), "noticias_sector")
            if result.get("status") == "SUCCESS":
                news_data = result.get("data", {})
                context.user_data["news_cache"] = news_data
                text, kb = render_noticias(news_data)
            else:
                text = "❌ No se pudieron cargar las noticias."
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🔙 Menú", callback_data="intent:menu"
                )]])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    # FASE D: Pregunta libre — análisis IA y volver a datos
    elif data == "qa_ia":
        track_telegram_user(user.id, user.username, user.first_name)
        cached = context.user_data.get("pregunta_cache", {})
        pregunta = cached.get("pregunta", "")
        if not pregunta:
            await _safe_send(chat, "Escribe una pregunta primero.", None)
            return
        await chat.send_action("typing")
        result = await call_orchestrator(
            get_session_id(user.id), "pregunta_libre",
            {"pregunta": pregunta, "con_analisis_ia": True}
        )
        if result.get("status") == "SUCCESS":
            result_data = result.get("data", {})
            context.user_data["pregunta_cache"] = result_data
            text, kb = render_pregunta_ia(result_data)
        else:
            text = "❌ No se pudo generar el análisis."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menú", callback_data="intent:menu")]])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)

    elif data == "qa_datos":
        track_telegram_user(user.id, user.username, user.first_name)
        cached = context.user_data.get("pregunta_cache", {})
        if cached:
            text, kb = render_pregunta_datos(cached)
        else:
            text = "No hay datos en cache. Escribe una nueva pregunta."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menú", callback_data="intent:menu")]])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except Exception:
                await _safe_send(chat, text, kb)


# ── Texto libre ───────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    message = update.message.text.strip()

    logger.info(f"[TEXT] {user.id} (@{user.username}): {message}")
    track_telegram_user(user.id, user.username, user.first_name)

    # ¿Esperando fecha personalizada?
    if context.user_data.get("awaiting_custom_date"):
        context.user_data["awaiting_custom_date"] = False
        if re.match(r'^\d{2}-\d{2}-\d{4}$', message):
            await send_orchestrated(
                chat, user, "predicciones_sector",
                {"horizonte": "personalizado", "fecha_personalizada": message}
            )
        else:
            await chat.send_message(
                "⚠️ Formato inválido. Usa *DD-MM-AAAA* (ej: 15-03-2026)",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data["awaiting_custom_date"] = True
        return

    # Selección numérica (1-5) → atajos del menú
    if message in ("1", "2", "3", "4", "5"):
        intent_map = {"1": "estado_actual", "2": "predicciones_sector",
                      "3": "anomalias_sector", "4": "noticias_sector",
                      "5": "mas_informacion"}
        intent = intent_map[message]
        if intent in ("predicciones_sector",):
            text, kb = render_predicciones_submenu()
            await _safe_send(chat, text, kb)
        elif intent == "mas_informacion":
            text, kb = render_mas_informacion_submenu()
            await _safe_send(chat, text, kb)
        else:
            await send_orchestrated(chat, user, intent)
        return

    # FASE D: Todo lo demás → pregunta libre con dos pasos (datos + IA)
    await chat.send_action("typing")
    result = await call_orchestrator(get_session_id(user.id), "pregunta_libre", {"pregunta": message})
    if result.get("status") == "SUCCESS":
        result_data = result.get("data", {})
        context.user_data["pregunta_cache"] = result_data
        text, kb = render_pregunta_datos(result_data)
    else:
        text = f"❌ {result.get('message', 'Error al procesar tu pregunta')}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menú", callback_data="intent:menu")]])
    await _safe_send(chat, text, kb)


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN no configurado")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("🤖 Telegram Bot v2 — Portal Energético MME")
    logger.info(f"   Modo: POLLING")
    logger.info(f"   Orquestador: {ORCHESTRATOR_ENDPOINT}")
    logger.info("=" * 60)

    async def post_init(application):
        """Registrar comandos visibles en menú de Telegram"""
        from telegram import BotCommand
        await application.bot.set_my_commands([
            BotCommand("menu", "Menú principal"),
            BotCommand("estado", "Estado actual del sector eléctrico"),
            BotCommand("predicciones", "Predicciones del sector"),
            BotCommand("anomalias", "Anomalías detectadas"),
            BotCommand("noticias", "Noticias clave del sector"),
            BotCommand("informe", "Informe ejecutivo completo"),
            BotCommand("ayuda", "Ayuda y comandos disponibles"),
        ])
        logger.info("✅ Comandos del menú registrados")

    app = Application.builder().token(token).post_init(post_init).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("predicciones", cmd_predicciones))
    app.add_handler(CommandHandler("anomalias", cmd_anomalias))
    app.add_handler(CommandHandler("noticias", cmd_noticias))
    app.add_handler(CommandHandler("informe", cmd_informe))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CommandHandler("help", cmd_ayuda))

    # Callbacks y texto
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("✅ Handlers registrados")
    logger.info("🚀 Iniciando polling...")

    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
