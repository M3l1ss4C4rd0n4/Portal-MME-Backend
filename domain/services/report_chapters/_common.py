"""Helpers compartidos para capítulos del informe PDF."""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from domain.services.report_service import (
    _build_header_html,
    _fecha_corte_html,
    _strip_emojis,
)

ChartSpec = Tuple[str, str]  # (chart_key, caption)

KPI_BG = "#254553"
KPI_ACCENT = "#287270"
GAUGES_PER_PAGE = 4
LARGE_CHARTS_PER_PAGE = 2

# Altura útil del cuerpo en hoja Letter (px aprox.) tras header del informe
PAGE_USABLE_PX = 710
INTRO_WITH_KPI_PX = 168
INTRO_COVER_ONLY_PX = 58
MINI_HDR_PX = 22


def chapter_cover(num: int, title: str, subtitle: str = "") -> str:
    sub = (
        f'<div style="font-size:9pt;color:#cbd5e1;margin-top:3px;">{subtitle}</div>'
        if subtitle else ""
    )
    return f"""
    <div style="background:{KPI_BG};color:#fff;padding:8px 14px;margin:0 0 4px 0;border-radius:4px;">
      <div style="font-size:7.5pt;opacity:0.85;letter-spacing:1px;">CAP&Iacute;TULO {num}</div>
      <div style="font-size:13pt;font-weight:bold;margin-top:2px;">{title}</div>
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


def _intro_overhead(intro_html: str) -> int:
    if not intro_html:
        return 0
    if "min-height:105px" in intro_html or "kpi-label" in intro_html.lower():
        return INTRO_WITH_KPI_PX
    return INTRO_COVER_ONLY_PX


def _mini_hdr(title: str) -> str:
    return (
        f'<div style="background:#287270;color:#fff;font-size:7.5pt;font-weight:bold;'
        f'padding:3px 8px;margin:0 0 1px 0;line-height:1.2;">{title}</div>'
    )


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
    """Fila de KPIs — ocupa ancho completo con tarjetas altas."""
    if not kpis:
        return ""
    cells = ""
    subset = kpis[:max_items]
    width = 100 // max(len(subset), 1)
    for k in subset:
        label = _strip_emojis(str(k.get("label", "")))
        val_str = _format_kpi_value(k)
        cells += f"""
        <td style="width:{width}%;padding:3px;vertical-align:stretch;">
          <div style="background:{KPI_BG};border-left:5px solid {KPI_ACCENT};border-radius:4px;
                      padding:16px 18px;min-height:105px;height:100%;box-sizing:border-box;">
            <div style="font-size:9.5pt;font-weight:bold;color:#e2e8f0;
                        text-transform:uppercase;letter-spacing:0.4px;">{label}</div>
            <div style="font-size:24pt;font-weight:bold;color:#fff;margin-top:10px;line-height:1.05;">
              {val_str}</div>
          </div>
        </td>
        """
    fc = _parse_fecha_corte(fecha_corte)
    fc_row = (
        f'<tr><td colspan="{len(subset)}" style="padding:3px 6px 0;">{fc}</td></tr>'
        if fc else ""
    )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="3" '
        f'style="margin:0 0 6px 0;"><tr>{cells}</tr>{fc_row}</table>'
    )


def _is_gauge(key: str) -> bool:
    return "_gauge_" in key or key.endswith("_gauge")


def embed_chart_path(
    path: Optional[str],
    caption: str = "",
    *,
    height: int = 480,
    show_caption: bool = False,
) -> str:
    if not path or not os.path.isfile(path):
        return (
            '<div style="margin:2px;padding:10px;background:#fef2f2;border:1px dashed #fca5a5;'
            'text-align:center;font-size:7pt;color:#991b1b;">Gr&aacute;fico no disponible</div>'
        )
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
    except OSError:
        return ""
    cap = (
        f'<div style="font-size:6.5pt;color:#64748b;margin-top:1px;text-align:center;">{caption}</div>'
        if show_caption and caption else ""
    )
    return f"""
    <div style="margin:0;text-align:center;line-height:0;">
      <img src="data:image/png;base64,{b64}" alt="{caption}"
           style="width:100%;height:{height}px;max-height:{height}px;object-fit:contain;display:block;">
      {cap}
    </div>
    """


def embed_chart(
    chart_paths: Optional[Dict[str, str]],
    key: str,
    caption: str = "",
    *,
    height: int = 480,
    show_caption: bool = False,
) -> str:
    if not chart_paths:
        return embed_chart_path(None, caption, height=height, show_caption=show_caption)
    return embed_chart_path(
        chart_paths.get(key),
        caption or key,
        height=height,
        show_caption=show_caption,
    )


def _gauge_cell(
    chart_paths: Optional[Dict[str, str]],
    key: str,
    caption: str,
    height: int,
    colspan: int = 1,
) -> str:
    block = _mini_hdr(caption) + embed_chart(
        chart_paths, key, caption, height=height - MINI_HDR_PX,
    )
    cs = f' colspan="{colspan}"' if colspan > 1 else ""
    w = "100%" if colspan > 1 else "50%"
    return f'<td width="{w}" style="padding:2px;vertical-align:top;"{cs}>{block}</td>'


def _gauge_grid(
    batch: Sequence[ChartSpec],
    chart_paths: Optional[Dict[str, str]],
    *,
    intro_html: str = "",
) -> str:
    """Gauges agrupados — altura calculada para llenar la hoja."""
    n = len(batch)
    if n == 0:
        return ""
    overhead = _intro_overhead(intro_html)
    avail = PAGE_USABLE_PX - overhead

    if n == 1:
        h = avail - 4
        return (
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{_gauge_cell(chart_paths, batch[0][0], batch[0][1], h, colspan=2)}</tr></table>'
        )

    if n == 2:
        h = avail - 4
        c0 = _gauge_cell(chart_paths, batch[0][0], batch[0][1], h)
        c1 = _gauge_cell(chart_paths, batch[1][0], batch[1][1], h)
        return f'<table width="100%" cellpadding="0" cellspacing="0"><tr>{c0}{c1}</tr></table>'

    if n == 3:
        h_top = int(avail * 0.47)
        h_bot = avail - h_top - 4
        c0 = _gauge_cell(chart_paths, batch[0][0], batch[0][1], h_top)
        c1 = _gauge_cell(chart_paths, batch[1][0], batch[1][1], h_top)
        c2 = _gauge_cell(chart_paths, batch[2][0], batch[2][1], h_bot, colspan=2)
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>{c0}{c1}</tr>
          <tr>{c2}</tr>
        </table>
        """

    h_row = (avail - 4) // 2
    cells = [
        _gauge_cell(chart_paths, key, caption, h_row)
        for key, caption in batch[:4]
    ]
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>{cells[0]}{cells[1]}</tr>
      <tr>{cells[2]}{cells[3]}</tr>
    </table>
    """


def _large_chart_block(
    key: str,
    caption: str,
    chart_paths: Optional[Dict[str, str]],
    img_h: int,
) -> str:
    return (
        f'{_mini_hdr(caption)}'
        f'{embed_chart(chart_paths, key, caption, height=img_h)}'
    )


def _large_charts_batch(
    batch: Sequence[ChartSpec],
    chart_paths: Optional[Dict[str, str]],
    *,
    intro_html: str = "",
) -> str:
    """Dos gráficas grandes apiladas (ancho completo); una sola ocupa toda la hoja."""
    overhead = _intro_overhead(intro_html)
    avail = PAGE_USABLE_PX - overhead
    gap = 3

    if len(batch) == 1:
        key, caption = batch[0]
        return _large_chart_block(key, caption, chart_paths, avail - MINI_HDR_PX)

    per_chart = (avail - 2 * MINI_HDR_PX - gap) // 2
    key0, cap0 = batch[0]
    key1, cap1 = batch[1]
    return (
        f'<div style="margin:0 0 {gap}px 0;">'
        f'{_large_chart_block(key0, cap0, chart_paths, per_chart)}'
        f"</div>"
        f"{_large_chart_block(key1, cap1, chart_paths, per_chart)}"
    )


def chart_pages(
    logo_b64: str,
    fecha_label: str,
    specs: Sequence[ChartSpec],
    chart_paths: Optional[Dict[str, str]],
    intro_html: str = "",
) -> str:
    """
    Layout optimizado:
    - Cover + KPIs en la misma hoja que el primer bloque visual.
    - Gauges agrupados (2×2 o 2+1) llenando altura disponible.
    - Gráficas grandes: 2 por hoja apiladas a ancho completo.
    """
    gauges = [(k, c) for k, c in specs if _is_gauge(k)]
    large = [(k, c) for k, c in specs if not _is_gauge(k)]

    pages: List[str] = []
    pending_intro = intro_html

    for i in range(0, len(gauges), GAUGES_PER_PAGE):
        batch = gauges[i : i + GAUGES_PER_PAGE]
        body = pending_intro
        pending_intro = ""
        body += _gauge_grid(batch, chart_paths, intro_html=body)
        pages.append(wrap_chapter_page(logo_b64, fecha_label, body))

    for i in range(0, len(large), LARGE_CHARTS_PER_PAGE):
        batch = large[i : i + LARGE_CHARTS_PER_PAGE]
        body = pending_intro
        pending_intro = ""
        body += _large_charts_batch(batch, chart_paths, intro_html=body)
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
