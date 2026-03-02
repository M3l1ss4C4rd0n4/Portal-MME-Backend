"""
Hidrología - Definición del Layout
=====================================

Layout principal del dashboard de hidrología: tabs, modals, dcc.Stores.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from interface.components.chart_card import crear_page_header

layout = html.Div([
    html.Div(className="t-page", children=[
        crear_page_header(
            "Hidrología",
            "fas fa-water",
            "Inicio / Generación / Hidrología"
        ),
        # Panel de controles en tabs
        dbc.Tabs([
            dbc.Tab(label="⚡ Aportes de Energía", tab_id="tab-consulta"),
            dbc.Tab(label="📅 Comparación Anual", tab_id="tab-comparacion-anual"),
        ], id="hidro-tabs", active_tab="tab-consulta", className="mb-4"),
        # Contenido dinámico
        html.Div(id="hidrologia-tab-content")
    ])
])

# Modal global para tablas de datos
modal_rio_table = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle(id="modal-title-dynamic", children="Detalle de datos hidrológicos"), close_button=True),
    dbc.ModalBody([
        html.Div(id="modal-description", className="mb-3", style={"fontSize": "0.9rem", "color": "#666"}),
        html.Div(id="modal-table-content")
    ]),
], id="modal-rio-table", is_open=False, size="xl", backdrop=True, centered=True, style={"zIndex": 2000})

# Modal de información de la ficha KPI
modal_info_ficha_kpi = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Indicador de Aportes Energéticos"), close_button=True),
    dbc.ModalBody([
        html.H6("¿Qué mide?", className="fw-bold mb-2"),
        html.P("Compara los aportes energéticos actuales del año 2025 con el promedio histórico de los últimos 5 años."),
        
        html.H6("Cálculo:", className="fw-bold mb-2 mt-3"),
        html.Ul([
            html.Li("Período: Últimos 365 días"),
            html.Li("Datos reales: Suma de aportes energéticos (GWh) de todos los ríos del SIN"),
            html.Li("Media histórica: Promedio de los últimos 5 años (2020-2024) para el mismo período"),
            html.Li([
                "Fórmula: ",
                html.Code("[(Aportes Reales / Media Histórica) × 100] - 100")
            ])
        ]),
        
        html.H6("Interpretación:", className="fw-bold mb-2 mt-3"),
        html.Ul([
            html.Li([
                html.I(className="fas fa-arrow-up", style={'color': '#28a745'}),
                " Positivo (+): Más aportes que el promedio histórico (favorable)"
            ]),
            html.Li([
                html.I(className="fas fa-arrow-down", style={'color': '#dc3545'}),
                " Negativo (-): Menos aportes que el promedio histórico (crítico)"
            ])
        ]),
        
        html.H6("Colores:", className="fw-bold mb-2 mt-3"),
        html.Ul([
            html.Li([
                html.Span("●", style={'color': '#28a745', 'fontSize': '1.2rem'}),
                " Verde: ≥100% del histórico (excelente - abundancia hídrica)"
            ]),
            html.Li([
                html.Span("●", style={'color': '#17a2b8', 'fontSize': '1.2rem'}),
                " Azul: 90-100% del histórico (normal - cerca del promedio)"
            ]),
            html.Li([
                html.Span("●", style={'color': '#dc3545', 'fontSize': '1.2rem'}),
                " Rojo: <90% del histórico (crítico - déficit hídrico)"
            ])
        ])
    ])
], id="modal-info-ficha-kpi", is_open=False, size="lg", centered=True)

# Agregar modales al layout final
layout_with_modal = html.Div([layout, modal_rio_table, modal_info_ficha_kpi])
layout = layout_with_modal

# Layout del panel de controles (lo que antes estaba en el layout principal)


layout = html.Div([
    dcc.Store(id="participacion-jerarquica-data"),
    dcc.Store(id="capacidad-jerarquica-data"),
    dcc.Store(id="ultima-fecha-con-datos"),
    layout_with_modal
])

# Funciones auxiliares heredadas
# --- Función para crear tabla con participación porcentual y semáforo ---


