"""
Componente Data Table compacto y accesible.

Uso:
    from interface.components.data_display.data_table import data_table
    
    table = data_table(
        id="tabla-plantas",
        data=df.to_dict('records'),
        columns=[
            {"name": "Planta", "id": "Planta"},
            {"name": "Fuente", "id": "Fuente"},
            {"name": "Generación (GWh)", "id": "Generacion_GWh", "type": "numeric"},
            {"name": "Participación (%)", "id": "Participacion_Pct", "type": "numeric"},
        ],
        page_size=10,
        sortable=True,
        filterable=True,
        total_row=True
    )
"""
from dash import html, dash_table
import dash_bootstrap_components as dbc
from typing import List, Dict, Any, Optional
import pandas as pd


def data_table(
    id: str,
    data: List[Dict[str, Any]],
    columns: List[Dict[str, str]],
    title: Optional[str] = None,
    page_size: int = 10,
    sortable: bool = True,
    filterable: bool = False,
    searchable: bool = False,
    total_row: bool = False,
    row_selectable: bool = False,
    className: str = "",
    style_cell: Optional[Dict[str, Any]] = None,
    style_header: Optional[Dict[str, Any]] = None,
) -> html.Div:
    """
    Crea una tabla de datos consistente y compacta.
    
    Args:
        id: ID único de la tabla
        data: Lista de diccionarios con los datos
        columns: Lista de columnas con formato {"name": "Nombre", "id": "id"}
        title: Título opcional de la tabla
        page_size: Número de filas por página
        sortable: Permitir ordenar columnas
        filterable: Permitir filtrar por columna
        searchable: Barra de búsqueda global
        total_row: Mostrar fila de totales
        row_selectable: Permitir seleccionar filas
        className: Clases CSS adicionales
        style_cell: Estilos personalizados para celdas
        style_header: Estilos personalizados para header
    
    Returns:
        html.Div con la tabla
    """
    
    # Estilos por defecto
    default_cell_style = {
        'fontFamily': 'Inter, sans-serif',
        'fontSize': '11px',
        'padding': '5px 8px',
        'textAlign': 'left',
        'borderBottom': '1px solid #f1f5f9',
    }
    
    default_header_style = {
        'fontFamily': 'Inter, sans-serif',
        'fontSize': '10px',
        'fontWeight': '600',
        'textTransform': 'uppercase',
        'letterSpacing': '0.4px',
        'padding': '6px 8px',
        'backgroundColor': '#f9fafb',
        'borderBottom': '2px solid #e5e7eb',
    }
    
    # Preparar columnas para dash_table
    table_columns = []
    for col in columns:
        column_def = {
            'name': col['name'],
            'id': col['id'],
        }
        # Formato numérico
        if col.get('type') == 'numeric':
            column_def['type'] = 'numeric'
            column_def['format'] = {
                'specifier': col.get('format', ',.2f')
            }
        table_columns.append(column_def)
    
    # Configuración de acciones
    sort_action = 'native' if sortable else 'none'
    filter_action = 'native' if filterable else 'none'
    row_selectable_config = 'single' if row_selectable else False
    
    # Crear tabla
    table_component = dash_table.DataTable(
        id=id,
        data=data,
        columns=table_columns,
        
        # Paginación
        page_size=page_size,
        page_action='native',
        page_current=0,
        
        # Ordenamiento
        sort_action=sort_action,
        sort_mode='multi' if sortable else 'none',
        
        # Filtrado
        filter_action=filter_action,
        
        # Selección
        row_selectable=row_selectable_config,
        
        # Estilos
        style_table={
            'overflowX': 'auto',
            'borderRadius': '0 0 8px 8px',
        },
        style_cell={**default_cell_style, **(style_cell or {})},
        style_header={**default_header_style, **(style_header or {})},
        
        # Zebra striping
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#fafbfc'
            },
            {
                'if': {'state': 'selected'},
                'backgroundColor': '#eff6ff',
                'border': '1px solid #3b82f6'
            },
        ],
        
        # Fila total
        style_data={
            'border': 'none',
        },
        
        # Accesibilidad
        aria_label=title or "Tabla de datos",
        role="grid",
        
        # CSS adicional para fila total
        css=[{
            'selector': 'tr:last-child td',
            'rule': 'font-weight: 600;'
        }] if total_row else [],
    )
    
    # Envolver en contenedor
    children = []
    
    if title:
        children.append(
            html.Div(
                title,
                className="table-title",
                style={
                    'fontSize': '12px',
                    'fontWeight': '600',
                    'color': '#374151',
                    'padding': '8px 12px',
                    'backgroundColor': '#f9fafb',
                    'borderBottom': '1px solid #e5e7eb',
                    'borderRadius': '8px 8px 0 0',
                }
            )
        )
    
    children.append(table_component)
    
    return html.Div(
        className=f"table-container {className}",
        children=children
    )


def data_table_from_dataframe(
    id: str,
    df: pd.DataFrame,
    title: Optional[str] = None,
    page_size: int = 10,
    sortable: bool = True,
    filterable: bool = False,
    numeric_columns: Optional[List[str]] = None,
    **kwargs
) -> html.Div:
    """
    Crea una tabla directamente desde un DataFrame.
    
    Args:
        id: ID único
        df: DataFrame de pandas
        title: Título opcional
        page_size: Filas por página
        sortable: Permitir ordenar
        filterable: Permitir filtrar
        numeric_columns: Lista de columnas numéricas
        **kwargs: Argumentos adicionales para data_table
    
    Returns:
        html.Div con la tabla
    """
    # Inferir columnas del DataFrame
    columns = []
    for col in df.columns:
        col_def = {'name': col, 'id': col}
        if numeric_columns and col in numeric_columns:
            col_def['type'] = 'numeric'
        elif df[col].dtype in ['int64', 'float64']:
            col_def['type'] = 'numeric'
        columns.append(col_def)
    
    return data_table(
        id=id,
        data=df.to_dict('records'),
        columns=columns,
        title=title,
        page_size=page_size,
        sortable=sortable,
        filterable=filterable,
        **kwargs
    )


def data_table_loading(
    title: str = "Cargando datos...",
    rows: int = 5,
    id: Optional[str] = None,
) -> html.Div:
    """
    Crea una tabla en estado de carga.
    
    Args:
        title: Título
        rows: Número de filas skeleton
        id: ID opcional
    
    Returns:
        html.Div con skeleton de tabla
    """
    return html.Div(
        className="table-container",
        id=id,
        children=[
            html.Div(
                title,
                className="table-title"
            ),
            html.Div(
                className="skeleton-table",
                children=[
                    html.Div(className="skeleton-row header"),
                    *[html.Div(className="skeleton-row") for _ in range(rows)]
                ]
            )
        ]
    )
