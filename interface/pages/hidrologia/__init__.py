"""
Módulo de Hidrología - Portal Energético MME
=============================================

Paquete modular refactorizado desde el archivo monolítico original
de 7,318 líneas.

Organización:
- utils.py: Funciones auxiliares, formateo, caché GeoJSON
- data_services.py: Servicios de obtención de datos XM
- tables.py: Componentes de tablas Dash
- charts.py: Gráficos y visualizaciones Plotly
- maps.py: Mapas geográficos de Colombia
- kpis.py: KPIs y fichas informativas
- callbacks.py: Callbacks de interactividad Dash
- layout_def.py: Layout principal del dashboard
"""

__version__ = "2.0.0"
__author__ = "Equipo Portal Energético MME"

# Re-export layout for the thin wrapper
from .layout_def import layout
