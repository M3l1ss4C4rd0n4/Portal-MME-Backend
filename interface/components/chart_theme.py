"""
Chart Theme Helper - Configuración de temas para gráficos Plotly

Este módulo proporciona funciones para aplicar temas consistentes
a los gráficos Plotly, con soporte automático para modo oscuro/claro.
"""

from typing import Optional, Dict, Any
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# Colores para tema claro
LIGHT_THEME = {
    'paper_bgcolor': 'rgba(0,0,0,0)',  # Transparente
    'plot_bgcolor': 'rgba(0,0,0,0)',   # Transparente
    'font_color': '#111827',
    'grid_color': '#e5e7eb',
    'axis_color': '#374151',
    'legend_bgcolor': 'rgba(255,255,255,0.9)',
}

# Colores para tema oscuro
DARK_THEME = {
    'paper_bgcolor': 'rgba(0,0,0,0)',  # Transparente
    'plot_bgcolor': 'rgba(0,0,0,0)',   # Transparente
    'font_color': '#f1f5f9',
    'grid_color': '#334155',
    'axis_color': '#94a3b8',
    'legend_bgcolor': 'rgba(15,23,42,0.9)',
}


def apply_chart_theme(
    fig: go.Figure,
    dark_mode: bool = False,
    custom_layout: Optional[Dict[str, Any]] = None
) -> go.Figure:
    """
    Aplica configuración de tema a un gráfico Plotly.
    
    Args:
        fig: Figura de Plotly a configurar
        dark_mode: Si es True, usa colores de tema oscuro
        custom_layout: Dict opcional con configuraciones adicionales
        
    Returns:
        Figura configurada
        
    Example:
        >>> fig = go.Figure(data=...)
        >>> fig = apply_chart_theme(fig, dark_mode=True)
    """
    theme = DARK_THEME if dark_mode else LIGHT_THEME
    
    layout_updates = {
        'paper_bgcolor': theme['paper_bgcolor'],
        'plot_bgcolor': theme['plot_bgcolor'],
        'font': {'color': theme['font_color'], 'family': 'Inter, sans-serif'},
        'xaxis': {
            'gridcolor': theme['grid_color'],
            'linecolor': theme['axis_color'],
            'tickfont': {'color': theme['axis_color']},
            'title': {'font': {'color': theme['font_color']}},
        },
        'yaxis': {
            'gridcolor': theme['grid_color'],
            'linecolor': theme['axis_color'],
            'tickfont': {'color': theme['axis_color']},
            'title': {'font': {'color': theme['font_color']}},
        },
        'legend': {
            'bgcolor': theme['legend_bgcolor'],
            'font': {'color': theme['font_color']},
        },
    }
    
    if custom_layout:
        layout_updates.update(custom_layout)
    
    fig.update_layout(**layout_updates)
    return fig


def create_themed_figure(
    data: Optional[list] = None,
    dark_mode: bool = False,
    layout: Optional[Dict[str, Any]] = None,
    **kwargs
) -> go.Figure:
    """
    Crea una nueva figura Plotly con tema aplicado.
    
    Args:
        data: Lista de trazas (opcional)
        dark_mode: Si es True, usa tema oscuro
        layout: Configuración de layout adicional
        **kwargs: Argumentos adicionales para go.Figure
        
    Returns:
        Figura configurada
    """
    fig = go.Figure(data=data, **kwargs)
    return apply_chart_theme(fig, dark_mode=dark_mode, custom_layout=layout)


def create_themed_subplots(
    rows: int = 1,
    cols: int = 1,
    dark_mode: bool = False,
    subplot_titles: Optional[list] = None,
    **kwargs
) -> go.Figure:
    """
    Crea subplots con tema aplicado.
    
    Args:
        rows: Número de filas
        cols: Número de columnas
        dark_mode: Si es True, usa tema oscuro
        subplot_titles: Títulos de subplots
        **kwargs: Argumentos adicionales para make_subplots
        
    Returns:
        Figura con subplots configurada
    """
    fig = make_subplots(
        rows=rows,
        cols=cols,
        subplot_titles=subplot_titles,
        **kwargs
    )
    return apply_chart_theme(fig, dark_mode=dark_mode)


def get_theme_colors(dark_mode: bool = False) -> Dict[str, str]:
    """
    Obtiene el diccionario de colores del tema actual.
    
    Args:
        dark_mode: Si es True, devuelve colores de tema oscuro
        
    Returns:
        Dict con colores del tema
    """
    return DARK_THEME if dark_mode else LIGHT_THEME


# Configuración por defecto para dcc.Graph
GRAPH_CONFIG = {
    'displayModeBar': True,
    'displaylogo': False,
    'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
    'responsive': True,
}


def get_graph_config(dark_mode: bool = False) -> Dict[str, Any]:
    """
    Obtiene configuración para componente dcc.Graph.
    
    Args:
        dark_mode: Si es True, ajusta configuración para tema oscuro
        
    Returns:
        Dict con configuración
    """
    config = GRAPH_CONFIG.copy()
    if dark_mode:
        # En modo oscuro, podemos ajustar el color de la barra de herramientas
        config['toImageButtonOptions'] = {
            'format': 'png',
            'filename': 'chart',
            'height': 600,
            'width': 800,
            'scale': 2
        }
    return config
