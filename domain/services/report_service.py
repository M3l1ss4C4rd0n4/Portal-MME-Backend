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

# ── Mapa de emojis → texto para PDF (WeasyPrint no renderiza emojis) ──
_EMOJI_MAP = {
    '\U0001f4ca': '[Grafico]',
    '\U0001f4c5': '[Fecha]',
    '\u26a1': '[Energia]',
    '\U0001f50c': '[Enchufe]',
    '\U0001f4b0': '[Precio]',
    '\U0001f4b2': '[Precio]',
    '\U0001f4a7': '[Agua]',
    '\U0001f321\ufe0f': '[Temp]',
    '\U0001f525': '[Fuego]',
    '\u2600\ufe0f': '[Sol]',
    '\U0001f32c\ufe0f': '[Viento]',
    '\U0001f534': '[CRITICO]',
    '\U0001f7e0': '[ALERTA]',
    '\U0001f7e2': '[OK]',
    '\u26aa': '[--]',
    '\u2705': '[OK]',
    '\u26a0\ufe0f': '[!]',
    '\u26a0': '[!]',
    '\U0001f4c8': '[Subida]',
    '\U0001f4c9': '[Bajada]',
    '\u27a1\ufe0f': '[->]',
    '\u27a1': '[->]',
    '\U0001f4cb': '[Lista]',
    '\U0001f527': '[Config]',
    '\U0001f3ed': '[Planta]',
    '\U0001f3e2': '[Edificio]',
    '\U0001f30e': '[Mundo]',
    '\U0001f4f0': '[Prensa]',
    '\U0001f4a1': '[Idea]',
    '\U0001f6e0\ufe0f': '[Herr]',
    '\U0001f6e0': '[Herr]',
    '\U0001f4dd': '[Nota]',
    '\U0001f3af': '[Meta]',
    '\U0001f4cc': '[Pin]',
    '\U0001f91d': '[Acuerdo]',
    '\U0001f4e2': '[Alerta]',
    '\U0001f4d1': '[Doc]',
    '\u2796': '[-]',
    '\u2795': '[+]',
    '\u27a4': '[>]',
    '\u2192': '->',
    '\U0001f1f2': '',
    '\U0001f1ea': '',
}

# Regex para detectar emojis Unicode restantes
_EMOJI_PATTERN = re.compile(
    '['
    '\U0001F600-\U0001F64F'  # emoticons
    '\U0001F300-\U0001F5FF'  # misc symbols & pictographs
    '\U0001F680-\U0001F6FF'  # transport & map symbols
    '\U0001F1E0-\U0001F1FF'  # flags
    '\U00002702-\U000027B0'  # dingbats
    '\U000024C2-\U0001F251'  # enclosed characters
    '\U0001F900-\U0001F9FF'  # supplemental symbols
    '\U0001FA00-\U0001FA6F'  # chess symbols
    '\U0001FA70-\U0001FAFF'  # symbols extended-A
    ']+', flags=re.UNICODE
)


def _replace_emojis_for_pdf(text: str) -> str:
    """Reemplaza emojis por equivalentes de texto para PDF."""
    for emoji, replacement in _EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    # Eliminar cualquier emoji restante no mapeado
    text = _EMOJI_PATTERN.sub('', text)
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
        re.compile(r'^[━─\-]{5,}$'),  # separators
    ]
    for line in lines:
        stripped = line.strip()
        # Remove emoji-only or decoration-only lines
        cleaned = _EMOJI_PATTERN.sub('', stripped).strip()
        if cleaned in ('INFORME EJECUTIVO — SECTOR ELÉCTRICO',
                       'INFORME EJECUTIVO  SECTOR ELÉCTRICO',
                       'INFORME EJECUTIVO'):
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


# ── CSS corporativo MME ──────────────────────────────────

_CSS = """
@page {
    size: letter;
    margin: 2cm 2.5cm;
    @top-center {
        content: "Ministerio de Minas y Energía — Informe Ejecutivo";
        font-size: 8pt;
        color: #666;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
    @bottom-center {
        content: "Página " counter(page) " de " counter(pages);
        font-size: 8pt;
        color: #666;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
}

body {
    font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #222;
    max-width: 100%;
}

.header {
    text-align: center;
    border-bottom: 3px solid #1a5276;
    padding-bottom: 12px;
    margin-bottom: 20px;
}

.header h1 {
    font-size: 18pt;
    color: #1a5276;
    margin: 0 0 4px 0;
}

.header .subtitle {
    font-size: 10pt;
    color: #555;
    margin: 0;
}

.metadata {
    display: flex;
    justify-content: space-between;
    font-size: 9pt;
    color: #555;
    margin-bottom: 16px;
    padding: 6px 10px;
    background: #f0f4f8;
    border-radius: 4px;
}

h2 {
    font-size: 14pt;
    color: #1a5276;
    border-bottom: 1px solid #d4e6f1;
    padding-bottom: 4px;
    margin-top: 20px;
    margin-bottom: 8px;
}

h3 {
    font-size: 12pt;
    color: #2c3e50;
    margin-top: 14px;
    margin-bottom: 6px;
}

p {
    margin: 4px 0;
    text-align: justify;
}

ul {
    margin: 4px 0 4px 20px;
    padding: 0;
}

li {
    margin-bottom: 4px;
}

hr {
    border: none;
    border-top: 1px solid #d4e6f1;
    margin: 12px 0;
}

strong {
    color: #1a5276;
}

em {
    color: #555;
}

.footer-note {
    margin-top: 24px;
    padding-top: 8px;
    border-top: 1px solid #ccc;
    font-size: 8pt;
    color: #888;
    text-align: center;
}

.charts-section {
    margin: 12px 0;
}

.charts-section h3 {
    text-align: center;
    color: #1a5276;
    font-size: 12pt;
    margin-bottom: 8px;
}

.chart-container {
    text-align: center;
    margin: 8px 0;
    page-break-inside: avoid;
}

.chart-container img {
    width: 85%;
    max-width: 480px;
    height: auto;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
}

.chart-caption {
    font-size: 8pt;
    color: #64748b;
    text-align: center;
    margin-top: 2px;
    margin-bottom: 6px;
    font-style: italic;
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
) -> Optional[str]:
    """
    Genera un PDF del informe ejecutivo.

    Args:
        informe_texto: Texto Markdown del informe.
        fecha_generacion: Fecha/hora de generación.
        generado_con_ia: Si fue generado con IA.
        chart_paths: Lista de paths a imágenes PNG de gráficos para incrustar
                     después de la sección 1 (Situación actual).

    Returns:
        Ruta absoluta al archivo PDF temporal, o None si falla.
    """
    try:
        from weasyprint import HTML

        # Limpiar encabezado redundante y emojis
        informe_texto = _strip_redundant_header(informe_texto)
        informe_texto = _replace_emojis_for_pdf(informe_texto)

        # Convertir Markdown → HTML
        body_html = _markdown_to_html(informe_texto)

        # Incrustar gráficos después de la sección 1 ("Situación actual")
        charts_html = _build_charts_html(chart_paths or [])
        if charts_html:
            # Insertar después del primer </h2> + su contenido (sección 1)
            # Buscamos el cierre de la primera sección (inicio de la segunda <h2>)
            h2_positions = [m.start() for m in re.finditer(r'<h2>', body_html)]
            if len(h2_positions) >= 2:
                insert_pos = h2_positions[1]
                body_html = body_html[:insert_pos] + charts_html + body_html[insert_pos:]
            else:
                # Si no hay 2 secciones, agregar al final del body
                body_html += charts_html

        hoy = fecha_generacion or datetime.now().strftime('%Y-%m-%d %H:%M')
        metodo = "Asistido por IA" if generado_con_ia else "Datos consolidados"
        fecha_label = datetime.now().strftime('%Y-%m-%d')

        full_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <style>{_CSS}</style>
</head>
<body>
    <div class="header">
        <h1>Informe Ejecutivo del Sector El&eacute;ctrico</h1>
        <p class="subtitle">Rep&uacute;blica de Colombia &mdash; Ministerio de Minas y Energ&iacute;a</p>
    </div>

    <div class="metadata">
        <span>{hoy}</span>
        <span>{metodo}</span>
        <span>Despacho del Viceministro</span>
    </div>

    {body_html}

    <div class="footer-note">
        Documento generado autom&aacute;ticamente por el Portal Energ&eacute;tico MME.
        Los datos provienen de XM, SIMEM y fuentes oficiales del sector.
        Las predicciones utilizan modelos ENSEMBLE con validaci&oacute;n holdout.
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
