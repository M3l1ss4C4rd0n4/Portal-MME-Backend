"""Capítulo 1 — bloque de riesgos e índices (extraído de la antigua página de noticias)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain.services.report_service import _build_page_noticias


def build_chapter_gestion_riesgos(
    logo_b64: str,
    fecha_label: str,
    anomalias: List[Dict[str, Any]],
    indices_compuestos: Optional[Dict[str, Any]] = None,
) -> str:
    """Página de cierre del Cap. 1: índices ISH/IPM/IES/CIS + anomalías."""
    return _build_page_noticias(
        logo_b64,
        fecha_label,
        anomalias or [],
        [],
        indices_compuestos=indices_compuestos,
        include_noticias=False,
        include_canales=False,
    )
