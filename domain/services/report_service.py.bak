"""
Servicio de generación de PDFs para informes ejecutivos.

Convierte el informe ejecutivo (Markdown) a HTML profesional
y luego a PDF usando WeasyPrint. Los PDFs se generan en /tmp
y se eliminan después de enviarse.
"""

import base64
import logging
import os
import re
import tempfile
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

# Regex para detectar emojis Unicode (WeasyPrint no los renderiza)
_EMOJI_PATTERN = re.compile(
    '['
    '\U0001F600-\U0001F64F'
    '\U0001F300-\U0001F5FF'
    '\U0001F680-\U0001F6FF'
    '\U0001F1E0-\U0001F1FF'
    '\U00002702-\U000027B0'
    '\U000024C2-\U0001F251'
    '\U0001F900-\U0001F9FF'
    '\U0001FA00-\U0001FA6F'
    '\U0001FA70-\U0001FAFF'
    '\u2600-\u26FF'
    '\u2700-\u27BF'
    '\uFE00-\uFE0F'
    '\u200D'
    ']+', flags=re.UNICODE
)


def _strip_emojis(text: str) -> str:
    """Elimina todos los emojis del texto para renderizado limpio en PDF."""
    text = _EMOJI_PATTERN.sub('', text)
    # Limpiar espacios dobles resultantes
    text = re.sub(r'  +', ' ', text)
    return text


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
            # Only skip if original had content (don't remove blank lines)
            if stripped:
                continue
        if any(p.match(stripped) for p in skip_patterns):
            continue
        if any(p.match(cleaned) for p in skip_patterns):
            continue
        filtered.append(line)
    return '\n'.join(filtered)


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

        # Empty line
        if not stripped:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<br>')
            continue

        # Headers — standard markdown
        if stripped.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            title = stripped[3:].strip()
            title = _inline_format(title)
            html_lines.append(f'<h2>{title}</h2>')
            continue

        # Headers — fallback format: *1. Título* or *N. Título*
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

        # Horizontal rule
        if stripped in ('━━━━━━━━━━━━━━━━━━━━━━━━━━━━', '---', '───'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<hr>')
            continue

        # Bullet list
        if stripped.startswith(('- ', '• ', '· ')):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            content = stripped[2:].strip()
            content = _inline_format(content)
            html_lines.append(f'  <li>{content}</li>')
            continue

        # Regular paragraph
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
    # Bold: **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic: *text* (pero no confundir con bold)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    # Italic: _text_
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    return text


# ── CSS profesional institucional MME ───────────────────────────

_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'assets', 'images', 'logo-minenergia.png'
)

_CSS = """
@page {
    size: letter;
    margin: 2cm 2cm 2.5cm 2cm;
    @bottom-center {
        content: "Portal Energetico MME  |  Pagina " counter(page) " de " counter(pages);
        font-size: 7.5pt;
        color: #888;
        font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    }
}

body {
    font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.55;
    color: #222;
    max-width: 100%;
    text-rendering: optimizeLegibility;
}

/* ── Encabezado institucional ── */
.header {
    display: flex;
    align-items: center;
    border-bottom: 2.5pt solid #1a3c5e;
    padding-bottom: 10px;
    margin-bottom: 4px;
}

.header-logo {
    flex: 0 0 auto;
    margin-right: 16px;
}

.header-logo img {
    width: 52px;
    height: auto;
}

.header-text {
    flex: 1;
}

.header-text h1 {
    font-size: 17pt;
    font-weight: 700;
    color: #1a3c5e;
    margin: 0 0 2px 0;
    letter-spacing: 0.3pt;
}

.header-text .subtitle {
    font-size: 9.5pt;
    color: #555;
    margin: 0;
    font-weight: 400;
}

/* ── Barra de metadatos ── */
.metadata {
    font-size: 8.5pt;
    color: #555;
    margin-bottom: 16px;
    padding: 6px 12px;
    background: #f5f7fa;
    border-bottom: 1px solid #ddd;
}

.metadata table {
    width: 100%;
    border: none;
    border-collapse: collapse;
}

.metadata td {
    padding: 1px 0;
    border: none;
}

.metadata td:last-child {
    text-align: right;
}

/* ── Titulos de seccion (h2) ── */
h2 {
    font-size: 13.5pt;
    font-weight: 700;
    color: #1a3c5e;
    margin-top: 20px;
    margin-bottom: 8px;
    padding-bottom: 3px;
    padding-left: 8px;
    border-left: 3pt solid #1a3c5e;
    border-bottom: 0.5pt solid #ccc;
    page-break-after: avoid;
}

/* ── Subtitulos (h3) ── */
h3 {
    font-size: 11.5pt;
    font-weight: 600;
    color: #2c3e50;
    margin-top: 14px;
    margin-bottom: 5px;
    padding-left: 8px;
    border-left: 2pt solid #6c9ec2;
    page-break-after: avoid;
}

/* ── Parrafos ── */
p {
    margin: 5px 0;
    text-align: justify;
    orphans: 3;
    widows: 3;
}

/* ── Listas ── */
ul {
    margin: 5px 0 5px 24px;
    padding: 0;
    list-style-type: disc;
}

li {
    margin-bottom: 3px;
    text-align: justify;
}

/* ── Separadores ── */
hr {
    border: none;
    border-top: 0.5pt solid #ccc;
    margin: 12px 0;
}

/* ── Estilos de texto ── */
strong {
    font-weight: 700;
    color: inherit;
}

em {
    font-style: italic;
    color: inherit;
}

/* ── Nota al pie del documento ── */
.footer-note {
    margin-top: 24px;
    padding-top: 8px;
    border-top: 1pt solid #1a3c5e;
    font-size: 7.5pt;
    color: #888;
    text-align: center;
    line-height: 1.4;
}

/* ── Graficos ── */
.charts-section {
    margin: 12px 0;
    page-break-inside: avoid;
}

.chart-container {
    text-align: center;
    margin: 8px 0;
    page-break-inside: avoid;
}

.chart-container img {
    width: 82%;
    max-width: 440px;
    height: auto;
    border: 0.5pt solid #ddd;
}

.chart-caption {
    font-size: 8pt;
    color: #666;
    text-align: center;
    margin-top: 2px;
    margin-bottom: 6px;
    font-style: italic;
}

.chart-caption a {
    color: #1a3c5e;
    text-decoration: underline;
}
"""


def _build_charts_html(chart_paths: List[str]) -> str:
    """
    Convierte una lista de paths a imágenes PNG en HTML con data URIs base64.
    Las imágenes se incrustan directamente en el HTML para que WeasyPrint las renderice.
    """
    if not chart_paths:
        return ""

    captions = {
        'gen_pie': 'Participación por fuente de generación',
        'embalses_map': 'Nivel de embalses por región hidrológica',
        'precio_evol': 'Evolución del Precio de Bolsa Nacional (90 días)',
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

            fname = os.path.basename(path).split('_202')[0]  # gen_pie, embalses_map, etc.
            caption = captions.get(fname, '')
            url = urls.get(fname, '')

            block = f'<div class="chart-container">'
            block += f'<img src="data:image/png;base64,{b64}" alt="{caption}">'
            if caption:
                if url:
                    block += (f'<p class="chart-caption">{caption} — '
                             f'<a href="{url}" style="color:#1a5276;">'
                             f'Ver en el Portal Energético</a></p>')
                else:
                    block += f'<p class="chart-caption">{caption}</p>'
            block += '</div>'
            img_blocks.append(block)
        except Exception as e:
            logger.warning(f"[REPORT] Error embediendo imagen {path}: {e}")

    if not img_blocks:
        return ""

    html = '<div class="charts-section">'
    html += '\n'.join(img_blocks)
    html += '</div>'
    return html


def generar_pdf_informe(
    informe_texto: str,
    fecha_generacion: str = "",
    generado_con_ia: bool = True,
    chart_paths: Optional[List[str]] = None,
    fichas: Optional[List[dict]] = None,
    predicciones = None,
    anomalias: Optional[list] = None,
    noticias: Optional[list] = None,
) -> Optional[str]:
    """
    Genera un PDF del informe ejecutivo con datos estructurados + narrativa IA.

    Args:
        informe_texto: Texto Markdown del informe.
        fecha_generacion: Fecha/hora de generación.
        generado_con_ia: Si fue generado con IA.
        chart_paths: Lista de paths a imágenes PNG de gráficos.
        fichas: Lista de KPIs estructurados [{indicador, valor, unidad, ...}].
        predicciones: Dict o lista de dicts con estadisticas, predicciones[], modelo.
        anomalias: Lista de anomalías [{severidad, metrica, descripcion}].
        noticias: Lista de noticias [{titulo, resumen, fuente, url}].

    Returns:
        Ruta absoluta al archivo PDF temporal, o None si falla.
    """
    try:
        from weasyprint import HTML

        # Limpiar encabezado redundante y emojis
        informe_texto = _strip_redundant_header(informe_texto)
        informe_texto = _strip_emojis(informe_texto)

        hoy = fecha_generacion or datetime.now().strftime('%Y-%m-%d %H:%M')
        metodo = "Asistido por IA" if generado_con_ia else "Datos consolidados"
        fecha_label = datetime.now().strftime('%Y-%m-%d')

        # ── KPI Cards HTML ──
        kpi_html = ''
        if fichas:
            cards = []
            colors = ['#1565C0', '#2E7D32', '#E65100']
            for i, f in enumerate(fichas[:3]):
                color = colors[i % len(colors)]
                valor = f.get('valor', '')
                unidad = f.get('unidad', '')
                indicador = _strip_emojis(f.get('indicador', ''))
                ctx = f.get('contexto', {})
                var_pct = ctx.get('variacion_vs_promedio_pct', None)

                if isinstance(valor, float):
                    val_str = f"{valor:,.2f} {unidad}"
                else:
                    val_str = f"{valor} {unidad}"

                var_line = ''
                if var_pct is not None:
                    sign = '+' if float(var_pct) >= 0 else ''
                    etiqueta_var = ctx.get('etiqueta_variacion', 'vs promedio 7d')
                    var_line = f'<div style="font-size:10px;color:#666;margin-top:2px;">{sign}{var_pct:.1f}% {etiqueta_var}</div>'

                cards.append(
                    f'<div style="flex:1;background:#f8f9fa;border-left:4px solid {color};'
                    f'border-radius:6px;padding:12px 14px;margin:0 6px;">'
                    f'<div style="font-size:11px;color:#666;margin-bottom:4px;">{indicador}</div>'
                    f'<div style="font-size:20px;font-weight:700;color:{color};">{val_str}</div>'
                    f'{var_line}'
                    f'</div>'
                )
            kpi_html = (
                '<div style="margin:16px 0;">'
                '<h2 style="color:#1a3c5e;border-bottom:2px solid #1a3c5e;padding-bottom:6px;">'
                'Indicadores Clave del Dia</h2>'
                '<div style="display:flex;gap:10px;margin-top:10px;">'
                + ''.join(cards)
                + '</div></div>'
            )

        # ── Predicciones HTML ──
        pred_html = ''
        # Normalizar: aceptar dict (legacy) o lista (multi-métrica)
        _pred_items = []
        if isinstance(predicciones, list):
            _pred_items = [p for p in predicciones if p and p.get('estadisticas')]
        elif isinstance(predicciones, dict) and predicciones.get('estadisticas'):
            _pred_items = [predicciones]

        if _pred_items:
            # Determinar título de sección
            if len(_pred_items) >= 3:
                sec_title = 'Proyecciones a 1 Mes — 3 M' + chr(233) + 'tricas Clave'
            elif len(_pred_items) == 1:
                fl = _pred_items[0].get('fuente_label', _pred_items[0].get('fuente', 'General'))
                sec_title = f'Proyecciones a 1 Mes — {fl}'
            else:
                sec_title = 'Proyecciones a 1 Mes'

            first_modelo = ''
            for pi in _pred_items:
                m = pi.get('modelo', '')
                if m:
                    first_modelo = m
                    break

            pred_html = (
                '<div style="margin:16px 0;">'
                '<h2 style="color:#1a3c5e;border-bottom:2px solid #1a3c5e;padding-bottom:6px;">'
                f'{sec_title}'
                + (f' <span style="font-size:12px;color:#888;">({first_modelo})</span>' if first_modelo else '')
                + '</h2>'
            )

            for pred_item in _pred_items:
                stats = pred_item['estadisticas']
                preds_list = pred_item.get('predicciones', [])
                fuente = pred_item.get('fuente', 'General')
                fuente_label = pred_item.get('fuente_label', fuente)
                fuente_lower = fuente.lower() if fuente else ''
                if fuente_lower in ('hidráulica', 'hidraulica', 'térmica', 'termica',
                                    'solar', 'eólica', 'eolica'):
                    fuente_label = f'Generaci' + chr(243) + 'n {fuente}'

                # Unidad según métrica
                if 'precio' in fuente_lower or 'bolsa' in fuente_lower or 'PRECIO' in fuente:
                    unidad = 'COP/kWh'
                elif 'embalse' in fuente_lower or 'EMBALSES' in fuente:
                    unidad = '%'
                else:
                    unidad = 'GWh/dia'

                pred_html += (
                    f'<h3 style="color:#333;margin:14px 0 6px;font-size:14px;">{fuente_label}</h3>'
                    '<table style="width:100%;border-collapse:collapse;margin-top:4px;font-size:12px;">'
                    '<tr style="background:#1a3c5e;color:#fff;">'
                    '<th style="padding:8px 12px;text-align:left;">Estadistica</th>'
                    '<th style="padding:8px 12px;text-align:right;">Valor</th></tr>'
                    f'<tr style="background:#f8f9fa;"><td style="padding:8px 12px;">Promedio diario</td>'
                    f'<td style="padding:8px 12px;text-align:right;font-weight:600;">'
                    f'{stats.get("promedio_gwh", 0):,.1f} {unidad}</td></tr>'
                    f'<tr><td style="padding:8px 12px;">Maximo esperado</td>'
                    f'<td style="padding:8px 12px;text-align:right;">'
                    f'{stats.get("maximo_gwh", 0):,.1f} {unidad}</td></tr>'
                    f'<tr style="background:#f8f9fa;"><td style="padding:8px 12px;">Minimo esperado</td>'
                    f'<td style="padding:8px 12px;text-align:right;">'
                    f'{stats.get("minimo_gwh", 0):,.1f} {unidad}</td></tr>'
                    f'<tr><td style="padding:8px 12px;">Total predicciones</td>'
                    f'<td style="padding:8px 12px;text-align:right;">'
                    f'{pred_item.get("total_predicciones", len(preds_list))} dias</td></tr>'
                    '</table>'
                )

                # Tabla detallada de primeros 10 + últimos 5 días
                if preds_list:
                    pred_html += (
                        '<table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:11px;">'
                        '<tr style="background:#eee;"><th style="padding:6px 10px;text-align:left;">Fecha</th>'
                        f'<th style="padding:6px 10px;text-align:right;">Valor ({unidad})</th>'
                        '<th style="padding:6px 10px;text-align:right;">Intervalo Inferior</th>'
                        '<th style="padding:6px 10px;text-align:right;">Intervalo Superior</th></tr>'
                    )
                    show = preds_list[:10]
                    if len(preds_list) > 15:
                        show += [None]  # separator
                        show += preds_list[-5:]
                    elif len(preds_list) > 10:
                        show = preds_list

                    for j, p in enumerate(show):
                        if p is None:
                            pred_html += (
                                '<tr><td colspan="4" style="padding:4px 10px;text-align:center;'
                                'color:#999;font-style:italic;">...</td></tr>'
                            )
                            continue
                        bg = 'background:#f8f9fa;' if j % 2 == 0 else ''
                        pred_html += (
                            f'<tr style="{bg}">'
                            f'<td style="padding:5px 10px;">{p.get("fecha", "")}</td>'
                            f'<td style="padding:5px 10px;text-align:right;font-weight:600;">'
                            f'{p.get("valor_gwh", 0):.1f}</td>'
                            f'<td style="padding:5px 10px;text-align:right;">'
                            f'{p.get("intervalo_inferior", 0):.1f}</td>'
                            f'<td style="padding:5px 10px;text-align:right;">'
                            f'{p.get("intervalo_superior", 0):.1f}</td></tr>'
                        )
                    pred_html += '</table>'

            pred_html += '</div>'

        # ── Anomalías HTML ──
        anom_html = ''
        if anomalias:
            rows = []
            for a in anomalias[:10]:
                sev = a.get('severidad', 'ALERTA')
                if sev in ('CRITICA', 'CRITICO', 'CRITICAL'):
                    s_color = '#C62828'
                    s_bg = '#FFEBEE'
                elif sev == 'ALERTA':
                    s_color = '#E65100'
                    s_bg = '#FFF3E0'
                else:
                    s_color = '#F9A825'
                    s_bg = '#FFFDE7'
                rows.append(
                    f'<tr>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #eee;">'
                    f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
                    f'font-size:10px;font-weight:700;color:#fff;background:{s_color};">'
                    f'{sev}</span></td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #eee;font-weight:600;">'
                    f'{_strip_emojis(a.get("metrica", ""))}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:11px;">'
                    f'{_strip_emojis(a.get("descripcion", ""))}</td></tr>'
                )
            anom_html = (
                '<div style="margin:16px 0;">'
                '<h2 style="color:#E65100;border-bottom:2px solid #E65100;padding-bottom:6px;">'
                'Riesgos y Anomalias</h2>'
                '<table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:12px;">'
                '<tr style="background:#FFF8E1;">'
                '<th style="padding:6px 10px;text-align:left;width:80px;">Severidad</th>'
                '<th style="padding:6px 10px;text-align:left;">Metrica</th>'
                '<th style="padding:6px 10px;text-align:left;">Descripcion</th></tr>'
                + ''.join(rows)
                + '</table></div>'
            )

        # ── Noticias HTML ──
        news_html = ''
        if noticias:
            items = []
            for n in noticias[:5]:
                titulo = _strip_emojis(n.get('titulo', ''))
                resumen = _strip_emojis(n.get('resumen', n.get('resumen_corto', '')))
                fuente = n.get('fuente', '')
                fecha_n = n.get('fecha', n.get('fecha_publicacion', ''))
                url = n.get('url', '')
                link = f' <a href="{url}" style="color:#1565C0;">Leer mas</a>' if url else ''
                meta = ''
                if fuente or fecha_n:
                    parts = [p for p in [fuente, str(fecha_n)] if p]
                    meta = f'<div style="font-size:10px;color:#888;margin-top:2px;">{" | ".join(parts)}</div>'
                items.append(
                    f'<div style="padding:8px 0;border-bottom:1px solid #eee;">'
                    f'<div style="font-size:12px;font-weight:600;color:#222;">{titulo}</div>'
                    f'<div style="font-size:11px;color:#555;margin-top:2px;line-height:1.5;">'
                    f'{resumen}{link}</div>{meta}</div>'
                )
            news_html = (
                '<div style="margin:16px 0;">'
                '<h2 style="color:#1565C0;border-bottom:2px solid #1565C0;padding-bottom:6px;">'
                'Noticias del Sector Energetico</h2>'
                + ''.join(items) + '</div>'
            )

        # ── Convertir narrativa Markdown a HTML ──
        body_html = _markdown_to_html(informe_texto)

        # ── Incrustar gráficos después de la sección 1 ──
        charts_html = _build_charts_html(chart_paths or [])
        if charts_html:
            h2_positions = [m.start() for m in re.finditer(r'<h2>', body_html)]
            if len(h2_positions) >= 2:
                insert_pos = h2_positions[1]
                body_html = body_html[:insert_pos] + charts_html + body_html[insert_pos:]
            else:
                body_html += charts_html

        # Logo embebido en base64
        logo_html = ''
        if os.path.exists(_LOGO_PATH):
            try:
                with open(_LOGO_PATH, 'rb') as lf:
                    logo_b64 = base64.b64encode(lf.read()).decode('utf-8')
                logo_html = (
                    '<div class="header-logo">'
                    f'<img src="data:image/png;base64,{logo_b64}" alt="MME">'
                    '</div>'
                )
            except Exception:
                pass

        # ── Ensamblar HTML completo ──
        # Orden: KPIs → Gráficos+Narrativa → Predicciones → Anomalías → Noticias
        full_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <style>{_CSS}</style>
</head>
<body>
    <div class="header">
        {logo_html}
        <div class="header-text">
            <h1>Informe Ejecutivo del Sector El&eacute;ctrico &mdash; {fecha_label}</h1>
            <p class="subtitle">Portal Energ&eacute;tico MME &bull; Rep&uacute;blica de Colombia</p>
        </div>
    </div>

    <div class="metadata">
        <table><tr>
            <td>Generado: {hoy}</td>
            <td>M&eacute;todo: {metodo}</td>
            <td>Destinatario: Despacho del Viceministro</td>
        </tr></table>
    </div>

    {kpi_html}

    {body_html}

    {pred_html}

    {anom_html}

    {news_html}

    <div style="margin:20px 0;padding:16px;background:#F5F7FA;border-radius:10px;">
        <div style="font-size:14px;font-weight:700;color:#333;margin-bottom:12px;">
            &#128204; Canales de Consulta
        </div>
        <table cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td style="padding:6px 0;">
                    <span style="background:#0088cc;border-radius:6px;padding:8px 16px;display:inline-block;">
                        <a href="https://t.me/MinEnergiaColombia_bot"
                           style="color:#ffffff;text-decoration:none;font-size:12px;font-weight:600;">
                            &#128172; Chatbot Telegram
                        </a>
                    </span>
                    <span style="padding-left:10px;">
                        <a href="https://t.me/MinEnergiaColombia_bot"
                           style="color:#0088cc;font-size:11px;">t.me/MinEnergiaColombia_bot</a>
                    </span>
                </td>
            </tr>
            <tr>
                <td style="padding:6px 0;">
                    <span style="background:#1565C0;border-radius:6px;padding:8px 16px;display:inline-block;">
                        <a href="https://portalenergetico.minenergia.gov.co/"
                           style="color:#ffffff;text-decoration:none;font-size:12px;font-weight:600;">
                            &#127760; Portal Energ&eacute;tico
                        </a>
                    </span>
                    <span style="padding-left:10px;">
                        <a href="https://portalenergetico.minenergia.gov.co/"
                           style="color:#1565C0;font-size:11px;">portalenergetico.minenergia.gov.co</a>
                    </span>
                </td>
            </tr>
        </table>
    </div>

    <div class="footer-note">
        Documento generado autom&aacute;ticamente por el Portal Energ&eacute;tico MME &bull;
        Datos: XM, SIMEM y fuentes oficiales &bull;
        Predicciones: modelos ENSEMBLE con validaci&oacute;n holdout
    </div>
</body>
</html>"""

        # Generar PDF en /tmp
        filename = f"Informe_Ejecutivo_MME_{fecha_label}.pdf"
        pdf_path = os.path.join(tempfile.gettempdir(), filename)

        HTML(string=full_html).write_pdf(pdf_path)

        file_size = os.path.getsize(pdf_path)
        logger.info(
            f"[REPORT_SERVICE] PDF generado: {pdf_path} "
            f"({file_size / 1024:.1f} KB)"
        )
        return pdf_path

    except ImportError:
        logger.error("[REPORT_SERVICE] weasyprint no instalado")
        return None
    except Exception as e:
        logger.error(f"[REPORT_SERVICE] Error generando PDF: {e}", exc_info=True)
        return None
