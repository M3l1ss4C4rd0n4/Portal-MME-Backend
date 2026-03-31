"""
Componente Chart Card con header y controles opcionales.

Uso:
    from interface.components.data_display.chart_card import chart_card
    import plotly.express as px
    
    fig = px.line(df, x="fecha", y="generacion")
    
    chart = chart_card(
        title="Generación por Fuente",
        figure=fig,
        id="grafica-generacion",
        subtitle="Últimos 30 días",
        download_button=True,
        height=400
    )
"""
from dash import html, dcc
import dash_bootstrap_components as dbc
from typing import Optional, List, Dict, Any, Union
import plotly.graph_objects as go


def chart_card(
    title: str,
    figure: go.Figure,
    id: str,
    subtitle: Optional[str] = None,
    controls: Optional[List[Any]] = None,
    download_button: bool = False,
    height: int = 350,
    className: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> dbc.Card:
    """
    Crea una tarjeta de gráfica consistente.
    
    Args:
        title: Título de la gráfica
        figure: Figura de Plotly
        id: ID base para el componente (usado para el gráfico)
        subtitle: Subtítulo opcional debajo del título
        controls: Lista de controles adicionales (botones, dropdowns, etc.)
        download_button: Mostrar botón de descarga PNG
        height: Altura de la gráfica en píxeles
        className: Clases CSS adicionales
        config: Configuración adicional de Plotly
    
    Returns:
        dbc.Card con la gráfica
    
    Ejemplo:
        chart_card(
            title="Generación por Fuente",
            figure=fig,
            id="grafica-temporal",
            subtitle="Período: 01/01/2024 - 31/01/2024",
            download_button=True,
            height=400
        )
    """
    
    # Configuración por defecto de Plotly
    default_config = {
        'displayModeBar': False,
        'responsive': True,
    }
    
    if download_button:
        default_config['displayModeBar'] = True
        default_config['modeBarButtonsToRemove'] = [
            'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d',
            'autoScale2d', 'resetScale2d', 'hoverClosestCartesian',
            'hoverCompareCartesian', 'toggleSpikelines'
        ]
        default_config['displaylogo'] = False
    
    # Merge con config personalizado
    final_config = {**default_config, **(config or {})}
    
    # Header con título y controles
    header_children = [
        html.Div(
            [
                html.H5(title, className="chart-title mb-0"),
                html.Small(
                    subtitle,
                    className="chart-subtitle d-block mt-1"
                ) if subtitle else None,
            ]
        )
    ]
    
    # Agregar controles si existen
    if controls:
        header_children.append(
            html.Div(controls, className="chart-controls d-flex gap-2")
        )
    
    # Botón de descarga
    if download_button:
        header_children.append(
            html.Button(
                html.I(className="fas fa-download"),
                className="btn btn-sm btn-outline-secondary",
                id=f"{id}-download-btn",
                title="Descargar gráfica"
            )
        )
    
    return dbc.Card(
        className=f"chart-card {className}",
        children=[
            dbc.CardHeader(
                header_children,
                className="chart-header d-flex justify-content-between align-items-center flex-wrap gap-2"
            ),
            dbc.CardBody(
                dcc.Graph(
                    id=id,
                    figure=figure,
                    config=final_config,
                    style={'height': f'{height}px'},
                    className="chart-graph"
                ),
                className="chart-body p-0"
            ),
        ]
    )


def chart_card_loading(
    title: str = "Cargando...",
    id: Optional[str] = None,
    height: int = 350,
) -> dbc.Card:
    """
    Crea una tarjeta de gráfica en estado de carga.
    
    Args:
        title: Título temporal
        id: ID opcional
        height: Altura del skeleton
    
    Returns:
        dbc.Card con skeleton
    """
    return dbc.Card(
        className="chart-card",
        id=id,
        children=[
            dbc.CardHeader(
                html.H5(title, className="chart-title mb-0"),
                className="chart-header"
            ),
            dbc.CardBody(
                html.Div(
                    className="skeleton skeleton-chart",
                    style={'height': f'{height - 60}px'}
                ),
                className="chart-body p-3"
            ),
        ]
    )


def chart_card_error(
    title: str = "Error al cargar gráfica",
    message: str = "No se pudieron obtener los datos. Intente nuevamente.",
    id: Optional[str] = None,
    on_retry: Optional[str] = None,
) -> dbc.Card:
    """
    Crea una tarjeta de gráfica para mostrar errores.
    
    Args:
        title: Título del error
        message: Mensaje descriptivo
        id: ID opcional
        on_retry: ID del callback para reintentar (opcional)
    
    Returns:
        dbc.Card con estado de error
    """
    body_content = [
        html.I(className="fas fa-exclamation-circle fa-3x text-danger mb-3"),
        html.H5(title, className="text-danger"),
        html.P(message, className="text-muted"),
    ]
    
    if on_retry:
        body_content.append(
            html.Button(
                [html.I(className="fas fa-redo mr-2"), "Reintentar"],
                className="btn btn-primary mt-3",
                id=on_retry
            )
        )
    
    return dbc.Card(
        className="chart-card",
        id=id,
        children=[
            dbc.CardBody(
                html.Div(
                    body_content,
                    className="text-center py-5"
                )
            ),
        ]
    )


def chart_card_empty(
    title: str = "Sin datos disponibles",
    message: str = "No hay datos para el período seleccionado.",
    icon: str = "fas fa-inbox",
    id: Optional[str] = None,
) -> dbc.Card:
    """
    Crea una tarjeta de gráfica vacía.
    
    Args:
        title: Título
        message: Mensaje informativo
        icon: Icono FontAwesome
        id: ID opcional
    
    Returns:
        dbc.Card con estado vacío
    """
    return dbc.Card(
        className="chart-card",
        id=id,
        children=[
            dbc.CardBody(
                html.Div(
                    [
                        html.I(className=f"{icon} fa-3x text-muted mb-3"),
                        html.H5(title, className="text-muted"),
                        html.P(message, className="text-muted small"),
                    ],
                    className="text-center py-5"
                )
            ),
        ]
    )
