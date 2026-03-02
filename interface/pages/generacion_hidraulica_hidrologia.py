"""
Hidrología — Thin wrapper para Dash Pages
===========================================

Este archivo existe para que Dash Pages auto-descubra la página
de hidrología via register_page(). Toda la lógica se encuentra
en el paquete ``interface.pages.hidrologia``.

Refactorizado desde el monolito original de 7,318 líneas.
"""

from dash import register_page

# --- Registrar la página para Dash Pages auto-discovery ---
register_page(
    __name__,
    path="/generacion/hidraulica/hidrologia",
    name="Hidrología",
    title="Hidrología - Ministerio de Minas y Energía de Colombia",
    order=6
)

# --- Importar layout desde el paquete modular ---
from interface.pages.hidrologia.layout_def import layout  # noqa: F401, E402

# --- Importar callbacks (se registran automáticamente al importarse) ---
import interface.pages.hidrologia.callbacks  # noqa: F401, E402
