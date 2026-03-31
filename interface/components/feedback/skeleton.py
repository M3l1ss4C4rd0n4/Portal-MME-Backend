"""
Componentes Skeleton para estados de carga.

Uso:
    from interface.components.feedback.skeleton import (
        skeleton_card, skeleton_chart, skeleton_table, skeleton_kpi
    )
    
    # En un callback de loading:
    return skeleton_chart()
"""
from dash import html
import dash_bootstrap_components as dbc
from typing import Optional


def skeleton_card(
    id: Optional[str] = None,
    className: str = "",
) -> html.Div:
    """
    Skeleton para tarjetas genéricas.
    
    Returns:
        html.Div con skeleton de card
    """
    return html.Div(
        className=f"card skeleton-card {className}",
        id=id,
        style={
            'padding': '16px',
            'border': '1px solid #e5e7eb',
            'borderRadius': '8px',
            'background': 'white',
        },
        children=[
            html.Div(className="skeleton skeleton-line w-50", style={'marginBottom': '12px'}),
            html.Div(className="skeleton skeleton-line w-75", style={'marginBottom': '8px'}),
            html.Div(className="skeleton skeleton-line w-100"),
        ]
    )


def skeleton_kpi(
    id: Optional[str] = None,
    className: str = "",
) -> html.Div:
    """
    Skeleton para KPI cards.
    
    Returns:
        html.Div con skeleton de KPI
    """
    return html.Div(
        className=f"kpi-card skeleton-card {className}",
        id=id,
        children=[
            html.Div(
                className="skeleton skeleton-icon",
                style={'flexShrink': '0'}
            ),
            html.Div(
                className="skeleton-content",
                style={'flex': '1'},
                children=[
                    html.Div(className="skeleton skeleton-line w-50"),
                    html.Div(className="skeleton skeleton-line w-75"),
                ]
            ),
        ]
    )


def skeleton_kpi_row(
    count: int = 4,
    id: Optional[str] = None,
) -> dbc.Row:
    """
    Fila de skeletons para KPIs.
    
    Args:
        count: Número de KPIs skeleton
        id: ID opcional
    
    Returns:
        dbc.Row con skeletons
    """
    return dbc.Row(
        [
            dbc.Col(
                skeleton_kpi(),
                xs=12,
                sm=6,
                md=3,
                className="mb-3"
            )
            for _ in range(count)
        ],
        id=id
    )


def skeleton_chart(
    height: int = 350,
    show_header: bool = True,
    id: Optional[str] = None,
    className: str = "",
) -> html.Div:
    """
    Skeleton para gráficas.
    
    Args:
        height: Altura del skeleton
        show_header: Mostrar header skeleton
        id: ID opcional
        className: Clases adicionales
    
    Returns:
        html.Div con skeleton de chart
    """
    children = []
    
    if show_header:
        children.append(
            html.Div(
                className="skeleton skeleton-header",
                style={'width': '40%', 'marginBottom': '16px'}
            )
        )
    
    children.append(
        html.Div(
            className="skeleton skeleton-body",
            style={'height': f'{height - 60}px'}
        )
    )
    
    return html.Div(
        className=f"card chart-card {className}",
        id=id,
        style={
            'padding': '16px',
            'border': '1px solid #e5e7eb',
        },
        children=children
    )


def skeleton_table(
    rows: int = 5,
    show_header: bool = True,
    id: Optional[str] = None,
    className: str = "",
) -> html.Div:
    """
    Skeleton para tablas.
    
    Args:
        rows: Número de filas skeleton
        show_header: Mostrar header
        id: ID opcional
        className: Clases adicionales
    
    Returns:
        html.Div con skeleton de tabla
    """
    return html.Div(
        className=f"table-container {className}",
        id=id,
        children=[
            html.Div(
                className="skeleton skeleton-row header" if show_header else "",
                style={'height': '36px', 'background': '#f3f4f6'} if show_header else {}
            ) if show_header else None,
            *[
                html.Div(
                    className="skeleton skeleton-row",
                    style={
                        'height': '36px',
                        'marginBottom': '4px',
                        'borderBottom': '1px solid #f3f4f6'
                    }
                )
                for _ in range(rows)
            ]
        ]
    )


def skeleton_page(
    kpi_count: int = 4,
    chart_count: int = 2,
    table_count: int = 1,
    id: Optional[str] = None,
) -> html.Div:
    """
    Layout completo de skeleton para una página.
    
    Args:
        kpi_count: Número de KPIs
        chart_count: Número de charts
        table_count: Número de tablas
        id: ID opcional
    
    Returns:
        html.Div con layout completo de skeletons
    """
    children = []
    
    # Fila de KPIs
    if kpi_count > 0:
        children.append(skeleton_kpi_row(count=kpi_count))
    
    # Charts
    for i in range(chart_count):
        children.append(
            html.Div(skeleton_chart(), className="mb-4")
        )
    
    # Tablas
    for i in range(table_count):
        children.append(
            html.Div(skeleton_table(), className="mb-4")
        )
    
    return html.Div(
        className="skeleton-page",
        id=id,
        children=children
    )


def skeleton_text(
    lines: int = 3,
    widths: Optional[list] = None,
    id: Optional[str] = None,
) -> html.Div:
    """
    Skeleton para bloques de texto.
    
    Args:
        lines: Número de líneas
        widths: Lista de anchos por línea (ej: ['100%', '75%', '50%'])
        id: ID opcional
    
    Returns:
        html.Div con líneas de texto skeleton
    """
    if widths is None:
        widths = ['100%'] * lines
    
    return html.Div(
        id=id,
        children=[
            html.Div(
                className="skeleton skeleton-line",
                style={'width': widths[i] if i < len(widths) else '100%', 'marginBottom': '8px'}
            )
            for i in range(lines)
        ]
    )


# Exportar todos los componentes
__all__ = [
    'skeleton_card',
    'skeleton_kpi',
    'skeleton_kpi_row',
    'skeleton_chart',
    'skeleton_table',
    'skeleton_page',
    'skeleton_text',
]
