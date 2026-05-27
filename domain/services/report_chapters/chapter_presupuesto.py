"""Capítulo 5 — Ejecución presupuestal DEE (gráficos del tablero)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from domain.services.report_chapters._common import chapter_cover, chart_pages, kpi_row


def build_chapter_presupuesto(
    logo_b64: str,
    fecha_label: str,
    data: Dict[str, Any],
    chart_paths: Optional[Dict[str, str]] = None,
) -> str:
    tot = data.get("totales") or {}
    intro = (
        chapter_cover(5, "Ejecuci&oacute;n Presupuestal DEE", "Tablero presupuesto — Direcci&oacute;n EE")
        + kpi_row([
            {"label": "Apropiación", "valor": f'${tot.get("apropiacion", 0)/1e9:.1f} mil M', "unidad": ""},
            {"label": "% comprometido", "valor": tot.get("pct_comprometido", 0), "unidad": "%"},
            {"label": "% obligado", "valor": tot.get("pct_obligado", 0), "unidad": "%"},
        ], data.get("fecha_corte", ""))
    )
    specs = [
        ("pre_gauge_comp", "Comprometido (% apropiación)"),
        ("pre_gauge_obl", "Obligado (% apropiación)"),
        ("pre_gauge_disp", "Disponible sin comprometer (% apropiación)"),
        ("pre_ejecucion", "Ejecución — Obligado / Comprometido / Disponible"),
        ("pre_proyectos", "Comparativo por proyecto (Top 8)"),
    ]
    return chart_pages(logo_b64, fecha_label, specs, chart_paths, intro)
