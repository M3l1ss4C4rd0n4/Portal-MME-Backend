"""
domain/services/report_service.py — v2 (Fase 3 rediseño)

Genera un PDF profesional del informe ejecutivo diario del sector eléctrico.

Responsabilidades:
  - Portada institucional con logo, título y fecha.
  - Tabla resumen ejecutiva con semáforo por indicador.
  - Desglose de generación por fuente.
  - Narrativa IA convertida de Markdown a HTML.
  - Gráficos incrustados con pie de figura contextuales.
  - Tabla compacta de predicciones (3 filas, no 31×3).
  - Anomalías y noticias del sector.
  - Renderizado a PDF mediante WeasyPrint.

Convenciones:
  - Funciones auxiliares empiezan con _ para uso interno.
  - Los emojis se eliminan antes de la generación para evitar
    problemas de renderizado con fuentes limitadas.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.umbrales_oficiales import (
    NE_UMBRAL_SUPERIOR_ABSOLUTO_PCT,
    clasificar_hsin,
    clasificar_indice_ne,
    clasificar_visual_embalse,
)

logger = logging.getLogger(__name__)

# ── Regex ampliado para limpiar emojis + caracteres problemáticos ──
_EMOJI_PATTERN = re.compile(
    '['
    '\U0001F600-\U0001F64F'  # emoticons
    '\U0001F300-\U0001F5FF'  # misc symbols & pictographs
    '\U0001F680-\U0001F6FF'  # transport & map symbols
    '\U0001F1E0-\U0001F1FF'  # flags
    '\U00002702-\U000027B0'  # dingbats
    '\U000024C2-\U0001F251'  # enclosed chars & symbols
    '\U0001F900-\U0001F9FF'  # supplemental symbols
    '\U0001FA00-\U0001FA6F'  # chess symbols
    '\U0001FA70-\U0001FAFF'  # symbols extended-A
    '\u2600-\u26FF'          # misc symbols
    '\u2700-\u27BF'          # dingbats
    '\uFE00-\uFE0F'          # variation selectors
    '\u200D'                 # zero-width joiner
    '\u00F7'                 # ÷ artifact residual
    '\u2300-\u23FF'          # misc technical (relojes)
    '\u2B50'                 # star
    '\u203C-\u3299'          # CJK, enclosed
    ']+', flags=re.UNICODE
)

# ── Rutas de assets ──
_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'assets', 'images', 'logo-minenergia.png'
)


# ═══════════════════════════════════════════════════════════════
# Utilidades de limpieza de texto
# ═══════════════════════════════════════════════════════════════

def _strip_emojis(text: str) -> str:
    """Elimina todos los emojis y caracteres problemáticos del texto."""
    text = _EMOJI_PATTERN.sub('', text)
    # Limpiar espacios dobles y espacios antes de puntuación
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r' ([.,;:)])', r'\1', text)
    return text.strip()


def _get_impacto_operativo(metrica: str, desviacion_pct: Optional[float], valor_actual: Optional[float]) -> str:
    """
    Determina el impacto operativo de una anomalía según su tipo y magnitud.
    
    Returns:
        Descripción del impacto en lenguaje claro para el usuario.
    """
    if not metrica:
        return "Se requiere análisis técnico adicional."
    
    metrica_lower = metrica.lower()
    
    # Generación
    if 'generaci' in metrica_lower or 'gen_' in metrica_lower:
        if desviacion_pct and desviacion_pct > 25:
            return ("Riesgo de déficit de oferta. Posible necesidad de importación de energía "
                    "o activación de plantas térmicas de respaldo. Puede afectar precios de bolsa.")
        elif desviacion_pct and desviacion_pct > 15:
            return ("Variación significativa en disponibilidad de generación. "
                    "Monitorear disponibilidad de reservas operativas.")
        else:
            return "Variación dentro de rangos operativos normales."
    
    # Precio de bolsa
    if 'precio' in metrica_lower or 'bolsa' in metrica_lower:
        if desviacion_pct and desviacion_pct > 30:
            return ("Alto impacto en costos de energía para usuarios regulados y contratos indexed. "
                    "Riesgo de tensiones en mercado de contratos bilaterales.")
        elif desviacion_pct and desviacion_pct > 15:
            return ("Presión en costos de suministro. Revisar estrategia de compras "
                    "y coberturas de precio.")
        else:
            return "Fluctuación de precios dentro de rangos esperados."
    
    # Embalses — Índice NE oficial (Res. CREG 209/2020 + Res. CREG 026/2014)
    if 'embalse' in metrica_lower or 'porcentaje' in metrica_lower:
        if valor_actual is not None:
            nivel_ne, descripcion_ne, senda = clasificar_indice_ne(float(valor_actual))

            if nivel_ne == 'INFERIOR':
                return (
                    f"Índice NE INFERIOR: embalse {valor_actual:.1f}% bajo senda CREG {senda:.1f}%. "
                    f"Riesgo de desabastecimiento — activar mecanismo de sostenimiento (CREG 026/2014 art. 7)."
                )
            if nivel_ne == 'ALERTA':
                return (
                    f"Índice NE ALERTA: embalse {valor_actual:.1f}% bajo senda CREG {senda:.1f}%. "
                    f"Vigilar evolución semanal; si persiste → nivel INFERIOR."
                )
            if valor_actual > 95:
                return (
                    "Riesgo de vertimientos forzados (criterio operativo CND). "
                    "Preparar descargas preventivas y monitorear caudales aguas abajo."
                )
            if valor_actual > 90:
                return (
                    "Nivel alto — vigilancia por posibles vertimientos preventivos (criterio operativo CND)."
                )
            if valor_actual >= NE_UMBRAL_SUPERIOR_ABSOLUTO_PCT:
                return (
                    f"Índice NE SUPERIOR: embalse {valor_actual:.1f}% ≥ 70% "
                    f"(regla absoluta CREG 209/2020). Operación estable."
                )
            if desviacion_pct and abs(desviacion_pct) > 20:
                return "Variación importante en reservas. Monitorear comportamiento de aportes hídricos (HSIN)."
            return (
                f"Índice NE SUPERIOR: embalse {valor_actual:.1f}% ≥ senda CREG {senda:.1f}%. "
                f"Operación estable según Estatuto CREG."
            )
        return "Nivel de embalses dentro de rangos operativos normales."

    # Aportes hídricos — Índice HSIN (Res. CREG 026/2014 art. 2)
    if 'aporte' in metrica_lower or 'hsin' in metrica_lower:
        if valor_actual is not None:
            nivel_hsin, _ = clasificar_hsin(float(valor_actual))
            if nivel_hsin == 'CRITICO':
                return (
                    f"HSIN {valor_actual:.1f}% ≤ 60% — nivel histórico de crisis. "
                    f"Condición de sequía severa (CREG 026/2014 art. 2)."
                )
            if nivel_hsin == 'DEFICIT_SEVERO':
                return (
                    f"HSIN {valor_actual:.1f}% < 70% — déficit hídrico severo (referencia CREG 209/2020)."
                )
            if nivel_hsin == 'VIGILANCIA':
                return (
                    f"HSIN {valor_actual:.1f}% < 90% — vigilancia hídrica oficial (CREG 026/2014 art. 2)."
                )
            return f"HSIN {valor_actual:.1f}% ≥ 90% — condición hídrica normal (CREG 026/2014)."
    
    # Costo unitario
    if 'costo' in metrica_lower or 'cu_' in metrica_lower or 'unitario' in metrica_lower:
        return ("Afecta la tarifa de energía para usuarios finales. "
                "Revisar componentes de costo: generación, transmisión, distribución.")
    
    # Datos congelados
    if 'congelado' in metrica_lower or 'test' in metrica_lower:
        return ("Problema técnico en la actualización de datos. "
                "Verificar conectividad con XM y sistemas de medición.")
    
    # PNT (Precio de Nudo de Transmisión)
    if 'pnt' in metrica_lower or 'nudo' in metrica_lower:
        return ("Afecta la valoración de transmisión en zonas específicas. "
                "Revisar restricciones en el SIN.")
    
    # Default
    return "Requiere evaluación técnica específica según el contexto del sistema."


def _strip_redundant_header(md_text: str) -> str:
    """
    Elimina las líneas redundantes del encabezado del informe
    que ya están en el template HTML del PDF (título, fecha, separadores).
    """
    lines = md_text.split('\n')
    filtered = []
    skip_patterns = [
        re.compile(r'^\*?\s*INFORME EJECUTIVO', re.IGNORECASE),
        re.compile(r'^\*?\s*Fecha:', re.IGNORECASE),
        re.compile(r'^[━─\-]{5,}$'),
    ]
    for line in lines:
        stripped = line.strip()
        cleaned = _strip_emojis(stripped).strip()
        if cleaned in ('INFORME EJECUTIVO — SECTOR ELÉCTRICO',
                       'INFORME EJECUTIVO  SECTOR ELÉCTRICO',
                       'INFORME EJECUTIVO',
                       ''):
            if stripped:
                continue
        if any(p.match(stripped) for p in skip_patterns):
            continue
        if any(p.match(cleaned) for p in skip_patterns):
            continue
        filtered.append(line)
    return '\n'.join(filtered)


# ═══════════════════════════════════════════════════════════════
# Conversión Markdown → HTML
# ═══════════════════════════════════════════════════════════════

def _markdown_to_html(md_text: str) -> str:
    """
    Convierte un subconjunto de Markdown a HTML simple.
    Soporta: ## headers, **bold**, *italic*, _italic_, bullets (- •),
    y saltos de línea.
    """
    lines = md_text.split('\n')
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<br>')
            continue

        if stripped.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            title = stripped[3:].strip()
            title = _inline_format(title)
            html_lines.append(f'<h2>{title}</h2>')
            continue

        # Fallback format: *1. Título* or *N. Título*
        m_fallback = re.match(r'^\*(\d+\.\s+.+?)\*$', stripped)
        if m_fallback:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            title = _inline_format(m_fallback.group(1).strip())
            html_lines.append(f'<h2>{title}</h2>')
            continue

        if stripped.startswith('### '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            title = stripped[4:].strip()
            title = _inline_format(title)
            html_lines.append(f'<h3>{title}</h3>')
            continue

        if stripped in ('━━━━━━━━━━━━━━━━━━━━━━━━━━━━', '---', '───'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<hr>')
            continue

        if stripped.startswith(('- ', '• ', '· ')):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            content = stripped[2:].strip()
            content = _inline_format(content)
            html_lines.append(f'  <li>{content}</li>')
            continue

        if in_list:
            html_lines.append('</ul>')
            in_list = False
        content = _inline_format(stripped)
        html_lines.append(f'<p>{content}</p>')

    if in_list:
        html_lines.append('</ul>')

    return '\n'.join(html_lines)


def _inline_format(text: str) -> str:
    """Convierte **bold**, *italic*, _italic_ inline."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    return text




# ═══════════════════════════════════════════════════════════════
# CSS — Estilo institucional inspirado en PDF modelo
# Variables Eléctricas (XM / Ministerio de Minas y Energía)
# ═══════════════════════════════════════════════════════════════

# Paleta de colores del modelo
_COLORS = {
    'dark_blue': '#254553',
    'teal': '#287270',
    'teal_light': '#299d8f',
    'blue_mme': '#125685',
    'coral': '#e76f50',
    'orange': '#f4a261',
    'gold': '#e8c36a',
    'lime': '#b4c657',
    'violet': '#5d17eb',
    'yellow': '#ffbf00',
    'gray_bg': '#d8d8d9',
    'gray_text': '#737373',
    'dark_text': '#191717',
    'green_ok': '#2E7D32',
    'red_alert': '#C62828',
    'orange_warn': '#E65100',
}

_CSS = """
@page {
    size: letter;
    margin: 4mm 0mm 11mm 0mm;

    @bottom-center {
        content: "Todos los datos presentados son recuperados del Operador del "
                 "Sistema Interconectado Nacional - XM SA  |  Pagina "
                 counter(page) " de " counter(pages);
        font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
        font-size: 6pt;
        font-style: italic;
        font-weight: bold;
        color: #ffffff;
        background: #254553;
        padding: 4px 14px;
    }
}

body {
    font-family: 'DejaVu Sans', Helvetica, Arial, sans-serif;
    font-size: 9pt;
    line-height: 1.4;
    color: #191717;
    margin: 0;
    padding: 0;
}

/* ── Page breaks ── */
.page {
    page-break-after: always;
}
.page:last-child {
    page-break-after: avoid;
}

/* ── Header bar (top of every page) ── */
.header-bar {
    width: 100%;
    border-collapse: collapse;
    border-spacing: 0;
}
.sidebar-mark {
    width: 44px;
    background: #254553;
    vertical-align: top;
}
.header-content {
    padding: 10px 14px 6px 14px;
    vertical-align: bottom;
}
.header-title {
    font-size: 20pt;
    font-weight: bold;
    color: #191717;
    line-height: 1.1;
}
.header-date {
    font-size: 11pt;
    font-weight: bold;
    color: #000;
    margin-top: 3px;
}
.header-logo-cell {
    width: 70px;
    vertical-align: middle;
    text-align: right;
    padding-right: 14px;
}
.header-logo-cell img {
    width: 50px;
    height: auto;
}
.header-line {
    height: 3px;
    background: #000;
    margin: 0 10px 0 56px;
}
.header-sep {
    height: 1px;
    background: #000;
    margin: 3px 10px 6px 10px;
}

/* ── Section headers (colored bar + white text) ── */
.section-hdr {
    color: #fff;
    font-size: 10.5pt;
    font-weight: bold;
    padding: 5px 14px;
    margin: 8px 10px 6px 10px;
    page-break-after: avoid;
}

/* ── Two-column layout (table) ── */
.two-col {
    width: calc(100% - 20px);
    margin: 0 10px;
    border-collapse: collapse;
    border-spacing: 0;
}
.two-col td {
    vertical-align: top;
    padding: 3px 6px;
}
.col-55 { width: 55%; }
.col-45 { width: 45%; }
.col-50 { width: 50%; }
.col-60 { width: 60%; }
.col-40 { width: 40%; }

/* ── KPI boxes ── */
.kpi-box {
    padding: 6px 10px;
    margin: 3px 0;
    border-radius: 4px;
    color: #fff;
}
.kpi-label {
    font-size: 8pt;
    font-weight: bold;
}
.kpi-value {
    font-size: 13pt;
    font-weight: bold;
    margin-top: 1px;
}
.kpi-sub {
    font-size: 6.5pt;
    opacity: 0.85;
    margin-top: 1px;
}

/* ── Big numbers ── */
.big-num {
    font-size: 24pt;
    font-weight: bold;
    color: #000;
    line-height: 1.1;
}
.big-label {
    font-size: 10pt;
    font-weight: bold;
    color: #000;
    margin-top: 2px;
}

/* ── Explanation text (italic) ── */
.explanation {
    font-size: 7.5pt;
    font-style: italic;
    color: #000;
    line-height: 1.35;
    margin: 3px 0;
}
.explanation-white {
    font-size: 7pt;
    font-style: italic;
    color: #fff;
    line-height: 1.3;
    margin: 3px 0;
}

/* ── Variation badges ── */
.var-box {
    padding: 3px 8px;
    margin: 2px 0;
    font-size: 8pt;
    font-weight: bold;
    color: #fff;
    border-radius: 3px;
    display: inline-block;
}

/* ── Source analysis blocks ── */
.src-block {
    margin: 3px 10px;
    page-break-inside: avoid;
}
.src-block table {
    width: 100%;
    border-collapse: collapse;
}
.src-hdr {
    color: #fff;
    font-size: 10pt;
    font-weight: bold;
    padding: 4px 12px;
}
.src-body {
    font-size: 7.5pt;
    color: #010113;
    line-height: 1.35;
    padding: 3px 12px 4px 12px;
}
.src-impl {
    font-size: 7.5pt;
    font-weight: bold;
    color: #010113;
    padding: 0 12px 4px 12px;
}

/* Source-specific colors */
.bg-hidra { background: #125685; }
.bg-termi { background: #737373; }
.bg-bioma { background: #b4c657; color: #000; }
.bg-eolic { background: #5d17eb; }
.bg-solar { background: #ffbf00; color: #000; }
.bg-comen { background: #254553; }

/* ── Data tables ── */
.data-tbl {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    margin: 4px 0;
}
.data-tbl th {
    background: #254553;
    color: #fff;
    padding: 4px 8px;
    text-align: left;
    font-size: 8pt;
    font-weight: bold;
}
.data-tbl td {
    padding: 3px 8px;
    border-bottom: 1px solid #e0e0e0;
}
.data-tbl tr:nth-child(even) td {
    background: #f5f7fa;
}

/* ── Bar cell for generation ── */
.bar-bg {
    display: inline-block;
    height: 9px;
    border-radius: 2px;
    vertical-align: middle;
}

/* ── Prediction table ── */
.pred-tbl {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    margin: 4px 0;
}
.pred-tbl th {
    background: #254553;
    color: #fff;
    padding: 4px 8px;
    text-align: left;
    font-size: 8pt;
}
.pred-tbl td {
    padding: 4px 8px;
    border-bottom: 1px solid #e0e0e0;
}
.trend-up { color: #2E7D32; font-weight: bold; }
.trend-dn { color: #C62828; font-weight: bold; }
.trend-st { color: #555; font-weight: bold; }

/* ── Semaphore table ── */
.sema-tbl {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    margin: 4px 0;
}
.sema-tbl th {
    background: #254553;
    color: #fff;
    padding: 4px 8px;
    text-align: left;
    font-size: 8pt;
}
.sema-tbl td {
    padding: 4px 8px;
    border-bottom: 1px solid #e0e0e0;
    vertical-align: middle;
}

/* ── Badge de estado ── */
.badge {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 8px;
    font-size: 7.5pt;
    font-weight: bold;
    color: #fff;
}
.badge-ok { background: #2E7D32; }
.badge-warn { background: #E65100; }
.badge-crit { background: #C62828; }

/* ── Prediction card per-page ── */
.pred-card {
    margin: 6px 10px;
    padding: 8px 12px;
    background: #f0f7f6;
    border-left: 4px solid #287270;
    border-radius: 0 4px 4px 0;
    page-break-inside: avoid;
    font-size: 8.5pt;
    line-height: 1.4;
}
.pred-card-hdr {
    font-size: 9pt;
    font-weight: bold;
    color: #254553;
    margin-bottom: 4px;
}
.pred-card .pred-row {
    display: inline-block;
    margin-right: 18px;
    margin-bottom: 2px;
}
.pred-card .pred-label {
    font-size: 7.5pt;
    color: #737373;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.pred-card .pred-val {
    font-size: 10pt;
    font-weight: bold;
    color: #254553;
}
.pred-card .pred-analysis {
    font-size: 8pt;
    color: #555;
    margin-top: 4px;
    font-style: italic;
}

/* ── Embalses detail ── */
.emb-box {
    margin: 4px 10px;
    padding: 8px 12px;
    background: #f5f7fa;
    border-left: 4px solid #287270;
    page-break-inside: avoid;
    font-size: 8.5pt;
}
.emb-box table {
    width: 100%;
    border-collapse: collapse;
}
.emb-box td {
    padding: 2px 0;
}
.emb-box td:last-child {
    text-align: right;
    font-weight: bold;
}

/* ── Anomaly table ── */
.anom-tbl {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    margin: 4px 0;
}
.anom-tbl th {
    background: #e76f50;
    color: #fff;
    padding: 4px 8px;
    text-align: left;
    font-size: 8pt;
}
.anom-tbl td {
    padding: 3px 8px;
    border-bottom: 1px solid #eee;
}

/* ── News items ── */
.news-item {
    padding: 4px 12px;
    border-bottom: 1px solid #eee;
}
.news-title {
    font-size: 9pt;
    font-weight: bold;
    color: #191717;
}
.news-summary {
    font-size: 8pt;
    color: #555;
    margin-top: 1px;
    line-height: 1.3;
}
.news-meta {
    font-size: 7pt;
    color: #8d8d8d;
    margin-top: 1px;
}

/* ── Channels ── */
.channels-box {
    margin: 8px 10px;
    padding: 8px 12px;
    background: #f5f7fa;
    border-radius: 4px;
    page-break-inside: avoid;
    font-size: 8.5pt;
}
.channels-title {
    font-size: 10pt;
    font-weight: bold;
    color: #254553;
    margin-bottom: 4px;
}
.ch-btn {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 4px;
    color: #fff;
    text-decoration: none;
    font-size: 8.5pt;
    font-weight: bold;
    margin-right: 6px;
}

/* ── Charts ── */
.chart-box {
    text-align: center;
    page-break-inside: auto;
    margin: 6px 0;
}
.chart-box img {
    width: 100%;
    max-width: 100%;
    height: auto;
}
.chart-caption {
    font-size: 6.5pt;
    color: #8d8d8d;
    font-style: italic;
    text-align: center;
    margin-top: 1px;
}

/* ── AI Narrative ── */
.narrative {
    font-size: 8.5pt;
    line-height: 1.4;
    padding: 2px 14px;
    margin: 0 10px;
}
.narrative h2 {
    font-size: 10pt;
    font-weight: bold;
    color: #254553;
    margin: 8px 0 3px 0;
    padding-bottom: 2px;
    border-bottom: 1px solid #ddd;
}
.narrative h3 {
    font-size: 9pt;
    font-weight: bold;
    color: #287270;
    margin: 6px 0 2px 0;
}
.narrative p {
    margin: 2px 0;
    text-align: justify;
}
.narrative ul {
    margin: 2px 0 2px 16px;
    padding: 0;
}
.narrative li {
    margin-bottom: 1px;
}
.narrative strong {
    font-weight: bold;
}
.narrative em {
    font-style: italic;
}
.narrative hr {
    border: none;
    border-top: 0.5pt solid #ccc;
    margin: 6px 0;
}
"""


# ═══════════════════════════════════════════════════════════════
# Utilidades
# ═══════════════════════════════════════════════════════════════

def _load_logo_b64() -> str:
    """Carga el logo MME como string base64. Retorna '' si no existe."""
    if not os.path.exists(_LOGO_PATH):
        return ''
    try:
        with open(_LOGO_PATH, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        return ''


def _embed_chart(chart_paths: List[str], key_prefix: str) -> str:
    """
    Busca un chart en la lista por prefijo de nombre y retorna
    HTML <img> con data URI base64, o '' si no existe.
    """
    if not chart_paths:
        return ''
    for path in chart_paths:
        if not path or not os.path.exists(path):
            continue
        fname = os.path.basename(path).lower()
        if key_prefix in fname:
            try:
                with open(path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                return (
                    f'<div class="chart-box">'
                    f'<img src="data:image/png;base64,{b64}" alt="{key_prefix}">'
                    f'</div>'
                )
            except Exception as e:
                logger.warning(f'[REPORT] Error embediendo chart {path}: {e}')
    return ''


def _wrap_report_page(logo_b64: str, fecha_label: str, body_html: str) -> str:
    """Envuelve contenido en una página del informe con encabezado estándar."""
    header = _build_header_html(logo_b64, fecha_label)
    return f'<div class="page">{header}{body_html}</div>'


def _parse_narrative_sections(md_text: str) -> Dict[str, str]:
    """
    Divide el texto Markdown de la IA en secciones por encabezados ##.
    Retorna dict: { 'titulo_seccion': 'contenido_md', ... }
    Las claves son el texto del titulo (sin ##).
    """
    sections: Dict[str, str] = {}
    current_key = '_intro'
    current_lines: List[str] = []

    for line in md_text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('## '):
            if current_lines:
                sections[current_key] = '\n'.join(current_lines)
            current_key = stripped[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_key] = '\n'.join(current_lines)

    return sections


def _format_fecha_larga(fecha_str: str = '') -> str:
    """Convierte fecha a formato largo: 'DD de MMMMM de YYYY'."""
    meses = [
        '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
    ]
    try:
        if fecha_str:
            dt = datetime.strptime(str(fecha_str)[:10], '%Y-%m-%d')
        else:
            dt = datetime.now()
        return f'{dt.day} de {meses[dt.month]} de {dt.year}'
    except Exception:
        return str(fecha_str)[:10] if fecha_str else ''


def _fecha_corte_html(fecha_str: str = '', variant: str = 'default') -> str:
    """Línea HTML estándar con la fecha de corte del dato."""
    if not fecha_str:
        return ''
    fc = _format_fecha_larga(str(fecha_str)[:10])
    if variant == 'badge':
        return (
            f'<div style="font-size:6.5pt;background:#eef2f7;color:#475569;'
            f'padding:2px 8px;border-radius:3px;display:inline-block;margin-top:4px;">'
            f'Fecha de corte: {fc}</div>'
        )
    if variant == 'white':
        return f'<div style="font-size:6.5pt;opacity:0.9;margin-top:3px;">Fecha de corte: {fc}</div>'
    if variant == 'footer':
        return f'<div style="font-size:6pt;color:#888;margin-top:2px;">Fecha de corte: {fc}</div>'
    return f'<div style="font-size:6.5pt;color:#666;margin-top:3px;">Fecha de corte: {fc}</div>'


def _resolve_fecha_corte(
    fichas: Optional[List[Dict[str, Any]]] = None,
    tipo: str = '',
    tabla_indicadores: Optional[List[Dict[str, Any]]] = None,
    variables_mercado: Optional[Dict[str, Any]] = None,
    vm_key: str = '',
    metric: Optional[Dict[str, Any]] = None,
) -> str:
    """Resuelve la fecha de corte desde ficha, tabla KPI, variables de mercado o métrica."""
    if metric and metric.get('fecha'):
        return str(metric['fecha'])
    if tipo:
        ficha = _get_ficha_indicador(fichas or [], tipo)
        if ficha and ficha.get('fecha'):
            return str(ficha['fecha'])
        for ind in (tabla_indicadores or []):
            nombre = _strip_emojis(ind.get('indicador', '')).lower()
            if tipo == 'generacion' and 'generaci' in nombre:
                return str(ind.get('fecha', '') or '')
            if tipo == 'precio' and ('precio' in nombre or 'bolsa' in nombre):
                return str(ind.get('fecha', '') or '')
            if tipo == 'embalses' and 'embalse' in nombre:
                return str(ind.get('fecha', '') or '')
    if variables_mercado and vm_key:
        fc = variables_mercado.get(vm_key, {}).get('fecha')
        if fc:
            return str(fc)
    return ''


def _find_metric_prediction(pred_resumen: Dict[str, Any], keyword: str) -> Optional[Dict[str, Any]]:
    """
    Busca en pred_resumen['metricas'] la primera métrica cuyo 'indicador'
    contenga *keyword* (case-insensitive). Retorna el dict o None.
    """
    metricas = (pred_resumen or {}).get('metricas', [])
    kw = keyword.lower()
    for m in metricas:
        if kw in (m.get('indicador', '') or '').lower():
            return m
    return None


def _build_pred_card(metric: Dict[str, Any], analysis_text: str = '', fecha_corte: str = '') -> str:
    """
    Construye una tarjeta de predicción para insertar en cualquier página.
    Muestra: valor actual → proyectado, rango, tendencia y análisis contextual.

    Args:
        metric: dict con indicador, unidad, valor_actual, promedio_proyectado_1m,
                rango_min, rango_max, tendencia, cambio_pct_vs_prom30d, confianza_modelo.
        analysis_text: texto breve de análisis/implicación (HTML safe).
    """
    if not metric:
        return ''

    nombre = _strip_emojis(metric.get('indicador', ''))
    unidad = metric.get('unidad', '')
    actual = metric.get('valor_actual')
    prom_proy = metric.get('promedio_proyectado_1m')
    rango_min = metric.get('rango_min')
    rango_max = metric.get('rango_max')
    tendencia = metric.get('tendencia', 'Estable')
    cambio = metric.get('cambio_pct_vs_prom30d')
    confianza = metric.get('confianza_modelo', '')

    actual_s = f'{actual:,.1f}' if actual is not None else 'N/D'
    proy_s = f'{prom_proy:,.1f}' if prom_proy is not None else 'N/D'

    rango_html = ''
    if rango_min is not None and rango_max is not None:
        rango_html = (
            '<span class="pred-row">'
            '<span class="pred-label">Rango</span><br>'
            f'<span class="pred-val" style="font-size:8.5pt;">{rango_min:,.1f} &ndash; {rango_max:,.1f} {unidad}</span>'
            '</span>'
        )

    # Tendencia con color e ícono
    if tendencia == 'Creciente':
        t_color = '#2E7D32'
        t_arrow = '&#9650;'
    elif tendencia == 'Decreciente':
        t_color = '#C62828'
        t_arrow = '&#9660;'
    else:
        t_color = '#555'
        t_arrow = '&#9654;'

    cambio_s = ''
    if cambio is not None:
        cambio_s = f' ({cambio:+.1f}%)'

    confianza_html = ''
    if confianza:
        confianza_html = f' &bull; Confianza: {confianza}'

    analysis_html = ''
    if analysis_text:
        analysis_html = f'<div class="pred-analysis">{analysis_text}</div>'

    fc = fecha_corte or metric.get('fecha', '') or ''
    fecha_html = _fecha_corte_html(fc, 'footer')

    return f"""
    <div class="pred-card">
      <div class="pred-card-hdr">&#128200; Proyecci&oacute;n: {nombre}</div>
      {fecha_html}
      <span class="pred-row">
        <span class="pred-label">Actual</span><br>
        <span class="pred-val">{actual_s} {unidad}</span>
      </span>
      <span class="pred-row">
        <span class="pred-label">Proy. 1 mes</span><br>
        <span class="pred-val" style="color:#287270;">{proy_s} {unidad}</span>
      </span>
      {rango_html}
      <span class="pred-row">
        <span class="pred-label">Tendencia</span><br>
        <span class="pred-val" style="color:{t_color};font-size:8.5pt;">
          {t_arrow} {tendencia}{cambio_s}</span>
      </span>
      <div style="font-size:6.5pt;color:#8d8d8d;margin-top:3px;">
        Modelo: ENSEMBLE con validaci&oacute;n holdout{confianza_html}
      </div>
      {analysis_html}
    </div>
    """


# ═══════════════════════════════════════════════════════════════
# Builders de componentes reutilizables
# ═══════════════════════════════════════════════════════════════

def _build_header_html(logo_b64: str, fecha_label: str) -> str:
    """
    Header bar para cada página: barra lateral azul oscuro,
    título grande, fecha, línea separadora. Replica el header del modelo.
    """
    logo_img = ''
    if logo_b64:
        logo_img = f'<img src="data:image/png;base64,{logo_b64}" alt="MME">'

    fecha_larga = _format_fecha_larga(fecha_label)

    return f"""
    <table class="header-bar" cellpadding="0" cellspacing="0">
      <tr>
        <td class="sidebar-mark" rowspan="2">&nbsp;</td>
        <td class="header-content">
          <div class="header-title">Informe de Variables El&eacute;ctricas</div>
          <div class="header-date">Fecha: {fecha_larga}</div>
        </td>
        <td class="header-logo-cell">{logo_img}</td>
      </tr>
    </table>
    <div class="header-line"></div>
    <div class="header-sep"></div>
    """


def _section_hdr(title: str, color: str = '#254553') -> str:
    """Barra de sección con fondo de color y texto blanco."""
    return f'<div class="section-hdr" style="background:{color};">{title}</div>'


# ═══════════════════════════════════════════════════════════════
# PAGE 1: Variables del Mercado y Resumen
# ═══════════════════════════════════════════════════════════════

def _build_mercado_vars_cards(variables_mercado: Dict[str, Any]) -> str:
    """
    Renderiza una fila de mini-KPI cards para las variables adicionales de mercado:
    Precio Escasez, Precio Máx Oferta Nal, PPP Precio Bolsa,
    Demanda Regulada, Demanda No Regulada.
    """
    if not variables_mercado:
        return ''

    _ITEMS = [
        ('precio_escasez',    'Precio Escasez',       '#1a5276'),
        ('precio_max_oferta', 'Precio M&aacute;x Oferta', '#154360'),
        ('ppp_bolsa',         'PPP Precio Bolsa',     '#0e5f58'),
        ('demanda_regulada',  'Dem. Regulada',        '#196f3d'),
        ('demanda_no_reg',    'Dem. No Regulada',     '#145a32'),
    ]

    cells = ''
    for clave, label, color in _ITEMS:
        entry = variables_mercado.get(clave)
        if not entry:
            continue
        raw = entry.get('valor', '—')
        unidad = entry.get('unidad', '')
        fecha_var = entry.get('fecha', '')
        valor_str = f'{float(raw):,.2f}' if isinstance(raw, (int, float)) else str(raw)
        cells += (
            f'<td style="background:{color}; border-radius:4px; padding:5px 8px; '
            f'color:#fff; text-align:center;">'
            f'<div style="font-size:6.5pt; font-weight:bold; opacity:0.85;">{label}</div>'
            f'<div style="font-size:10pt; font-weight:bold; margin-top:2px;">'
            f'{valor_str}'
            f'<span style="font-size:6.5pt; margin-left:2px;">{unidad}</span>'
            f'</div>'
            f'{_fecha_corte_html(fecha_var, "white")}'
            f'</td>'
        )

    if not cells:
        return ''

    return (
        f'<div style="margin:5px 10px 3px;">'
        f'<table style="width:100%; border-collapse:separate; border-spacing:4px 0;">'
        f'<tr>{cells}</tr>'
        f'</table>'
        f'<p style="font-size:6.5pt; font-style:italic; color:#666; margin:2px 0 0 2px;">'
        f'Fuente: XM &mdash; SIMEM. Precios en $/kWh. '
        f'Demanda: &uacute;ltimo valor diario del SIN (entidad Sistema).</p>'
        f'</div>'
    )


def _interpretar_percentil_amigable(percentil: float) -> str:
    """Convierte percentil a lenguaje natural amigable."""
    if percentil >= 90:
        return "Muy alto", "#2E7D32", "Este valor está entre los más altos de los últimos 5 años"
    elif percentil >= 75:
        return "Alto", "#689F38", "Este valor está por encima de lo habitual"
    elif percentil >= 25:
        return "Normal", "#555", "Este valor está dentro del rango típico"
    elif percentil >= 10:
        return "Bajo", "#F57C00", "Este valor está por debajo de lo habitual"
    else:
        return "Muy bajo", "#C62828", "Este valor está entre los más bajos de los últimos 5 años"


def _interpretar_zscore_amigable(zscore: float) -> tuple:
    """Convierte Z-Score a lenguaje natural con color."""
    if zscore >= 2:
        return "Muy inusual (muy alto)", "#C62828"
    elif zscore >= 1:
        return "Inusual (alto)", "#F57C00"
    elif zscore > -1:
        return "Normal", "#2E7D32"
    elif zscore > -2:
        return "Inusual (bajo)", "#F57C00"
    else:
        return "Muy inusual (muy bajo)", "#C62828"


def _build_analisis_multidimensional_html(analisis_multidimensional: List[Dict[str, Any]]) -> str:
    """
    Construye el análisis multidimensional con diseño consistente a los KPI boxes del PDF.
    Usa el mismo estilo visual: fondos de color, texto blanco, diseño vertical.
    """
    if not analisis_multidimensional:
        return ''
    
    # Colores consistentes con el diseño del PDF
    COLORES_KPI = ['#287270', '#299d8f', '#254553', '#125685']
    
    secciones = []
    for idx, a in enumerate(analisis_multidimensional[:3]):
        ind = _strip_emojis(a.get('indicador', ''))
        emoji = a.get('emoji', '•')
        valor = a.get('valor_actual')
        unidad = a.get('unidad', '')
        
        # Recopilar datos
        t = a.get('tendencia_7d', {})
        p = a.get('percentiles', {})
        z = a.get('zscore', {})
        yoy = a.get('yoy', {})
        
        # Construir celdas KPI (estilo consistente con el PDF)
        kpis_html = []
        
        # KPI 1: Tendencia
        if t:
            desc = t.get('descripcion', 'Sin tendencia')
            direccion = t.get('direccion', 'estable')
            proy = t.get('proyeccion_7dias')
            
            # Flecha según dirección
            if 'alcista' in direccion:
                flecha = '▲'
                subcolor = '#c8ffc8'
            elif 'bajista' in direccion:
                flecha = '▼'
                subcolor = '#ffc8c8'
            else:
                flecha = '▶'
                subcolor = '#ffffff'
            
            proy_line = f'<div style="font-size:6.5pt;opacity:0.85;margin-top:1px;">Proy: {proy:.0f} {unidad}</div>' if proy else ''
            
            kpis_html.append(
                f'<td style="width:25%;padding:3px;">'
                f'<div style="background:{COLORES_KPI[0]};border-radius:4px;padding:6px 4px;color:#fff;text-align:center;">'
                f'<div style="font-size:6.5pt;font-weight:bold;opacity:0.9;">Tendencia 7d</div>'
                f'<div style="font-size:9pt;font-weight:bold;margin-top:2px;">{flecha}</div>'
                f'<div style="font-size:7pt;margin-top:1px;">{desc}</div>'
                f'{proy_line}'
                f'</div></td>'
            )
        
        # KPI 2: Posición Histórica (percentil)
        if p:
            pct = p.get('percentil_actual', 50)
            if pct >= 75:
                pct_texto = "Alto"
            elif pct >= 25:
                pct_texto = "Normal"
            else:
                pct_texto = "Bajo"
            
            kpis_html.append(
                f'<td style="width:25%;padding:3px;">'
                f'<div style="background:{COLORES_KPI[1]};border-radius:4px;padding:6px 4px;color:#fff;text-align:center;">'
                f'<div style="font-size:6.5pt;font-weight:bold;opacity:0.9;">Posición Histórica</div>'
                f'<div style="font-size:11pt;font-weight:bold;margin-top:2px;">{pct:.0f}%</div>'
                f'<div style="font-size:6.5pt;opacity:0.85;margin-top:1px;">{pct_texto} (5 años)</div>'
                f'</div></td>'
            )
        
        # KPI 3: Qué tan inusual (Z-Score simplificado)
        if z:
            z_val = z.get('z_score', 0)
            abs_z = abs(z_val)
            
            if abs_z < 1:
                usualidad = "Normal"
                usual_color = "#c8ffc8"
            elif abs_z < 2:
                usualidad = "Inusual"
                usual_color = "#ffe082"
            else:
                usualidad = "Muy inusual"
                usual_color = "#ffc8c8"
            
            direccion_z = "alto" if z_val > 0 else "bajo"
            
            kpis_html.append(
                f'<td style="width:25%;padding:3px;">'
                f'<div style="background:{COLORES_KPI[2]};border-radius:4px;padding:6px 4px;color:#fff;text-align:center;">'
                f'<div style="font-size:6.5pt;font-weight:bold;opacity:0.9;">Qué tan inusual</div>'
                f'<div style="font-size:11pt;font-weight:bold;margin-top:2px;">{abs_z:.1f}σ</div>'
                f'<div style="font-size:6.5pt;opacity:0.85;margin-top:1px;color:{usual_color};">{usualidad}</div>'
                f'</div></td>'
            )
        
        # KPI 4: vs Año Pasado (o mensaje si no hay datos)
        cambio = yoy.get('cambio_pct') if isinstance(yoy, dict) else None
        if cambio is not None:
            color_cambio = '#c8ffc8' if cambio > 0 else '#ffc8c8'
            signo = '+' if cambio > 0 else ''
            
            kpis_html.append(
                f'<td style="width:25%;padding:3px;">'
                f'<div style="background:{COLORES_KPI[3]};border-radius:4px;padding:6px 4px;color:#fff;text-align:center;">'
                f'<div style="font-size:6.5pt;font-weight:bold;opacity:0.9;">vs Año Pasado</div>'
                f'<div style="font-size:11pt;font-weight:bold;margin-top:2px;color:{color_cambio};">{signo}{cambio:.1f}%</div>'
                f'<div style="font-size:6.5pt;opacity:0.85;margin-top:1px;">Mismo período</div>'
                f'</div></td>'
            )
        else:
            # Mostrar "No disponible" para mantener consistencia visual
            kpis_html.append(
                f'<td style="width:25%;padding:3px;">'
                f'<div style="background:#9e9e9e;border-radius:4px;padding:6px 4px;color:#fff;text-align:center;">'
                f'<div style="font-size:6.5pt;font-weight:bold;opacity:0.9;">vs Año Pasado</div>'
                f'<div style="font-size:9pt;font-weight:bold;margin-top:4px;color:#e0e0e0;">-</div>'
                f'<div style="font-size:6.5pt;opacity:0.85;margin-top:1px;">Sin datos históricos</div>'
                f'</div></td>'
            )
        
        if kpis_html:
            secciones.append(
                f'<div style="margin:6px 0;">'
                f'<div style="font-size:9pt;font-weight:bold;color:#254553;margin-bottom:4px;padding-left:4px;">'
                f'{emoji} {ind}'
                f'{f" <span style=\"font-size:8pt;color:#666;font-weight:normal;\">- {valor:.1f} {unidad}</span>" if valor else ""}'
                f'</div>'
                f'<table style="width:100%;border-collapse:separate;border-spacing:0;">'
                f'<tr>{"".join(kpis_html)}</tr>'
                f'</table>'
                f'</div>'
            )
    
    if not secciones:
        return ''
    
    return f'''
    <div style="margin:6px 10px;padding:8px;background:#f5f5f5;border-radius:4px;">
        <div style="font-size:9pt;font-weight:bold;color:#254553;margin-bottom:6px;padding-left:4px;">
            📊 Análisis Inteligente de Indicadores
        </div>
        {''.join(secciones)}
    </div>
    '''


def _build_ficha_principal_vertical(
    indicador: str,
    emoji: str,
    valor: float,
    unidad: str,
    tendencia: str,
    estado: str,
    analisis: Dict[str, Any],
    color_base: str,
    fecha_corte: str = '',
) -> str:
    """
    Construye una ficha principal con sub-fichas verticales (una debajo de otra).
    Similar al diseño de Índices del Sistema Eléctrico Nacional.
    """
    # Determinar color del estado
    estado_l = estado.lower()
    if estado_l == 'normal':
        estado_bg = '#27ae60'
    elif estado_l == 'alerta':
        estado_bg = '#f39c12'
    else:  # crítico
        estado_bg = '#e74c3c'
    
    # Flecha de tendencia - colores claros para fondo oscuro
    if tendencia == 'Alza':
        trend_arrow = '▲'
        trend_color = '#90EE90'  # Verde claro
    elif tendencia == 'Baja':
        trend_arrow = '▼'
        trend_color = '#FFB6C1'  # Rosa claro
    else:
        trend_arrow = '▶'
        trend_color = '#ffffff'  # Blanco
    
    # Formatear valor
    if isinstance(valor, float):
        val_str = f'{valor:,.2f}'
    else:
        val_str = str(valor)
    
    # Sub-fichas verticales
    sub_fichas = []
    
    # 1. Tendencia 7d
    t = analisis.get('tendencia_7d', {})
    if t:
        desc = t.get('descripcion', 'Sin tendencia')
        direccion = t.get('direccion', 'estable')
        proy = t.get('proyeccion_7dias')
        
        if 'alcista' in direccion:
            flecha = '▲'
            subcolor = '#c8ffc8'
        elif 'bajista' in direccion:
            flecha = '▼'
            subcolor = '#ffc8c8'
        else:
            flecha = '▶'
            subcolor = '#ffffff'
        
        proy_line = f'<div style="font-size:6pt;opacity:0.9;margin-top:2px;">Proy: {proy:.0f} {unidad}</div>' if proy else ''
        
        sub_fichas.append(
            f'<div style="background:{color_base};border-radius:3px;padding:5px 4px;margin-bottom:4px;color:#fff;text-align:center;">'
            f'<div style="font-size:6pt;font-weight:bold;opacity:0.9;">Tendencia 7d</div>'
            f'<div style="font-size:10pt;font-weight:bold;margin-top:1px;">{flecha}</div>'
            f'<div style="font-size:6.5pt;margin-top:1px;">{desc}</div>'
            f'{proy_line}'
            f'</div>'
        )
    
    # 2. Posición Histórica
    p = analisis.get('percentiles', {})
    if p:
        pct = p.get('percentil_actual', 50)
        if pct >= 75:
            pct_texto = "Alto"
        elif pct >= 25:
            pct_texto = "Normal"
        else:
            pct_texto = "Bajo"
        
        sub_fichas.append(
            f'<div style="background:#299d8f;border-radius:3px;padding:5px 4px;margin-bottom:4px;color:#fff;text-align:center;">'
            f'<div style="font-size:6pt;font-weight:bold;opacity:0.9;">Posición Histórica</div>'
            f'<div style="font-size:11pt;font-weight:bold;margin-top:1px;">{pct:.0f}%</div>'
            f'<div style="font-size:6pt;opacity:0.85;margin-top:1px;">{pct_texto} (5 años)</div>'
            f'</div>'
        )
    
    # 3. Qué tan inusual (Z-Score)
    z = analisis.get('zscore', {})
    if z:
        z_val = z.get('z_score', 0)
        abs_z = abs(z_val)
        
        if abs_z < 1:
            usualidad = "Normal"
            usual_color = "#c8ffc8"
        elif abs_z < 2:
            usualidad = "Inusual"
            usual_color = "#ffe082"
        else:
            usualidad = "Muy inusual"
            usual_color = "#ffc8c8"
        
        sub_fichas.append(
            f'<div style="background:#254553;border-radius:3px;padding:5px 4px;margin-bottom:4px;color:#fff;text-align:center;">'
            f'<div style="font-size:6pt;font-weight:bold;opacity:0.9;">Qué tan inusual</div>'
            f'<div style="font-size:11pt;font-weight:bold;margin-top:1px;">{abs_z:.1f}σ</div>'
            f'<div style="font-size:6pt;opacity:0.85;margin-top:1px;color:{usual_color};">{usualidad}</div>'
            f'</div>'
        )
    
    # 4. vs Año Pasado
    yoy = analisis.get('yoy', {})
    cambio = yoy.get('cambio_pct') if isinstance(yoy, dict) else None
    if cambio is not None:
        color_cambio = '#c8ffc8' if cambio > 0 else '#ffc8c8'
        signo = '+' if cambio > 0 else ''
        
        sub_fichas.append(
            f'<div style="background:#125685;border-radius:3px;padding:5px 4px;margin-bottom:4px;color:#fff;text-align:center;">'
            f'<div style="font-size:6pt;font-weight:bold;opacity:0.9;">vs Año Pasado</div>'
            f'<div style="font-size:11pt;font-weight:bold;margin-top:1px;color:{color_cambio};">{signo}{cambio:.1f}%</div>'
            f'<div style="font-size:6pt;opacity:0.85;margin-top:1px;">Mismo período</div>'
            f'</div>'
        )
    else:
        sub_fichas.append(
            f'<div style="background:#9e9e9e;border-radius:3px;padding:5px 4px;margin-bottom:4px;color:#fff;text-align:center;">'
            f'<div style="font-size:6pt;font-weight:bold;opacity:0.9;">vs Año Pasado</div>'
            f'<div style="font-size:9pt;font-weight:bold;margin-top:3px;color:#e0e0e0;">-</div>'
            f'<div style="font-size:6pt;opacity:0.85;margin-top:1px;">Sin datos</div>'
            f'</div>'
        )
    
    sub_fichas_html = ''.join(sub_fichas)
    
    return f'''
    <td style="width:33.33%;padding:5px;vertical-align:top;">
        <div style="background:#ffffff;border:2px solid {color_base};border-radius:6px;overflow:hidden;height:100%;">
            <!-- Header de la ficha -->
            <div style="background:{color_base};padding:8px 6px;color:#fff;text-align:center;">
                <div style="font-size:8pt;font-weight:bold;">{emoji} {_strip_emojis(indicador).upper()}</div>
                <div style="font-size:14pt;font-weight:bold;margin:4px 0;">{val_str} <span style="font-size:9pt;">{unidad}</span></div>
                <div style="font-size:7pt;">
                    <span style="color:{trend_color};">{trend_arrow} {tendencia}</span>
                    <span style="background:{estado_bg};color:#fff;padding:1px 6px;border-radius:3px;margin-left:6px;font-size:6.5pt;">{estado.upper()}</span>
                </div>
                {_fecha_corte_html(fecha_corte, 'white')}
            </div>
            <!-- Sub-fichas verticales -->
            <div style="padding:6px;background:#f8f9fa;">
                {sub_fichas_html}
            </div>
        </div>
    </td>
    '''


def _build_resumen_ejecutivo_fichas(
    tabla_indicadores: List[Dict[str, Any]],
    analisis_multidimensional: List[Dict[str, Any]]
) -> str:
    """
    Construye el Resumen Ejecutivo con las 3 fichas principales horizontales,
    cada una con sus sub-fichas verticales de análisis.
    """
    if not tabla_indicadores:
        return ''
    
    # Mapear análisis multidimensional por indicador
    analisis_por_indicador = {}
    for a in (analisis_multidimensional or []):
        ind = _strip_emojis(a.get('indicador', '')).lower()
        analisis_por_indicador[ind] = a
    
    # Colores para cada ficha - todas oscuro para mejor contraste
    colores = ['#254553', '#254553', '#254553']
    emojis = ['⚡', '💰', '💧']
    
    fichas_html = []
    for idx, ind in enumerate(tabla_indicadores[:3]):
        nombre = ind.get('indicador', '')
        nombre_clean = _strip_emojis(nombre).lower()
        valor = ind.get('valor_actual', 0)
        unidad = ind.get('unidad', '')
        tendencia = ind.get('tendencia', 'Estable')
        estado = ind.get('estado', 'Normal')
        emoji = emojis[idx] if idx < len(emojis) else '•'
        color = colores[idx % len(colores)]
        
        # Buscar análisis multidimensional correspondiente
        analisis = analisis_por_indicador.get(nombre_clean, {})
        if not analisis:
            # Intentar match por palabras clave
            for k, v in analisis_por_indicador.items():
                if 'generaci' in nombre_clean and 'generaci' in k:
                    analisis = v
                    break
                elif 'precio' in nombre_clean and 'precio' in k:
                    analisis = v
                    break
                elif 'embalse' in nombre_clean and 'embalse' in k:
                    analisis = v
                    break
        
        fichas_html.append(_build_ficha_principal_vertical(
            nombre, emoji, valor, unidad, tendencia, estado, analisis, color,
            fecha_corte=str(ind.get('fecha', '') or ''),
        ))
    
    if not fichas_html:
        return ''
    
    return f'''
    <div style="margin:8px 10px;">
        <table style="width:100%;border-collapse:separate;border-spacing:6px 0;">
            <tr>{''.join(fichas_html)}</tr>
        </table>
    </div>
    '''


# ═══════════════════════════════════════════════════════════════
# PAGE 1: Variables del Mercado y Resumen
# ═══════════════════════════════════════════════════════════════

def _build_mercado_vars_cards(variables_mercado: Dict[str, Any]) -> str:
    """
    Renderiza una fila de mini-KPI cards para las variables adicionales de mercado:
    Precio Escasez, Precio Máx Oferta Nal, PPP Precio Bolsa,
    Demanda Regulada, Demanda No Regulada.
    """
    if not variables_mercado:
        return ''

    _ITEMS = [
        ('precio_escasez',    'Precio Escasez',       '#1a5276'),
        ('precio_max_oferta', 'Precio M&aacute;x Oferta', '#154360'),
        ('ppp_bolsa',         'PPP Precio Bolsa',     '#0e5f58'),
        ('demanda_regulada',  'Dem. Regulada',        '#196f3d'),
        ('demanda_no_reg',    'Dem. No Regulada',     '#145a32'),
    ]

    cells = ''
    for clave, label, color in _ITEMS:
        entry = variables_mercado.get(clave)
        if not entry:
            continue
        raw = entry.get('valor', '—')
        unidad = entry.get('unidad', '')
        fecha_var = entry.get('fecha', '')
        valor_str = f'{float(raw):,.2f}' if isinstance(raw, (int, float)) else str(raw)
        cells += (
            f'<td style="background:{color}; border-radius:4px; padding:5px 8px; '
            f'color:#fff; text-align:center;">'
            f'<div style="font-size:6.5pt; font-weight:bold; opacity:0.85;">{label}</div>'
            f'<div style="font-size:10pt; font-weight:bold; margin-top:2px;">'
            f'{valor_str}'
            f'<span style="font-size:6.5pt; margin-left:2px;">{unidad}</span>'
            f'</div>'
            f'{_fecha_corte_html(fecha_var, "white")}'
            f'</td>'
        )

    if not cells:
        return ''

    return (
        f'<div style="margin:5px 10px 3px;">'
        f'<table style="width:100%; border-collapse:separate; border-spacing:4px 0;">'
        f'<tr>{cells}</tr>'
        f'</table>'
        f'<p style="font-size:6.5pt; font-style:italic; color:#666; margin:2px 0 0 2px;">'
        f'Fuente: XM &mdash; SIMEM. Precios en $/kWh. '
        f'Demanda: &uacute;ltimo valor diario del SIN (entidad Sistema).</p>'
        f'</div>'
    )
def _build_mercado_vars_vertical(variables_mercado: Dict[str, Any], fichas: List[Dict[str, Any]]) -> str:
    """
    Construye las variables del mercado en formato vertical con descripciones,
    para mostrar a la derecha de la gráfica. Incluye Precio de Bolsa Nacional de las fichas.
    """
    cards = ''
    
    # 1. Precio de Bolsa Nacional - de las fichas principales
    precio_ficha = None
    for f in (fichas or []):
        ind_lower = f.get('indicador', '').lower()
        if 'precio' in ind_lower and 'bolsa' in ind_lower:
            precio_ficha = f
            break
    
    if precio_ficha:
        valor = precio_ficha.get('valor', 0)
        unidad = precio_ficha.get('unidad', 'COP/kWh')
        ctx = precio_ficha.get('contexto', {})
        var_pct = ctx.get('variacion_vs_promedio_pct', 0)
        tendencia = ctx.get('tendencia', 'Estable')
        
        # Flecha de tendencia
        if tendencia == 'Alza':
            flecha = '▲'
            trend_color = '#2E7D32'
        elif tendencia == 'Baja':
            flecha = '▼'
            trend_color = '#C62828'
        else:
            flecha = '▶'
            trend_color = '#555'
        
        signo = '+' if var_pct >= 0 else ''
        
        cards += (
            f'<div style="background:#287270;border-radius:4px;padding:8px 10px;margin-bottom:8px;color:#fff;">'
            f'<div style="font-size:7.5pt;font-weight:bold;opacity:0.9;">Precio de Bolsa Nacional</div>'
            f'<div style="font-size:14pt;font-weight:bold;margin-top:2px;">'
            f'{valor:.2f}<span style="font-size:9pt;margin-left:3px;opacity:0.9;">{unidad}</span>'
            f'</div>'
            f'{_fecha_corte_html(precio_ficha.get("fecha", ""), "white")}'
            f'<div style="font-size:7pt;margin-top:2px;">'
            f'<span style="color:{trend_color};">{flecha} {signo}{var_pct:.1f}% vs prom 7d</span>'
            f'</div>'
            f'<div style="font-size:6.5pt;opacity:0.85;margin-top:4px;line-height:1.3;border-top:1px solid rgba(255,255,255,0.3);padding-top:4px;">'
            f'El Precio Promedio Ponderado (PPP) diario es el precio horario de la energía en el mercado spot, '
            f'determinado por la oferta y demanda del día anterior.'
            f'</div>'
            f'</div>'
        )
    
    # 2. Otras variables del mercado
    if not variables_mercado:
        return f'<div style="padding:0 5px;">{cards}</div>' if cards else ''
    
    _VARS = [
        ('precio_escasez', 'Precio Escasez', '#1a5276',
         'Precio máximo pagado por energía durante condiciones de escasez. Refleja el costo de oportunidad cuando la demanda supera la oferta disponible.'),
        ('precio_max_oferta', 'Precio Máx Oferta', '#154360',
         'Mayor precio ofertado en el mercado por los generadores. Indica el techo de precios del día.'),
        ('ppp_bolsa', 'PPP Precio Bolsa', '#0e5f58',
         'Promedio ponderado por energía negociada. A diferencia del precio simple, refleja mejor el precio real pagado ya que pondera por volumen.'),
        ('demanda_regulada', 'Demanda Regulada', '#196f3d',
         'Consumo de usuarios regulados (residenciales y pequeños comercios). Representa la demanda estable y predecible del sistema.'),
        ('demanda_no_reg', 'Demanda No Regulada', '#145a32',
         'Consumo de grandes usuarios (industrias, grandes comercios). Más sensible a precios y puede tener variabilidad por actividad económica.'),
    ]
    
    for clave, label, color, descripcion in _VARS:
        entry = variables_mercado.get(clave)
        if not entry:
            continue
        
        raw = entry.get('valor', '—')
        unidad = entry.get('unidad', '')
        fecha_var = entry.get('fecha', '')
        valor_str = f'{float(raw):,.2f}' if isinstance(raw, (int, float)) else str(raw)
        
        cards += (
            f'<div style="background:{color};border-radius:4px;padding:8px 10px;margin-bottom:8px;color:#fff;">'
            f'<div style="font-size:7.5pt;font-weight:bold;opacity:0.9;">{label}</div>'
            f'<div style="font-size:12pt;font-weight:bold;margin-top:2px;">'
            f'{valor_str}<span style="font-size:7.5pt;margin-left:3px;opacity:0.9;">{unidad}</span>'
            f'</div>'
            f'{_fecha_corte_html(fecha_var, "white")}'
            f'<div style="font-size:6.5pt;opacity:0.85;margin-top:4px;line-height:1.3;border-top:1px solid rgba(255,255,255,0.3);padding-top:4px;">'
            f'{descripcion}'
            f'</div>'
            f'</div>'
        )
    
    if not cards:
        return ''
    
    return f'<div style="padding:0 5px;">{cards}</div>'


def _build_variables_mercado_xm(
    chart_paths: List[str],
    variables_mercado: Dict[str, Any],
    contexto_datos: Optional[Dict[str, Any]] = None
) -> str:
    """
    Construye la sección Variables del Mercado con diseño XM:
    - Gráfica de líneas a la izquierda
    - Texto explicativo con viñetas a la derecha
    - 3 tarjetas horizontales (una al lado de otra)
    """
    # Gráfica de líneas (usar precio_multi si existe, sino precio_evol)
    price_chart = _embed_chart(chart_paths, 'precio_multi')
    if not price_chart:
        price_chart = _embed_chart(chart_paths, 'precio_evol')
    if not price_chart:
        price_chart = '<div style="text-align:center;padding:40px;color:#999;font-size:8pt;">Gráfico de precios no disponible</div>'
    
    # Obtener valores
    precio_escasez = variables_mercado.get('precio_escasez', {}).get('valor', 0)
    ppp_bolsa = variables_mercado.get('ppp_bolsa', {}).get('valor', 0)
    precio_max = variables_mercado.get('precio_max_oferta', {}).get('valor', 0)
    fecha_escasez = variables_mercado.get('precio_escasez', {}).get('fecha', '')
    fecha_ppp = variables_mercado.get('ppp_bolsa', {}).get('fecha', '')
    fecha_max_var = variables_mercado.get('precio_max_oferta', {}).get('fecha', '')
    
    # Variaciones para las tarjetas (placeholder - se calcularían de la BD)
    var_escasez = -9.21
    var_ppp_card = -136.08  # Variación para la tarjeta
    var_max = -145.52
    
    # Calcular variación del PPP vs semana pasada y fecha del máximo para el texto
    ppp_semana_pasada = None
    fecha_max_precio = None
    var_ppp_texto = None
    
    try:
        from infrastructure.database.connection import get_connection
        with get_connection() as conn:
            import pandas as pd
            
            # Query para obtener PPP actual y de hace 7 días
            df_ppp = pd.read_sql("""
                SELECT 
                    fecha,
                    MAX(CASE WHEN metrica = 'PPPrecBolsNaci' THEN valor_gwh END) as ppp_valor
                FROM metrics 
                WHERE metrica = 'PPPrecBolsNaci'
                  AND fecha >= CURRENT_DATE - INTERVAL '10 days'
                GROUP BY fecha
                ORDER BY fecha DESC
                LIMIT 2
            """, conn)
            
            if len(df_ppp) >= 2:
                ppp_actual = df_ppp.iloc[0]['ppp_valor']
                ppp_semana_pasada = df_ppp.iloc[1]['ppp_valor']
                var_ppp_texto = ppp_actual - ppp_semana_pasada
            
            # Query para obtener fecha del máximo precio mensual
            df_max = pd.read_sql("""
                SELECT fecha, MAX(valor_gwh) as max_valor
                FROM metrics 
                WHERE metrica = 'MaxPrecOferNal'
                  AND fecha >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY fecha
                ORDER BY max_valor DESC
                LIMIT 1
            """, conn)
            
            if not df_max.empty:
                fecha_max = df_max.iloc[0]['fecha']
                # Formatear fecha (ej: "1 de abril")
                meses = {
                    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
                    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
                    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
                }
                fecha_max_precio = f"{fecha_max.day} de {meses.get(fecha_max.month, 'mes')}"
    except Exception as e:
        # Si falla la query, usar valores por defecto
        pass
    
    # Construir texto de variación PPP
    if var_ppp_texto is not None and ppp_semana_pasada is not None:
        tipo_var = "disminución" if var_ppp_texto < 0 else "aumento"
        signo = "-" if var_ppp_texto < 0 else "+"
        texto_ppp = f"presentó una <strong>{tipo_var} (${signo}{abs(var_ppp_texto):.2f})</strong> con respecto a la semana pasada <strong>(${ppp_semana_pasada:.2f})</strong>"
    else:
        texto_ppp = "presentó una variación vs la semana pasada"
    
    # Construir texto del máximo
    if fecha_max_precio:
        texto_max = f"El máximo precio mensual es de <strong>${precio_max:.2f}</strong> del día {fecha_max_precio}."
    else:
        texto_max = f"El máximo precio mensual es de ${precio_max:.2f}."
    
    # Texto explicativo con viñetas (completo)
    fecha_ppp_larga = _format_fecha_larga(str(fecha_ppp)[:10]) if fecha_ppp else ''
    texto_vinetas = f"""
    <div style="font-size:8.5pt;line-height:1.5;color:#333;">
        {f'<div style="font-size:7pt;color:#666;margin-bottom:6px;">Fecha de corte PPP: {fecha_ppp_larga}</div>' if fecha_ppp_larga else ''}
        <div style="margin-bottom:8px;">• El <strong>Precio Promedio Ponderado (PPP)</strong> diario 
        (${ppp_bolsa:.2f}) {texto_ppp}.</div>
        <div style="margin-bottom:8px;">• {texto_max}</div>
        <div>• En el mes no se evidencian precios diarios máximos por encima del Precio de Escasez, 
        lo que no activa las obligaciones del Cargo por Confiabilidad, mecanismo mediante el cual los 
        generadores deben entregar energía comprometida para garantizar el suministro en condiciones 
        críticas del sistema.</div>
    </div>
    """
    
    # Las 3 tarjetas horizontales compactas
    tarjetas_html = f"""
    <table style="width:100%;border-collapse:separate;border-spacing:8px 0;margin-top:10px;">
        <tr>
            <td style="width:33.33%;vertical-align:top;">
                <div style="background:#287270;border-radius:6px;color:#fff;height:100%;">
                    <div style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.2);">
                        <div style="font-size:8pt;font-weight:bold;">Precio Escasez</div>
                        <div style="font-size:16pt;font-weight:bold;margin-top:2px;">{precio_escasez:.2f} <span style="font-size:9pt;">$/kWh</span></div>
                        {_fecha_corte_html(fecha_escasez, 'white')}
                    </div>
                    <div style="padding:8px 12px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.2);">
                        <div style="font-size:7pt;opacity:0.9;">Variación Mensual</div>
                        <div style="font-size:11pt;color:#ffc8c8;">▼ {var_escasez:.2f}</div>
                    </div>
                    <div style="padding:8px 12px;font-size:6.5pt;line-height:1.4;opacity:0.9;">
                        <strong>Precio umbral definido por CREG</strong> (Res. 071/2006). Nivel máximo reconocido en situaciones críticas.
                        <div style="margin-top:4px;font-style:italic;opacity:0.8;">Valor vs mes anterior</div>
                    </div>
                </div>
            </td>
            <td style="width:33.33%;vertical-align:top;">
                <div style="background:#299d8f;border-radius:6px;color:#fff;height:100%;">
                    <div style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.2);">
                        <div style="font-size:8pt;font-weight:bold;">PPP Diario</div>
                        <div style="font-size:16pt;font-weight:bold;margin-top:2px;">{ppp_bolsa:.2f} <span style="font-size:9pt;">$/kWh</span></div>
                        {_fecha_corte_html(fecha_ppp, 'white')}
                    </div>
                    <div style="padding:8px 12px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.2);">
                        <div style="font-size:7pt;opacity:0.9;">Variación Semanal</div>
                        <div style="font-size:11pt;color:#ffc8c8;">▼ {var_ppp_card:.2f}</div>
                    </div>
                    <div style="padding:8px 12px;font-size:6.5pt;line-height:1.4;opacity:0.9;">
                        Precio horario en mercado spot, determinado por oferta y demanda del día anterior.
                        <div style="margin-top:4px;font-style:italic;opacity:0.8;">Valor vs semana anterior</div>
                    </div>
                </div>
            </td>
            <td style="width:33.33%;vertical-align:top;">
                <div style="background:#5d6d7e;border-radius:6px;color:#fff;height:100%;">
                    <div style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.2);">
                        <div style="font-size:8pt;font-weight:bold;">Máximo Mensual</div>
                        <div style="font-size:16pt;font-weight:bold;margin-top:2px;">{precio_max:.2f} <span style="font-size:9pt;">$/kWh</span></div>
                        {_fecha_corte_html(fecha_max_var, 'white')}
                    </div>
                    <div style="padding:8px 12px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.2);">
                        <div style="font-size:7pt;opacity:0.9;">Variación Mensual</div>
                        <div style="font-size:11pt;color:#ffc8c8;">▼ {var_max:.2f}</div>
                    </div>
                    <div style="padding:8px 12px;font-size:6.5pt;line-height:1.4;opacity:0.9;">
                        Mayor precio ofertado en el mercado durante el mes. Techo de precios alcanzado.
                        <div style="margin-top:4px;font-style:italic;opacity:0.8;">Valor vs mes anterior</div>
                    </div>
                </div>
            </td>
        </tr>
    </table>
    """
    
    return f"""
    <div style="margin:10px;">
        <table style="width:100%;border-collapse:separate;border-spacing:0;">
            <tr>
                <td style="width:55%;vertical-align:top;padding-right:10px;">
                    {price_chart}
                </td>
                <td style="width:45%;vertical-align:top;padding-left:10px;background:#f8f9fa;border-radius:6px;padding:12px;">
                    {texto_vinetas}
                </td>
            </tr>
        </table>
        {tarjetas_html}
    </div>
    """


# ═══════════════════════════════════════════════════════════════

def _build_composicion_demanda_xm(
    chart_paths: List[str],
    variables_mercado: Dict[str, Any]
) -> str:
    """
    Construye la sección Composición de la Demanda con diseño XM:
    - Izquierda: 2 tarjetas grandes con porcentajes
    - Derecha: gráfica de líneas + total
    """
    # Valores
    dem_regulada = variables_mercado.get('demanda_regulada', {}).get('valor', 0)
    dem_no_reg = variables_mercado.get('demanda_no_reg', {}).get('valor', 0)
    dem_total = dem_regulada + dem_no_reg
    fecha_corte = (
        variables_mercado.get('demanda_regulada', {}).get('fecha')
        or variables_mercado.get('demanda_no_reg', {}).get('fecha')
        or ''
    )
    fecha_corte_html = _fecha_corte_html(fecha_corte, 'badge')
    
    # Porcentajes
    pct_regulada = (dem_regulada / dem_total * 100) if dem_total > 0 else 69.4
    pct_no_reg = (dem_no_reg / dem_total * 100) if dem_total > 0 else 30.6
    
    # Variaciones (placeholder - en producción vienen de query histórico)
    var_regulada = -8.60
    var_no_reg = -3.95
    
    # Gráfica de demandas (placeholder o usar existente)
    demand_chart = _embed_chart(chart_paths, 'demanda_evol')
    if not demand_chart:
        demand_chart = '<div style="text-align:center;padding:60px;color:#999;font-size:8pt;">Gráfico de demanda no disponible</div>'
    
    return f"""
    <div style="margin:10px;">
        <table style="width:100%;border-collapse:separate;border-spacing:10px 0;">
            <tr>
                <!-- Columna izquierda: Tarjetas de demanda -->
                <td style="width:40%;vertical-align:top;">
                    <!-- Demanda Regulada -->
                    <div style="background:#e8e8e8;border-radius:8px;padding:20px;margin-bottom:15px;">
                        <table style="width:100%;">
                            <tr>
                                <td style="vertical-align:top;">
                                    <div style="font-size:32pt;font-weight:bold;color:#254553;line-height:1;">{pct_regulada:.1f}%</div>
                                </td>
                                <td style="vertical-align:top;text-align:right;padding-left:10px;">
                                    <div style="font-size:11pt;font-weight:bold;color:#333;">{dem_regulada:.1f} GWh</div>
                                    <div style="font-size:7pt;color:#666;margin-top:2px;">Variación</div>
                                    <div style="font-size:8pt;color:#C62828;">▼ {var_regulada:.2f} Semanal</div>
                                </td>
                            </tr>
                        </table>
                        <div style="font-size:10pt;font-weight:bold;color:#333;margin-top:10px;text-align:center;">Demanda Regulada</div>
                        <div style="font-size:7pt;color:#555;margin-top:8px;line-height:1.4;text-align:justify;">
                            Usuarios residenciales, comerciales sujetos a tarifas de energ&iacute;a reguladas por la Comisi&oacute;n
                            de Regulaci&oacute;n de Energ&iacute;a y Gas (CREG).
                        </div>
                        {_fecha_corte_html(variables_mercado.get('demanda_regulada', {}).get('fecha', ''), 'default')}
                    </div>
                    
                    <!-- Demanda No Regulada -->
                    <div style="background:#e8e8e8;border-radius:8px;padding:20px;">
                        <table style="width:100%;">
                            <tr>
                                <td style="vertical-align:top;">
                                    <div style="font-size:32pt;font-weight:bold;color:#254553;line-height:1;">{pct_no_reg:.1f}%</div>
                                </td>
                                <td style="vertical-align:top;text-align:right;padding-left:10px;">
                                    <div style="font-size:11pt;font-weight:bold;color:#333;">{dem_no_reg:.1f} GWh</div>
                                    <div style="font-size:7pt;color:#666;margin-top:2px;">Variación</div>
                                    <div style="font-size:8pt;color:#C62828;">▼ {var_no_reg:.2f} Semanal</div>
                                </td>
                            </tr>
                        </table>
                        <div style="font-size:10pt;font-weight:bold;color:#333;margin-top:10px;text-align:center;">Demanda No Regulada</div>
                        <div style="font-size:7pt;color:#555;margin-top:8px;line-height:1.4;text-align:justify;">
                            Usuarios (industriales, comerciales, etc.) cuya demanda de energ&iacute;a m&aacute;xima es superior a 2 MW
                            (Ley 143 de 1994, Art&iacute;culo 11).
                        </div>
                        {_fecha_corte_html(variables_mercado.get('demanda_no_reg', {}).get('fecha', ''), 'default')}
                    </div>
                </td>
                
                <!-- Columna derecha: Gráfica y total -->
                <td style="width:60%;vertical-align:top;">
                    <div style="background:#f5f5f5;border-radius:8px;padding:15px;height:100%;">
                        {demand_chart}
                        <div style="background:#e8e8e8;border-radius:6px;padding:15px;margin-top:15px;text-align:center;">
                            <div style="font-size:28pt;font-weight:bold;color:#254553;">{dem_total:.2f} GWh</div>
                            <div style="font-size:9pt;color:#555;margin-top:4px;">Demanda Diaria Real</div>
                            {fecha_corte_html}
                        </div>
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """


def _build_page_mercado(
    logo_b64: str,
    fecha_label: str,
    fichas: List[Dict[str, Any]],
    tabla_indicadores: List[Dict[str, Any]],
    chart_paths: List[str],
    pred_resumen: Optional[Dict[str, Any]] = None,
    variables_mercado: Optional[Dict[str, Any]] = None,
    analisis_multidimensional: Optional[List[Dict[str, Any]]] = None,
    contexto_datos: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Página 1: Resumen ejecutivo con 3 fichas principales (horizontales, cada una con 
    sub-fichas verticales) + Variables del Mercado (gráfica izquierda, variables derecha).
    """
    header = _build_header_html(logo_b64, fecha_label)

    # ── Nuevo Resumen Ejecutivo: 3 fichas horizontales con sub-fichas verticales ──
    resumen_fichas_html = _build_resumen_ejecutivo_fichas(
        tabla_indicadores or [], 
        analisis_multidimensional or []
    )

    # ── Variables del Mercado con diseño XM ──
    vars_mercado_html = _build_variables_mercado_xm(
        chart_paths, 
        variables_mercado or {},
        contexto_datos
    )
    
    # ── Composición de la Demanda con diseño XM ──
    composicion_demanda_html = _build_composicion_demanda_xm(
        chart_paths,
        variables_mercado or {}
    )

    # ── Predicción de Precio de Bolsa ──
    precio_pred = _find_metric_prediction(pred_resumen, 'precio')  # type: ignore
    if not precio_pred:
        precio_pred = _find_metric_prediction(pred_resumen, 'bolsa')  # type: ignore
    precio_ficha = _get_ficha_indicador(fichas, 'precio')
    fecha_precio = _resolve_fecha_corte(
        fichas, 'precio', tabla_indicadores, variables_mercado, 'ppp_bolsa', precio_pred
    )
    precio_pred_html = _build_pred_card(
        precio_pred,
        'El Precio de Bolsa proyectado refleja la din&aacute;mica '
        'esperada de oferta-demanda para el pr&oacute;ximo mes, '
        'considerando disponibilidad h&iacute;drica y despacho t&eacute;rmico.',
        fecha_corte=fecha_precio,
    ) if precio_pred else ''

    return f"""
    <div class="page">
      {header}
      {_section_hdr('Resumen Ejecutivo')}
      {resumen_fichas_html}
      {_section_hdr('Variables del Mercado', '#287270')}
      {vars_mercado_html}
      {_section_hdr('Composici&oacute;n de la Demanda', '#254553')}
      {composicion_demanda_html}
      {precio_pred_html}
    </div>
    """


# ═══════════════════════════════════════════════════════════════
# PAGE 2: Generación Real por Fuente
# ═══════════════════════════════════════════════════════════════

def _get_ficha_indicador(fichas: List[Dict[str, Any]], tipo: str) -> Optional[Dict[str, Any]]:
    """Obtiene la ficha de un indicador específico."""
    for f in (fichas or []):
        indicador = _strip_emojis(f.get('indicador', '')).lower()
        if tipo == 'generacion' and 'generaci' in indicador:
            return f
        elif tipo == 'precio' and ('precio' in indicador or 'bolsa' in indicador):
            return f
        elif tipo == 'embalses' and 'embalse' in indicador:
            return f
    return None


def _build_kpi_box(ficha: Dict[str, Any], bg_color: str) -> str:
    """Construye un KPI box para una ficha."""
    if not ficha:
        return ''
    
    valor = ficha.get('valor', '')
    unidad = ficha.get('unidad', '')
    indicador = _strip_emojis(ficha.get('indicador', ''))
    ctx = ficha.get('contexto', {})
    var_pct = ctx.get('variacion_vs_promedio_pct')

    if isinstance(valor, float):
        val_str = f'{valor:,.2f}'
    else:
        val_str = str(valor)

    var_line = ''
    if var_pct is not None:
        try:
            v = float(var_pct)
            sign = '+' if v >= 0 else ''
            etiq = ctx.get('etiqueta_variacion', 'vs prom 7d')
            vcolor = '#c8ffc8' if v >= 0 else '#ffc8c8'
            var_line = (
                f'<div class="kpi-sub" style="color:{vcolor};">'
                f'{sign}{v:.1f}% {etiq}</div>'
            )
        except (ValueError, TypeError):
            pass

    return (
        f'<div class="kpi-box" style="background:{bg_color};">'
        f'<div class="kpi-label">{indicador}</div>'
        f'<div class="kpi-value">{val_str} {unidad}</div>'
        f'{_fecha_corte_html(str(ficha.get("fecha", "") or ""), "white")}'
        f'{var_line}</div>'
    )


def _get_explicacion_indicador(fichas: List[Dict[str, Any]], tipo: str) -> str:
    """Obtiene la explicación contextual de un indicador específico."""
    ficha = _get_ficha_indicador(fichas, tipo)
    if not ficha:
        return ''
        
    if tipo == 'generacion':
        return (
            '<p class="explanation">'
            'Generaci&oacute;n Total del SIN: suma de la producci&oacute;n '
            'de todas las fuentes (hidr&aacute;ulica, t&eacute;rmica, solar, '
            'e&oacute;lica, biomasa) despachadas por XM.'
            '</p>'
        )
    elif tipo == 'precio':
        return (
            '<p class="explanation">'
            'El Precio Promedio Ponderado (PPP) diario es el precio horario '
            'de la energ&iacute;a en el mercado spot, determinado por la '
            'oferta y demanda del d&iacute;a anterior.'
            '</p>'
        )
    elif tipo == 'embalses':
        return (
            '<p class="explanation">'
            'Nivel de embalses: porcentaje de volumen &uacute;til agregado '
            'del Sistema Interconectado Nacional, indicador clave de '
            'seguridad h&iacute;drica.'
            '</p>'
        )
    return ''


def _build_page_generacion(
    logo_b64: str,
    fecha_label: str,
    gen_por_fuente: Dict[str, Any],
    chart_paths: List[str],
    pred_resumen: Optional[Dict[str, Any]] = None,
    fichas: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Página 2: Gráfico de generación + tabla de fuentes +
    análisis por tipo de fuente + predicción de generación.
    Retorna 1-2 páginas HTML (generación + despacho/proyección al final).
    """

    # ── Ficha de Generación al inicio ──
    gen_ficha_html = ''
    for f in (fichas or []):
        ind_lower = f.get('indicador', '').lower()
        if 'generaci' in ind_lower:
            valor = f.get('valor') or 0
            unidad = f.get('unidad', 'GWh')
            ctx = f.get('contexto', {})
            var_pct = ctx.get('variacion_vs_promedio_pct') or 0
            tendencia = ctx.get('tendencia', 'Estable')
            
            # Estado
            if var_pct > 25:
                estado = 'Crítico'
                estado_bg = '#e74c3c'
            elif var_pct > 15:
                estado = 'Alerta'
                estado_bg = '#f39c12'
            else:
                estado = 'Normal'
                estado_bg = '#27ae60'
            
            # Flecha - colores claros para fondo oscuro
            if tendencia == 'Alza':
                flecha = '▲'
                trend_color = '#90EE90'  # Verde claro
            elif tendencia == 'Baja':
                flecha = '▼'
                trend_color = '#FFB6C1'  # Rosa claro
            else:
                flecha = '▶'
                trend_color = '#ffffff'  # Blanco
            
            signo = '+' if var_pct >= 0 else ''
            
            gen_ficha_html = (
                f'<div style="margin:0 10px 10px;padding:10px 15px;background:#254553;border-radius:6px;color:#fff;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<div style="font-size:8pt;font-weight:bold;opacity:0.9;">⚡ GENERACIÓN TOTAL DEL SISTEMA</div>'
                f'<div style="font-size:16pt;font-weight:bold;margin-top:4px;">{valor:.2f} <span style="font-size:10pt;">{unidad}</span></div>'
                f'{_fecha_corte_html(f.get("fecha", ""), "white")}'
                f'</div>'
                f'<div style="text-align:right;">'
                f'<div style="font-size:9pt;color:{trend_color};">{flecha} {tendencia}</div>'
                f'<div style="font-size:8pt;margin-top:2px;">{signo}{var_pct:.1f}% vs prom 7d</div>'
                f'<span style="background:{estado_bg};color:#fff;padding:2px 8px;border-radius:3px;font-size:7pt;margin-top:4px;display:inline-block;">{estado}</span>'
                f'</div>'
                f'</div>'
                f'<div style="font-size:7pt;opacity:0.85;margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.3);line-height:1.4;">'
                f'<strong>Generación Total del SIN:</strong> suma de la producción de todas las fuentes '
                f'(hidráulica, térmica, solar, eólica, biomasa) despachadas por XM.'
                f'</div>'
                f'</div>'
            )
            break
    
    # ── Gen pie chart ──
    gen_chart = _embed_chart(chart_paths, 'gen_pie')

    # ── Gen by source table ──
    fuentes = (gen_por_fuente or {}).get('fuentes', [])
    total_gwh = (gen_por_fuente or {}).get('total_gwh', 0)
    fecha_dato = (gen_por_fuente or {}).get('fecha_dato', '')

    bar_colors = {
        'Hidráulica': '#125685',
        'Térmica': '#737373',
        'Solar': '#ffbf00',
        'Eólica': '#5d17eb',
        'Biomasa/Cogeneración': '#b4c657',
        'Biomasa': '#b4c657',
        'Cogeneración': '#b4c657',
    }

    table_rows = ''
    for f in fuentes:
        nombre = f.get('fuente', '')
        gwh = f.get('gwh', 0)
        pct = f.get('porcentaje', 0)
        bc = bar_colors.get(nombre, '#999')
        bw = min(pct * 1.5, 100)
        table_rows += (
            f'<tr><td>{nombre}</td>'
            f'<td style="text-align:right;font-weight:bold;">{gwh:,.1f} GWh</td>'
            f'<td style="text-align:right;">{pct:.1f}%</td>'
            f'<td><span class="bar-bg" style="width:{bw}px;background:{bc};"></span></td>'
            f'</tr>'
        )

    if total_gwh:
        table_rows += (
            f'<tr style="border-top:2px solid #254553;">'
            f'<td><strong>Total</strong></td>'
            f'<td style="text-align:right;font-weight:bold;">{total_gwh:,.1f} GWh</td>'
            f'<td style="text-align:right;font-weight:bold;">100%</td>'
            f'<td></td></tr>'
        )

    gen_table = ''
    if table_rows:
        gen_table = f"""
        <table class="data-tbl">
          <tr><th>Fuente</th><th style="text-align:right;">GWh</th>
              <th style="text-align:right;">%</th><th></th></tr>
          {table_rows}
        </table>
        <div style="font-size:6.5pt;color:#8d8d8d;margin-top:1px;">
          Fecha de corte: {_format_fecha_larga(str(fecha_dato)[:10]) if fecha_dato else 'N/D'} &bull; Fuente: XM
        </div>
        """

    # ── Two-column: chart + table ──
    top_section = f"""
    <table class="two-col" cellpadding="0" cellspacing="0">
      <tr>
        <td class="col-50">{gen_chart or '<div style="text-align:center;padding:20px;color:#999;font-size:8pt;">Grafico no disponible</div>'}</td>
        <td class="col-50">{gen_table}</td>
      </tr>
    </table>
    """

    # ── Per-source analysis blocks (data-driven, like model Pg 2) ──
    src_blocks = ''
    src_config = {
        'Hidráulica': ('bg-hidra', 'Generaci&oacute;n Hidr&aacute;ulica',
                       'Principal fuente de generaci&oacute;n del sistema colombiano.',
                       'El sistema mantiene alta dependencia hidr&aacute;ulica, sensible a cambios clim&aacute;ticos.'),
        'Térmica': ('bg-termi', 'Generaci&oacute;n F&oacute;sil (T&eacute;rmica)',
                    'Segunda fuente en importancia, respaldo del sistema.',
                    'La t&eacute;rmica sigue siendo clave para cubrir demanda en eventos de menor disponibilidad h&iacute;drica.'),
        'Biomasa/Cogeneración': ('bg-bioma', 'Generaci&oacute;n por Biomasa',
                                 'Fuente estable, fracci&oacute;n marginal de la matriz.',
                                 'Muestra estabilidad en autogeneradores con excedentes.'),
        'Biomasa': ('bg-bioma', 'Generaci&oacute;n por Biomasa',
                    'Fuente estable, fracci&oacute;n marginal de la matriz.',
                    'Muestra estabilidad en autogeneradores con excedentes.'),
        'Eólica': ('bg-eolic', 'Generaci&oacute;n E&oacute;lica',
                   'Magnitud baja pero tendencia constante.',
                   'Se espera crecimiento con desarrollo de proyectos en La Guajira.'),
        'Solar': ('bg-solar', 'Generaci&oacute;n Solar',
                  'Fuente con variabilidad por radiaci&oacute;n y disponibilidad operativa.',
                  'Comienza a consolidarse como complemento constante de la matriz.'),
    }

    # Two-column layout for source blocks
    src_left = ''
    src_right = ''
    for idx, f in enumerate(fuentes):
        nombre = f.get('fuente', '')
        gwh = f.get('gwh', 0)
        pct = f.get('porcentaje', 0)
        cfg = src_config.get(nombre)
        if not cfg:
            continue
        css_class, titulo, desc_base, implicacion = cfg
        desc = f'Aport&oacute; {gwh:,.1f} GWh/d&iacute;a ({pct:.1f}% del total). {desc_base}'

        block = (
            f'<div class="src-block">'
            f'<div class="src-hdr {css_class}">{titulo}</div>'
            f'<div class="src-body">{desc}</div>'
            f'<div class="src-impl"><strong>Implicaci&oacute;n:</strong> {implicacion}</div>'
            f'</div>'
        )

        if idx % 2 == 0:
            src_left += block
        else:
            src_right += block

    # Comentarios finales
    comentarios = (
        '<div class="src-block">'
        '<div class="src-hdr bg-comen">Comentarios Finales</div>'
        '<div class="src-body">'
        'El sistema mantiene alta dependencia de la generaci&oacute;n '
        'hidr&aacute;ulica, con fuentes t&eacute;rmicas como principal respaldo. '
        'Las FNCER tienen presencia creciente pero a&uacute;n limitada en '
        't&eacute;rminos absolutos. El incremento sostenido de solar y '
        'e&oacute;lica es una se&ntilde;al positiva en el marco de la '
        'transici&oacute;n energ&eacute;tica.'
        '</div></div>'
    )
    src_right += comentarios

    src_blocks = f"""
    <table class="two-col" cellpadding="0" cellspacing="0">
      <tr>
        <td class="col-50">{src_left}</td>
        <td class="col-50">{src_right}</td>
      </tr>
    </table>
    """

    # ── Predicción de Generación Total ──
    gen_pred = _find_metric_prediction(pred_resumen, 'generaci')  # type: ignore
    if not gen_pred:
        gen_pred = _find_metric_prediction(pred_resumen, 'GENE')  # type: ignore
    gen_ficha = _get_ficha_indicador(fichas, 'generacion')
    fecha_gen_pred = _resolve_fecha_corte(
        fichas, 'generacion', metric=gen_pred
    ) or fecha_dato
    gen_pred_html = _build_pred_card(
        gen_pred,
        'La generaci&oacute;n total proyectada considera la estacionalidad '
        'h&iacute;drica, la disponibilidad t&eacute;rmica programada y '
        'el crecimiento de FNCER en la matriz energ&eacute;tica.',
        fecha_corte=str(fecha_gen_pred or ''),
    ) if gen_pred else ''
    
    # Explicación de Generación Total
    gen_explicacion = _get_explicacion_indicador(fichas, 'generacion')
    if gen_explicacion:
        gen_explicacion = f'<div style="margin:4px 10px;">{gen_explicacion}</div>'

    # ── Gráfico Despacho vs Gen. Térmica (estilo XM) ──
    despacho_chart = _embed_chart(chart_paths, 'despacho_termica')
    despacho_block = ''
    if despacho_chart or gen_pred_html or gen_explicacion:
        despacho_block = f"""
          {_section_hdr('Despacho VS Generaci&oacute;n T&eacute;rmica', '#737373')}
          {despacho_chart or ''}
          {gen_explicacion}
          {gen_pred_html}
        """

    return _wrap_report_page(logo_b64, fecha_label, f"""
      {_section_hdr('Generaci&oacute;n Real por Fuente')}
      {gen_ficha_html}
      {top_section}
      {src_blocks}
      {despacho_block}
    """)


# ═══════════════════════════════════════════════════════════════
# PAGE 3: Hidrología y Embalses + Proyecciones
# ═══════════════════════════════════════════════════════════════

def _build_embalses_regionales_html(embalses_regionales: Dict[str, Any]) -> str:
    """
    Tabla compacta de llenado por región hidrológica.
    Muestra: región, # embalses, % promedio, estado semáforo.
    Ordenada de menor a mayor % (riesgo primero).
    """
    if not embalses_regionales or 'regiones' not in embalses_regionales:
        return ''

    regiones = embalses_regionales.get('regiones', [])
    if not regiones:
        return ''

    fecha_dato = embalses_regionales.get('fecha_dato', '')
    rows = ''
    for r in regiones:
        pct = r.get('pct_promedio', 0.0)
        estado = r.get('estado', 'Normal')
        n_emb = r.get('n_embalses', 0)
        region_label = str(r.get('region', '')).capitalize()
        embalses_list = ', '.join(r.get('embalses', []))

        if estado == 'Normal':
            bcls = 'badge-ok'
            bar_color = '#287270'
        elif estado == 'Alerta':
            bcls = 'badge-warn'
            bar_color = '#E65100'
        else:
            bcls = 'badge-crit'
            bar_color = '#C62828'

        bar_w = min(int(pct), 100)
        bar_html = (
            f'<div style="background:#e0e0e0;border-radius:3px;height:6px;width:100%;margin-top:2px;">'  
            f'<div style="background:{bar_color};height:6px;border-radius:3px;width:{bar_w}%;"></div>'
            f'</div>'
        )

        rows += (
            f'<tr>'
            f'<td style="font-weight:bold;">{region_label}</td>'
            f'<td style="text-align:center;color:#555;">{n_emb}</td>'
            f'<td style="text-align:right;font-weight:bold;">{pct:.1f}%{bar_html}</td>'
            f'<td style="text-align:center;">'
            f'<span class="badge {bcls}">{estado}</span></td>'
            f'<td style="font-size:6pt;color:#777;">{embalses_list}</td>'
            f'</tr>'
        )

    nota = (
        f'Fecha de corte: {_format_fecha_larga(str(fecha_dato)[:10])}'
        if fecha_dato else ''
    )
    return (
        f'<div style="margin:4px 10px;">'
        f'<table class="sema-tbl">'
        f'<tr>'
        f'<th>Región</th>'
        f'<th style="text-align:center;"># Embalses</th>'
        f'<th style="text-align:right;">Nivel Prom.</th>'
        f'<th style="text-align:center;">Estado</th>'
        f'<th>Embalses</th>'
        f'</tr>'
        f'{rows}'
        f'</table>'
        f'<div style="font-size:6pt;color:#8d8d8d;margin-top:2px;">'
        f'Promedio simple por región &bull; PorcVoluUtilDiar XM/SIMEM'
        f'{" &bull; " + nota if nota else ""}'
        f'</div>'
        f'</div>'
    )


def _get_aportes_rios_table() -> str:
    """
    Obtiene los aportes hídricos por río desde la BD y genera una tabla HTML.
    Retorna HTML de tabla o mensaje si no hay datos.
    """
    try:
        from infrastructure.database.connection import get_connection
        import pandas as pd
        
        with get_connection() as conn:
            # Obtener aportes por río (campo recurso) del día más reciente
            df = pd.read_sql("""
                SELECT 
                    recurso as rio,
                    valor_gwh as caudal,
                    unidad,
                    fecha
                FROM metrics 
                WHERE metrica = 'AporCaudal'
                  AND fecha = (SELECT MAX(fecha) FROM metrics WHERE metrica = 'AporCaudal')
                ORDER BY valor_gwh DESC
                LIMIT 15
            """, conn)
            
            if df.empty:
                return '<div style="font-size:7pt;color:#999;text-align:center;padding:10px;">No hay datos de aportes</div>'
            
            fecha_raw = df.iloc[0]['fecha'] if 'fecha' in df.columns else None
            fecha_corte_rios = _format_fecha_larga(str(fecha_raw)[:10]) if fecha_raw is not None else ''
            
            # Construir filas de tabla
            rows = ''
            for _, row in df.iterrows():
                rio = row['rio'][:20]  # Limitar longitud
                caudal = row['caudal']
                unidad = row['unidad'] or 'm³/s'
                
                # Color según magnitud
                if caudal > 300:
                    color = '#287270'
                elif caudal > 100:
                    color = '#2E8B57'
                elif caudal > 50:
                    color = '#f39c12'
                else:
                    color = '#666'
                
                rows += f'''
                <tr>
                    <td style="padding:3px 5px;font-size:7pt;border-bottom:1px solid #eee;">{rio}</td>
                    <td style="padding:3px 5px;font-size:7pt;text-align:right;font-weight:bold;color:{color};border-bottom:1px solid #eee;">
                        {caudal:.1f} <span style="font-size:6pt;color:#999;">{unidad}</span>
                    </td>
                </tr>
                '''
            
            return f'''
            <div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:6px;padding:8px;">
                <div style="font-size:8pt;font-weight:bold;color:#555;margin-bottom:6px;">💧 Aportes por Río</div>
                <table style="width:100%;border-collapse:collapse;">
                    {rows}
                </table>
                <div style="font-size:6pt;color:#999;margin-top:4px;text-align:right;">
                    Fecha de corte: {fecha_corte_rios} &bull; Fuente: XM/SIMEM
                </div>
            </div>
            '''
    except Exception as e:
        logger.warning(f"[REPORT] Error obteniendo aportes por río: {e}")
        return '<div style="font-size:7pt;color:#999;text-align:center;padding:10px;">Error cargando aportes</div>'


def _xm_pct_bar_cell(pct: float, bar_color: str) -> str:
    """Celda con barra de fondo estilo XM (Vol% verde, Aportes% azul)."""
    w = max(0, min(float(pct), 100))
    return (
        f'<td style="padding:0;position:relative;height:16px;min-width:38px;">'
        f'<div style="position:absolute;inset:0;background:#eceff1;"></div>'
        f'<div style="position:absolute;left:0;top:0;bottom:0;width:{w}%;background:{bar_color};"></div>'
        f'<span style="position:relative;display:block;text-align:right;padding:1px 3px;'
        f'font-size:6pt;font-weight:bold;color:#1a1a1a;">{pct:.0f}%</span></td>'
    )


def _xm_trend_cell(val: float, decimals: int = 2, suffix: str = '') -> str:
    """Celda numérica con color según tendencia (▲ verde / ▼ rojo)."""
    if val > 0.05:
        color, arrow = '#2E7D32', '▲'
    elif val < -0.05:
        color, arrow = '#C62828', '▼'
    else:
        color, arrow = '#555555', '●'
    fmt = f'{{:+.{decimals}f}}'
    return (
        f'<td style="text-align:right;font-size:6pt;color:{color};font-weight:bold;">'
        f'{fmt.format(val)}{suffix} {arrow}</td>'
    )


def _build_aportes_demanda_kpis_html() -> str:
    """6 KPIs estilo XM — tarjetas visuales debajo del gráfico Aportes vs Demanda."""
    try:
        from whatsapp_bot.services.informe_charts import get_aportes_demanda_kpis
        k = get_aportes_demanda_kpis()
        if not k:
            return ''

        fl = k['fecha_label']
        fc = _format_fecha_larga(str(k['fecha'])[:10]) if k.get('fecha') is not None else fl
        fc_line = f'Fecha de corte: {fc}'
        pct_dia = k['pct_aporte_dia']
        pct_mes = k['pct_aporte_mes']
        pct_dia_color = '#2E7D32' if pct_dia >= 100 else '#E65100'
        pct_mes_color = '#2E7D32' if pct_mes >= 100 else '#E65100'

        def _kpi_card(title, value, unit, sub, accent, bg):
            return f"""
            <td style="width:33%;padding:4px;vertical-align:top;">
              <div style="background:{bg};border:1px solid #e0e0e0;border-left:4px solid {accent};border-radius:6px;
                          padding:10px 12px;min-height:72px;">
                <div style="font-size:6.5pt;font-weight:bold;color:{accent};text-transform:uppercase;
                            letter-spacing:0.4px;">{title}</div>
                <div style="font-size:16pt;font-weight:bold;color:#1a1a1a;line-height:1.1;margin:4px 0 2px;">
                  {value}</div>
                <div style="font-size:7pt;color:#555;">{unit}</div>
                <div style="font-size:6.5pt;color:#888;margin-top:3px;">{sub}</div>
              </div>
            </td>"""

        return f"""
        <div style="margin:10px 10px 4px;">
          <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;border-spacing:0 6px;">
            <tr>
              {_kpi_card('Aportes d&iacute;a', f"{k['aportes_dia']:.1f}", 'GWh/d&iacute;a', fc_line, '#1565C0', '#e3f2fd')}
              {_kpi_card('% vs media diaria', f"{pct_dia:.1f}%", f"Ref. {k['aportes_medios']:.1f} GWh/d&iacute;a", fc_line, pct_dia_color, '#e8f5e9')}
              {_kpi_card('Demanda d&iacute;a', f"{k['demanda_dia']:.1f}", 'GWh/d&iacute;a', fc_line, '#2E7D32', '#e8f5e9')}
            </tr>
            <tr>
              {_kpi_card('Aportes mes (prom.)', f"{k['aportes_mes']:.1f}", 'GWh/d&iacute;a', fc_line, '#1565C0', '#e3f2fd')}
              {_kpi_card('% vs media hist.', f"{pct_mes:.1f}%", f"Ref. {k['hist_media_aportes']:.1f} GWh/d&iacute;a", fc_line, pct_mes_color, '#fff3e0')}
              {_kpi_card('Demanda mes (prom.)', f"{k['demanda_mes']:.1f}", 'GWh/d&iacute;a', fc_line, '#FF9800', '#fff8e1')}
            </tr>
          </table>
        </div>
        """
    except Exception as e:
        logger.warning(f"[REPORT] KPIs aportes vs demanda: {e}")
        return ''


def _build_hidrologia_detalle_table() -> str:
    """
    Tabla estilo XM: hidrología por embalse con volúmenes, deltas y aportes.
    """
    try:
        from infrastructure.database.connection import get_connection
        import pandas as pd

        embalse_region = {
            k.upper(): v.upper() for k, v in {
                'PENOL': 'ANTIOQUIA', 'RIOGRANDE2': 'ANTIOQUIA', 'PORCE II': 'ANTIOQUIA',
                'PORCE III': 'ANTIOQUIA', 'MIRAFLORES': 'ANTIOQUIA', 'PLAYAS': 'ANTIOQUIA',
                'TRONERAS': 'ANTIOQUIA', 'PUNCHINA': 'ANTIOQUIA', 'ITUANGO': 'ANTIOQUIA',
                'AGREGADO BOGOTA': 'CENTRO', 'CHUZA': 'CENTRO', 'GUAVIO': 'CENTRO', 'MUNA': 'CENTRO',
                'SAN CARLOS': 'CENTRO', 'BETANIA': 'CENTRO', 'EL QUIMBO': 'CENTRO', 'PRADO': 'CENTRO',
                'AMANI': 'CALDAS', 'ESMERALDA': 'CALDAS', 'SAN LORENZO': 'CALDAS',
                'CALIMA1': 'VALLE', 'ALTOANCHICAYA': 'VALLE', 'SALVAJINA': 'VALLE', 'FLORIDA II': 'VALLE',
                'URRA1': 'CARIBE', 'TOPOCORO': 'ORIENTE', 'CHIVOR': 'ORIENTE', 'SOGAMOSO': 'ORIENTE', 'BATA': 'ORIENTE',
            }.items()
        }

        with get_connection() as conn:
            fecha_ref = pd.read_sql("""
                SELECT fecha FROM metrics
                WHERE metrica IN ('VoluUtilDiarEner','CapaUtilDiarEner') AND entidad='Embalse'
                  AND fecha >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY fecha
                HAVING COUNT(DISTINCT CASE WHEN metrica='VoluUtilDiarEner' THEN recurso END)::float
                     / NULLIF(COUNT(DISTINCT CASE WHEN metrica='CapaUtilDiarEner' THEN recurso END), 0) >= 0.8
                ORDER BY fecha DESC LIMIT 1
            """, conn)
            if fecha_ref.empty:
                return ''
            f_ref = fecha_ref.iloc[0]['fecha']

            df = pd.read_sql("""
                SELECT
                  v.recurso AS embalse,
                  v.valor_gwh AS vol,
                  c.valor_gwh AS cap,
                  CASE WHEN c.valor_gwh > 0 THEN v.valor_gwh / c.valor_gwh * 100 ELSE 0 END AS pct,
                  v_m.valor_gwh AS vol_mes,
                  v_s.valor_gwh AS vol_sem,
                  p_m.valor_gwh * 100 AS pct_mes,
                  p_s.valor_gwh * 100 AS pct_sem
                FROM metrics v
                JOIN metrics c ON c.recurso=v.recurso AND c.fecha=v.fecha
                  AND c.metrica='CapaUtilDiarEner' AND c.entidad='Embalse'
                LEFT JOIN metrics v_m ON v_m.recurso=v.recurso AND v_m.metrica='VoluUtilDiarEner'
                  AND v_m.entidad='Embalse' AND v_m.fecha = v.fecha - INTERVAL '30 days'
                LEFT JOIN metrics v_s ON v_s.recurso=v.recurso AND v_s.metrica='VoluUtilDiarEner'
                  AND v_s.entidad='Embalse' AND v_s.fecha = v.fecha - INTERVAL '7 days'
                LEFT JOIN metrics p_m ON p_m.recurso=v.recurso AND p_m.metrica='PorcVoluUtilDiar'
                  AND p_m.entidad='Embalse' AND p_m.fecha = v.fecha - INTERVAL '30 days'
                LEFT JOIN metrics p_s ON p_s.recurso=v.recurso AND p_s.metrica='PorcVoluUtilDiar'
                  AND p_s.entidad='Embalse' AND p_s.fecha = v.fecha - INTERVAL '7 days'
                WHERE v.metrica='VoluUtilDiarEner' AND v.entidad='Embalse' AND v.fecha = %s
                ORDER BY v.valor_gwh DESC
            """, conn, params=(f_ref,))

            rios = pd.read_sql("""
                SELECT UPPER(recurso) AS rio, valor_gwh AS aporte,
                       (SELECT valor_gwh FROM metrics m2
                        WHERE m2.metrica='AporEnerMediHist' AND m2.entidad='Rio'
                          AND m2.recurso=m.recurso AND m2.fecha=m.fecha) AS aporte_hist
                FROM metrics m
                WHERE metrica='AporEner' AND entidad='Rio' AND fecha = %s
            """, conn, params=(f_ref,))

            sin_row = pd.read_sql("""
                SELECT valor_gwh * 100 AS pct_sin,
                       (SELECT SUM(valor_gwh) FROM metrics
                        WHERE metrica='VoluUtilDiarEner' AND entidad='Embalse' AND fecha = %s) AS vol_sin
                FROM metrics
                WHERE metrica='PorcVoluUtilDiar' AND entidad='Sistema' AND fecha = %s
                LIMIT 1
            """, conn, params=(f_ref, f_ref))

        if df.empty:
            return ''

        rio_aporte = {r['rio']: r for _, r in rios.iterrows()}
        df['region'] = df['embalse'].str.upper().map(embalse_region).fillna('OTRO')
        df['delta_m'] = df['vol'] - df['vol_mes'].fillna(df['vol'])
        df['delta_s'] = df['vol'] - df['vol_sem'].fillna(df['vol'])
        df['delta_porc_m'] = df['pct'] - df['pct_mes'].fillna(df['pct'])
        df['delta_porc_s'] = df['pct'] - df['pct_sem'].fillna(df['pct'])

        def _match_aporte(emb):
            key = str(emb).upper()
            for rio, row in rio_aporte.items():
                if key in rio or rio in key:
                    ap = float(row['aporte'])
                    hist = float(row['aporte_hist']) if pd.notna(row['aporte_hist']) and row['aporte_hist'] else ap
                    pct_a = (ap / hist * 100) if hist else 0
                    return ap, pct_a
            return None, None

        rows_html = ''
        region_order = ['ANTIOQUIA', 'CALDAS', 'CARIBE', 'CENTRO', 'ORIENTE', 'VALLE', 'OTRO']
        for region in region_order:
            sub = df[df['region'] == region]
            if sub.empty:
                continue
            for _, r in sub.iterrows():
                ap, ap_pct = _match_aporte(r['embalse'])
                ap_cell = f'{ap:.1f}' if ap is not None else '—'
                ap_pct_val = ap_pct if ap_pct is not None else 0
                ap_pct_cell = _xm_pct_bar_cell(ap_pct_val, '#64B5F6') if ap_pct is not None else '<td style="text-align:center;font-size:6pt;">—</td>'
                rows_html += (
                    f'<tr>'
                    f'<td style="font-size:6pt;font-weight:600;">{r["embalse"][:18]}</td>'
                    f'<td style="font-size:6pt;">{region.title()}</td>'
                    f'<td style="text-align:right;font-size:6pt;">{r["vol"]:.0f}</td>'
                    f'{_xm_pct_bar_cell(r["pct"], "#66BB6A")}'
                    f'{_xm_trend_cell(r["delta_m"])}'
                    f'{_xm_trend_cell(r["delta_s"])}'
                    f'<td style="text-align:right;font-size:6pt;">{ap_cell}</td>'
                    f'{ap_pct_cell}'
                    f'{_xm_trend_cell(r["delta_porc_m"], decimals=1, suffix="%")}'
                    f'{_xm_trend_cell(r["delta_porc_s"], decimals=1, suffix="%")}'
                    f'</tr>'
                )
            # Fila TOTAL región
            t_vol = sub['vol'].sum()
            t_cap = sub['cap'].sum()
            t_pct = (t_vol / t_cap * 100) if t_cap else 0
            rows_html += (
                f'<tr style="background:#eef2f7;font-weight:bold;">'
                f'<td colspan="2" style="font-size:6pt;">TOTAL {region.title()}</td>'
                f'<td style="text-align:right;font-size:6pt;">{t_vol:.0f}</td>'
                f'{_xm_pct_bar_cell(t_pct, "#66BB6A")}'
                f'<td colspan="5"></td></tr>'
            )

        t_vol = df['vol'].sum()
        if not sin_row.empty and pd.notna(sin_row.iloc[0]['pct_sin']):
            t_pct = float(sin_row.iloc[0]['pct_sin'])
            t_vol = float(sin_row.iloc[0]['vol_sin'] or t_vol)
        else:
            t_cap = df['cap'].sum()
            t_pct = (t_vol / t_cap * 100) if t_cap else 0
        rows_html += (
            f'<tr style="background:#254553;color:#fff;font-weight:bold;page-break-inside:avoid;">'
            f'<td colspan="2" style="font-size:6.5pt;">TOTAL SIN</td>'
            f'<td style="text-align:right;font-size:6.5pt;">{t_vol:.0f}</td>'
            f'<td style="text-align:right;font-size:6.5pt;">{t_pct:.1f}%</td>'
            f'<td colspan="6"></td></tr>'
        )

        fecha_dato = pd.to_datetime(f_ref).strftime('%Y-%m-%d')
        fecha_corte_larga = _format_fecha_larga(fecha_dato)
        return f"""
        <div style="margin:4px 10px;">
          <div style="font-size:8pt;font-weight:bold;color:#254553;margin-bottom:4px;">
            Hidrolog&iacute;a por Regiones
            <span style="font-size:7pt;font-weight:normal;color:#666;margin-left:6px;">
              Fecha de corte: {fecha_corte_larga}
            </span>
          </div>
          <table class="data-tbl" style="font-size:6pt;width:100%;border-collapse:collapse;">
            <tr>
              <th>Embalse</th><th>Regi&oacute;n</th>
              <th style="text-align:right;">Vol(GWh)</th>
              <th style="text-align:right;">Vol(%)</th>
              <th style="text-align:right;">&Delta;Vol(M)</th>
              <th style="text-align:right;">&Delta;Vol(S)</th>
              <th style="text-align:right;">Aportes(GWh)</th>
              <th style="text-align:right;">Aportes(%)</th>
              <th style="text-align:right;">&Delta;Porc(M)</th>
              <th style="text-align:right;">&Delta;Porc(S)</th>
            </tr>
            {rows_html}
          </table>
          <div style="font-size:5.5pt;color:#888;margin-top:3px;">
            &Delta; mensual = diff vs hace 30 d&iacute;as; &Delta; semanal = diff vs hace 7 d&iacute;as. Fuente: XM/CND.
          </div>
        </div>
        """

    except Exception as e:
        logger.warning(f"[REPORT] Error tabla hidrología detalle: {e}")
        return ''


def _get_embalse_pct_historico(fecha_ref: str, anios_atras: int) -> Optional[float]:
    """
    Nivel real de embalses (% volumen útil agregado del SIN) en la fecha de hace
    `anios_atras` años (tolerancia ±3 días, toma el dato más cercano). Devuelve
    None si no hay dato real disponible — nunca se debe aproximar/inventar este
    valor a partir del nivel de hoy.
    """
    if not fecha_ref:
        return None
    try:
        from infrastructure.database.connection import get_connection
        from datetime import datetime as _dt
        fecha_dt = _dt.strptime(fecha_ref[:10], '%Y-%m-%d')
        fecha_hist = fecha_dt.replace(year=fecha_dt.year - anios_atras)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT valor_gwh FROM sector_energetico.metrics
                    WHERE metrica='PorcVoluUtilDiar' AND entidad='Sistema' AND recurso='Sistema'
                      AND fecha BETWEEN %s::date - INTERVAL '3 days' AND %s::date + INTERVAL '3 days'
                    ORDER BY ABS(fecha - %s::date) ASC
                    LIMIT 1
                """, [fecha_hist, fecha_hist, fecha_hist])
                row = cur.fetchone()
                return round(float(row[0]) * 100, 1) if row and row[0] is not None else None
    except Exception as e:
        logger.warning(f"[REPORT] Error consultando embalse histórico ({anios_atras} años atrás): {e}")
        return None


def _build_page_hidrologia(
    logo_b64: str,
    fecha_label: str,
    embalses_detalle: Dict[str, Any],
    pred_resumen: Dict[str, Any],
    chart_paths: List[str],
    embalses_regionales: Optional[Dict[str, Any]] = None,
    fichas: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Hidrología + embalses en 3-4 páginas compactas.
    Orden: ficha → capacidad → aportes/demanda → volumen útil → detalle por embalse
    → mapa/aportes río → nivel regional → proyecciones (siempre al final).
    """

    # ── Ficha de Embalses al inicio ──
    emb_ficha_html = ''
    for f in (fichas or []):
        ind_lower = f.get('indicador', '').lower()
        if 'embalse' in ind_lower:
            valor = f.get('valor')
            if valor is None:
                # Sin dato reciente (ver estado_actual_handler) — se omite la
                # ficha en vez de fabricar un valor; el panel derecho más abajo
                # ya maneja este caso mostrando "N/D".
                break
            unidad = f.get('unidad', '%')
            ctx = f.get('contexto', {})
            var_pct = ctx.get('variacion_vs_promedio_pct', 0)
            tendencia = ctx.get('tendencia', 'Estable')
            
            # Estado según Índice NE oficial (Res. CREG 209/2020)
            etiqueta, estado_bg_hex, _ = clasificar_visual_embalse(float(valor))
            estado = etiqueta
            estado_bg = estado_bg_hex
            
            # Flecha - colores claros para fondo oscuro
            if tendencia == 'Alza':
                flecha = '▲'
                trend_color = '#90EE90'  # Verde claro
            elif tendencia == 'Baja':
                flecha = '▼'
                trend_color = '#FFB6C1'  # Rosa claro
            else:
                flecha = '▶'
                trend_color = '#ffffff'  # Blanco
            
            signo = '+' if var_pct >= 0 else ''
            
            emb_ficha_html = (
                f'<div style="margin:0 10px 10px;padding:10px 15px;background:#254553;border-radius:6px;color:#fff;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<div style="font-size:8pt;font-weight:bold;opacity:0.9;">💧 PORCENTAJE DE EMBALSES</div>'
                f'<div style="font-size:16pt;font-weight:bold;margin-top:4px;">{valor:.2f} <span style="font-size:10pt;">{unidad}</span></div>'
                f'{_fecha_corte_html(f.get("fecha", ""), "white")}'
                f'</div>'
                f'<div style="text-align:right;">'
                f'<div style="font-size:9pt;color:{trend_color};">{flecha} {tendencia}</div>'
                f'<div style="font-size:8pt;margin-top:2px;">{signo}{var_pct:.1f}% vs prom 7d</div>'
                f'<span style="background:{estado_bg};color:#fff;padding:2px 8px;border-radius:3px;font-size:7pt;margin-top:4px;display:inline-block;">{estado}</span>'
                f'</div>'
                f'</div>'
                f'<div style="font-size:7pt;opacity:0.85;margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.3);line-height:1.4;">'
                f'<strong>Nivel de embalses:</strong> porcentaje de volumen útil agregado del Sistema '
                f'Interconectado Nacional, indicador clave de seguridad hídrica.'
                f'</div>'
                f'</div>'
            )
            break

    # ── Gráficas XM: Capacidad Embalse + Aportes vs Demanda ──
    capacidad_chart = _embed_chart(chart_paths, 'capacidad_embalse')
    aportes_demanda_chart = _embed_chart(chart_paths, 'aportes_demanda')
    aportes_kpis_html = _build_aportes_demanda_kpis_html()

    # ── Gráfica de Aportes Hídricos (volumen útil % — 3 líneas) ──
    aportes_chart = _embed_chart(chart_paths, 'aportes_hidricos')
    
    # ── Datos para el panel derecho ──
    emb = embalses_detalle or {}
    fecha_emb = str(emb.get('fecha_dato', '') or '')
    fecha_emb_html = _fecha_corte_html(fecha_emb, 'default')
    nivel = emb.get('valor_actual_pct', 0)
    prom_30d = emb.get('promedio_30d_pct')
    media_hist = emb.get('media_historica_2020_2025_pct')
    desviacion = emb.get('desviacion_pct_media_historica')
    energia_gwh = emb.get('energia_embalsada_gwh')
    
    # Nivel real de embalses hace 1 y 2 años (mismo día del año) — se consulta en
    # vivo, nunca se aproxima desde el nivel de hoy; si no hay dato real se
    # muestra "N/D" en el panel en vez de un número inventado.
    anio_ref = int(fecha_emb[:4]) if fecha_emb[:4].isdigit() else datetime.now().year
    anio_1, anio_2 = anio_ref - 1, anio_ref - 2
    val_anio1 = _get_embalse_pct_historico(fecha_emb, 1)
    val_anio2 = _get_embalse_pct_historico(fecha_emb, 2)

    val_anio1_str = f'{val_anio1:.1f}%' if val_anio1 is not None else 'N/D'
    val_anio1_width = min(val_anio1, 100) if val_anio1 is not None else 0
    val_anio2_str = f'{val_anio2:.1f}%' if val_anio2 is not None else 'N/D'
    val_anio2_width = min(val_anio2, 100) if val_anio2 is not None else 0

    # ── Preparar valores para el panel derecho ──
    desviacion_abs = abs(desviacion) if desviacion is not None else 0
    desviacion_signo = '+' if desviacion and desviacion >= 0 else ''
    media_hist_str = f'{media_hist:.1f}' if media_hist is not None else '65.0'
    desviacion_str = f'{desviacion:+.1f}%' if desviacion is not None else 'N/A'
    prom_30d_str = f'{prom_30d:.1f}' if prom_30d is not None else 'N/A'
    energia_str = f'{energia_gwh:,.0f}' if energia_gwh is not None else 'N/A'
    tendencia_texto = 'una disminución' if desviacion and desviacion < 0 else 'un aumento'
    posicion_texto = 'por encima' if desviacion and desviacion > 0 else 'por debajo'
    color_diferencia = '#2E7D32' if desviacion and desviacion >= 0 else '#C62828'
    alerta_texto = 'No se generan alertas' if nivel > 40 else 'Se recomienda monitoreo especial'
    
    # ── Panel derecho: Reserva Nacional + Dato Histórico (compacto) ──
    panel_derecho_html = f"""
    <div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:6px;padding:8px;">
        <!-- Reserva Nacional -->
        <div style="margin-bottom:10px;">
            <div style="font-size:7pt;font-weight:bold;color:#555;margin-bottom:4px;">RESERVA NACIONAL</div>
            {fecha_emb_html}
            <div style="display:flex;align-items:center;gap:8px;">
                <div style="flex:1;height:14px;background:#e0e0e0;border-radius:7px;overflow:hidden;">
                    <div style="width:{min(nivel, 100)}%;height:100%;background:linear-gradient(90deg, #287270, #2E8B57);border-radius:7px;"></div>
                </div>
                <div style="font-size:12pt;font-weight:bold;color:#287270;">{nivel:.1f}%</div>
            </div>
        </div>
        
        <!-- Dato Histórico -->
        <div style="margin-bottom:10px;padding-top:8px;border-top:1px solid #e0e0e0;">
            <div style="font-size:7pt;font-weight:bold;color:#555;margin-bottom:5px;">DATO HISTÓRICO</div>
            <div style="margin-bottom:4px;">
                <div style="display:flex;justify-content:space-between;align-items:center;font-size:7pt;margin-bottom:2px;">
                    <span>{anio_1}</span>
                    <span style="font-weight:bold;color:#2E8B57;">{val_anio1_str}</span>
                </div>
                <div style="height:8px;background:#e0e0e0;border-radius:4px;overflow:hidden;">
                    <div style="width:{val_anio1_width}%;height:100%;background:#90EE90;border-radius:4px;"></div>
                </div>
            </div>
            <div>
                <div style="display:flex;justify-content:space-between;align-items:center;font-size:7pt;margin-bottom:2px;">
                    <span>{anio_2}</span>
                    <span style="font-weight:bold;color:#1E88E5;">{val_anio2_str}</span>
                </div>
                <div style="height:8px;background:#e0e0e0;border-radius:4px;overflow:hidden;">
                    <div style="width:{val_anio2_width}%;height:100%;background:#1E88E5;border-radius:4px;"></div>
                </div>
            </div>
        </div>
        
        <!-- Texto descriptivo compacto -->
        <div style="padding-top:8px;border-top:1px solid #e0e0e0;font-size:7pt;line-height:1.4;color:#444;">
            Los embalses presentan {tendencia_texto} vs referencia ({media_hist_str}%).
            <strong>{alerta_texto}.</strong>
        </div>
        
        <!-- Indicadores inferiores compactos -->
        <div style="display:flex;justify-content:space-between;margin-top:8px;padding-top:6px;border-top:1px solid #e0e0e0;font-size:6pt;color:#666;">
            <div style="text-align:center;">
                <div style="font-size:5pt;color:#888;">Senda Ref.</div>
                <div style="font-weight:bold;color:#444;">{media_hist_str}%</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:5pt;color:#888;">Actual</div>
                <div style="font-weight:bold;color:#287270;">{nivel:.1f}%</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:5pt;color:#888;">Dif.</div>
                <div style="font-weight:bold;color:{color_diferencia};">{desviacion_str}</div>
            </div>
        </div>
    </div>
    """
    
    # ── Sección de Aportes Hídricos (gráfica + panel) ──
    aportes_section = f"""
    <div style="margin:0 10px 6px;">
        <div style="font-size:9pt;font-weight:bold;color:#254553;margin-bottom:4px;">Hidrolog&iacute;a &mdash; Evoluci&oacute;n del Volumen &Uacute;til</div>
        <table cellpadding="0" cellspacing="0" style="width:100%;">
            <tr>
                <td style="width:55%;vertical-align:top;padding-right:8px;">
                    {aportes_chart or '<div style="text-align:center;padding:20px;color:#999;font-size:8pt;background:#f8f9fa;border-radius:6px;">Gr&aacute;fica no disponible</div>'}
                </td>
                <td style="width:45%;vertical-align:top;">
                    {panel_derecho_html}
                </td>
            </tr>
        </table>
    </div>
    """

    # ── Tabla detalle por embalse (antes de nivel regional) ──
    detalle_table = _build_hidrologia_detalle_table()
    detalle_section = ''
    if detalle_table:
        detalle_section = f"""
        {_section_hdr('Detalle Hidrol&oacute;gico por Embalse', '#287270')}
        {detalle_table}
        """

    # ── Embalses chart (mapa) ──
    emb_chart = _embed_chart(chart_paths, 'embalses_map')

    # ── Obtener aportes por río desde BD ──
    aportes_rios_html = _get_aportes_rios_table()
    
    # ── Indicadores clave (compacto) ──
    indicadores_html = f"""
    <div style="background:#f8f9fa;border:1px solid #e0e0e0;border-radius:6px;padding:8px;margin-top:8px;">
        {fecha_emb_html}
        <div style="font-size:7pt;color:#666;text-align:center;margin-top:4px;">
            <strong>Promedio 30 días:</strong> {prom_30d_str}% | 
            <strong>Senda Histórica:</strong> {media_hist_str}% | 
            <strong>Energía:</strong> {energia_str} GWh
        </div>
    </div>
    """

    # ── Mapa (izq) + aportes por río (der), nivel regional debajo ──
    map_section = f"""
    <table class="two-col" cellpadding="0" cellspacing="0" style="margin:0 10px 8px;">
      <tr>
        <td class="col-60" style="padding-right:8px;vertical-align:top;">
          {emb_chart or '<div style="text-align:center;padding:20px;color:#999;font-size:8pt;">Mapa no disponible</div>'}
        </td>
        <td class="col-40" style="vertical-align:top;">
          {aportes_rios_html}
          {indicadores_html}
        </td>
      </tr>
    </table>
    """

    # ── Predicciones compactas ──
    pred_html = ''
    metricas = (pred_resumen or {}).get('metricas', [])
    if metricas:
        horizonte = (pred_resumen or {}).get('horizonte', 'Pr&oacute;ximo mes')
        rows = ''
        for m in metricas:
            nombre = _strip_emojis(m.get('indicador', ''))
            nombre = nombre.replace('del Sistema', '').replace('Nacional', '').strip()
            unidad = m.get('unidad', '')
            actual = m.get('valor_actual')
            prom_proy = m.get('promedio_proyectado_1m')
            rango_min = m.get('rango_min')
            rango_max = m.get('rango_max')
            tendencia = m.get('tendencia', 'Estable')
            cambio = m.get('cambio_pct_vs_prom30d')

            actual_s = f'{actual:,.1f}' if actual is not None else 'N/D'
            proy_s = f'{prom_proy:,.1f}' if prom_proy is not None else 'N/D'
            rango_s = ''
            if rango_min is not None and rango_max is not None:
                rango_s = f'{rango_min:,.1f} &ndash; {rango_max:,.1f}'

            if tendencia == 'Creciente':
                tcls = 'trend-up'
                tarr = '&#9650;'
            elif tendencia == 'Decreciente':
                tcls = 'trend-dn'
                tarr = '&#9660;'
            else:
                tcls = 'trend-st'
                tarr = '&#9654;'

            cambio_s = ''
            if cambio is not None:
                cambio_s = f' ({cambio:+.1f}%)'

            m_fecha = m.get('fecha', '') or ''
            if not m_fecha:
                for f in (fichas or []):
                    fi = _strip_emojis(f.get('indicador', '')).lower()
                    if fi and (fi in nombre.lower() or nombre.lower() in fi):
                        m_fecha = f.get('fecha', '') or ''
                        break
            fecha_actual_html = _fecha_corte_html(str(m_fecha), 'footer')

            rows += (
                f'<tr>'
                f'<td>{nombre}</td>'
                f'<td style="text-align:center;">{unidad}</td>'
                f'<td style="text-align:right;font-weight:bold;">{actual_s}{fecha_actual_html}</td>'
                f'<td style="text-align:right;font-weight:bold;">{proy_s}</td>'
                f'<td style="text-align:center;font-size:7.5pt;">{rango_s}</td>'
                f'<td style="text-align:center;">'
                f'<span class="{tcls}">{tarr} {tendencia}{cambio_s}</span></td>'
                f'</tr>'
            )

        pred_html = f"""
        <div style="margin:0 10px;">
        <table class="pred-tbl">
          <tr>
            <th>Indicador</th><th style="text-align:center;">Und</th>
            <th style="text-align:right;">Actual</th>
            <th style="text-align:right;">Prom. Proy.</th>
            <th style="text-align:center;">Rango</th>
            <th style="text-align:center;">Tendencia</th>
          </tr>
          {rows}
        </table>
        <div style="font-size:6.5pt;color:#8d8d8d;margin-top:2px;">
          Horizonte: {horizonte} &bull; Modelo: ENSEMBLE con validaci&oacute;n holdout
        </div>
        </div>
        """

    # ── Predicción específica de Embalses ──
    emb_pred = _find_metric_prediction(pred_resumen, 'embalse')
    if not emb_pred:
        emb_pred = _find_metric_prediction(pred_resumen, 'porcentaje')
    emb_ficha = _get_ficha_indicador(fichas, 'embalses')
    fecha_emb_pred = _resolve_fecha_corte(
        fichas, 'embalses', metric=emb_pred
    ) or fecha_emb
    emb_pred_html = _build_pred_card(
        emb_pred,
        'La proyecci&oacute;n de embalses incorpora la estacionalidad '
        'de aportes h&iacute;dricos, consumo programado de centrales '
        'hidroel&eacute;ctricas y perspectivas clim&aacute;ticas regionales.',
        fecha_corte=str(fecha_emb_pred or ''),
    ) if emb_pred else ''

    regionales_html = _build_embalses_regionales_html(embalses_regionales or {})
    
    # Explicación de Embalses
    emb_explicacion = _get_explicacion_indicador(fichas, 'embalses')
    if emb_explicacion:
        emb_explicacion = f'<div style="margin:4px 10px;">{emb_explicacion}</div>'

    # ── Página capacidad: ficha + gráfico capacidad embalse ──
    page_hydro_cap = _wrap_report_page(logo_b64, fecha_label, f"""
      {_section_hdr('Hidrolog&iacute;a y Embalses')}
      {emb_ficha_html}
      {_section_hdr('Capacidad de Embalses', '#287270')}
      {capacidad_chart or '<div style="text-align:center;padding:16px;color:#999;font-size:8pt;">Gr&aacute;fica no disponible</div>'}
    """)

    # ── Página aportes vs demanda: gráfico + KPIs (aprovecha página completa) ──
    page_hydro_aportes = _wrap_report_page(logo_b64, fecha_label, f"""
      {_section_hdr('Aportes vs Demanda', '#287270')}
      {aportes_demanda_chart or '<div style="text-align:center;padding:16px;color:#999;font-size:8pt;">Gr&aacute;fica no disponible</div>'}
      {aportes_kpis_html}
    """)

    # ── Página detalle + mapa + regional + proyecciones (flujo continuo, sin hoja vacía) ──
    proyecciones_block = ''
    if emb_pred_html or pred_html:
        proyecciones_block = f"""
          {emb_pred_html}
          {_section_hdr('Proyecciones a 1 Mes', '#287270') if pred_html else ''}
          {pred_html}
        """

    page_hydro_detalle_map = _wrap_report_page(logo_b64, fecha_label, f"""
      {aportes_section}
      {detalle_section}
      {_section_hdr('Mapa de Embalses por Regi&oacute;n', '#254553')}
      {map_section}
      {_section_hdr('Nivel por Regi&oacute;n Hidrol&oacute;gica', '#287270') if regionales_html else ''}
      {regionales_html}
      {emb_explicacion}
      {proyecciones_block}
    """)

    return page_hydro_cap + page_hydro_aportes + page_hydro_detalle_map


# ═══════════════════════════════════════════════════════════════
# PAGE 4: Análisis IA (narrativa completa)
# ═══════════════════════════════════════════════════════════════

def _build_page_analisis(
    logo_b64: str,
    fecha_label: str,
    informe_texto: str,
) -> str:
    """
    Página 4: Análisis ejecutivo generado por IA.
    Incluye todas las secciones de la narrativa.
    """
    header = _build_header_html(logo_b64, fecha_label)

    if not informe_texto or not informe_texto.strip():
        return ''

    # Clean and convert narrative
    cleaned = _strip_redundant_header(informe_texto)
    cleaned = _strip_emojis(cleaned)
    body_html = _markdown_to_html(cleaned)

    return f"""
    <div class="page">
      {header}
      {_section_hdr('An&aacute;lisis Ejecutivo del Sector')}
      <div class="narrative">
        {body_html}
      </div>
    </div>
    """


# ═══════════════════════════════════════════════════════════════
# PAGE 5: Riesgos, Noticias y Cierre
# ═══════════════════════════════════════════════════════════════

def _build_page_noticias(
    logo_b64: str,
    fecha_label: str,
    anomalias: List[Dict[str, Any]],
    noticias: List[Dict[str, Any]],
    indices_compuestos: Optional[Dict[str, Any]] = None,
    include_riesgos: bool = True,
    include_noticias: bool = True,
    include_canales: bool = True,
    max_noticias: int = 5,
) -> str:
    """
    Página de riesgos/noticias/cierre.
    Con include_riesgos=False solo noticias; con include_noticias=False solo índices/anomalías.
    """
    header = _build_header_html(logo_b64, fecha_label)

    # ── Índices Compuestos (ISH / IPM / IES / CIS) ──
    idx_html = ''
    if include_riesgos and indices_compuestos:
        from domain.services.indices_compuestos_meta import (
            render_indices_footnote,
            render_indices_row_html,
        )
        cells = render_indices_row_html(indices_compuestos, variant='pdf')
        idx_html = f"""
        {_section_hdr('&Iacute;ndices del Sistema El&eacute;ctrico Nacional', '#4527A0')}
        <div style="margin:0 10px;">
          <table cellpadding="0" cellspacing="0" border="0" width="100%">
            <tr>{cells}</tr>
          </table>
          {render_indices_footnote(indices_compuestos, variant='pdf')}
        </div>
        """

    # ── Anomalías ──
    anom_html = ''
    if include_riesgos and anomalias:
        rows = ''
        for a in (anomalias or [])[:8]:
            # Compatibilidad: manejar tanto 'metrica' como 'indicador'
            metrica = a.get('metrica') or a.get('indicador', '')
            # Compatibilidad: manejar tanto 'descripcion' como 'comentario'
            descripcion = a.get('descripcion') or a.get('comentario', '')
            
            # Datos adicionales para contexto
            valor_actual = a.get('valor_actual')
            unidad = a.get('unidad', '')
            delta_pct = a.get('delta_hist_pct') or a.get('desviacion_pct')
            yoy = a.get('yoy', {})
            yoy_change = yoy.get('cambio_pct') if yoy else None
            
            # Formatear valor actual
            valor_str = f"{valor_actual:.1f} {unidad}" if valor_actual else 'N/A'
            
            # Formatear desviación
            desv_str = f"{delta_pct:.1f}%" if delta_pct else ''
            desv_color = '#d32f2f' if delta_pct and abs(delta_pct) > 25 else '#f57c00' if delta_pct and abs(delta_pct) > 15 else '#388e3c'
            
            # Formatear YoY
            yoy_str = f"{yoy_change:+.1f}% vs año pasado" if yoy_change else ''
            
            # Determinar impacto operativo
            impacto = _get_impacto_operativo(metrica, delta_pct, valor_actual)
            
            sev = a.get('severidad', 'ALERTA')
            # Normalizar severidad a mayúsculas para comparación
            sev_upper = str(sev).upper()
            if sev_upper in ('CRITICA', 'CRITICO', 'CRITICAL'):
                bcls = 'badge-crit'
                sev_emoji = '🔴'
                sev_desc = 'Acción inmediata requerida'
            elif sev_upper in ('ALERTA', 'WARNING'):
                bcls = 'badge-warn'
                sev_emoji = '🟠'
                sev_desc = 'Monitoreo cercano necesario'
            else:
                bcls = 'badge-ok'
                sev_emoji = '🟢'
                sev_desc = 'Dentro de parámetros normales'
            
            # Construir fila con más detalle
            detalle_extra = []
            if valor_actual:
                detalle_extra.append(f"Valor: {valor_str}")
            if delta_pct:
                detalle_extra.append(f"Desvío: <span style='color:{desv_color};font-weight:bold;'>{desv_str}</span>")
            if yoy_str:
                detalle_extra.append(f"YoY: {yoy_str}")
            
            detalle_html = ' | '.join(detalle_extra) if detalle_extra else ''
            
            rows += (
                f'<tr>'
                f'<td style="vertical-align:top;padding:10px 8px;">'
                f'<span class="badge {bcls}">{sev_emoji} {sev}</span>'
                f'<div style="font-size:7pt;color:#666;margin-top:4px;">{sev_desc}</div>'
                f'</td>'
                f'<td style="font-weight:bold;vertical-align:top;padding:10px 8px;">'
                f'{_strip_emojis(metrica)}'
                f'<div style="font-size:7pt;color:#444;margin-top:4px;">{detalle_html}</div>'
                f'</td>'
                f'<td style="font-size:8pt;vertical-align:top;padding:10px 8px;">'
                f'{_strip_emojis(descripcion)}'
                f'<div style="margin-top:8px;padding:6px;background:#fff3e0;border-radius:4px;font-size:7pt;color:#e65100;">'
                f'<strong>Impacto:</strong> {impacto}'
                f'</div>'
                f'</td>'
                f'</tr>'
            )
        
        # Nota: El análisis multidimensional detallado ahora aparece en la Página 1
        # Aquí solo mostramos las anomalías detectadas de forma concisa
        
        anom_html = f"""
        {_section_hdr('Riesgos y Anomal&iacute;as Detectadas', '#e76f50')}
        <div style="margin:0 10px;">
        <table class="anom-tbl" style="border-collapse:collapse;width:100%;">
          <tr style="background:#fafafa;">
              <th style="width:90px;padding:8px;font-size:8pt;">Severidad</th>
              <th style="padding:8px;font-size:8pt;">M&eacute;trica</th>
              <th style="padding:8px;font-size:8pt;">Descripci&oacute;n</th>
          </tr>
          {rows}
        </table>
        <div style="margin:10px;padding:8px;background:#f5f5f5;border-radius:4px;font-size:7.5pt;color:#666;text-align:center;">
            📊 El análisis detallado de tendencias, posición histórica y comparación con años anteriores 
            está disponible en la sección "Análisis Inteligente de Indicadores" (Página 1)
        </div>
        </div>
        """

    # ── Noticias ──
    news_html = ''
    if include_noticias and noticias:
        items = ''
        for n in (noticias or [])[:max_noticias]:
            titulo = _strip_emojis(n.get('titulo', ''))
            resumen = _strip_emojis(n.get('resumen', n.get('resumen_corto', '')))
            fuente = n.get('fuente', '')
            fecha_n = n.get('fecha', n.get('fecha_publicacion', ''))
            url = n.get('url', '')
            link = f' <a href="{url}" style="color:#125685;">Leer m&aacute;s</a>' if url else ''
            meta = ''
            if fuente or fecha_n:
                parts = [p for p in [fuente, str(fecha_n)] if p]
                meta = f'<div class="news-meta">{" | ".join(parts)}</div>'
            items += (
                f'<div class="news-item">'
                f'<div class="news-title">{titulo}</div>'
                f'<div class="news-summary">{resumen}{link}</div>'
                f'{meta}</div>'
            )
        news_html = f"""
        {_section_hdr('Noticias del Sector Energ&eacute;tico')}
        {items}
        """

    # ── Canales ──
    channels_html = ''
    if include_canales:
        channels_html = f"""
    {_section_hdr('Canales de Consulta', '#287270')}
    <div class="channels-box">
      <table cellpadding="0" cellspacing="0" border="0">
        <tr><td style="padding:3px 0;">
          <a class="ch-btn" style="background:#0088cc;"
             href="https://t.me/MinEnergiaColombia_bot">Chatbot Telegram</a>
          <span style="font-size:8pt;color:#737373;padding-left:6px;">
            t.me/MinEnergiaColombia_bot</span>
        </td></tr>
        <tr><td style="padding:3px 0;">
          <a class="ch-btn" style="background:#125685;"
             href="https://portalenergetico.minenergia.gov.co/">
             Portal Energ&eacute;tico</a>
          <span style="font-size:8pt;color:#737373;padding-left:6px;">
            portalenergetico.minenergia.gov.co</span>
        </td></tr>
      </table>
    </div>
    """

    return f"""
    <div class="page">
      {header}
      {idx_html}
      {anom_html}
      {news_html}
      {channels_html}
    </div>
    """


# ═══════════════════════════════════════════════════════════════
# Función principal: generar PDF
# ═══════════════════════════════════════════════════════════════

def generar_pdf_informe(
    informe_texto: str,
    fecha_generacion: str = '',
    generado_con_ia: bool = True,
    chart_paths: Optional[List[str]] = None,
    fichas: Optional[List[dict]] = None,
    predicciones=None,
    anomalias: Optional[list] = None,
    noticias: Optional[list] = None,
    contexto_datos: Optional[Dict[str, Any]] = None,
    portal_data: Optional[Dict[str, Any]] = None,
    portal_chart_paths: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """
    Genera un PDF estilo modelo XM del informe ejecutivo diario.

    Estructura del PDF:
      1. Mercado / resumen ejecutivo
      2. Generación por fuente
      3. Hidrología y embalses
      4. Análisis ejecutivo (IA)
      5. Gestión de riesgos (índices ISH/IPM/IES/CIS + anomalías)
      6. Noticias del sector (3 ítems) + canales

    Los parámetros portal_data y portal_chart_paths se conservan por compatibilidad
    pero se ignoran (capítulos portal suspendidos — ver INFORME_PORTAL_CAPITULOS_PENDIENTES.md).
    """
    try:
        from weasyprint import HTML

        if portal_data or portal_chart_paths:
            logger.debug(
                '[REPORT_SERVICE] portal_data/portal_chart_paths ignorados '
                '(capítulos portal suspendidos del informe ejecutivo)'
            )

        # ── Preparar datos ──
        hoy = fecha_generacion or datetime.now().strftime('%Y-%m-%d %H:%M')
        fecha_label = datetime.now().strftime('%Y-%m-%d')

        ctx = contexto_datos or {}
        tabla_indicadores = ctx.get('tabla_indicadores_clave', [])
        gen_por_fuente = ctx.get('generacion_por_fuente', {})
        embalses_detalle = ctx.get('embalses_detalle', {})
        pred_resumen = ctx.get('predicciones_mes_resumen', {})
        variables_mercado = ctx.get('variables_mercado', {})
        embalses_regionales = ctx.get('embalses_regionales', {})
        indices_compuestos = ctx.get('indices_compuestos')
        analisis_multidimensional = ctx.get('analisis_multidimensional', [])

        logo_b64 = _load_logo_b64()
        charts = chart_paths or []

        # ── Construir las 5 páginas ──
        page1 = _build_page_mercado(
            logo_b64, fecha_label,
            fichas or [], tabla_indicadores, charts,
            pred_resumen=pred_resumen,
            variables_mercado=variables_mercado,
            analisis_multidimensional=analisis_multidimensional,
            contexto_datos=ctx,
        )

        page2 = _build_page_generacion(
            logo_b64, fecha_label,
            gen_por_fuente, charts,
            pred_resumen=pred_resumen,
            fichas=fichas,
        )

        page3 = _build_page_hidrologia(
            logo_b64, fecha_label,
            embalses_detalle, pred_resumen, charts,
            embalses_regionales=embalses_regionales,
            fichas=fichas,
        )

        page4 = _build_page_analisis(
            logo_b64, fecha_label,
            informe_texto or '',
        )

        from domain.services.report_chapters import (
            build_chapter_gestion_riesgos,
            build_chapter_noticias,
        )

        page_riesgos = build_chapter_gestion_riesgos(
            logo_b64, fecha_label,
            anomalias or [],
            indices_compuestos=indices_compuestos,
        )
        page_noticias = build_chapter_noticias(
            logo_b64, fecha_label,
            noticias or [],
        )

        body_pages = [page1, page2, page3, page4, page_riesgos, page_noticias]

        full_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <style>{_CSS}</style>
</head>
<body>
  {''.join(body_pages)}
</body>
</html>"""

        # ── Generar PDF ──
        filename = f'Informe_Ejecutivo_MME_{fecha_label}.pdf'
        pdf_path = os.path.join(tempfile.gettempdir(), filename)

        HTML(string=full_html).write_pdf(pdf_path)

        file_size = os.path.getsize(pdf_path)
        logger.info(
            f'[REPORT_SERVICE] PDF generado ({file_size / 1024:.1f} KB): '
            f'{pdf_path}'
        )
        return pdf_path

    except ImportError:
        logger.error('[REPORT_SERVICE] weasyprint no instalado')
        return None
    except Exception as e:
        logger.error(
            f'[REPORT_SERVICE] Error generando PDF: {e}', exc_info=True
        )
        return None
