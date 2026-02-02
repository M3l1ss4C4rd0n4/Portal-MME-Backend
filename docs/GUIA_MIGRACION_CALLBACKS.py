"""
Ejemplo Práctico: Migración de Callback a Patrón XM
Muestra el ANTES y DESPUÉS de aplicar indicators_service
"""

# ==========================================
# ANTES (Código Antiguo)
# ==========================================

"""
@callback(
    [
        Output('restricciones-total-kpi', 'children'),
        Output('restricciones-aliviadas-kpi', 'children'),
        Output('restricciones-sin-alivio-kpi', 'children')
    ],
    Input('interval-component', 'n_intervals')
)
def update_restricciones_kpis_OLD(n):
    # Código antiguo con múltiples consultas y lógica duplicada
    
    # Consulta 1: Total
    df_total = db_manager.query_df(
        "SELECT fecha, valor_gwh FROM metrics WHERE metrica = 'RestTotal' ORDER BY fecha DESC LIMIT 1"
    )
    valor_total = df_total['valor_gwh'].iloc[0] if not df_total.empty else 0
    
    # Consulta 2: Aliviadas
    df_aliv = db_manager.query_df(
        "SELECT fecha, valor_gwh FROM metrics WHERE metrica = 'RestAliv' ORDER BY fecha DESC LIMIT 1"
    )
    valor_aliv = df_aliv['valor_gwh'].iloc[0] if not df_aliv.empty else 0
    
    # Consulta 3: Sin Alivio
    df_sin = db_manager.query_df(
        "SELECT fecha, valor_gwh FROM metrics WHERE metrica = 'RestSinAliv' ORDER BY fecha DESC LIMIT 1"
    )
    valor_sin = df_sin['valor_gwh'].iloc[0] if not df_sin.empty else 0
    
    # Formateo manual (sin validación)
    return (
        html.Div([
            html.Span(f"${valor_total/1_000_000:,.0f}", className="kpi-value"),
            html.Span("Millones COP", className="kpi-unit")
        ]),
        html.Div([
            html.Span(f"${valor_aliv/1_000_000:,.0f}", className="kpi-value"),
            html.Span("Millones COP", className="kpi-unit")
        ]),
        html.Div([
            html.Span(f"${valor_sin/1_000_000:,.0f}", className="kpi-value"),
            html.Span("Millones COP", className="kpi-unit")
        ])
    )
"""


# ==========================================
# DESPUÉS (Código Nuevo con Patrón XM)
# ==========================================

from dash import html, Input, Output, callback
from domain.services.indicators_service import indicators_service


def create_kpi_with_variation(indicator):
    """
    Helper para crear KPI con variación según patrón XM.
    Reutilizable en todos los callbacks.
    """
    if not indicator:
        return html.Div("Sin datos", className="kpi-empty")
    
    return html.Div([
        # Valor principal
        html.Div([
            html.Span(indicator['valor_formateado'], className="kpi-value"),
            html.Span(indicator['unidad'], className="kpi-unit")
        ], className="kpi-main"),
        
        # Variación con flecha
        html.Div([
            html.Span(
                indicator['variacion_formateada'], 
                className=f"variation-{indicator['direccion']}"
            )
        ], className="kpi-variation"),
        
        # Fecha (opcional)
        html.Div([
            html.Span(f"Actualizado: {indicator['fecha_actual']}", className="kpi-date")
        ], className="kpi-footer")
    ], className="kpi-card")


@callback(
    [
        Output('restricciones-total-kpi', 'children'),
        Output('restricciones-aliviadas-kpi', 'children'),
        Output('restricciones-sin-alivio-kpi', 'children')
    ],
    Input('interval-component', 'n_intervals')
)
def update_restricciones_kpis(n):
    """
    Versión nueva usando indicators_service.
    
    Ventajas:
    - 1 sola consulta para 3 métricas
    - Cálculo automático de variaciones
    - Formateo estandarizado
    - Validación de rangos
    - Código más limpio
    """
    # Una sola llamada obtiene las 3 métricas
    indicators = indicators_service.get_multiple_indicators([
        'RestTotal',
        'RestAliv',
        'RestSinAliv'
    ])
    
    # Crear KPIs usando el helper
    return (
        create_kpi_with_variation(indicators.get('RestTotal')),
        create_kpi_with_variation(indicators.get('RestAliv')),
        create_kpi_with_variation(indicators.get('RestSinAliv'))
    )


# ==========================================
# COMPARACIÓN DE RESULTADOS
# ==========================================

"""
ANTES:
┌─────────────────────────┐
│ $226                    │
│ Millones COP            │
└─────────────────────────┘

DESPUÉS:
┌─────────────────────────┐
│ $226,06                 │ ← Valor formateado correctamente
│ Millones COP            │
│ ▲ +8.34%                │ ← Variación con flecha
│ Actualizado: 2026-01-30 │ ← Fecha
└─────────────────────────┘

VENTAJAS:
1. ✅ Variación automática (no requiere código manual)
2. ✅ Formateo estandarizado según XM
3. ✅ Validación de rangos en backend
4. ✅ Menos consultas a DB (1 vs 3)
5. ✅ Código más mantenible
6. ✅ Consistencia entre dashboards
"""


# ==========================================
# OTRO EJEMPLO: Callback con Gráfico
# ==========================================

@callback(
    [
        Output('restricciones-graph', 'figure'),
        Output('restricciones-stats-panel', 'children')
    ],
    [
        Input('fecha-dropdown', 'value'),
        Input('metrica-dropdown', 'value')
    ]
)
def update_restricciones_chart(fecha_range, metrica):
    """
    Callback que combina gráfico + panel de estadísticas.
    Usa indicator_with_history para datos históricos.
    """
    # Obtener indicador con 30 días de historia
    indicator = indicators_service.get_indicator_with_history(
        metrica or 'RestAliv',
        entity='Sistema',
        days=30
    )
    
    if not indicator or 'history' not in indicator:
        return {}, html.Div("Sin datos históricos")
    
    # Crear gráfico con Plotly
    import plotly.graph_objects as go
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=indicator['history']['dates'],
        y=indicator['history']['values'],
        mode='lines+markers',
        name=metrica,
        line=dict(color='#0066cc', width=2),
        marker=dict(size=6)
    ))
    
    fig.update_layout(
        title=f"{metrica} - Últimos 30 días",
        xaxis_title="Fecha",
        yaxis_title=f"Valor ({indicator['unidad']})",
        hovermode='x unified',
        template='plotly_white'
    )
    
    # Panel de estadísticas
    stats_panel = html.Div([
        html.H4("Estadísticas Actuales"),
        
        html.Div([
            html.Strong("Valor Actual:"),
            html.Span(f" {indicator['valor_formateado']}")
        ], className="stat-row"),
        
        html.Div([
            html.Strong("Variación 24h:"),
            html.Span(
                f" {indicator['variacion_formateada']}",
                className=f"variation-{indicator['direccion']}"
            )
        ], className="stat-row"),
        
        html.Div([
            html.Strong("Fecha Actual:"),
            html.Span(f" {indicator['fecha_actual']}")
        ], className="stat-row"),
        
        html.Div([
            html.Strong("Valor Anterior:"),
            html.Span(f" {format_value(indicator['valor_anterior'], indicator['unidad'])}")
        ], className="stat-row"),
        
        html.Div([
            html.Strong("Fecha Anterior:"),
            html.Span(f" {indicator['fecha_anterior']}")
        ], className="stat-row"),
        
    ], className="stats-panel")
    
    return fig, stats_panel


# ==========================================
# CSS NECESARIO (agregar a assets/)
# ==========================================

"""
/* kpi-variations.css */

.kpi-card {
    background: white;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transition: transform 0.2s, box-shadow 0.2s;
}

.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(0,0,0,0.12);
}

.kpi-main {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 12px;
}

.kpi-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: #1a1a1a;
    line-height: 1;
}

.kpi-unit {
    font-size: 0.875rem;
    color: #666;
    font-weight: 500;
}

.kpi-variation {
    margin-bottom: 8px;
}

.variation-up {
    color: #16a34a;
    font-weight: 600;
    font-size: 1rem;
}

.variation-down {
    color: #dc2626;
    font-weight: 600;
    font-size: 1rem;
}

.variation-neutral {
    color: #6b7280;
    font-weight: 600;
    font-size: 1rem;
}

.kpi-footer {
    border-top: 1px solid #e5e7eb;
    padding-top: 8px;
    margin-top: 8px;
}

.kpi-date {
    font-size: 0.75rem;
    color: #9ca3af;
}

.kpi-empty {
    background: #f3f4f6;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    color: #6b7280;
}

.stats-panel {
    background: #f9fafb;
    border-left: 4px solid #0066cc;
    border-radius: 8px;
    padding: 20px;
}

.stat-row {
    padding: 8px 0;
    border-bottom: 1px solid #e5e7eb;
}

.stat-row:last-child {
    border-bottom: none;
}
"""


# ==========================================
# GUÍA DE MIGRACIÓN
# ==========================================

"""
PASOS PARA MIGRAR UN CALLBACK EXISTENTE:

1. Identificar métricas usadas en el callback
   Ejemplo: 'RestAliv', 'RestSinAliv', 'RestAGC'

2. Reemplazar consultas manuales por:
   indicators = indicators_service.get_multiple_indicators(['RestAliv', ...])

3. Usar create_kpi_with_variation() para crear HTML
   return create_kpi_with_variation(indicators.get('RestAliv'))

4. Para gráficos con historia:
   indicator = indicators_service.get_indicator_with_history('RestAliv', days=30)

5. Eliminar código de:
   - Cálculo manual de variaciones
   - Formateo manual de números
   - Consultas SQL repetidas
   - Validaciones ad-hoc

6. Agregar CSS de kpi-variations.css a assets/

TIEMPO ESTIMADO POR CALLBACK:
- Simple (1-3 KPIs): 10-15 minutos
- Complejo (gráficos + stats): 20-30 minutos

ARCHIVOS A MIGRAR:
1. interface/pages/restricciones.py
2. interface/pages/hidrologia.py
3. interface/pages/generacion.py
4. interface/pages/precio_bolsa.py
5. interface/pages/dashboard.py (página principal)

ORDEN RECOMENDADO:
1. Empezar por restricciones.py (ya tiene fixes previos)
2. Seguir con precio_bolsa.py (más simple)
3. Luego hidrologia.py (más complejo)
4. Finalmente dashboard.py (consolidación)
"""
