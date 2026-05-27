"""Capítulo 6 — Noticias del sector (solo 3 ítems)."""
from __future__ import annotations

from typing import Any, Dict, List

from domain.services.report_service import _build_page_noticias


def build_chapter_noticias(
    logo_b64: str,
    fecha_label: str,
    noticias: List[Dict[str, Any]],
) -> str:
    return _build_page_noticias(
        logo_b64,
        fecha_label,
        [],
        (noticias or [])[:3],
        include_riesgos=False,
        include_noticias=True,
        include_canales=True,
        max_noticias=3,
    )
