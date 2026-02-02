"""
Ejemplo de Integración de Indicadores Completos
Muestra cómo usar indicators_service en callbacks
"""

from dash import dcc, html, Input, Output, callback
import plotly.graph_objects as go
from domain.services.indicators_service import indicators_service


# ==========================================
# EJEMPLO 1: KPI Simple con Variación
# ==========================================

def create_kpi_card(indicator_data):
    """
    Crea tarjeta KPI con variación según XM Sinergox.
    
    Args:
        indicator_data: Dict con estructura completa del indicador
    """
    if not indicator_data:
        return html.Div("Sin datos", className="kpi-card-empty")
    
    # Extraer datos
    valor_fmt = indicator_data['valor_formateado']
    var_fmt = indicator_data['variacion_formateada']
    direccion = indicator_data['direccion']
    
    # Clase CSS según dirección
    var_class = f"variation-{direccion}"
    
    return html.Div([
        html.Div([
            html.Span(valor_fmt, className="kpi-value"),
            html.Span(indicator_data['unidad'], className="kpi-unit")
        ], className="kpi-main"),
        html.Div([
            html.Span(var_fmt, className=var_class)
        ], className="kpi-variation")
    ], className="kpi-card")


@callback(
    Output('precio-bolsa-kpi', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_precio_bolsa_kpi(n):
    """Callback para KPI de Precio Bolsa"""
    indicator = indicators_service.get_indicator_complete('PrecBolsNaci', 'Sistema')
    return create_kpi_card(indicator)


# ==========================================
# EJEMPLO 2: KPIs Múltiples
# ==========================================

@callback(
    [
        Output('precio-bolsa-kpi', 'children'),
        Output('restricciones-kpi', 'children'),
        Output('aportes-kpi', 'children')
    ],
    Input('interval-component', 'n_intervals')
)
def update_multiple_kpis(n):
    """Actualiza múltiples KPIs en una sola consulta"""
    indicators = indicators_service.get_multiple_indicators([
        'PrecBolsNaci',
        'RestAliv',
        'AporEner'
    ])
    
    return (
        create_kpi_card(indicators.get('PrecBolsNaci')),
        create_kpi_card(indicators.get('RestAliv')),
        create_kpi_card(indicators.get('AporEner'))
    )


# ==========================================
# EJEMPLO 3: Gráfico con Indicador
# ==========================================

@callback(
    [
        Output('precio-bolsa-graph', 'figure'),
        Output('precio-bolsa-stats', 'children')
    ],
    Input('fecha-dropdown', 'value')
)
def update_precio_bolsa_chart(fecha_range):
    """Gráfico + Estadísticas"""
    # Obtener indicador con historia
    indicator = indicators_service.get_indicator_with_history(
        'PrecBolsNaci', 
        'Sistema', 
        days=30
    )
    
    if not indicator or 'history' not in indicator:
        return go.Figure(), html.Div("Sin datos")
    
    # Crear gráfico
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=indicator['history']['dates'],
        y=indicator['history']['values'],
        mode='lines+markers',
        name='Precio Bolsa',
        line=dict(color='#0066cc', width=2)
    ))
    
    fig.update_layout(
        title='Precio Bolsa Nacional',
        xaxis_title='Fecha',
        yaxis_title=f"Precio ({indicator['unidad']})",
        hovermode='x unified'
    )
    
    # Crear estadísticas
    stats = html.Div([
        html.H4("Estadísticas"),
        html.P([
            html.Strong("Actual: "),
            html.Span(indicator['valor_formateado'])
        ]),
        html.P([
            html.Strong("Variación 24h: "),
            html.Span(
                indicator['variacion_formateada'], 
                className=f"variation-{indicator['direccion']}"
            )
        ]),
        html.P([
            html.Strong("Fecha: "),
            html.Span(indicator['fecha_actual'])
        ])
    ], className="stats-panel")
    
    return fig, stats


# ==========================================
# EJEMPLO 4: Tabla Comparativa
# ==========================================

@callback(
    Output('metricas-table', 'children'),
    Input('refresh-button', 'n_clicks')
)
def update_metricas_table(n_clicks):
    """Tabla con múltiples métricas y sus variaciones"""
    
    metricas = {
        'PrecBolsNaci': 'Precio Bolsa',
        'RestAliv': 'Restricciones Aliviadas',
        'RestSinAliv': 'Restricciones Sin Alivio',
        'AporEner': 'Aportes Hídricos',
        'DemaEner': 'Demanda Energía'
    }
    
    indicators = indicators_service.get_multiple_indicators(list(metricas.keys()))
    
    rows = []
    for metric_id, nombre in metricas.items():
        ind = indicators.get(metric_id)
        
        if not ind:
            continue
        
        rows.append(html.Tr([
            html.Td(nombre),
            html.Td(ind['valor_formateado']),
            html.Td(ind['unidad']),
            html.Td(
                ind['variacion_formateada'],
                className=f"variation-{ind['direccion']}"
            ),
            html.Td(ind['fecha_actual'])
        ]))
    
    return html.Table([
        html.Thead(html.Tr([
            html.Th('Métrica'),
            html.Th('Valor'),
            html.Th('Unidad'),
            html.Th('Variación'),
            html.Th('Fecha')
        ])),
        html.Tbody(rows)
    ], className="metricas-table")


# ==========================================
# CSS Necesario (agregar a assets/)
# ==========================================

"""
/* kpi-cards.css */

.kpi-card {
    background: white;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.kpi-main {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 8px;
}

.kpi-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: #1a1a1a;
}

.kpi-unit {
    font-size: 1rem;
    color: #666;
    font-weight: 500;
}

.kpi-variation {
    font-size: 1rem;
    font-weight: 600;
}

.variation-up {
    color: #16a34a;  /* Verde */
}

.variation-down {
    color: #dc2626;  /* Rojo */
}

.variation-neutral {
    color: #6b7280;  /* Gris */
}

.stats-panel {
    background: #f9fafb;
    border-left: 4px solid #0066cc;
    padding: 16px;
    margin-top: 16px;
}

.metricas-table {
    width: 100%;
    border-collapse: collapse;
}

.metricas-table th {
    background: #f3f4f6;
    padding: 12px;
    text-align: left;
    font-weight: 600;
}

.metricas-table td {
    padding: 12px;
    border-bottom: 1px solid #e5e7eb;
}
"""


# ==========================================
# EJEMPLO 5: Layout Completo
# ==========================================

def create_dashboard_layout():
    """Layout ejemplo con KPIs y gráficos integrados"""
    return html.Div([
        # Fila de KPIs
        html.Div([
            html.Div(id='precio-bolsa-kpi', className='kpi-col'),
            html.Div(id='restricciones-kpi', className='kpi-col'),
            html.Div(id='aportes-kpi', className='kpi-col'),
        ], className='kpi-row'),
        
        # Gráfico con estadísticas
        html.Div([
            html.Div([
                dcc.Graph(id='precio-bolsa-graph')
            ], className='graph-col'),
            html.Div([
                html.Div(id='precio-bolsa-stats')
            ], className='stats-col')
        ], className='content-row'),
        
        # Tabla comparativa
        html.Div([
            html.Button('Actualizar', id='refresh-button'),
            html.Div(id='metricas-table')
        ], className='table-section'),
        
        # Componentes auxiliares
        dcc.Interval(id='interval-component', interval=60000, n_intervals=0),
        dcc.Dropdown(id='fecha-dropdown')
    ])
