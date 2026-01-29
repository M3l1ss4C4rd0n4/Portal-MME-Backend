"""
Shim de compatibilidad para página piloto
Mantiene auto-discovery de Dash en /pages
"""

from dash import register_page
from presentation.pages.metricas_piloto import layout  # noqa: F401

register_page(
    __name__,
    path="/metricas-piloto",
    name="Métricas (Piloto)",
    title="Métricas Piloto",
    description="Página piloto con nueva arquitectura",
)
