"""Capítulo 3 — Subsidios energéticos (gráficos del tablero)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from domain.services.report_chapters._common import chapter_cover, chart_pages, kpi_row


def build_chapter_subsidios(
    logo_b64: str,
    fecha_label: str,
    data: Dict[str, Any],
    chart_paths: Optional[Dict[str, str]] = None,
) -> str:
    pagos = data.get("pagos") or {}
    deficit = data.get("deficit_historico") or []
    ult = deficit[-1] if deficit else {}

    intro_def = (
        chapter_cover(3, "Subsidios — D&eacute;ficit Hist&oacute;rico", "Tablero FSSRI / FOES")
        + kpi_row([
            {"label": "Último año", "valor": ult.get("anio", "N/D"), "unidad": ""},
            {"label": "Déficit acumulado", "valor": f'${ult.get("deficit_acumulado", 0)/1e9:.1f} mil M' if ult else "N/D", "unidad": ""},
        ])
    )
    specs_def = [
        ("sub_subsidios_contrib", "Subsidios (SIN+ZNI) y Contribuciones por año"),
        ("sub_deficit_combo", "Déficit acumulado + Déficit anual + Apropiación PGN"),
        ("sub_apropiacion", "Apropiación PGN y déficit acumulado A-1"),
    ]
    pages = chart_pages(logo_b64, fecha_label, specs_def, chart_paths, intro_def)

    intro_pagos = (
        chapter_cover(3, "Subsidios — Detalle de Pagos", "Tablero pagos FSSRI / FOES")
        + kpi_row([
            {"label": "% pagado", "valor": pagos.get("pct_pagado", 0), "unidad": "%"},
            {"label": "Pendiente", "valor": f'${pagos.get("pendiente", 0)/1e9:.2f} mil M', "unidad": ""},
        ], pagos.get("fecha_corte", ""))
    )
    specs_pagos = [
        ("sub_gauge_pagado", "Porcentaje pagado sobre comprometido"),
        ("sub_trimestres", "Valores pagados y pendientes por trimestre"),
        ("sub_prestadores", "Prestadores con mayor saldo pendiente"),
    ]
    pages += chart_pages(logo_b64, fecha_label, specs_pagos, chart_paths, intro_pagos)

    val = data.get("validaciones") or {}
    intro_val = chapter_cover(3, "Subsidios — Validaciones", "Tablero validaciones SIN / ZNI")
    specs_val = [
        ("sub_valid_sin", "SIN — Validaciones por trimestre (VF / VP / VI)"),
        ("sub_valid_zni", "ZNI — Validaciones por trimestre (VF / VP / VI)"),
    ]
    pages += chart_pages(logo_b64, fecha_label, specs_val, chart_paths, intro_val)
    return pages
