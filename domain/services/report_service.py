"""
Servicio de generación de PDFs para informes ejecutivos.

Convierte el informe ejecutivo (Markdown) a HTML profesional
y luego a PDF usando WeasyPrint. Los PDFs se generan en /tmp
y se eliminan después de enviarse.
"""

import logging
import os
import re
import tempfile
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


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

        # Headers
        if stripped.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            title = stripped[3:].strip()
            title = _inline_format(title)
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
"""


def generar_pdf_informe(
    informe_texto: str,
    fecha_generacion: str = "",
    generado_con_ia: bool = True,
) -> Optional[str]:
    """
    Genera un PDF del informe ejecutivo.

    Args:
        informe_texto: Texto Markdown del informe.
        fecha_generacion: Fecha/hora de generación.
        generado_con_ia: Si fue generado con IA.

    Returns:
        Ruta absoluta al archivo PDF temporal, o None si falla.
    """
    try:
        from weasyprint import HTML

        # Convertir Markdown → HTML
        body_html = _markdown_to_html(informe_texto)

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
        <h1>📊 Informe Ejecutivo del Sector Eléctrico</h1>
        <p class="subtitle">República de Colombia — Ministerio de Minas y Energía</p>
    </div>

    <div class="metadata">
        <span>📅 {hoy}</span>
        <span>🔧 {metodo}</span>
        <span>📋 Despacho del Viceministro</span>
    </div>

    {body_html}

    <div class="footer-note">
        Documento generado automáticamente por el Portal Energético MME.
        Los datos provienen de XM, SIMEM y fuentes oficiales del sector.
        Las predicciones utilizan modelos ENSEMBLE con validación holdout.
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
