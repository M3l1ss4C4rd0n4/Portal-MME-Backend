"""Helpers compartidos para capítulos del informe PDF."""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from domain.services.report_service import (
    _build_header_html,
    _fecha_corte_html,
    _section_hdr,
    _strip_emojis,
)

ChartSpec = Tuple[str, str]  # (chart_key, caption)


def chapter_cover(num: int, title: str, subtitle: str = "") -> str:
    sub = (
        f'<div style="font-size:10pt;color:#475569;margin-top:6px;">{subtitle}</div>'
        if subtitle else ""
    )
    return f"""
    <div style="background:#254553;color:#fff;padding:14px 18px;margin:0 0 12px 0;border-radius:4px;">
      <div style="font-size:8pt;opacity:0.85;letter-spacing:1px;">CAP&Iacute;TULO {num}</div>
      <div style="font-size:16pt;font-weight:bold;margin-top:4px;">{title}</div>
      {sub}
    </div>
    """


def _parse_fecha_corte(fecha_corte: str) -> str:
    if not fecha_corte or fecha_corte == "N/D":
        return ""
    if "/" in str(fecha_corte):
        d, m, y = str(fecha_corte).split("/")
        return _fecha_corte_html(f"{y}-{m}-{d}")
    return _fecha_corte_html(str(fecha_corte)[:10])


def subsection_hdr(title: str, fecha_corte: str = "") -> str:
    fc = _parse_fecha_corte(fecha_corte)
    fc_block = f'<div style="margin:0 10px 6px;">{fc}</div>' if fc else ""
    return f'{_section_hdr(title, "#287270")}{fc_block}'


def kpi_row(kpis: List[Dict[str, Any]], fecha_corte: str = "", max_items: int = 4) -> str:
    if not kpis:
        return ""
    cells = ""
    subset = kpis[:max_items]
    width = 100 // max(len(subset), 1)
    for k in subset:
        label = _strip_emojis(str(k.get("label", "")))
        valor = k.get("valor", "")
        unidad = k.get("unidad", "")
        if isinstance(valor, (int, float)) and unidad == "%":
            val_str = f"{valor:.1f}%"
        elif isinstance(valor, (int, float)):
            val_str = f"{valor:,.0f}" if abs(float(valor)) >= 100 else f"{valor}"
        else:
            val_str = str(valor)
        if unidad and unidad != "%":
            val_str = f"{val_str} {unidad}"
        cells += f"""
        <td style="width:{width}%;padding:4px;vertical-align:top;">
          <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{val_str}</div>
          </div>
        </td>
        """
    fc = _parse_fecha_corte(fecha_corte)
    fc_row = f'<tr><td colspan="{len(subset)}">{fc}</td></tr>' if fc else ""
    return f'<table width="100%" cellpadding="0" cellspacing="4"><tr>{cells}</tr>{fc_row}</table>'


def embed_chart_path(path: Optional[str], caption: str = "") -> str:
    """Incrusta PNG directamente (sin depender de substring en nombre de archivo)."""
    if not path or not os.path.isfile(path):
        return (
            '<div style="margin:12px;padding:20px;background:#fef2f2;border:1px dashed #fca5a5;'
            'text-align:center;font-size:8pt;color:#991b1b;">Gráfico no disponible</div>'
        )
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
    except OSError:
        return ""
    cap = (
        f'<div class="chart-caption" style="font-size:7.5pt;color:#475569;margin-top:4px;">{caption}</div>'
        if caption else ""
    )
    return f"""
    <div class="chart-box" style="margin:8px 6px 14px;text-align:center;">
      <img src="data:image/png;base64,{b64}" alt="{caption}"
           style="width:100%;max-height:540px;object-fit:contain;">
      {cap}
    </div>
    """


def embed_chart(chart_paths: Optional[Dict[str, str]], key: str, caption: str = "") -> str:
    if not chart_paths:
        return embed_chart_path(None, caption)
    return embed_chart_path(chart_paths.get(key), caption or key)


def chart_pages(
    logo_b64: str,
    fecha_label: str,
    specs: Sequence[ChartSpec],
    chart_paths: Optional[Dict[str, str]],
    intro_html: str = "",
) -> str:
    """Una página PDF por gráfico — layout centrado en visualizaciones."""
    pages: List[str] = []
    if intro_html:
        pages.append(wrap_chapter_page(logo_b64, fecha_label, intro_html))

    for key, caption in specs:
        body = f"""
        {subsection_hdr(caption)}
        {embed_chart(chart_paths, key, caption)}
        """
        pages.append(wrap_chapter_page(logo_b64, fecha_label, body))
    return "".join(pages)


def simple_table(headers: List[str], rows: List[List[str]], caption: str = "") -> str:
    hdr = "".join(f"<th style='padding:6px;font-size:8pt;'>{h}</th>" for h in headers)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(
            f"<td style='padding:5px 6px;font-size:8pt;'>{c}</td>" for c in row
        ) + "</tr>"
    cap = (
        f"<div style='font-size:7pt;color:#666;margin-bottom:4px;'>{caption}</div>"
        if caption else ""
    )
    return f"""
    {cap}
    <table class="anom-tbl" style="width:100%;border-collapse:collapse;">
      <tr style="background:#f1f5f9;">{hdr}</tr>
      {body}
    </table>
    """


def wrap_chapter_page(logo_b64: str, fecha_label: str, body: str) -> str:
    header = _build_header_html(logo_b64, fecha_label)
    return f'<div class="page">{header}{body}</div>'
