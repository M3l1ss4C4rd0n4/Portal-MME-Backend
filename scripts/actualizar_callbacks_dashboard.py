"""
Script para actualizar páginas de dashboard con callbacks funcionales
Una vez se validen las métricas de XM disponibles, ejecutar este script

Actualiza:
1. perdidas_tecnicas.py → Callback completo con cálculo real
2. restricciones_operativas.py → Callback usando DemaNoAtenProg
3. transmision_lineas.py → Placeholder con estructura lista

Uso:
    python3 scripts/actualizar_callbacks_dashboard.py
"""
import os
import sys

SERVIDOR_PATH = "/home/admonctrlxm/server"

# ============================================================================
# CALLBACK PÉRDIDAS TÉCNICAS (FUNCIONAL - USA SQLITE)
# ============================================================================

CALLBACK_PERDIDAS = '''
@callback(
    [
        Output("kpi-perdidas-total", "children"),
        Output("kpi-perdidas-pct", "children"),
        Output("perdidas-status", "children"),
        Output("graph-perdidas-calculo", "figure")
    ],
    [Input("perdidas-btn-calcular", "n_clicks")],
    [
        State("perdidas-fecha-inicio", "date"),
        State("perdidas-fecha-fin", "date")
    ],
    prevent_initial_call=False
)
def calcular_perdidas(n_clicks, fecha_inicio_str, fecha_fin_str):
    """Calcular pérdidas de energía desde Gene y DemaCome"""
    px, go = get_plotly_modules()
    
    try:
        from infrastructure.external.xm_service import obtener_datos_inteligente
        
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        
        # Consultar desde SQLite
        df_gene, _ = obtener_datos_inteligente('Gene', 'Sistema', fecha_inicio, fecha_fin)
        df_dema, _ = obtener_datos_inteligente('DemaCome', 'Sistema', fecha_inicio, fecha_fin)
        
        if df_gene is not None and not df_gene.empty and df_dema is not None and not df_dema.empty:
            # Preparar datos
            df_gene['Date'] = pd.to_datetime(df_gene['Date']).dt.date
            df_dema['Date'] = pd.to_datetime(df_dema['Date']).dt.date
            
            # Merge
            df = pd.merge(df_gene[['Date', 'Value']], df_dema[['Date', 'Value']], 
                         on='Date', suffixes=('_Gene', '_Dema'))
            
            # Calcular pérdidas
            df['Perdidas'] = df['Value_Gene'] - df['Value_Dema']
            df['Pct'] = (df['Perdidas'] / df['Value_Gene'] * 100)
            
            # KPIs
            total = df['Perdidas'].sum()
            pct = df['Pct'].mean()
            
            # Gráfico
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Value_Gene'], 
                                    name='Generación', line=dict(color='#0d6efd', width=2)))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Value_Dema'], 
                                    name='Demanda', line=dict(color='#28a745', width=2)))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Perdidas'], 
                                    name='Pérdidas', fill='tozeroy', 
                                    line=dict(color='#dc3545', width=2)))
            
            fig.update_layout(
                title='Generación vs Demanda vs Pérdidas',
                xaxis_title='Fecha',
                yaxis_title='Energía (GWh)',
                template='plotly_white',
                height=500,
                hovermode='x unified'
            )
            
            status = dbc.Alert(
                f"✅ Calculado: {len(df)} días. Período {fecha_inicio} a {fecha_fin}",
                color="success"
            )
            
            return f"{total:,.1f} GWh", f"{pct:.2f}% de generación", status, fig
        else:
            raise ValueError("Datos insuficientes en rango")
            
    except Exception as e:
        fig_error = go.Figure()
        fig_error.add_annotation(
            text=f"❌ Error: {str(e)}", xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return "Error", "Error", dbc.Alert(str(e), color="danger"), fig_error
'''

# ============================================================================
# LAYOUT PÉRDIDAS TÉCNICAS
# ============================================================================

LAYOUT_PERDIDAS = '''
def layout():
    """Layout Pérdidas Técnicas - CON CÁLCULO REAL"""
    return html.Div([
        crear_header(),
        crear_navbar(),
        
        dbc.Container([
            dbc.Row([dbc.Col([
                html.H1("⚠️ Pérdidas de Energía Eléctrica", 
                       className="text-center mb-4", 
                       style={"color": COLORS['primary']}),
                html.P("Análisis de pérdidas técnicas en el Sistema Interconectado Nacional",
                      className="text-center text-muted mb-4"),
                
                # Filtros
                dbc.Card([dbc.CardBody([dbc.Row([
                    dbc.Col([
                        html.Label("Fecha Inicio:", className="fw-bold"),
                        dcc.DatePickerSingle(
                            id='perdidas-fecha-inicio',
                            date=(date.today() - timedelta(days=90)),
                            display_format='YYYY-MM-DD'
                        )
                    ], md=4),
                    dbc.Col([
                        html.Label("Fecha Fin:", className="fw-bold"),
                        dcc.DatePickerSingle(
                            id='perdidas-fecha-fin',
                            date=date.today() - timedelta(days=1),
                            display_format='YYYY-MM-DD'
                        )
                    ], md=4),
                    dbc.Col([
                        html.Label(" ", className="d-block"),
                        dbc.Button("🔄 Calcular Pérdidas", 
                                  id="perdidas-btn-calcular", 
                                  color="primary", className="w-100")
                    ], md=4)
                ])])], className="shadow-sm mb-4"),
                
                html.Div(id="perdidas-status", className="mb-3"),
                
                # KPIs
                dbc.Row([dbc.Col([
                    dbc.Card([dbc.CardBody([
                        html.H6("Pérdidas Totales", className="text-muted mb-2"),
                        html.H3(id="kpi-perdidas-total", children="-- GWh",
                               style={"color": COLORS.get('danger', '#dc3545')}),
                        html.P(id="kpi-perdidas-pct", children="--% de generación",
                              className="small text-muted")
                    ])], className="shadow-sm text-center")
                ], md=12)], className="mb-4"),
                
                # Gráfico
                dbc.Card([dbc.CardBody([
                    html.H5("📊 Generación vs Demanda vs Pérdidas", className="mb-3"),
                    html.P([
                        "Fórmula: ", html.Code("Pérdidas = Gene - DemaCome"), html.Br(),
                        html.Code("% = (Pérdidas / Gene) × 100")
                    ], className="small text-muted mb-3"),
                    dcc.Loading(dcc.Graph(id='graph-perdidas-calculo'))
                ])], className="shadow-sm mb-4"),
                
                dbc.Alert([
                    html.I(className="fas fa-check-circle me-2"),
                    "✅ Cálculo desde datos SQLite (Gene + DemaCome). ",
                    "Típico Colombia: 7-9% pérdidas."
                ], color="info")
                
            ], width=12)])
        ], fluid=True, className="py-4"),
        
        crear_sidebar_universal()
    ])
'''

# ============================================================================
# CALLBACK RESTRICCIONES (PARCIALMENTE FUNCIONAL)
# ============================================================================

CALLBACK_RESTRICCIONES = '''
@callback(
    [
        Output("kpi-dema-no-atendida", "children"),
        Output("restricciones-status", "children"),
        Output("graph-dema-no-atendida-evol", "figure"),
        Output("graph-dema-no-atendida-area", "figure")
    ],
    [Input("restricciones-btn-actualizar", "n_clicks")],
    [
        State("restricciones-fecha-inicio", "date"),
        State("restricciones-fecha-fin", "date")
    ],
    prevent_initial_call=False
)
def actualizar_restricciones(n_clicks, fecha_inicio_str, fecha_fin_str):
    """Actualizar restricciones - USA DemaNoAtenProg de SQLite"""
    px, go = get_plotly_modules()
    
    try:
        from infrastructure.external.xm_service import obtener_datos_inteligente
        
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        
        # Consultar desde SQLite
        df, warning = obtener_datos_inteligente('DemaNoAtenProg', 'Area', fecha_inicio, fecha_fin)
        
        if df is not None and not df.empty:
            df['Date'] = pd.to_datetime(df['Date'])
            
            # KPI
            total = df['Value'].sum()
            
            # Gráfico 1: Evolución temporal
            df_time = df.groupby('Date')['Value'].sum().reset_index()
            fig_evol = px.line(df_time, x='Date', y='Value',
                              title='Demanda No Atendida - Evolución',
                              labels={'Value': 'MWh', 'Date': 'Fecha'})
            fig_evol.update_layout(template='plotly_white', height=400)
            
            # Gráfico 2: Por área
            fig_area = px.bar(df, x='Date', y='Value', color='Name',
                             title='Demanda No Atendida por Área',
                             labels={'Value': 'MWh', 'Date': 'Fecha', 'Name': 'Área'})
            fig_area.update_layout(template='plotly_white', height=400)
            
            status = dbc.Alert(
                f"✅ {len(df)} registros. Período {fecha_inicio} a {fecha_fin}. " +
                (f"⚠️ {warning}" if warning else ""),
                color="success"
            )
            
            return f"{total:,.1f} MWh", status, fig_evol, fig_area
        else:
            raise ValueError("Sin datos de DemaNoAtenProg")
            
    except Exception as e:
        fig_error = go.Figure()
        fig_error.add_annotation(
            text=f"❌ Error: {str(e)}", xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return "Error", dbc.Alert(str(e), color="danger"), fig_error, fig_error
'''


def main():
    """Mostrar código para copiar manualmente a páginas"""
    
    print("=" * 80)
    print("ACTUALIZACIÓN DE CALLBACKS DASHBOARD")
    print("=" * 80)
    print()
    
    print("📋 INSTRUCCIONES:")
    print("1. Las páginas ya existen en /home/admonctrlxm/server/pages/")
    print("2. perdidas_tecnicas.py → Agregar callback funcional")
    print("3. restricciones_operativas.py → Agregar callback funcional")
    print("4. transmision_lineas.py → Actualizada (solo placeholder)")
    print()
    
    print("=" * 80)
    print("CALLBACK PÉRDIDAS TÉCNICAS (perdidas_tecnicas.py)")
    print("=" * 80)
    print(CALLBACK_PERDIDAS)
    print()
    
    print("=" * 80)
    print("LAYOUT PÉRDIDAS TÉCNICAS (perdidas_tecnicas.py)")
    print("=" * 80)
    print(LAYOUT_PERDIDAS)
    print()
    
    print("=" * 80)
    print("CALLBACK RESTRICCIONES (restricciones_operativas.py)")
    print("=" * 80)
    print(CALLBACK_RESTRICCIONES)
    print()
    
    print("=" * 80)
    print("✅ PRÓXIMOS PASOS:")
    print("=" * 80)
    print("1. Esperar que TIC habilite acceso a internet")
    print("2. Ejecutar: python3 scripts/explorar_metricas_xm.py --categoria TODAS")
    print("3. Actualizar etl/config_metricas.py con nuevas métricas")
    print("4. Ejecutar: python3 etl/etl_xm_to_sqlite.py")
    print("5. Completar callbacks con métricas reales de XM")
    print("6. Reiniciar dashboard: sudo systemctl restart dashboard-mme")
    print()


if __name__ == '__main__':
    main()
