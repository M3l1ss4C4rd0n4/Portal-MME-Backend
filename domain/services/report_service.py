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
    page-break-inside: avoid;
}
.chart-box img {
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
        if fname.startswith(key_prefix):
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
            dt = datetime.strptime(fecha_str[:10], '%Y-%m-%d')
        else:
            dt = datetime.now()
        return f'{dt.day} de {meses[dt.month]} de {dt.year}'
    except Exception as e:
        return datetime.now().strftime('%Y-%m-%d')


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


def _build_pred_card(metric: Dict[str, Any], analysis_text: str = '') -> str:
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

    return f"""
    <div class="pred-card">
      <div class="pred-card-hdr">&#128200; Proyecci&oacute;n: {nombre}</div>
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

def _build_page_mercado(
    logo_b64: str,
    fecha_label: str,
    fichas: List[Dict[str, Any]],
    tabla_indicadores: List[Dict[str, Any]],
    chart_paths: List[str],
    pred_resumen: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Página 1: Resumen ejecutivo con semáforo + Variables del Mercado
    (gráfico precios + KPIs + predicción de precio) — replica la Página 1 del modelo.
    """
    header = _build_header_html(logo_b64, fecha_label)

    # ── Semáforo ejecutivo ──
    sema_rows = ''
    for ind in (tabla_indicadores or []):
        nombre = _strip_emojis(ind.get('indicador', ind.get('nombre', '')))
        valor = ind.get('valor_actual', 'N/D')
        unidad = ind.get('unidad', '')
        tendencia = ind.get('tendencia', 'Estable')
        estado = ind.get('estado', 'Normal')

        if isinstance(valor, float):
            val_str = f'{valor:,.2f} {unidad}'
        elif valor is not None:
            val_str = f'{valor} {unidad}'
        else:
            val_str = 'N/D'

        estado_l = estado.lower()
        if estado_l == 'normal':
            bcls = 'badge-ok'
        elif estado_l == 'alerta':
            bcls = 'badge-warn'
        else:
            bcls = 'badge-crit'

        if tendencia == 'Alza':
            trend = '<span style="color:#2E7D32;">&#9650; Alza</span>'
        elif tendencia == 'Baja':
            trend = '<span style="color:#C62828;">&#9660; Baja</span>'
        else:
            trend = '<span style="color:#555;">&#9654; Estable</span>'

        sema_rows += (
            f'<tr><td><strong>{nombre}</strong></td>'
            f'<td style="text-align:right;font-weight:bold;">{val_str}</td>'
            f'<td style="text-align:center;">{trend}</td>'
            f'<td style="text-align:center;"><span class="badge {bcls}">{estado}</span></td>'
            f'</tr>'
        )

    semaphore_html = ''
    if sema_rows:
        semaphore_html = f"""
        <div style="margin:0 10px;">
        <table class="sema-tbl">
          <tr><th>Indicador</th><th style="text-align:right;">Valor Actual</th>
              <th style="text-align:center;">Tendencia</th>
              <th style="text-align:center;">Estado</th></tr>
          {sema_rows}
        </table>
        </div>
        """

    # ── KPI boxes (right column) ──
    kpi_html = ''
    colors_kpi = ['#287270', '#299d8f', '#254553']
    for i, f in enumerate((fichas or [])[:3]):
        bg = colors_kpi[i % len(colors_kpi)]
        valor = f.get('valor', '')
        unidad = f.get('unidad', '')
        indicador = _strip_emojis(f.get('indicador', ''))
        ctx = f.get('contexto', {})
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

        kpi_html += (
            f'<div class="kpi-box" style="background:{bg};">'
            f'<div class="kpi-label">{indicador}</div>'
            f'<div class="kpi-value">{val_str} {unidad}</div>'
            f'{var_line}</div>'
        )

    # ── Explicaciones contextuales (estilo modelo) ──
    explanations = []
    for f in (fichas or [])[:3]:
        indicador = _strip_emojis(f.get('indicador', '')).lower()
        ctx = f.get('contexto', {})
        if 'precio' in indicador or 'bolsa' in indicador:
            explanations.append(
                'El Precio Promedio Ponderado (PPP) diario es el precio horario '
                'de la energ&iacute;a en el mercado spot, determinado por la '
                'oferta y demanda del d&iacute;a anterior.'
            )
        elif 'generaci' in indicador:
            explanations.append(
                'Generaci&oacute;n Total del SIN: suma de la producci&oacute;n '
                'de todas las fuentes (hidr&aacute;ulica, t&eacute;rmica, solar, '
                'e&oacute;lica, biomasa) despachadas por XM.'
            )
        elif 'embalse' in indicador:
            explanations.append(
                'Nivel de embalses: porcentaje de volumen &uacute;til agregado '
                'del Sistema Interconectado Nacional, indicador clave de '
                'seguridad h&iacute;drica.'
            )

    expl_html = ''
    if explanations:
        expl_html = '<div style="margin:4px 0;">'
        for e in explanations:
            expl_html += f'<p class="explanation">{e}</p>'
        expl_html += '</div>'

    # ── Price chart (left column) ──
    price_chart = _embed_chart(chart_paths, 'precio_evol')
    if not price_chart:
        price_chart = '<div style="text-align:center;padding:30px;color:#999;font-size:8pt;">Gr&aacute;fico de precios no disponible</div>'

    # ── Assemble two-column layout ──
    content = f"""
    <table class="two-col" cellpadding="0" cellspacing="0">
      <tr>
        <td class="col-55">{price_chart}</td>
        <td class="col-45">
          {kpi_html}
          {expl_html}
        </td>
      </tr>
    </table>
    """

    # ── Predicción de Precio de Bolsa ──
    precio_pred = _find_metric_prediction(pred_resumen, 'precio')
    if not precio_pred:
        precio_pred = _find_metric_prediction(pred_resumen, 'bolsa')
    precio_pred_html = _build_pred_card(
        precio_pred,
        'El Precio de Bolsa proyectado refleja la din&aacute;mica '
        'esperada de oferta-demanda para el pr&oacute;ximo mes, '
        'considerando disponibilidad h&iacute;drica y despacho t&eacute;rmico.'
    ) if precio_pred else ''

    return f"""
    <div class="page">
      {header}
      {_section_hdr('Resumen Ejecutivo')}
      {semaphore_html}
      {_section_hdr('Variables del Mercado', '#287270')}
      {content}
      {precio_pred_html}
    </div>
    """


# ═══════════════════════════════════════════════════════════════
# PAGE 2: Generación Real por Fuente
# ═══════════════════════════════════════════════════════════════

def _build_page_generacion(
    logo_b64: str,
    fecha_label: str,
    gen_por_fuente: Dict[str, Any],
    chart_paths: List[str],
    pred_resumen: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Página 2: Gráfico de generación + tabla de fuentes +
    análisis por tipo de fuente + predicción de generación.
    """
    header = _build_header_html(logo_b64, fecha_label)

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
          Datos del {fecha_dato} &bull; Fuente: XM
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
    gen_pred = _find_metric_prediction(pred_resumen, 'generaci')
    if not gen_pred:
        gen_pred = _find_metric_prediction(pred_resumen, 'GENE')
    gen_pred_html = _build_pred_card(
        gen_pred,
        'La generaci&oacute;n total proyectada considera la estacionalidad '
        'h&iacute;drica, la disponibilidad t&eacute;rmica programada y '
        'el crecimiento de FNCER en la matriz energ&eacute;tica.'
    ) if gen_pred else ''

    return f"""
    <div class="page">
      {header}
      {_section_hdr('Generaci&oacute;n Real por Fuente')}
      {top_section}
      {src_blocks}
      {gen_pred_html}
    </div>
    """


# ═══════════════════════════════════════════════════════════════
# PAGE 3: Hidrología y Embalses + Proyecciones
# ═══════════════════════════════════════════════════════════════

def _build_page_hidrologia(
    logo_b64: str,
    fecha_label: str,
    embalses_detalle: Dict[str, Any],
    pred_resumen: Dict[str, Any],
    chart_paths: List[str],
) -> str:
    """
    Página 3: Hidrología + embalses + predicciones compactas.
    Replica Página 3 del modelo.
    """
    header = _build_header_html(logo_b64, fecha_label)

    # ── Embalses chart ──
    emb_chart = _embed_chart(chart_paths, 'embalses_map')

    # ── Embalses data box ──
    emb = embalses_detalle or {}
    nivel = emb.get('valor_actual_pct')
    prom_30d = emb.get('promedio_30d_pct')
    media_hist = emb.get('media_historica_2020_2025_pct')
    desviacion = emb.get('desviacion_pct_media_historica')
    energia_gwh = emb.get('energia_embalsada_gwh')
    estado = _strip_emojis(emb.get('estado', ''))

    emb_html = ''
    if nivel is not None:
        # Big number for current level
        if nivel < 40:
            nc = '#C62828'
        elif nivel < 60:
            nc = '#E65100'
        else:
            nc = '#287270'

        # Build analysis text
        emb_analysis = (
            f'Los embalses presentan un nivel actual de <strong>{nivel:.1f}%</strong>'
        )
        if media_hist is not None and desviacion is not None:
            sign = '+' if desviacion >= 0 else ''
            emb_analysis += (
                f', que se mantiene <strong>{sign}{desviacion:.1f} puntos</strong> '
                f'porcentuales {"por encima" if desviacion >= 0 else "por debajo"} '
                f'de la media hist&oacute;rica 2020-2025 ({media_hist:.1f}%).'
            )
        else:
            emb_analysis += '.'

        if desviacion is not None and desviacion > 5:
            emb_analysis += ' <strong>No se generan alertas relacionadas con el abastecimiento de energ&iacute;a de hidroel&eacute;ctricas.</strong>'
        elif desviacion is not None and desviacion < -5:
            emb_analysis += ' <strong>Se recomienda monitoreo especial por nivel inferior al hist&oacute;rico.</strong>'

        data_rows = ''
        if prom_30d is not None:
            data_rows += f'<tr><td>Promedio 30 d&iacute;as</td><td>{prom_30d:.1f}%</td></tr>'
        if media_hist is not None:
            data_rows += f'<tr><td>Senda de Referencia</td><td>{media_hist:.1f}%</td></tr>'
        if desviacion is not None:
            dc = '#2E7D32' if desviacion >= 0 else '#C62828'
            sign = '+' if desviacion >= 0 else ''
            data_rows += f'<tr><td>Diferencia</td><td style="color:{dc};">{sign}{desviacion:.1f}%</td></tr>'
        if energia_gwh is not None:
            data_rows += f'<tr><td>Energ&iacute;a embalsada</td><td>{energia_gwh:,.0f} GWh</td></tr>'

        emb_html = f"""
        <div style="margin:4px 0;">
          <div class="big-num" style="color:{nc};">{nivel:.1f}%</div>
          <div class="big-label">Reserva Nacional</div>
        </div>
        <div style="font-size:8.5pt;line-height:1.4;margin:6px 0;">{emb_analysis}</div>
        <div class="emb-box" style="margin:4px 0;">
          <table>{data_rows}</table>
        </div>
        """

    # ── Two-column: chart + data ──
    hydro_section = f"""
    <table class="two-col" cellpadding="0" cellspacing="0">
      <tr>
        <td class="col-55">{emb_chart or '<div style="text-align:center;padding:30px;color:#999;font-size:8pt;">Mapa no disponible</div>'}</td>
        <td class="col-45">{emb_html}</td>
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

            rows += (
                f'<tr>'
                f'<td>{nombre}</td>'
                f'<td style="text-align:center;">{unidad}</td>'
                f'<td style="text-align:right;font-weight:bold;">{actual_s}</td>'
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
    emb_pred_html = _build_pred_card(
        emb_pred,
        'La proyecci&oacute;n de embalses incorpora la estacionalidad '
        'de aportes h&iacute;dricos, consumo programado de centrales '
        'hidroel&eacute;ctricas y perspectivas clim&aacute;ticas regionales.'
    ) if emb_pred else ''

    return f"""
    <div class="page">
      {header}
      {_section_hdr('Hidrolog&iacute;a y Embalses')}
      {hydro_section}
      {emb_pred_html}
      {_section_hdr('Proyecciones a 1 Mes', '#287270') if pred_html else ''}
      {pred_html}
    </div>
    """


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
) -> str:
    """
    Página 5: Anomalías/riesgos + Noticias + Canales.
    Replica Páginas 4-5 del modelo (Alertas del Sector).
    """
    header = _build_header_html(logo_b64, fecha_label)

    # ── Anomalías ──
    anom_html = ''
    if anomalias:
        rows = ''
        for a in (anomalias or [])[:8]:
            sev = a.get('severidad', 'ALERTA')
            if sev in ('CRITICA', 'CRITICO', 'CRITICAL'):
                bcls = 'badge-crit'
            elif sev == 'ALERTA':
                bcls = 'badge-warn'
            else:
                bcls = 'badge-ok'
            rows += (
                f'<tr>'
                f'<td><span class="badge {bcls}">{sev}</span></td>'
                f'<td style="font-weight:bold;">{_strip_emojis(a.get("metrica", ""))}</td>'
                f'<td style="font-size:8pt;">{_strip_emojis(a.get("descripcion", ""))}</td>'
                f'</tr>'
            )
        anom_html = f"""
        {_section_hdr('Riesgos y Anomal&iacute;as Detectadas', '#e76f50')}
        <div style="margin:0 10px;">
        <table class="anom-tbl">
          <tr><th style="width:70px;">Severidad</th>
              <th>M&eacute;trica</th><th>Descripci&oacute;n</th></tr>
          {rows}
        </table>
        </div>
        """

    # ── Noticias ──
    news_html = ''
    if noticias:
        items = ''
        for n in (noticias or [])[:5]:
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
) -> Optional[str]:
    """
    Genera un PDF estilo modelo XM del informe ejecutivo diario.

    Estructura de 5 páginas:
      P1: Variables del Mercado y Resumen Ejecutivo
      P2: Generación Real por Fuente (con análisis por tipo)
      P3: Hidrología/Embalses + Proyecciones a 1 Mes
      P4: Análisis Ejecutivo IA (narrativa completa)
      P5: Riesgos, Noticias y Cierre

    Args:
        informe_texto: Texto Markdown de la narrativa IA.
        fecha_generacion: Fecha/hora de generación.
        generado_con_ia: Si fue generado con IA.
        chart_paths: Lista de paths a PNGs (gen_pie, embalses_map, precio_evol).
        fichas: Lista de KPIs [{indicador, valor, unidad, contexto}].
        predicciones: Dict o lista de predicciones (legacy, fallback).
        anomalias: Lista de anomalías [{severidad, metrica, descripcion}].
        noticias: Lista de noticias [{titulo, resumen, fuente, url}].
        contexto_datos: Dict del orquestador con campos enriquecidos.

    Returns:
        Ruta absoluta al PDF temporal, o None si falla.
    """
    try:
        from weasyprint import HTML

        # ── Preparar datos ──
        hoy = fecha_generacion or datetime.now().strftime('%Y-%m-%d %H:%M')
        fecha_label = datetime.now().strftime('%Y-%m-%d')

        ctx = contexto_datos or {}
        tabla_indicadores = ctx.get('tabla_indicadores_clave', [])
        gen_por_fuente = ctx.get('generacion_por_fuente', {})
        embalses_detalle = ctx.get('embalses_detalle', {})
        pred_resumen = ctx.get('predicciones_mes_resumen', {})

        logo_b64 = _load_logo_b64()
        charts = chart_paths or []

        # ── Construir las 5 páginas ──
        page1 = _build_page_mercado(
            logo_b64, fecha_label,
            fichas or [], tabla_indicadores, charts,
            pred_resumen=pred_resumen,
        )

        page2 = _build_page_generacion(
            logo_b64, fecha_label,
            gen_por_fuente, charts,
            pred_resumen=pred_resumen,
        )

        page3 = _build_page_hidrologia(
            logo_b64, fecha_label,
            embalses_detalle, pred_resumen, charts,
        )

        page4 = _build_page_analisis(
            logo_b64, fecha_label,
            informe_texto or '',
        )

        page5 = _build_page_noticias(
            logo_b64, fecha_label,
            anomalias or [], noticias or [],
        )

        # ── Ensamblar HTML ──
        full_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <style>{_CSS}</style>
</head>
<body>
  {page1}
  {page2}
  {page3}
  {page4}
  {page5}
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
