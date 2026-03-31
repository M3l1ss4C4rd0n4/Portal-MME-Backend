"""
EJEMPLO DE REFACTORIZACIÓN - Página de Transmisión

ANTES: Todo en un archivo de 717 líneas con problemas de Dash Pages
DESPUÉS: Arquitectura limpia separada por responsabilidades
"""

# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVO 1: interface/controllers/transmission_controller.py
# Responsabilidad: Lógica de negocio, datos, cálculos
# ═══════════════════════════════════════════════════════════════════════════

class TransmissionController:
    """Controlador para la página de transmisión"""
    
    def __init__(self, service=None):
        from domain.services.transmission_service import TransmissionService
        self.service = service or TransmissionService()
    
    def get_dashboard_data(self, fecha_inicio=None, fecha_fin=None, tension=None):
        """Obtiene todos los datos necesarios para el dashboard"""
        df = self.service.get_transmission_lines()
        
        if df.empty:
            return None
        
        # Aplicar filtros
        df = self._apply_filters(df, fecha_inicio, fecha_fin, tension)
        
        return {
            'dataframe': df,
            'total_lineas': len(df),
            'lineas_criticas': len(df[df['Criticidad'] == 'Crítica']) if 'Criticidad' in df.columns else 0,
            'kpis': self._calculate_kpis(df),
            'charts': {
                'criticidad': self._prepare_criticidad_data(df),
                'participacion': self._prepare_participacion_data(df),
                'decadas': self._prepare_decadas_data(df)
            }
        }
    
    def _apply_filters(self, df, fecha_inicio, fecha_fin, tension):
        """Aplica filtros al dataframe"""
        import pandas as pd
        
        # Filtro de tensión
        if tension and tension != 'TODAS':
            try:
                tension_val = float(tension)
                df = df[df['Tension'] == tension_val]
            except ValueError:
                pass
        
        # Filtro de fecha
        if fecha_inicio and fecha_fin and 'FPO' in df.columns:
            df['FPO'] = pd.to_datetime(df['FPO'], errors='coerce')
            fecha_ini = pd.to_datetime(fecha_inicio)
            fecha_fi = pd.to_datetime(fecha_fin)
            df = df[(df['FPO'] >= fecha_ini) & (df['FPO'] <= fecha_fi)]
        
        return df
    
    def _calculate_kpis(self, df):
        """Calcula KPIs del dashboard"""
        return {
            'total_lineas': len(df),
            'longitud_total': df['Longitud'].sum() if 'Longitud' in df.columns else 0,
            'tension_promedio': df['Tension'].mean() if 'Tension' in df.columns else 0,
            'antiguedad_promedio': df['Años_Operacion'].mean() if 'Años_Operacion' in df.columns else 0
        }
    
    def _prepare_criticidad_data(self, df):
        """Prepara datos para gráfica de criticidad"""
        # Lógica de preparación de datos
        return df[['Años_Operacion', 'ParticipacionLineaTotal', 'Criticidad']].to_dict('records')
    
    def _prepare_participacion_data(self, df):
        """Prepara datos para gráfica de participación"""
        import pandas as pd
        df_reciente = df[df['Fecha'] == df['Fecha'].max()] if 'Fecha' in df.columns else df
        
        participacion = df_reciente.groupby('Tension').agg({
            'ParticipacionLineaTotal': 'mean',
            'Longitud': 'mean',
            'CodigoLinea': 'count'
        }).reset_index()
        
        return participacion.to_dict('records')
    
    def _prepare_decadas_data(self, df):
        """Prepara datos para gráfica de décadas"""
        import pandas as pd
        df['FPO'] = pd.to_datetime(df['FPO'], errors='coerce')
        df['Decada'] = (df['FPO'].dt.year // 10) * 10
        
        decadas = df.groupby('Decada').agg({
            'CodigoLinea': 'count',
            'Longitud': 'sum'
        }).reset_index()
        
        return decadas.to_dict('records')


# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVO 2: interface/views/transmission_charts.py
# Responsabilidad: Crear gráficas Plotly (solo presentación)
# ═══════════════════════════════════════════════════════════════════════════

import plotly.graph_objects as go
from plotly.subplots import make_subplots


class TransmissionCharts:
    """Vista: Generación de gráficas para transmisión"""
    
    @staticmethod
    def create_criticidad_chart(data):
        """Gráfica de dispersión: Criticidad vs Antigüedad"""
        if not data:
            return go.Figure()
        
        import pandas as pd
        df = pd.DataFrame(data)
        
        fig = go.Figure()
        
        # Colores por criticidad
        colors = {'Crítica': '#ef4444', 'Importante': '#f59e0b', 'Normal': '#10b981'}
        
        for criticidad in ['Crítica', 'Importante', 'Normal']:
            mask = df['Criticidad'] == criticidad if 'Criticidad' in df.columns else pd.Series(True, index=df.index)
            df_filtered = df[mask]
            
            if not df_filtered.empty:
                fig.add_trace(go.Scatter(
                    x=df_filtered['Años_Operacion'],
                    y=df_filtered['ParticipacionLineaTotal'] * 100,
                    mode='markers',
                    name=criticidad,
                    marker=dict(color=colors.get(criticidad, '#6b7280'), size=8, opacity=0.7)
                ))
        
        fig.update_layout(
            title='Criticidad vs Antigüedad',
            xaxis_title='Años de Operación',
            yaxis_title='Participación (%)',
            height=340,
            template='plotly_white'
        )
        
        return fig
    
    @staticmethod
    def create_participacion_chart(data):
        """Gráfica de barras: Participación por nivel de tensión"""
        if not data:
            return go.Figure()
        
        import pandas as pd
        df = pd.DataFrame(data)
        
        df['TensionStr'] = df['Tension'].astype(str) + ' kV'
        df['Part_%'] = df['ParticipacionLineaTotal'] * 100
        
        fig = go.Figure(data=[
            go.Bar(
                x=df['TensionStr'],
                y=df['Part_%'],
                marker_color='#3b82f6',
                text=df['Part_%'].round(2),
                textposition='outside'
            )
        ])
        
        fig.update_layout(
            title='Participación por Voltaje',
            xaxis_title='Nivel de Tensión',
            yaxis_title='% Promedio',
            height=280,
            showlegend=False
        )
        
        return fig
    
    @staticmethod
    def create_decadas_chart(data):
        """Gráfica de líneas: Líneas por década"""
        if not data:
            return go.Figure()
        
        import pandas as pd
        df = pd.DataFrame(data)
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig.add_trace(
            go.Bar(
                x=df['Decada'],
                y=df['CodigoLinea'],
                name='Cantidad de Líneas',
                marker_color='#10b981'
            ),
            secondary_y=False
        )
        
        fig.add_trace(
            go.Scatter(
                x=df['Decada'],
                y=df['Longitud'],
                name='Longitud Total',
                mode='lines+markers',
                line=dict(color='#f59e0b')
            ),
            secondary_y=True
        )
        
        fig.update_layout(
            title='Líneas por Década',
            height=280
        )
        
        return fig


# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVO 3: interface/pages/transmission.py (NUEVO - 100 líneas vs 717)
# Responsabilidad: Solo layout y registro de callbacks con app
# ═══════════════════════════════════════════════════════════════════════════

from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc


def create_layout():
    """Crea el layout de la página de transmisión"""
    
    # Componentes reutilizables
    from interface.components.chart_card import crear_chart_card, crear_page_header, crear_filter_bar
    
    return html.Div([
        # Store para datos
        dcc.Store(id='transmision-data-trigger', data={'initialized': False}),
        
        # Header
        crear_page_header(
            titulo="Transmisión",
            icono="fas fa-bolt",
            breadcrumb="Inicio / Transmisión"
        ),
        
        # Filtros
        crear_filter_bar(
            dcc.Dropdown(
                id='dropdown-rango-transmision',
                options=[
                    {'label': 'Todo', 'value': 'todo'},
                    {'label': 'Último Año', 'value': '1y'},
                    {'label': '5 años', 'value': '5y'},
                ],
                value='todo',
                clearable=False
            ),
            dcc.DatePickerRange(id='fecha-filtro-transmision'),
            dcc.Dropdown(
                id='dropdown-tension-transmision',
                options=[
                    {'label': 'Todas', 'value': 'TODAS'},
                    {'label': '500 kV', 'value': 500},
                    {'label': '230 kV', 'value': 230},
                ],
                value='TODAS',
                clearable=False
            ),
            dbc.Button("Consultar", id="btn-actualizar-transmision", color="primary")
        ),
        
        # KPIs
        html.Div(id="kpis-transmision"),
        
        # Gráficas
        dbc.Row([
            dbc.Col([
                crear_chart_card(
                    titulo="Criticidad vs Antigüedad",
                    graph_id="grafica-criticidad-antiguedad",
                    height=340
                )
            ], lg=5),
            
            dbc.Col([
                crear_chart_card(
                    titulo="Participación por Voltaje",
                    graph_id="grafica-participacion-voltaje",
                    height=280
                ),
                crear_chart_card(
                    titulo="Líneas por Década",
                    graph_id="grafica-antiguedad-decadas",
                    height=280
                )
            ], lg=4)
        ])
    ])


def register_callbacks(app):
    """Registra todos los callbacks con la app de Dash"""
    
    from interface.controllers.transmission_controller import TransmissionController
    from interface.views.transmission_charts import TransmissionCharts
    
    controller = TransmissionController()
    charts_view = TransmissionCharts()
    
    @app.callback(
        [
            Output('kpis-transmision', 'children'),
            Output('grafica-criticidad-antiguedad', 'figure'),
            Output('grafica-participacion-voltaje', 'figure'),
            Output('grafica-antiguedad-decadas', 'figure')
        ],
        [
            Input('transmision-data-trigger', 'data'),
            Input('btn-actualizar-transmision', 'n_clicks')
        ],
        [
            State('fecha-filtro-transmision', 'start_date'),
            State('fecha-filtro-transmision', 'end_date'),
            State('dropdown-tension-transmision', 'value')
        ]
    )
    def update_dashboard(trigger_data, n_clicks, fecha_inicio, fecha_fin, tension):
        """Callback principal del dashboard"""
        
        import plotly.graph_objects as go
        from dash import html
        
        # Obtener datos del controlador
        data = controller.get_dashboard_data(fecha_inicio, fecha_fin, tension)
        
        if data is None:
            # Retornar estado vacío
            empty_fig = go.Figure()
            return html.Div("No hay datos"), empty_fig, empty_fig, empty_fig
        
        # Crear componentes
        kpis = html.Div([
            html.H4(f"Total: {data['total_lineas']} líneas"),
            html.P(f"Críticas: {data['lineas_criticas']}")
        ])
        
        # Crear gráficas
        fig_criticidad = charts_view.create_criticidad_chart(data['charts']['criticidad'])
        fig_participacion = charts_view.create_participacion_chart(data['charts']['participacion'])
        fig_decadas = charts_view.create_decadas_chart(data['charts']['decadas'])
        
        return kpis, fig_criticidad, fig_participacion, fig_decadas


# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVO 4: core/app_factory.py (Simplificado)
# ═══════════════════════════════════════════════════════════════════════════

def create_app():
    """Factory simplificada sin Dash Pages"""
    from dash import Dash
    import dash_bootstrap_components as dbc
    
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True
    )
    
    # Importar páginas manualmente (sin Dash Pages)
    from interface.pages import transmission, generacion, home
    
    # Layout principal con router manual
    from dash import html, dcc
    
    app.layout = html.Div([
        dcc.Location(id='url', refresh=False),
        html.Div(id='page-content')
    ])
    
    # Router manual
    @app.callback(
        Output('page-content', 'children'),
        Input('url', 'pathname')
    )
    def display_page(pathname):
        if pathname == '/transmision':
            return transmission.create_layout()
        elif pathname == '/generacion':
            return generacion.create_layout()
        else:
            return home.create_layout()
    
    # Registrar callbacks de cada página
    transmission.register_callbacks(app)
    generacion.register_callbacks(app)
    home.register_callbacks(app)
    
    return app


# ═══════════════════════════════════════════════════════════════════════════
# BENEFICIOS DE ESTA ARQUITECTURA
# ═══════════════════════════════════════════════════════════════════════════

"""
1. ✅ SOLUCIONA el problema de Dash 4.0 + Gunicorn
   - No usa Dash Pages (el source del problema)
   - Usa app.callback explícito (registrado correctamente)

2. ✅ TESTEABLE
   - Controller se puede testear unitariamente
   - Views se pueden testear independientemente
   - No hay dependencias circulares

3. ✅ MANTENIBLE
   - Cada archivo tiene una responsabilidad única
   - Cambios en lógica no afectan UI
   - Cambios en UI no afectan lógica

4. ✅ ESCALABLE
   - Fácil agregar nuevas páginas
   - Fácil modificar gráficas sin tocar datos
   - Fácil agregar nuevos filtros

5. ✅ RENDIMIENTO
   - Datos se procesan solo cuando cambian
   - Componentes se renderizan eficientemente
   - Sin imports circulares que ralentizan
"""
