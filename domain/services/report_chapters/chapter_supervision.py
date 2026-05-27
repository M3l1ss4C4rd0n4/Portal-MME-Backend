"""Capítulo 4 — Supervisión de contratos (gráficos del tablero)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from domain.services.report_chapters._common import chapter_cover, chart_pages, kpi_row


def build_chapter_supervision(
    logo_b64: str,
    fecha_label: str,
    data: Dict[str, Any],
    chart_paths: Optional[Dict[str, str]] = None,
) -> str:
    intro = (
        chapter_cover(4, "Supervisi&oacute;n de Contratos", "Tablero supervisi&oacute;n MinMinas")
        + kpi_row([
            {"label": "Contratos", "valor": data.get("n_contratos", 0), "unidad": ""},
            {"label": "Usuarios contratados", "valor": data.get("usuarios", 0), "unidad": ""},
        ], data.get("fecha_corte", ""))
    )
    specs = [
        ("sup_gauge_pf", "Avance físico — Portafolio"),
        ("sup_gauge_pfin", "Avance financiero — Portafolio"),
        ("sup_gauge_ef", "Avance físico — En ejecución"),
        ("sup_gauge_efin", "Avance financiero — En ejecución"),
        ("sup_pie_fondos", "Contratos por fondo"),
        ("sup_evolucion", "Evolución avance de obra promedio por año"),
        ("sup_fondo_estado", "Flujo de contratos — Fondo × Estado"),
    ]
    return chart_pages(logo_b64, fecha_label, specs, chart_paths, intro)
