"""Capítulo 2 — Comunidades energéticas (gráficos del tablero)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from domain.services.report_chapters._common import (
    chapter_cover,
    chart_pages,
    kpi_row,
)

COM_CHARTS = [
    ("com_mapa", "Comunidades implementadas — Mapa por departamento"),
    ("com_barras_ces", "CEs y capacidad (kWp) por departamento — Top 12"),
    ("com_inversion", "Inversión estimada por departamento — Top 12"),
]


def build_chapter_comunidades(
    logo_b64: str,
    fecha_label: str,
    data: Dict[str, Any],
    chart_paths: Optional[Dict[str, str]] = None,
) -> str:
    intro = (
        chapter_cover(2, "Comunidades Energ&eacute;ticas", "Tablero implementadas — r&eacute;plica visual del portal")
        + kpi_row(data.get("kpis") or [], data.get("fecha_corte", ""))
    )
    return chart_pages(logo_b64, fecha_label, COM_CHARTS, chart_paths, intro)


def build_chapter_contratos_or(
    logo_b64: str,
    fecha_label: str,
    data: Dict[str, Any],
    chart_paths: Optional[Dict[str, str]] = None,
) -> str:
    kpis = [
        {"label": "Contratos", "valor": data.get("n_contratos", 0), "unidad": ""},
        {"label": "Avance general", "valor": data.get("avance_general", 0), "unidad": "%"},
        {"label": "Avance financiero", "valor": data.get("avance_financiero", 0), "unidad": "%"},
    ]
    intro = (
        chapter_cover(2, "Contratos OR", "Seguimiento desembolsos comunidades energ&eacute;ticas")
        + kpi_row(kpis, data.get("fecha_corte", ""))
    )
    specs = [
        ("or_gauge_fin", "Avance Financiero — Portafolio OR"),
        ("or_gauge_gen", "Avance General — Portafolio OR"),
        ("or_gauge_fis", "Avance F&iacute;sico — Actividades OR"),
        ("or_proyectos", "Avance por proyecto — General vs Financiero"),
    ]
    return chart_pages(logo_b64, fecha_label, specs, chart_paths, intro)


def build_chapter_fenoge(
    logo_b64: str,
    fecha_label: str,
    data: Dict[str, Any],
    chart_paths: Optional[Dict[str, str]] = None,
) -> str:
    intro = (
        chapter_cover(2, "Fenoge 1.0 / 1.1", "Programa Fenoge — comunidades energ&eacute;ticas")
        + kpi_row(data.get("kpis") or [], data.get("fecha_corte", ""))
    )
    specs = [
        ("fen_deptos", "CEs y capacidad por departamento"),
        ("fen_inversion", "Inversi&oacute;n por departamento"),
        ("fen_seguimiento", "Avance de obra acumulado — Real vs Programado"),
    ]
    return chart_pages(logo_b64, fecha_label, specs, chart_paths, intro)


def build_chapter_colombia_solar(
    logo_b64: str,
    fecha_label: str,
    chart_paths: Optional[Dict[str, str]] = None,
) -> str:
    intro = chapter_cover(2, "Colombia Solar", "Curvas S — programaci&oacute;n vs avance reportado (OR)")
    specs = [
        ("curva_obras", "Curva S — Obras Civiles"),
        ("curva_usuarios", "Curva S — Usuarios"),
        ("curva_potencia", "Curva S — Potencia"),
        ("curva_internas", "Curva S — Internas"),
    ]
    return chart_pages(logo_b64, fecha_label, specs, chart_paths, intro)
