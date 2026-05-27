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

KPI_BG = "#254553"
GAUGES_PER_PAGE = 4


def chapter_cover(num: int, title: str, subtitle: str = "") -> str:
    sub = (
        f'<div style="font-size:9pt;color:#cbd5e1;margin-top:4px;">{subtitle}</div>'
        if subtitle else ""
    )
    return f"""
    <div style="background:{KPI_BG};color:#fff;padding:10px 14px;margin:0 0 6px 0;border-radius:4px;">
      <div style="font-size:7.5pt;opacity:0.85;letter-spacing:1px;">CAP&Iacute;TULO {num}</div>
      <div style="font-size:14pt;font-weight:bold;margin-top:2px;">{title}</div>
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


def subsection_hdr(title: str, fecha_corte: str = "", compact: bool = False) -> str:
    fc = _parse_fecha_corte(fecha_corte)
    margin = "2px 10px 4px" if compact else "0 10px 4px"
    fc_block = f'<div style="margin:{margin};">{fc}</div>' if fc else ""
    return f'{_section_hdr(title, "#287270")}{fc_block}'


def _format_kpi_value(k: Dict[str, Any]) -> str:
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
    return val_str


def kpi_row(kpis: List[Dict[str, Any]], fecha_corte: str = "", max_items: int = 4) -> str:
    """Fila de KPIs con el mismo estilo .kpi-box del informe principal."""
    if not kpis:
        return ""
    cells = ""
    subset = kpis[:max_items]
    width = 100 // max(len(subset), 1)
    for k in subset:
        label = _strip_emojis(str(k.get("label", "")))
        val_str = _format_kpi_value(k)
        cells += f"""
        <td style="width:{width}%;padding:2px;vertical-align:top;">
          <div class="kpi-box" style="background:{KPI_BG};">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{val_str}</div>
          </div>
        </td>
        """
    fc = _parse_fecha_corte(fecha_corte)
    fc_row = (
        f'<tr><td colspan="{len(subset)}" style="padding:2px 4px 0;">{fc}</td></tr>'
        if fc else ""
    )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="2" '
        f'style="margin:0 0 6px 0;"><tr>{cells}</tr>{fc_row}</table>'
    )


def _is_gauge(key: str) -> bool:
    return "_gauge_" in key or key.endswith("_gauge")


def embed_chart_path(
    path: Optional[str],
    caption: str = "",
    *,
    max_height: int = 480,
    compact: bool = False,
) -> str:
    """Incrusta PNG directamente (sin depender de substring en nombre de archivo)."""
    if not path or not os.path.isfile(path):
        return (
            '<div style="margin:4px;padding:12px;background:#fef2f2;border:1px dashed #fca5a5;'
            'text-align:center;font-size:7.5pt;color:#991b1b;">Gr&aacute;fico no disponible</div>'
        )
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
    except OSError:
        return ""
    margin = "2px 2px 4px" if compact else "4px 4px 8px"
    cap_size = "6.5pt" if compact else "7.5pt"
    cap = (
        f'<div class="chart-caption" style="font-size:{cap_size};color:#475569;margin-top:2px;">'
        f"{caption}</div>"
        if caption else ""
    )
    return f"""
    <div class="chart-box" style="margin:{margin};text-align:center;">
      <img src="data:image/png;base64,{b64}" alt="{caption}"
           style="width:100%;max-height:{max_height}px;object-fit:contain;">
      {cap}
    </div>
    """


def embed_chart(
    chart_paths: Optional[Dict[str, str]],
    key: str,
    caption: str = "",
    *,
    max_height: int = 480,
    compact: bool = False,
) -> str:
    if not chart_paths:
        return embed_chart_path(None, caption, max_height=max_height, compact=compact)
    return embed_chart_path(
        chart_paths.get(key),
        caption or key,
        max_height=max_height,
        compact=compact,
    )


def _gauge_grid(
    batch: Sequence[ChartSpec],
    chart_paths: Optional[Dict[str, str]],
) -> str:
    """Rejilla 2×2 de gauges compactos."""
    cells: List[str] = []
    for key, caption in batch:
        img = embed_chart(
            chart_paths, key, caption, max_height=175, compact=True,
        )
        cells.append(
            f'<td width="50%" style="padding:2px;vertical-align:top;">{img}</td>'
        )
    while len(cells) < 4:
        cells.append('<td width="50%" style="padding:2px;"></td>')

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:2px 0 4px;">
      <tr>{cells[0]}{cells[1]}</tr>
      <tr>{cells[2]}{cells[3]}</tr>
    </table>
    """


def _large_chart_block(
    key: str,
    caption: str,
    chart_paths: Optional[Dict[str, str]],
    fecha_corte: str = "",
) -> str:
    return (
        f'{subsection_hdr(caption, fecha_corte, compact=True)}'
        f'{embed_chart(chart_paths, key, caption, max_height=500)}'
    )


def chart_pages(
    logo_b64: str,
    fecha_label: str,
    specs: Sequence[ChartSpec],
    chart_paths: Optional[Dict[str, str]],
    intro_html: str = "",
) -> str:
    """
    Layout compacto:
    - KPIs + cover van en la misma página que el primer bloque de gráficos.
    - Gauges agrupados 2×2 por página.
    - Gráficas grandes ocupan el ancho disponible con márgenes mínimos.
    """
    gauges = [(k, c) for k, c in specs if _is_gauge(k)]
    large = [(k, c) for k, c in specs if not _is_gauge(k)]

    pages: List[str] = []
    pending_intro = intro_html

    for i in range(0, len(gauges), GAUGES_PER_PAGE):
        batch = gauges[i : i + GAUGES_PER_PAGE]
        body = pending_intro
        pending_intro = ""
        body += _gauge_grid(batch, chart_paths)
        pages.append(wrap_chapter_page(logo_b64, fecha_label, body))

    for key, caption in large:
        body = pending_intro
        pending_intro = ""
        body += _large_chart_block(key, caption, chart_paths)
        pages.append(wrap_chapter_page(logo_b64, fecha_label, body))

    if pending_intro and not pages:
        pages.append(wrap_chapter_page(logo_b64, fecha_label, pending_intro))

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
