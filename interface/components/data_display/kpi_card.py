"""
Componente KPI Card reutilizable con múltiples variantes.

Uso:
    from interface.components.data_display.kpi_card import kpi_card, kpi_row
    
    # KPI individual
    kpi = kpi_card(
        title="Generación Total",
        value="7464.0",
        unit="GWh",
        icon="fas fa-bolt",
        color="blue",
        subtitle="16/02/2026 - 18/03/2026"
    )
    
    # Fila de KPIs
    row = kpi_row([
        {"title": "Total", "value": "7464.0", "unit": "GWh", "icon": "fas fa-bolt", "color": "blue"},
        {"title": "Renovable", "value": "6648.6", "unit": "GWh", "icon": "fas fa-leaf", "color": "green"},
        {"title": "No Renovable", "value": "815.4", "unit": "GWh", "icon": "fas fa-industry", "color": "red"},
    ])
"""
from dash import html
import dash_bootstrap_components as dbc
from typing import Optional, Literal, List, Dict, Any


def kpi_card(
    title: str,
    value: str,
    unit: str = "",
    icon: str = "fas fa-chart-line",
    color: Literal["blue", "green", "orange", "red", "purple", "cyan", "gray"] = "blue",
    subtitle: Optional[str] = None,
    trend: Optional[str] = None,
    trend_direction: Literal["up", "down", "flat"] = "flat",
    id: Optional[str] = None,
    className: str = "",
) -> html.Div:
    """
    Crea una tarjeta KPI con estilo consistente.
    
    Args:
        title: Título de la métrica (ej: "Generación Total")
        value: Valor numérico formateado (ej: "7464.0")
        unit: Unidad de medida (ej: "GWh", "%")
        icon: Clase FontAwesome (ej: "fas fa-bolt")
        color: Color del tema (blue, green, orange, red, purple, cyan, gray)
        subtitle: Texto secundario (ej: rango de fechas)
        trend: Cambio porcentual (ej: "+5.2%")
        trend_direction: Dirección del trend (up, down, flat)
        id: ID opcional para callbacks
        className: Clases CSS adicionales
    
    Returns:
        html.Div con la tarjeta KPI
    """
    
    # Componente de tendencia
    trend_component = None
    if trend:
        arrow = {"up": "▲", "down": "▼", "flat": "—"}[trend_direction]
        trend_component = html.Span(
            f"{arrow} {trend}",
            className=f"kpi-trend {trend_direction}"
        )
    
    # Subtítulo
    subtitle_component = None
    if subtitle:
        subtitle_component = html.Div(
            subtitle,
            className="kpi-subtext"
        )
    
    return html.Div(
        className=f"kpi-card {className}",
        id=id,
        children=[
            # Icono
            html.Div(
                html.I(className=icon),
                className=f"kpi-icon {color}"
            ),
            
            # Contenido
            html.Div(
                className="kpi-content",
                children=[
                    html.Div(title, className="kpi-label"),
                    html.Div(
                        className="kpi-value-wrapper",
                        children=[
                            html.Span(value, className="kpi-value"),
                            html.Span(unit, className="kpi-unit") if unit else None,
                            trend_component,
                        ]
                    ),
                    subtitle_component,
                ]
            ),
        ]
    )


def kpi_row(
    kpis: List[Dict[str, Any]],
    columns: int = 4,
    className: str = "",
) -> dbc.Row:
    """
    Crea una fila de KPIs responsive.
    
    Args:
        kpis: Lista de diccionarios con props de kpi_card
              Cada dict debe tener: title, value, y opcionalmente:
              unit, icon, color, subtitle, trend, trend_direction
        columns: Número de columnas (1-4). Default 4 para "Último día disponible"
        className: Clases CSS adicionales
    
    Returns:
        dbc.Row con los KPIs
    
    Ejemplo:
        kpi_row([
            {
                "title": "Generación Total SIN",
                "value": "7464.0",
                "unit": "GWh",
                "icon": "fas fa-bolt",
                "color": "blue",
                "subtitle": "16/02/2026 - 18/03/2026"
            },
            {
                "title": "Renovable",
                "value": "6648.6",
                "unit": "GWh",
                "icon": "fas fa-leaf",
                "color": "green",
                "subtitle": "89.1% del total"
            },
            {
                "title": "No Renovable",
                "value": "815.4",
                "unit": "GWh",
                "icon": "fas fa-industry",
                "color": "red",
                "subtitle": "10.9% del total"
            },
            {
                "title": "Último Día Disponible",
                "value": "247.6",
                "unit": "GWh",
                "icon": "fas fa-calendar-day",
                "color": "purple",
                "subtitle": "18/03/2026"
            },
        ])
    """
    # Validar número de columnas
    if columns < 1 or columns > 4:
        columns = 4
    
    # Calcular ancho de columna para Bootstrap
    width_mapping = {1: 12, 2: 6, 3: 4, 4: 3}
    width = width_mapping.get(columns, 3)
    
    return dbc.Row(
        [
            dbc.Col(
                kpi_card(**kpi_props),
                xs=12,      # Móvil: 1 por fila
                sm=6,       # Tablet pequeña: 2 por fila
                md=width,   # Desktop: según configuración
                className="mb-3"
            )
            for kpi_props in kpis
        ],
        className=f"kpi-row {className}"
    )


def kpi_loading_card(id: Optional[str] = None) -> html.Div:
    """
    Crea un KPI card en estado de carga (skeleton).
    
    Args:
        id: ID opcional
    
    Returns:
        html.Div con skeleton de KPI
    """
    return html.Div(
        className="kpi-card skeleton-card",
        id=id,
        children=[
            html.Div(className="skeleton skeleton-icon"),
            html.Div(
                className="skeleton-content",
                children=[
                    html.Div(className="skeleton skeleton-line w-50"),
                    html.Div(className="skeleton skeleton-line w-75"),
                ]
            ),
        ]
    )


def kpi_error_card(
    title: str = "Error al cargar",
    message: str = "No se pudieron obtener los datos",
    id: Optional[str] = None,
) -> html.Div:
    """
    Crea un KPI card para mostrar errores.
    
    Args:
        title: Título del error
        message: Mensaje descriptivo
        id: ID opcional
    
    Returns:
        html.Div con estado de error
    """
    return html.Div(
        className="kpi-card",
        id=id,
        style={"borderLeft": "4px solid #ef4444"},
        children=[
            html.Div(
                html.I(className="fas fa-exclamation-triangle"),
                className="kpi-icon red"
            ),
            html.Div(
                className="kpi-content",
                children=[
                    html.Div(title, className="kpi-label"),
                    html.Div(
                        message,
                        style={"fontSize": "11px", "color": "#6b7280", "marginTop": "4px"}
                    ),
                ]
            ),
        ]
    )
