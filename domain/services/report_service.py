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
# CSS profesional institucional MME — v2
# ═══════════════════════════════════════════════════════════════

_CSS = """
@page {
    size: letter;
    margin: 1.8cm 2cm 2.2cm 2cm;
    @bottom-center {
        content: "Portal Energetico MME  |  Pagina " counter(page) " de " counter(pages);
        font-size: 7pt;
        color: #999;
        font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    }
}

@page :first {
    @bottom-center { content: ""; }
}

body {
    font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.5;
    color: #222;
    text-rendering: optimizeLegibility;
}

/* ── Portada ── */
.cover {
    page-break-after: always;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 80%;
    text-align: center;
    padding-top: 120px;
}

.cover-logo img {
    width: 90px;
    height: auto;
    margin-bottom: 24px;
}

.cover-title {
    font-size: 24pt;
    font-weight: 800;
    color: #1a3c5e;
    letter-spacing: 0.5pt;
    margin: 0 0 6px 0;
    line-height: 1.2;
}

.cover-subtitle {
    font-size: 13pt;
    color: #555;
    font-weight: 400;
    margin: 0 0 30px 0;
}

.cover-date {
    font-size: 14pt;
    color: #1a3c5e;
    font-weight: 600;
    margin: 0 0 8px 0;
}

.cover-meta {
    font-size: 9pt;
    color: #888;
    margin-top: 6px;
    line-height: 1.6;
}

.cover-line {
    width: 60%;
    height: 3px;
    background: linear-gradient(90deg, #1a3c5e, #6c9ec2, #1a3c5e);
    border: none;
    margin: 25px auto;
}

.cover-institution {
    font-size: 10pt;
    color: #444;
    margin-top: 60px;
    line-height: 1.5;
}

/* ── Header de página (páginas interiores) ── */
.page-header {
    display: flex;
    align-items: center;
    border-bottom: 2pt solid #1a3c5e;
    padding-bottom: 8px;
    margin-bottom: 14px;
}

.page-header-logo img {
    width: 38px;
    height: auto;
    margin-right: 12px;
}

.page-header-text {
    flex: 1;
}

.page-header-text h1 {
    font-size: 13pt;
    font-weight: 700;
    color: #1a3c5e;
    margin: 0;
    letter-spacing: 0.2pt;
}

.page-header-text .ph-sub {
    font-size: 8pt;
    color: #888;
    margin: 0;
}

/* ── Metadata bar ── */
.metadata-bar {
    font-size: 8pt;
    color: #666;
    padding: 5px 10px;
    background: #f5f7fa;
    border-bottom: 1px solid #ddd;
    margin-bottom: 14px;
}

.metadata-bar table {
    width: 100%;
    border: none;
    border-collapse: collapse;
}

.metadata-bar td {
    padding: 1px 0;
    border: none;
}

.metadata-bar td:last-child {
    text-align: right;
}

/* ── Secciones ── */
h2 {
    font-size: 13pt;
    font-weight: 700;
    color: #1a3c5e;
    margin-top: 18px;
    margin-bottom: 7px;
    padding-bottom: 3px;
    padding-left: 8px;
    border-left: 3pt solid #1a3c5e;
    border-bottom: 0.5pt solid #ccc;
    page-break-after: avoid;
}

h3 {
    font-size: 11pt;
    font-weight: 600;
    color: #2c3e50;
    margin-top: 12px;
    margin-bottom: 4px;
    padding-left: 8px;
    border-left: 2pt solid #6c9ec2;
    page-break-after: avoid;
}

p {
    margin: 4px 0;
    text-align: justify;
    orphans: 3;
    widows: 3;
}

ul {
    margin: 4px 0 4px 22px;
    padding: 0;
    list-style-type: disc;
}

li {
    margin-bottom: 2px;
    text-align: justify;
}

hr {
    border: none;
    border-top: 0.5pt solid #ccc;
    margin: 10px 0;
}

strong { font-weight: 700; color: inherit; }
em { font-style: italic; color: inherit; }

/* ── Resumen ejecutivo: semáforo ── */
.semaphore-section {
    margin: 10px 0 16px 0;
    page-break-inside: avoid;
}

.semaphore-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
    margin-top: 8px;
}

.semaphore-table th {
    background: #1a3c5e;
    color: #fff;
    padding: 7px 10px;
    text-align: left;
    font-size: 9pt;
    font-weight: 600;
}

.semaphore-table td {
    padding: 6px 10px;
    border-bottom: 1px solid #e0e0e0;
    vertical-align: middle;
}

.semaphore-table tr:nth-child(even) {
    background: #f8f9fa;
}

.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 10px;
    font-size: 8.5pt;
    font-weight: 700;
    color: #fff;
}
.badge-normal { background: #2E7D32; }
.badge-alerta { background: #E65100; }
.badge-critico { background: #C62828; }

/* ── KPI Cards ── */
.kpi-row {
    display: flex;
    gap: 8px;
    margin: 12px 0;
    page-break-inside: avoid;
}

.kpi-card {
    flex: 1;
    background: #f8f9fa;
    border-radius: 6px;
    padding: 10px 12px;
}

.kpi-label {
    font-size: 9pt;
    color: #666;
    margin-bottom: 3px;
}

.kpi-value {
    font-size: 18pt;
    font-weight: 700;
}

.kpi-variation {
    font-size: 8.5pt;
    color: #666;
    margin-top: 2px;
}

/* ── Generación por fuente ── */
.gen-source-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
    margin: 8px 0;
}

.gen-source-table th {
    background: #1a3c5e;
    color: #fff;
    padding: 6px 10px;
    text-align: left;
    font-size: 9pt;
}

.gen-source-table td {
    padding: 5px 10px;
    border-bottom: 1px solid #e0e0e0;
}

.gen-source-table tr:nth-child(even) td {
    background: #f8f9fa;
}

.bar-cell {
    position: relative;
    width: 120px;
}

.bar-bg {
    display: inline-block;
    height: 12px;
    border-radius: 3px;
    vertical-align: middle;
}

/* ── Predicciones compactas ── */
.pred-compact-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
    margin: 8px 0;
}

.pred-compact-table th {
    background: #1a3c5e;
    color: #fff;
    padding: 6px 10px;
    text-align: left;
    font-size: 9pt;
}

.pred-compact-table td {
    padding: 6px 10px;
    border-bottom: 1px solid #e0e0e0;
}

.pred-compact-table tr:nth-child(even) td {
    background: #f8f9fa;
}

.trend-up { color: #2E7D32; font-weight: 600; }
.trend-down { color: #C62828; font-weight: 600; }
.trend-stable { color: #555; font-weight: 600; }

/* ── Embalses detalle ── */
.embalses-box {
    background: #f5f7fa;
    border-left: 4px solid #1565C0;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 8px 0;
    page-break-inside: avoid;
    font-size: 10pt;
}

.embalses-box .emb-title {
    font-size: 11pt;
    font-weight: 700;
    color: #1a3c5e;
    margin-bottom: 6px;
}

.embalses-box table {
    width: 100%;
    border-collapse: collapse;
}

.embalses-box td {
    padding: 3px 0;
}

.embalses-box td:last-child {
    text-align: right;
    font-weight: 600;
}

/* ── Gráficos ── */
.charts-section {
    page-break-inside: avoid;
    margin: 10px 0;
}

.chart-container {
    text-align: center;
    margin: 6px 0;
    page-break-inside: avoid;
}

.chart-container img {
    width: 80%;
    max-width: 420px;
    height: auto;
    border: 0.5pt solid #ddd;
}

.chart-caption {
    font-size: 7.5pt;
    color: #666;
    text-align: center;
    margin-top: 2px;
    margin-bottom: 5px;
    font-style: italic;
}

.chart-caption a {
    color: #1a3c5e;
    text-decoration: underline;
}

/* ── Anomalías ── */
.anomaly-section {
    margin: 14px 0;
    page-break-inside: avoid;
}

.anom-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
    margin-top: 6px;
}

.anom-table th {
    background: #FFF8E1;
    padding: 6px 10px;
    text-align: left;
    font-size: 9pt;
    font-weight: 600;
    color: #E65100;
}

.anom-table td {
    padding: 5px 10px;
    border-bottom: 1px solid #eee;
}

/* ── Noticias ── */
.news-section {
    margin: 14px 0;
}

.news-item {
    padding: 7px 0;
    border-bottom: 1px solid #eee;
}

.news-title {
    font-size: 10.5pt;
    font-weight: 600;
    color: #222;
}

.news-summary {
    font-size: 9.5pt;
    color: #555;
    margin-top: 2px;
    line-height: 1.4;
}

.news-meta {
    font-size: 8pt;
    color: #888;
    margin-top: 2px;
}

/* ── Canales ── */
.channels-box {
    margin: 18px 0;
    padding: 12px 16px;
    background: #f5f7fa;
    border-radius: 8px;
    page-break-inside: avoid;
}

.channels-title {
    font-size: 11pt;
    font-weight: 700;
    color: #333;
    margin-bottom: 8px;
}

.channels-box table {
    border: none;
    border-collapse: collapse;
}

.channels-box td {
    padding: 4px 0;
    border: none;
}

.ch-btn {
    display: inline-block;
    padding: 6px 14px;
    border-radius: 6px;
    color: #fff;
    text-decoration: none;
    font-size: 10pt;
    font-weight: 600;
}

.ch-link {
    padding-left: 10px;
    font-size: 9pt;
}

/* ── Footer ── */
.footer-note {
    margin-top: 20px;
    padding-top: 8px;
    border-top: 1pt solid #1a3c5e;
    font-size: 7pt;
    color: #888;
    text-align: center;
    line-height: 1.4;
}

/* Forzar saltos de página */
.page-break {
    page-break-before: always;
}
"""


# ═══════════════════════════════════════════════════════════════
# Builders de secciones HTML
# ═══════════════════════════════════════════════════════════════

def _load_logo_b64() -> str:
    """Carga el logo MME como string base64. Retorna '' si no existe."""
    if not os.path.exists(_LOGO_PATH):
        return ''
    try:
        with open(_LOGO_PATH, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception:
        return ''


def _build_cover_html(logo_b64: str, fecha_label: str,
                      metodo: str, hoy: str) -> str:
    """Construye la página de portada institucional."""
    logo_img = ''
    if logo_b64:
        logo_img = f'<img src="data:image/png;base64,{logo_b64}" alt="MME">'

    return f"""
    <div class="cover">
        <div class="cover-logo">{logo_img}</div>
        <div class="cover-title">Informe Ejecutivo</div>
        <div class="cover-title" style="font-size:18pt;margin-top:4px;">
            Sector El&eacute;ctrico Colombiano
        </div>
        <hr class="cover-line">
        <div class="cover-date">{fecha_label}</div>
        <div class="cover-meta">
            Generado: {hoy}<br>
            M&eacute;todo: {metodo}
        </div>
        <div class="cover-institution">
            Rep&uacute;blica de Colombia<br>
            Ministerio de Minas y Energ&iacute;a<br>
            <em>Portal Energ&eacute;tico MME</em>
        </div>
    </div>
    """


def _build_page_header(logo_b64: str, fecha_label: str) -> str:
    """Header compacto para páginas interiores."""
    logo_html = ''
    if logo_b64:
        logo_html = (
            f'<div class="page-header-logo">'
            f'<img src="data:image/png;base64,{logo_b64}" alt="MME">'
            f'</div>'
        )
    return f"""
    <div class="page-header">
        {logo_html}
        <div class="page-header-text">
            <h1>Informe Ejecutivo &mdash; Sector El&eacute;ctrico</h1>
            <p class="ph-sub">{fecha_label} &bull; Portal Energ&eacute;tico MME</p>
        </div>
    </div>
    """


def _build_semaphore_html(tabla_indicadores: List[Dict[str, Any]]) -> str:
    """
    Construye tabla resumen ejecutivo con semáforo.
    Usa datos de tabla_indicadores_clave del contexto.
    """
    if not tabla_indicadores:
        return ''

    rows = []
    for ind in tabla_indicadores:
        nombre = _strip_emojis(ind.get('indicador', ''))
        valor = ind.get('valor_actual')
        unidad = ind.get('unidad', '')
        tendencia = ind.get('tendencia', 'Estable')
        variacion = ind.get('variacion_pct', 0)
        estado = ind.get('estado', 'Normal')

        # Formato valor
        if isinstance(valor, float):
            val_str = f'{valor:,.2f} {unidad}'
        elif valor is not None:
            val_str = f'{valor} {unidad}'
        else:
            val_str = 'N/D'

        # Badge de estado
        estado_lower = estado.lower()
        if estado_lower == 'normal':
            badge_cls = 'badge-normal'
        elif estado_lower == 'alerta':
            badge_cls = 'badge-alerta'
        else:
            badge_cls = 'badge-critico'

        # Flecha de tendencia
        if tendencia == 'Alza':
            trend_html = f'<span style="color:#2E7D32;">&#9650; +{abs(variacion):.1f}%</span>'
        elif tendencia == 'Baja':
            trend_html = f'<span style="color:#C62828;">&#9660; -{abs(variacion):.1f}%</span>'
        else:
            trend_html = f'<span style="color:#555;">&#9654; {variacion:+.1f}%</span>'

        rows.append(
            f'<tr>'
            f'<td><strong>{nombre}</strong></td>'
            f'<td style="text-align:right;font-weight:600;">{val_str}</td>'
            f'<td style="text-align:center;">{trend_html}</td>'
            f'<td style="text-align:center;">'
            f'<span class="badge {badge_cls}">{estado}</span></td>'
            f'</tr>'
        )

    return f"""
    <div class="semaphore-section">
        <h2>Resumen Ejecutivo</h2>
        <table class="semaphore-table">
            <tr>
                <th>Indicador</th>
                <th style="text-align:right;">Valor Actual</th>
                <th style="text-align:center;">Tendencia</th>
                <th style="text-align:center;">Estado</th>
            </tr>
            {''.join(rows)}
        </table>
    </div>
    """


def _build_kpi_cards_html(fichas: List[Dict[str, Any]]) -> str:
    """Construye las 3 tarjetas KPI del encabezado."""
    if not fichas:
        return ''

    colors = ['#1565C0', '#2E7D32', '#E65100']
    cards = []
    for i, f in enumerate(fichas[:3]):
        color = colors[i % len(colors)]
        valor = f.get('valor', '')
        unidad = f.get('unidad', '')
        indicador = _strip_emojis(f.get('indicador', ''))
        ctx = f.get('contexto', {})
        var_pct = ctx.get('variacion_vs_promedio_pct')

        if isinstance(valor, float):
            val_str = f'{valor:,.2f} {unidad}'
        else:
            val_str = f'{valor} {unidad}'

        var_line = ''
        if var_pct is not None:
            sign = '+' if float(var_pct) >= 0 else ''
            etiqueta = ctx.get('etiqueta_variacion', 'vs promedio 7d')
            var_line = (
                f'<div class="kpi-variation">'
                f'{sign}{var_pct:.1f}% {etiqueta}</div>'
            )

        cards.append(
            f'<div class="kpi-card" style="border-left:4px solid {color};">'
            f'<div class="kpi-label">{indicador}</div>'
            f'<div class="kpi-value" style="color:{color};">{val_str}</div>'
            f'{var_line}'
            f'</div>'
        )

    return (
        '<div class="kpi-row">'
        + ''.join(cards)
        + '</div>'
    )


def _build_gen_source_html(gen_por_fuente: Dict[str, Any]) -> str:
    """
    Construye tabla de desglose de generación por tipo de fuente.
    Usa datos de generacion_por_fuente del contexto.
    """
    if not gen_por_fuente or gen_por_fuente.get('error'):
        return ''

    fuentes = gen_por_fuente.get('fuentes', [])
    total_gwh = gen_por_fuente.get('total_gwh', 0)
    fecha_dato = gen_por_fuente.get('fecha_dato', '')

    if not fuentes:
        return ''

    rows = []
    bar_colors = {
        'Hidráulica': '#1565C0',
        'Térmica': '#E65100',
        'Solar': '#F9A825',
        'Eólica': '#00897B',
        'Biomasa/Cogeneración': '#6A1B9A',
    }

    for f in fuentes:
        nombre = f.get('fuente', '')
        gwh = f.get('gwh', 0)
        pct = f.get('porcentaje', 0)
        bar_color = bar_colors.get(nombre, '#999')
        bar_width = min(pct * 1.2, 100)  # escala visual

        rows.append(
            f'<tr>'
            f'<td>{nombre}</td>'
            f'<td style="text-align:right;font-weight:600;">{gwh:,.1f} GWh</td>'
            f'<td style="text-align:right;">{pct:.1f}%</td>'
            f'<td class="bar-cell">'
            f'<span class="bar-bg" style="width:{bar_width}px;background:{bar_color};"></span>'
            f'</td>'
            f'</tr>'
        )

    return f"""
    <div style="margin:10px 0;page-break-inside:avoid;">
        <h3>Desglose por Fuente de Generaci&oacute;n</h3>
        <table class="gen-source-table">
            <tr>
                <th>Fuente</th>
                <th style="text-align:right;">Generaci&oacute;n</th>
                <th style="text-align:right;">Participaci&oacute;n</th>
                <th></th>
            </tr>
            {''.join(rows)}
            <tr style="border-top:2px solid #1a3c5e;">
                <td><strong>Total</strong></td>
                <td style="text-align:right;font-weight:700;">{total_gwh:,.1f} GWh</td>
                <td style="text-align:right;font-weight:700;">100%</td>
                <td></td>
            </tr>
        </table>
        <div style="font-size:7.5pt;color:#888;margin-top:2px;">
            Datos del {fecha_dato} &bull; Fuente: XM
        </div>
    </div>
    """


def _build_embalses_detail_html(embalses: Dict[str, Any]) -> str:
    """
    Construye bloque detallado de embalses.
    Usa datos de embalses_detalle del contexto.
    """
    if not embalses or embalses.get('error'):
        return ''

    nivel = embalses.get('valor_actual_pct')
    prom_30d = embalses.get('promedio_30d_pct')
    media_hist = embalses.get('media_historica_2020_2025_pct')
    desviacion = embalses.get('desviacion_pct_media_historica')
    energia_gwh = embalses.get('energia_embalsada_gwh')
    estado = _strip_emojis(embalses.get('estado', ''))

    if nivel is None:
        return ''

    # Color del nivel
    if nivel < 40:
        nivel_color = '#C62828'
    elif nivel < 60:
        nivel_color = '#E65100'
    else:
        nivel_color = '#2E7D32'

    detail_rows = f"""
        <tr><td>Nivel actual</td>
            <td style="color:{nivel_color};font-size:14pt;font-weight:700;">
                {nivel:.1f}%</td></tr>
    """

    if prom_30d is not None:
        detail_rows += f'<tr><td>Promedio 30 d&iacute;as</td><td>{prom_30d:.1f}%</td></tr>'

    if media_hist is not None:
        detail_rows += (
            f'<tr><td>Media hist&oacute;rica 2020-2025</td>'
            f'<td>{media_hist:.1f}%</td></tr>'
        )

    if desviacion is not None:
        sign = '+' if desviacion >= 0 else ''
        dev_color = '#2E7D32' if desviacion >= 0 else '#C62828'
        detail_rows += (
            f'<tr><td>Desviaci&oacute;n vs hist&oacute;rica</td>'
            f'<td style="color:{dev_color};">{sign}{desviacion:.1f}%</td></tr>'
        )

    if energia_gwh is not None:
        detail_rows += (
            f'<tr><td>Energ&iacute;a embalsada</td>'
            f'<td>{energia_gwh:,.0f} GWh</td></tr>'
        )

    if estado:
        detail_rows += f'<tr><td>Evaluaci&oacute;n</td><td>{estado}</td></tr>'

    return f"""
    <div class="embalses-box">
        <div class="emb-title">Embalses del SIN</div>
        <table>{detail_rows}</table>
    </div>
    """


def _build_pred_compact_html(pred_resumen: Dict[str, Any]) -> str:
    """
    Construye tabla compacta de predicciones a 1 mes (3 filas).
    Usa datos de predicciones_mes_resumen del contexto.
    Reemplaza las tablas extensas de 31 rows × 3 métricas.
    """
    if not pred_resumen or pred_resumen.get('error'):
        return ''

    metricas = pred_resumen.get('metricas', [])
    if not metricas:
        return ''

    horizonte = pred_resumen.get('horizonte', 'Pr\u00f3ximo mes')

    rows = []
    for m in metricas:
        nombre = _strip_emojis(m.get('indicador', ''))
        # Acortar nombre para la tabla
        nombre_corto = nombre.replace('del Sistema', '').replace('Nacional', '').strip()
        unidad = m.get('unidad', '')
        actual = m.get('valor_actual')
        prom_proy = m.get('promedio_proyectado_1m')
        rango_min = m.get('rango_min')
        rango_max = m.get('rango_max')
        tendencia = m.get('tendencia', 'Estable')
        cambio = m.get('cambio_pct_vs_prom30d')

        # Formato valores
        if actual is not None:
            actual_str = f'{actual:,.1f}'
        else:
            actual_str = 'N/D'

        if prom_proy is not None:
            proy_str = f'{prom_proy:,.1f}'
        else:
            proy_str = 'N/D'

        rango_str = ''
        if rango_min is not None and rango_max is not None:
            rango_str = f'{rango_min:,.1f} &ndash; {rango_max:,.1f}'

        # Styling de tendencia
        if tendencia == 'Creciente':
            trend_cls = 'trend-up'
            trend_arrow = '&#9650;'
        elif tendencia == 'Decreciente':
            trend_cls = 'trend-down'
            trend_arrow = '&#9660;'
        else:
            trend_cls = 'trend-stable'
            trend_arrow = '&#9654;'

        cambio_str = ''
        if cambio is not None:
            cambio_str = f' ({cambio:+.1f}%)'

        rows.append(
            f'<tr>'
            f'<td>{nombre_corto}</td>'
            f'<td style="text-align:center;">{unidad}</td>'
            f'<td style="text-align:right;font-weight:600;">{actual_str}</td>'
            f'<td style="text-align:right;font-weight:600;">{proy_str}</td>'
            f'<td style="text-align:center;font-size:9pt;">{rango_str}</td>'
            f'<td style="text-align:center;">'
            f'<span class="{trend_cls}">{trend_arrow} {tendencia}{cambio_str}</span></td>'
            f'</tr>'
        )

    return f"""
    <div style="margin:12px 0;page-break-inside:avoid;">
        <h2>Proyecciones a 1 Mes</h2>
        <table class="pred-compact-table">
            <tr>
                <th>Indicador</th>
                <th style="text-align:center;">Unidad</th>
                <th style="text-align:right;">Actual</th>
                <th style="text-align:right;">Prom. Proyectado</th>
                <th style="text-align:center;">Rango</th>
                <th style="text-align:center;">Tendencia</th>
            </tr>
            {''.join(rows)}
        </table>
        <div style="font-size:7.5pt;color:#888;margin-top:3px;">
            Horizonte: {horizonte} &bull; Modelo: ENSEMBLE con validaci&oacute;n holdout &bull;
            Tendencia vs promedio real 30d
        </div>
    </div>
    """


def _build_charts_html(chart_paths: List[str]) -> str:
    """
    Convierte una lista de paths a imágenes PNG en HTML con data URIs base64.
    Las imágenes se incrustan directamente en el HTML para WeasyPrint.
    """
    if not chart_paths:
        return ''

    captions = {
        'gen_pie': 'Fig. 1 — Participaci\u00f3n por fuente de generaci\u00f3n',
        'embalses_map': 'Fig. 2 — Nivel de embalses por regi\u00f3n hidrol\u00f3gica',
        'precio_evol': 'Fig. 3 — Evoluci\u00f3n del Precio de Bolsa Nacional (90 d\u00edas)',
    }

    urls = {
        'gen_pie': 'https://portalenergetico.minenergia.gov.co/generacion/fuentes',
        'embalses_map': 'https://portalenergetico.minenergia.gov.co/generacion/hidraulica/hidrologia',
        'precio_evol': 'https://portalenergetico.minenergia.gov.co/comercializacion',
    }

    img_blocks = []
    for path in chart_paths:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')

            fname = os.path.basename(path).split('_202')[0]
            caption = captions.get(fname, '')
            url = urls.get(fname, '')

            block = '<div class="chart-container">'
            block += f'<img src="data:image/png;base64,{b64}" alt="{caption}">'
            if caption:
                if url:
                    block += (
                        f'<p class="chart-caption">{caption} &mdash; '
                        f'<a href="{url}">Ver en el Portal Energ&eacute;tico</a></p>'
                    )
                else:
                    block += f'<p class="chart-caption">{caption}</p>'
            block += '</div>'
            img_blocks.append(block)
        except Exception as e:
            logger.warning(f'[REPORT] Error embediendo imagen {path}: {e}')

    if not img_blocks:
        return ''

    return (
        '<div class="charts-section">'
        + '\n'.join(img_blocks)
        + '</div>'
    )


def _build_anomalies_html(anomalias: List[Dict[str, Any]]) -> str:
    """Construye tabla de anomalías / riesgos."""
    if not anomalias:
        return ''

    rows = []
    for a in anomalias[:10]:
        sev = a.get('severidad', 'ALERTA')
        if sev in ('CRITICA', 'CRITICO', 'CRITICAL'):
            badge_cls = 'badge-critico'
        elif sev == 'ALERTA':
            badge_cls = 'badge-alerta'
        else:
            badge_cls = 'badge-normal'

        rows.append(
            f'<tr>'
            f'<td><span class="badge {badge_cls}">{sev}</span></td>'
            f'<td style="font-weight:600;">'
            f'{_strip_emojis(a.get("metrica", ""))}</td>'
            f'<td style="font-size:9.5pt;">'
            f'{_strip_emojis(a.get("descripcion", ""))}</td>'
            f'</tr>'
        )

    return f"""
    <div class="anomaly-section">
        <h2 style="color:#E65100;border-color:#E65100;">
            Riesgos y Anomal&iacute;as</h2>
        <table class="anom-table">
            <tr>
                <th style="width:80px;">Severidad</th>
                <th>M&eacute;trica</th>
                <th>Descripci&oacute;n</th>
            </tr>
            {''.join(rows)}
        </table>
    </div>
    """


def _build_news_html(noticias: List[Dict[str, Any]]) -> str:
    """Construye sección de noticias del sector."""
    if not noticias:
        return ''

    items = []
    for n in noticias[:5]:
        titulo = _strip_emojis(n.get('titulo', ''))
        resumen = _strip_emojis(n.get('resumen', n.get('resumen_corto', '')))
        fuente = n.get('fuente', '')
        fecha_n = n.get('fecha', n.get('fecha_publicacion', ''))
        url = n.get('url', '')
        link = f' <a href="{url}" style="color:#1565C0;">Leer m&aacute;s</a>' if url else ''
        meta = ''
        if fuente or fecha_n:
            parts = [p for p in [fuente, str(fecha_n)] if p]
            meta = f'<div class="news-meta">{" | ".join(parts)}</div>'
        items.append(
            f'<div class="news-item">'
            f'<div class="news-title">{titulo}</div>'
            f'<div class="news-summary">{resumen}{link}</div>'
            f'{meta}</div>'
        )

    return (
        '<div class="news-section">'
        '<h2 style="color:#1565C0;border-color:#1565C0;">'
        'Noticias del Sector Energ&eacute;tico</h2>'
        + ''.join(items)
        + '</div>'
    )


def _build_channels_html() -> str:
    """Construye bloque de canales de consulta."""
    return """
    <div class="channels-box">
        <div class="channels-title">Canales de Consulta</div>
        <table cellpadding="0" cellspacing="0" border="0">
            <tr><td>
                <a class="ch-btn" style="background:#0088cc;"
                   href="https://t.me/MinEnergiaColombia_bot">
                   Chatbot Telegram</a>
                <a class="ch-link" style="color:#0088cc;"
                   href="https://t.me/MinEnergiaColombia_bot">
                   t.me/MinEnergiaColombia_bot</a>
            </td></tr>
            <tr><td style="padding-top:6px;">
                <a class="ch-btn" style="background:#1565C0;"
                   href="https://portalenergetico.minenergia.gov.co/">
                   Portal Energ&eacute;tico</a>
                <a class="ch-link" style="color:#1565C0;"
                   href="https://portalenergetico.minenergia.gov.co/">
                   portalenergetico.minenergia.gov.co</a>
            </td></tr>
        </table>
    </div>
    """


# ═══════════════════════════════════════════════════════════════
#  Función principal de generación de PDF
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
    Genera un PDF del informe ejecutivo con portada institucional,
    resumen con semáforo, datos estructurados y narrativa IA.

    Args:
        informe_texto: Texto Markdown del informe.
        fecha_generacion: Fecha/hora de generación.
        generado_con_ia: Si fue generado con IA.
        chart_paths: Lista de paths a imágenes PNG de gráficos.
        fichas: Lista de KPIs estructurados [{indicador, valor, unidad, ...}].
        predicciones: Dict o lista de dicts con estadisticas, predicciones[], modelo.
        anomalias: Lista de anomalías [{severidad, metrica, descripcion}].
        noticias: Lista de noticias [{titulo, resumen, fuente, url}].
        contexto_datos: Dict con campos extra del orquestador:
            - tabla_indicadores_clave: lista de dicts con semáforo
            - generacion_por_fuente: dict con fuentes y porcentajes
            - embalses_detalle: dict consolidado de embalses
            - predicciones_mes_resumen: dict con métricas compactas

    Returns:
        Ruta absoluta al archivo PDF temporal, o None si falla.
    """
    try:
        from weasyprint import HTML

        # ── Preparación de datos ──
        informe_texto = _strip_redundant_header(informe_texto)
        informe_texto = _strip_emojis(informe_texto)

        hoy = fecha_generacion or datetime.now().strftime('%Y-%m-%d %H:%M')
        metodo = 'Asistido por IA' if generado_con_ia else 'Datos consolidados'
        fecha_label = datetime.now().strftime('%Y-%m-%d')

        ctx = contexto_datos or {}
        tabla_indicadores = ctx.get('tabla_indicadores_clave', [])
        gen_por_fuente = ctx.get('generacion_por_fuente', {})
        embalses_detalle = ctx.get('embalses_detalle', {})
        pred_resumen = ctx.get('predicciones_mes_resumen', {})

        logo_b64 = _load_logo_b64()

        # ── Construir secciones ──
        cover_html = _build_cover_html(logo_b64, fecha_label, metodo, hoy)
        page_header = _build_page_header(logo_b64, fecha_label)
        metadata_html = f"""
        <div class="metadata-bar">
            <table><tr>
                <td>Generado: {hoy}</td>
                <td>M&eacute;todo: {metodo}</td>
                <td>Destinatario: Despacho del Viceministro</td>
            </tr></table>
        </div>
        """

        # Semáforo ejecutivo
        semaphore_html = _build_semaphore_html(tabla_indicadores)

        # KPI cards
        kpi_html = _build_kpi_cards_html(fichas or [])

        # Generación por fuente
        gen_source_html = _build_gen_source_html(gen_por_fuente)

        # Embalses detalle
        embalses_html = _build_embalses_detail_html(embalses_detalle)

        # Convertir narrativa Markdown a HTML
        body_html = _markdown_to_html(informe_texto)

        # Gráficos con captions
        charts_html = _build_charts_html(chart_paths or [])

        # Insertar gráficos contextualizados en la narrativa
        # Buscar primera y segunda sección h2 para distribuir gráficos
        if charts_html:
            h2_positions = [m.start() for m in re.finditer(r'<h2>', body_html)]
            if len(h2_positions) >= 2:
                insert_pos = h2_positions[1]
                body_html = body_html[:insert_pos] + charts_html + body_html[insert_pos:]
            else:
                body_html += charts_html

        # Predicciones compactas (reemplaza tablas de 31 filas)
        pred_html = _build_pred_compact_html(pred_resumen)

        # Si no hay predicciones compactas, usar las legacy pero truncadas
        if not pred_html and predicciones:
            pred_html = _build_legacy_pred_html(predicciones)

        # Anomalías
        anom_html = _build_anomalies_html(anomalias or [])

        # Noticias
        news_html = _build_news_html(noticias or [])

        # Canales
        channels_html = _build_channels_html()

        # ══════════════════════════════════════════════
        # Ensamblar HTML completo
        # ══════════════════════════════════════════════
        # Orden: Portada → Header + Metadata → Semáforo → KPIs →
        #        Datos estructurados (gen/embalses) → Narrativa+Charts →
        #        Predicciones → Anomalías → Noticias → Canales → Footer

        full_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <style>{_CSS}</style>
</head>
<body>

    {cover_html}

    {page_header}
    {metadata_html}

    {semaphore_html}

    {kpi_html}

    {gen_source_html}

    {embalses_html}

    {body_html}

    {pred_html}

    {anom_html}

    {news_html}

    {channels_html}

    <div class="footer-note">
        Documento generado autom&aacute;ticamente por el Portal Energ&eacute;tico MME &bull;
        Datos: XM, SIMEM y fuentes oficiales &bull;
        Predicciones: modelos ENSEMBLE con validaci&oacute;n holdout
    </div>
</body>
</html>"""

        # Generar PDF en /tmp
        filename = f'Informe_Ejecutivo_MME_{fecha_label}.pdf'
        pdf_path = os.path.join(tempfile.gettempdir(), filename)

        HTML(string=full_html).write_pdf(pdf_path)

        file_size = os.path.getsize(pdf_path)
        logger.info(
            f'[REPORT_SERVICE] PDF generado: {pdf_path} '
            f'({file_size / 1024:.1f} KB)'
        )
        return pdf_path

    except ImportError:
        logger.error('[REPORT_SERVICE] weasyprint no instalado')
        return None
    except Exception as e:
        logger.error(f'[REPORT_SERVICE] Error generando PDF: {e}', exc_info=True)
        return None


def _build_legacy_pred_html(predicciones) -> str:
    """
    Fallback: genera HTML de predicciones cuando no hay predicciones_mes_resumen.
    Solo tabla de estadísticas, SIN la tabla detallada de 31 filas.
    """
    _pred_items = []
    if isinstance(predicciones, list):
        _pred_items = [p for p in predicciones if p and p.get('estadisticas')]
    elif isinstance(predicciones, dict) and predicciones.get('estadisticas'):
        _pred_items = [predicciones]

    if not _pred_items:
        return ''

    if len(_pred_items) >= 3:
        sec_title = 'Proyecciones a 1 Mes &mdash; 3 M&eacute;tricas Clave'
    elif len(_pred_items) == 1:
        fl = _pred_items[0].get('fuente_label', _pred_items[0].get('fuente', 'General'))
        sec_title = f'Proyecciones a 1 Mes &mdash; {fl}'
    else:
        sec_title = 'Proyecciones a 1 Mes'

    html = f'<div style="margin:12px 0;"><h2>{sec_title}</h2>'

    for pred_item in _pred_items:
        stats = pred_item['estadisticas']
        fuente_label = pred_item.get('fuente_label', pred_item.get('fuente', 'General'))
        fuente_lower = (pred_item.get('fuente', '') or '').lower()

        if 'precio' in fuente_lower or 'bolsa' in fuente_lower:
            unidad = 'COP/kWh'
        elif 'embalse' in fuente_lower:
            unidad = '%'
        else:
            unidad = 'GWh/d\u00eda'

        html += (
            f'<h3>{fuente_label}</h3>'
            '<table class="pred-compact-table">'
            '<tr><th>Estad&iacute;stica</th>'
            '<th style="text-align:right;">Valor</th></tr>'
            f'<tr><td>Promedio diario</td>'
            f'<td style="text-align:right;font-weight:600;">'
            f'{stats.get("promedio_gwh", 0):,.1f} {unidad}</td></tr>'
            f'<tr><td>M&aacute;ximo esperado</td>'
            f'<td style="text-align:right;">'
            f'{stats.get("maximo_gwh", 0):,.1f} {unidad}</td></tr>'
            f'<tr><td>M&iacute;nimo esperado</td>'
            f'<td style="text-align:right;">'
            f'{stats.get("minimo_gwh", 0):,.1f} {unidad}</td></tr>'
            '</table>'
        )

    html += '</div>'
    return html
