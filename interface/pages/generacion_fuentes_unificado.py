from dash import dcc, html, Input, Output, State, callback, register_page, dash_table
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta, datetime
from io import StringIO
import warnings
import traceback
import logging
import sys
from functools import lru_cache
import hashlib
import signal
from contextlib import contextmanager

# Configurar logging (heredado de la app principal)
logger = logging.getLogger(__name__)

# Use the installed pydataxm package
try:
    from pydataxm.pydataxm import ReadDB
    PYDATAXM_AVAILABLE = True
except ImportError:
    PYDATAXM_AVAILABLE = False

# Imports locales
from interface.components.layout import crear_navbar_horizontal, crear_filtro_fechas_compacto, registrar_callback_filtro_fechas
from core.constants import UIColors as COLORS
from infrastructure.external.xm_service import fetch_gene_recurso_chunked
from infrastructure.external.xm_service import get_objetoAPI, fetch_metric_data, obtener_datos_desde_bd, obtener_datos_inteligente
from infrastructure.database.manager import db_manager
# CACHE ELIMINADO - Ahora usamos solo ETL-SQLite

# SERVICIO DE DOMINIO - GENERACIÓN
from domain.services.generation_service import GenerationService
_generation_service = GenerationService()

warnings.filterwarnings("ignore")

def obtener_ultima_fecha_disponible():
    """
    Delegada al servicio de dominio (o métricas).
    """
    return _generation_service.get_latest_valid_date()

def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

register_page(
    __name__,
    path="/generacion/fuentes",
    name="Generación por Fuente",
    title="Tablero Generación por Fuente - Ministerio de Minas y Energía de Colombia",
    order=6
)

# ============================================
# TIMEOUT HANDLER PARA API XM LENTA
# ============================================
class TimeoutException(Exception):
    pass

@contextmanager
def timeout_handler(seconds):
    """Context manager para timeout en operaciones bloqueantes
    
    Uso:
        try:
            with timeout_handler(10):
                resultado = operacion_lenta()
        except TimeoutException:
    """
    def timeout_signal_handler(signum, frame):
        raise TimeoutException(f"Operación excedió {seconds} segundos")
    
    # Configurar señal de alarma
    old_handler = signal.signal(signal.SIGALRM, timeout_signal_handler)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        # Restaurar handler y cancelar alarma
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

# Mapeo de tipos de fuente
TIPOS_FUENTE = {
    'HIDRAULICA': {'label': 'Hidráulica', 'icon': 'fa-water', 'color': COLORS.get('energia_hidraulica', '#0d6efd')},
    'EOLICA': {'label': 'Eólica', 'icon': 'fa-wind', 'color': COLORS.get('success', '#28a745')},
    'SOLAR': {'label': 'Solar', 'icon': 'fa-sun', 'color': COLORS.get('warning', '#ffc107')},
    'TERMICA': {'label': 'Térmica', 'icon': 'fa-fire', 'color': COLORS.get('danger', '#dc3545')},
    'BIOMASA': {'label': 'Biomasa', 'icon': 'fa-leaf', 'color': COLORS.get('info', '#17a2b8')}
}

def obtener_listado_recursos(tipo_fuente='EOLICA'):
    """
    Delegada al GenerationService.
    """
    return _generation_service.get_resources_by_type(tipo_fuente)


def obtener_listado_recursos_desde_api(tipo_fuente='EOLICA'):
    """Fallback: obtener listado desde API XM (LENTO - solo si SQLite falla)"""
    # CACHE ELIMINADO - Consulta directa a SQLite/API
    
    try:
        objetoAPI = get_objetoAPI()
        if objetoAPI is None:
            logger.error("❌ API no disponible")
            return pd.DataFrame()
        
        fecha_fin = date.today() - timedelta(days=14)
        fecha_inicio = fecha_fin - timedelta(days=7)
        
        logger.info(f"✅ Consultando ListadoRecursos desde SQLite ({tipo_fuente})...")
        
        # ✅ OPTIMIZADO: Usar obtener_datos_inteligente (SQLite)
        recursos, warning = obtener_datos_inteligente("ListadoRecursos", "Sistema", 
                                                       fecha_inicio.strftime('%Y-%m-%d'), 
                                                       fecha_fin.strftime('%Y-%m-%d'))
        
        if recursos is not None and not recursos.empty:
            logger.info(f"✅ SQLite/API: {len(recursos)} recursos obtenidos")
            
            # Filtrar por tipo
            if tipo_fuente.upper() != 'TODAS':
                return filtrar_por_tipo_fuente(recursos, tipo_fuente)
            return recursos
        
        logger.error("❌ API no devolvió datos")
        return pd.DataFrame()
        
    except Exception as e:
        logger.error(f"❌ Error API: {e}")
        return pd.DataFrame()


def filtrar_por_tipo_fuente(df_recursos, tipo_fuente):
    """Filtrar recursos por tipo de fuente energética
    
    Args:
        df_recursos: DataFrame con columna Values_Type
        tipo_fuente: 'HIDRAULICA', 'EOLICA', 'SOLAR', 'TERMICA', 'BIOMASA'
    
    Returns:
        DataFrame filtrado
    """
    if df_recursos.empty or 'Values_Type' not in df_recursos.columns:
        return df_recursos
    
    # TODAS las fuentes
    if tipo_fuente.upper() == 'TODAS':
        return df_recursos
    
    # Buscar con términos alternativos para biomasa
    if tipo_fuente.upper() == 'BIOMASA':
        terminos_biomasa = ['BIOMASA', 'BIOMAS', 'COGENER', 'BAGAZO', 'RESIDUO']
        plantas = pd.DataFrame()
        for termino in terminos_biomasa:
            plantas_temp = df_recursos[
                df_recursos['Values_Type'].str.contains(termino, na=False, case=False)
            ]
            if not plantas_temp.empty:
                plantas = pd.concat([plantas, plantas_temp], ignore_index=True)
        
        if not plantas.empty:
            plantas = plantas.drop_duplicates(subset=['Values_Code'])
            return plantas
        
        logger.warning(f"⚠️ No se encontraron plantas de Biomasa")
        return pd.DataFrame()
    
    # Otros tipos: buscar coincidencia exacta o parcial
    tipo_upper = tipo_fuente.upper()
    plantas = df_recursos[
        df_recursos['Values_Type'].str.contains(tipo_upper, na=False, case=False)
    ]
    
    if plantas.empty:
        logger.warning(f"⚠️ No se encontraron plantas de {tipo_fuente}")
    
    return plantas


def obtener_generacion_agregada_por_tipo(fecha_inicio, fecha_fin, tipo_fuente='HIDRAULICA'):
    """
    Delegada al GenerationService.
    """
    return _generation_service.get_aggregated_generation_by_type(fecha_inicio, fecha_fin, tipo_fuente)

def crear_grafica_temporal_negra(df_generacion, planta_seleccionada=None, tipo_fuente='EOLICA'):
    """Gráfica temporal con línea nacional, barras apiladas y áreas por tipo de fuente"""
    px, go = get_plotly_modules()
    from plotly.subplots import make_subplots
    
    if df_generacion.empty:
        return go.Figure().add_annotation(
            text="No hay datos disponibles",
            xref="paper", yref="paper", x=0.5, y=0.5
        )
    
    # Clasificar por tipo de fuente
    def categorizar_fuente(codigo):
        codigo_str = str(codigo).upper()
        if any(x in codigo_str for x in ['H', 'PCH', 'HIDRA']):
            return 'Hidráulica'
        elif 'E' in codigo_str or 'EOL' in codigo_str:
            return 'Eólica'
        elif 'S' in codigo_str or 'SOL' in codigo_str or 'FV' in codigo_str:
            return 'Solar'
        elif 'B' in codigo_str or 'COG' in codigo_str or 'BIO' in codigo_str:
            return 'Biomasa'
        else:
            return 'Térmica'
    
    # Si no tiene columna 'Tipo', crearla
    if 'Tipo' not in df_generacion.columns:
        df_generacion['Tipo'] = df_generacion['Codigo'].apply(categorizar_fuente)
    
    # Colores para cada tipo de fuente
    colores_fuente = {
        'Hidráulica': '#1f77b4',    # Azul
        'Térmica': '#ff7f0e',       # Naranja
        'Eólica': '#2ca02c',        # Verde
        'Solar': '#ffbb33',         # Amarillo
        'Biomasa': '#17becf',       # Cian
    }
    
    # **OPTIMIZACIÓN: Agregar datos inteligentemente según el período**
    # Calcular días del período
    if not df_generacion.empty and 'Fecha' in df_generacion.columns:
        df_generacion['Fecha'] = pd.to_datetime(df_generacion['Fecha'])
        fecha_min = df_generacion['Fecha'].min()
        fecha_max = df_generacion['Fecha'].max()
        dias_periodo = (fecha_max - fecha_min).days
        
        # Aplicar agregación inteligente
        df_generacion = agregar_datos_inteligente(df_generacion, dias_periodo)
    
    # Agrupar por fecha y calcular totales
    df_por_fecha = df_generacion.groupby('Fecha', as_index=False)['Generacion_GWh'].sum().sort_values('Fecha')

    # Determinar columna de agrupación
    # Siempre agrupar por 'Tipo' para mostrar fuentes en barras apiladas
    grouping_col = 'Tipo'

    df_por_fuente = df_generacion.groupby(['Fecha', grouping_col], as_index=False)['Generacion_GWh'].sum().sort_values('Fecha')

    # Calcular porcentaje de participación
    df_por_fuente = df_por_fuente.merge(df_por_fecha[['Fecha', 'Generacion_GWh']], on='Fecha', suffixes=('', '_Total'))
    df_por_fuente['Participacion_%'] = (df_por_fuente['Generacion_GWh'] / df_por_fuente['Generacion_GWh_Total']) * 100

    # Ordenar categorías (Tipos o Plantas) por generación total (mayor a menor)
    generacion_por_categoria = df_generacion.groupby(grouping_col)['Generacion_GWh'].sum().sort_values(ascending=False)
    tipos_ordenados = generacion_por_categoria.index.tolist()

    # Datos para torta (última fecha)
    ultima_fecha = df_por_fecha['Fecha'].max()
    df_torta = df_por_fuente[df_por_fuente['Fecha'] == ultima_fecha].sort_values('Participacion_%', ascending=False)

    # Crear figura simple (SIN subplots - solo una gráfica)
    fig = go.Figure()

    # Preparar paleta de colores - siempre usar colores predefinidos para tipos de fuente
    colores_categoria = colores_fuente

    # --- BARRAS APILADAS (GWh) ---
    for cat in tipos_ordenados:
        df_cat = df_por_fuente[df_por_fuente[grouping_col] == cat]
        if not df_cat.empty:
            fig.add_trace(
                go.Bar(
                    x=df_cat['Fecha'],
                    y=df_cat['Generacion_GWh'],
                    name=str(cat),
                    marker_color=colores_categoria.get(cat, '#666'),
                    hovertemplate=f'<b>{cat}</b><br>Fecha: %{{x}}<br>Generación: %{{y:.2f}} GWh<extra></extra>',
                    legendgroup=str(cat),
                    showlegend=True
                )
            )

    # Línea negra de total
    fig.add_trace(
        go.Scatter(
            x=df_por_fecha['Fecha'],
            y=df_por_fecha['Generacion_GWh'],
            mode='lines',
            name='Total Nacional',
            line=dict(color='black', width=2),
            hovertemplate='<b>Total Nacional</b><br>Fecha: %{x}<br>Generación: %{y:.2f} GWh<extra></extra>',
            legendgroup='total',
            showlegend=True
        )
    )
    
    # Configurar layout
    fig.update_layout(
        height=340,
        hovermode='x unified',
        template='plotly_white',
        barmode='stack',
        title=dict(
            text='Generación por Fuente',
            font=dict(size=10, color='#666'),
            x=0.02,
            y=0.98,
            xanchor='left',
            yanchor='top'
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
            font=dict(size=8)
        ),
        margin=dict(t=5, b=5, l=40, r=5)
    )
    
    # Títulos de ejes
    fig.update_xaxes(title_text="")
    fig.update_yaxes(title_text="GWh", title_font=dict(size=9))
    
    return fig

def crear_grafica_torta_fuentes(df_por_fuente, fecha_seleccionada, grouping_col, tipo_fuente):
    """Crea gráfica de torta para una fecha específica"""
    px, go = get_plotly_modules()
    
    if df_por_fuente.empty:
        return go.Figure().add_annotation(
            text="No hay datos disponibles",
            xref="paper", yref="paper", x=0.5, y=0.5
        )
    
    # Colores para cada tipo de fuente
    colores_fuente = {
        'Hidráulica': '#1f77b4',
        'Térmica': '#ff7f0e',
        'Eólica': '#2ca02c',
        'Solar': '#ffbb33',
        'Biomasa': '#17becf',
    }
    
    # Filtrar datos para la fecha seleccionada
    # Normalizar ambas fechas al primer día del mes para comparación
    df_por_fuente_copy = df_por_fuente.copy()
    
    # Convertir fecha seleccionada a datetime para normalización
    if isinstance(fecha_seleccionada, str):
        fecha_sel_dt = pd.to_datetime(fecha_seleccionada)
    elif isinstance(fecha_seleccionada, date) and not isinstance(fecha_seleccionada, datetime):
        fecha_sel_dt = pd.Timestamp(fecha_seleccionada)
    else:
        fecha_sel_dt = pd.to_datetime(fecha_seleccionada)
    
    # Obtener año y mes de la fecha seleccionada
    year_sel = fecha_sel_dt.year
    month_sel = fecha_sel_dt.month
    
    # Convertir fechas del DataFrame a datetime si no lo son
    if 'Fecha' in df_por_fuente_copy.columns:
        df_por_fuente_copy['Fecha'] = pd.to_datetime(df_por_fuente_copy['Fecha'])
        # Agregar columnas de año y mes para comparación
        df_por_fuente_copy['Year'] = df_por_fuente_copy['Fecha'].dt.year
        df_por_fuente_copy['Month'] = df_por_fuente_copy['Fecha'].dt.month
    
    # Filtrar por año y mes (más robusto que comparar fechas exactas)
    df_torta = df_por_fuente_copy[
        (df_por_fuente_copy['Year'] == year_sel) & 
        (df_por_fuente_copy['Month'] == month_sel)
    ].sort_values('Participacion_%', ascending=False)
    
    if df_torta.empty:
        logger.warning(f"No hay datos para {year_sel}/{month_sel:02d}")
        return go.Figure().add_annotation(
            text=f"No hay datos para {fecha_sel_dt.strftime('%m/%Y')}",
            xref="paper", yref="paper", x=0.5, y=0.5
        )
    
    # Preparar colores
    if grouping_col == 'Tipo':
        colores_categoria = colores_fuente
    else:
        try:
            palette = px.colors.qualitative.Plotly
        except Exception:
            palette = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692']
        generacion_por_categoria = df_torta.sort_values('Generacion_GWh', ascending=False)
        categorias = generacion_por_categoria[grouping_col].tolist()
        colores_categoria = {cat: palette[i % len(palette)] for i, cat in enumerate(categorias)}
    
    # Crear figura de torta
    fig = go.Figure()
    fig.add_trace(
        go.Pie(
            labels=df_torta[grouping_col],
            values=df_torta['Generacion_GWh'],
            marker=dict(colors=[colores_categoria.get(cat, '#666') for cat in df_torta[grouping_col]]),
            textposition='inside',
            textinfo='percent',
            hovertemplate='<b>%{label}</b><br>Participación: %{percent}<br>Generación: %{value:.1f} GWh<extra></extra>'
        )
    )
    
    fig.update_layout(
        height=280,
        width=300,
        autosize=False,
        template='plotly_white',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
            font=dict(size=6),
            itemsizing='constant',
            tracegroupgap=0
        ),
        margin=dict(t=5, b=5, l=5, r=5)
    )
    
    return fig


def crear_tabla_participacion(df_participacion):
    """Crear tabla de participación por planta con paginación estilo XM"""
    if df_participacion.empty:
        return html.P("No hay datos de participación", className="text-muted")
    
    # Ordenar por generación descendente
    df_sorted = df_participacion.sort_values('Generacion_GWh', ascending=False).reset_index(drop=True)
    
    # Calcular totales
    total_generacion = df_sorted['Generacion_GWh'].sum()
    total_participacion = df_sorted['Participacion_%'].sum()
    
    # Formatear columnas para mostrar
    df_display = df_sorted.copy()
    df_display['Generación (GWh)'] = df_display['Generacion_GWh'].apply(lambda x: f"{x:.2f}")
    df_display['Participación (%)'] = df_display['Participacion_%'].apply(lambda x: f"{x:.2f}%")
    
    # Seleccionar columnas finales (sin columna Tipo, solo Fuente)
    columnas_mostrar = ['Planta', 'Fuente', 'Generación (GWh)', 'Participación (%)']
    df_display = df_display[columnas_mostrar]
    
    # Crear DataTable con paginación
    tabla = html.Div([
        html.Div("Detalle por Planta", style={'fontSize': '0.7rem', 'color': '#666', 'marginBottom': '3px', 'fontWeight': '500'}),
        dash_table.DataTable(
            data=df_display.to_dict('records'),
            columns=[{"name": col, "id": col} for col in columnas_mostrar],
            
            # PAGINACIÓN - 10 filas por página
            page_size=10,
            page_action='native',
            page_current=0,
            
            # ESTILO de tabla
            style_table={
                'overflowX': 'auto',
                'maxHeight': '240px',
                'border': '1px solid #dee2e6'
            },
            
            # ESTILO de celdas
            style_cell={
                'textAlign': 'left',
                'padding': '1px 2px',
                'fontFamily': 'Arial, sans-serif',
                'fontSize': '0.4rem',
                'border': '1px solid #dee2e6',
                'minWidth': '50px',
                'maxWidth': '100px',
                'whiteSpace': 'nowrap',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
                'lineHeight': '1.1'
            },
            
            # Ancho específico por columna
            style_cell_conditional=[
                {'if': {'column_id': 'Planta'}, 'minWidth': '80px', 'maxWidth': '100px'},
                {'if': {'column_id': 'Fuente'}, 'minWidth': '60px', 'maxWidth': '80px'},
                {'if': {'column_id': 'Generación (GWh)'}, 'minWidth': '55px', 'maxWidth': '70px'},
                {'if': {'column_id': 'Participación (%)'}, 'minWidth': '55px', 'maxWidth': '70px'}
            ],
            
            # ESTILO de header
            style_header={
                'backgroundColor': '#6c3fb5',  # Morado como XM
                'color': 'white',
                'fontWeight': 'bold',
                'textAlign': 'center',
                'border': '1px solid #5a2f99',
                'fontSize': '0.6rem',
                'padding': '3px 4px',
                'whiteSpace': 'normal',
                'height': 'auto',
                'lineHeight': '1.2'
            },
            
            # ESTILO de datos
            style_data={
                'backgroundColor': 'white',
                'color': 'black',
                'fontSize': '0.4rem',
                'padding': '1px 2px'
            },
            
            # ESTILO condicional para filas alternas
            style_data_conditional=[
                {
                    'if': {'row_index': 'odd'},
                    'backgroundColor': '#f8f9fa'
                },
                {
                    'if': {'column_id': 'Generación (GWh)'},
                    'textAlign': 'right',
                    'fontWeight': '600'
                },
                {
                    'if': {'column_id': 'Participación (%)'},
                    'textAlign': 'right',
                    'fontWeight': '600'
                }
            ],
            
            # CSS para paginación
            css=[{
                'selector': '.previous-next-container',
                'rule': 'display: flex; justify-content: center; margin-top: 10px;'
            }]
        ),
        
        # FILA DE TOTALES (ajustada para 4 columnas: Planta, Fuente, Generación, Participación)
        html.Div([
            dbc.Row([
                dbc.Col([
                    html.Strong("Total", style={'fontSize': '14px'})
                ], width=3),
                dbc.Col([
                    html.Span("")  # Columna vacía para Fuente
                ], width=3),
                dbc.Col([
                    html.Strong(f"{total_generacion:.2f}", 
                              style={'fontSize': '14px', 'textAlign': 'right', 'display': 'block'})
                ], width=3, style={'textAlign': 'right'}),
                dbc.Col([
                    html.Strong("100.00%",
                              style={'fontSize': '14px', 'textAlign': 'right', 'display': 'block'})
                ], width=3, style={'textAlign': 'right'})
            ], className="py-2 px-3", style={
                'backgroundColor': '#f8f9fa',
                'border': '2px solid #6c3fb5',
                'borderTop': '3px solid #6c3fb5',
                'fontWeight': 'bold'
            })
        ], className="mt-0")
    ])
    
    return tabla

# Función para agregar datos inteligentemente según el período
def agregar_datos_inteligente(df_generacion, dias_periodo):
    """
    Agrupa los datos según el período:
    - <= 60 días: datos diarios (sin cambios)
    - 61-180 días: datos semanales
    - > 180 días: datos mensuales
    """
    if df_generacion.empty:
        return df_generacion
    
    # Asegurar que Fecha sea datetime
    df_generacion['Fecha'] = pd.to_datetime(df_generacion['Fecha'])
    
    # Determinar nivel de agregación
    if dias_periodo <= 60:
        # Datos diarios - no cambiar
        return df_generacion
    elif dias_periodo <= 180:
        # Agrupar por semana
        df_generacion['Periodo'] = df_generacion['Fecha'].dt.to_period('W').dt.start_time
        periodo_label = 'Semana'
    else:
        # Agrupar por mes
        df_generacion['Periodo'] = df_generacion['Fecha'].dt.to_period('M').dt.start_time
        periodo_label = 'Mes'
    
    # Agregar datos
    columnas_grupo = ['Periodo']
    if 'Planta' in df_generacion.columns:
        columnas_grupo.append('Planta')
    if 'Codigo' in df_generacion.columns:
        columnas_grupo.append('Codigo')
    if 'Tipo' in df_generacion.columns:
        columnas_grupo.append('Tipo')
    
    df_agregado = df_generacion.groupby(columnas_grupo, as_index=False).agg({
        'Generacion_GWh': 'sum'
    })
    
    # Renombrar Periodo a Fecha
    df_agregado.rename(columns={'Periodo': 'Fecha'}, inplace=True)
    
    
    return df_agregado

# Función para crear fichas de generación renovable/no renovable según métricas XM
def crear_fichas_generacion_xm():
    """Crear fichas con datos reales de generación renovable y no renovable usando métricas oficiales de XM
    
    Metodología (según recomendación del usuario):
    1. Usar ListadoRecursos para identificar código → nombre de planta + tipo de fuente
    2. Con ese código identificado, sumar las 24 horas por cada planta y convertir a GWh (datos en kWh)
    3. Para generación total: sumar todos los tipos de fuente
    4. Para renovable: sumar solo renovables
    5. Para no renovable: sumar solo no renovables
    """
    # Deshabilitada temporalmente: usamos la versión parametrizada con fechas
    fin = date.today() - timedelta(days=3)
    inicio = fin - timedelta(days=365)
    return crear_fichas_generacion_xm_con_fechas(inicio, fin, 'TODAS')
    '''
        objetoAPI = get_objetoAPI()
        if objetoAPI is None:
            return dbc.Alert("API de XM no disponible", color="danger")
        
        
        # PASO 1: Obtener ListadoRecursos para mapear códigos (tolerante a fallas)
        codigo_info = {}
        try:
            # ✅ OPTIMIZADO: Usar obtener_datos_inteligente (SQLite)
            recursos_df, warning = obtener_datos_inteligente("ListadoRecursos", "Sistema", 
                                                              fecha_inicio.strftime('%Y-%m-%d'), 
                                                              fecha_fin.strftime('%Y-%m-%d'))
            if recursos_df is not None and not recursos_df.empty:
                for _, row in recursos_df.iterrows():
                    codigo = str(row.get('Values_Code', row.get('Values_SIC', '')))
                    if codigo:
                        codigo_info[str(codigo).upper()] = {
                            'nombre': str(row.get('Values_Name', row.get('Values_Resource_Name', codigo))),
                            'tipo': str(row.get('Values_Type', row.get('Values_Recurso', 'TERMICA'))).upper()
                        }
            else:
                recursos_df = pd.DataFrame()
        except Exception as e:
            recursos_df = pd.DataFrame()
        
        # PASO 2: Obtener datos de generación Gene/Recurso desde SQLite
        df_gene, warning = obtener_datos_inteligente("Gene", "Recurso", 
                                                      fecha_inicio.strftime('%Y-%m-%d'), 
                                                      fecha_fin.strftime('%Y-%m-%d'))
        
        if df_gene is None or df_gene.empty:
            return dbc.Alert("No se obtuvieron datos de generación", color="warning")
        
        
        # PASO 3: Sumar las 24 horas por cada planta y convertir a GWh
        horas_cols = [c for c in df_gene.columns if 'Hour' in str(c)]
        
        if not horas_cols:
            return dbc.Alert("No se encontraron columnas horarias en los datos", color="warning")
        
        
        # Identificar columna de código
        codigo_col = None
        for col in ['Values_code', 'Values_Code', 'Code']:
            if col in df_gene.columns:
                codigo_col = col
                break
        
        if not codigo_col:
            return dbc.Alert("No se encontró columna de código en los datos", color="warning")
        
        # Sumar 24 horas por cada fila (día) y convertir kWh → GWh
        df_gene['Generacion_Dia_GWh'] = df_gene[horas_cols].fillna(0).sum(axis=1) / 1_000_000
        
        # AGRUPAR por código y sumar TODOS LOS DÍAS del período
        df_agrupado = df_gene.groupby(codigo_col).agg({
            'Generacion_Dia_GWh': 'sum'  # Suma de todos los días
        }).reset_index()
        
        
        # Renombrar para compatibilidad
        df_agrupado.rename(columns={'Generacion_Dia_GWh': 'Generacion_GWh'}, inplace=True)
        df_gene = df_agrupado  # Reemplazar con datos agrupados
        
        # Mapear códigos a nombres y tipos (con fallback heurístico)
        df_gene['Codigo_Upper'] = df_gene[codigo_col].astype(str).str.upper()
        if codigo_info:
            df_gene['Nombre_Planta'] = df_gene['Codigo_Upper'].map(lambda x: codigo_info.get(x, {}).get('nombre', x))
            df_gene['Tipo_Fuente'] = df_gene['Codigo_Upper'].map(lambda x: codigo_info.get(x, {}).get('tipo', 'TERMICA'))
        else:
            # Heurística básica por prefijo/letra del código XM
            def mapear_basico(codigo):
                cs = str(codigo).upper()
                if cs.startswith('H') or 'PCH' in cs:
                    return 'HIDRAULICA'
                if cs.startswith('E'):
                    return 'EOLICA'
                if cs.startswith('S'):
                    return 'SOLAR'
                if cs.startswith('B') or 'COG' in cs:
                    return 'BIOMASA'
                return 'TERMICA'
            df_gene['Nombre_Planta'] = df_gene['Codigo_Upper']
            df_gene['Tipo_Fuente'] = df_gene['Codigo_Upper'].apply(mapear_basico)
        
        
        # FILTRAR POR TIPO DE FUENTE si no es "TODAS"
        if tipo_fuente != 'TODAS':
            df_gene = df_gene[df_gene['Tipo_Fuente'] == tipo_fuente]
            
            if df_gene.empty:
                return dbc.Alert(f"No hay datos para el tipo de fuente {tipo_fuente} en el período seleccionado", color="warning")
        
        # PASO 4: Clasificar renovable vs no renovable según XM
        
        def es_renovable_xm(tipo):
            """Clasificación oficial XM de fuentes renovables"""
            tipo_str = str(tipo).upper()
            renovables = ['HIDRAULICA', 'HIDRO', 'PCH', 'EOLICA', 'EOLIC', 
                         'SOLAR', 'FOTOVOLTAICA', 'FV', 'BIOMASA', 'COGENERADOR', 
                         'BAGAZO', 'BIOGAS']
            return any(ren in tipo_str for ren in renovables)
        
        df_gene['Es_Renovable'] = df_gene['Tipo_Fuente'].apply(es_renovable_xm)
        
        # PASO 5: Calcular totales
        
        # Calcular totales en GWh - CONVERSIÓN EXPLÍCITA A FLOAT
        gen_total = float(df_gene['Generacion_GWh'].sum())
        gen_renovable = float(df_gene[df_gene['Es_Renovable'] == True]['Generacion_GWh'].sum())
        gen_no_renovable = float(df_gene[df_gene['Es_Renovable'] == False]['Generacion_GWh'].sum())
        
        # Calcular porcentajes - CONVERSIÓN EXPLÍCITA A FLOAT
        pct_renovable = float((gen_renovable / gen_total * 100) if gen_total > 0 else 0)
        pct_no_renovable = float((gen_no_renovable / gen_total * 100) if gen_total > 0 else 0)
        
        
        # Usar fechas del período consultado
        fecha_dato_inicio = fecha_inicio
        fecha_dato_fin = fecha_fin
        
        # DEBUG: Verificar valores antes de crear HTML
        
        # Formatear valores como strings simples y aplicar fallbacks seguros
        def _fmt(v: float) -> str:
            try:
                s = f"{float(v):.1f}"
                # Evitar mostrar 'nan' o valores vacíos
                if s.lower() == 'nan' or s.strip() == '':
                    return '—'
                return s
            except Exception:
                return '—'

        valor_total = _fmt(gen_total)
        valor_renovable = _fmt(gen_renovable)
        valor_no_renovable = _fmt(gen_no_renovable)
        porcentaje_renovable = _fmt(pct_renovable)
        porcentaje_no_renovable = _fmt(pct_no_renovable)
        
        
        # Formatear fechas como string
        fecha_inicio_str = fecha_dato_inicio.strftime('%d/%m/%Y')
        fecha_fin_str = fecha_dato_fin.strftime('%d/%m/%Y')
        periodo_texto = f"{fecha_inicio_str} - {fecha_fin_str}"
        
        # Determinar título según filtro
        if tipo_fuente == 'TODAS':
            titulo_generacion = "Generación Total SIN"
        else:
            titulo_generacion = f"Generación {TIPOS_FUENTE.get(tipo_fuente, {}).get('label', tipo_fuente)}"
        
    # Crear las fichas HTML COMPACTAS con layout HORIZONTAL
        return dbc.Row([
            # Ficha Generación Total
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-bolt", style={'color': '#111827', 'fontSize': '0.9rem', 'marginRight': '6px'}),
                            html.Span(titulo_generacion, style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Span(valor_total, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#111827', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Small(periodo_texto, style={'color': '#999', 'fontSize': '0.6rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': '#ffffff', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, className="mb-2"),

            # Ficha Renovable
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-leaf", style={'color': '#000000', 'fontSize': '0.9rem', 'marginRight': '6px'}),
                            html.Span("Renovable", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Span(valor_renovable, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '4px'}),
                            html.Span(f"{porcentaje_renovable}% del total", className="badge bg-success", style={'fontSize': '0.6rem', 'padding': '0.15rem 0.4rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, className="mb-2"),
            
            # Ficha No Renovable
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-industry", style={'color': '#000000', 'fontSize': '0.9rem', 'marginRight': '6px'}),
                            html.Span("No Renovable", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Span(valor_no_renovable, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '4px'}),
                            html.Span(f"{porcentaje_no_renovable}% del total", className="badge bg-danger", style={'fontSize': '0.6rem', 'padding': '0.15rem 0.4rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, className="mb-2")
        ])
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return dbc.Alert(f"Error al cargar las fichas de generación: {str(e)}", color="danger")

'''
def crear_grafica_barras_apiladas():
    """Crear gráfica de barras apiladas por fuente de energía como en SinergoX"""
    try:
        px, go = get_plotly_modules()
        from infrastructure.external.xm_service import obtener_datos_inteligente
        
        fecha_fin = date.today() - timedelta(days=1)
        fecha_inicio = fecha_fin - timedelta(days=30)  # Últimos 30 días
        
        
        df_gene, warning = obtener_datos_inteligente('Gene', 'Recurso', 
                                                      fecha_inicio.strftime('%Y-%m-%d'), 
                                                      fecha_fin.strftime('%Y-%m-%d'))
        
        if df_gene is None or df_gene.empty:
            return go.Figure().add_annotation(
                text="No hay datos disponibles para la gráfica de barras",
                xref="paper", yref="paper", x=0.5, y=0.5
            )
        
        # Procesar datos horarios correctamente
        df_gene['Date'] = pd.to_datetime(df_gene['Date'])
        horas_cols = [c for c in df_gene.columns if str(c).startswith('Values_Hour')]
        
        if not horas_cols:
            return go.Figure().add_annotation(
                text="No se encontraron datos horarios",
                xref="paper", yref="paper", x=0.5, y=0.5
            )
        
        # Calcular generación total diaria por recurso
        df_gene['Generacion_GWh'] = df_gene[horas_cols].fillna(0).sum(axis=1) / 1_000_000  # ✅ FIX: kWh → GWh
        
        # El mapeo de 'Tipo' ya se hizo en la sección anterior, no necesitamos hacer nada más aquí
        
        # Categorizar fuentes según clasificación oficial XM
        def categorizar_fuente_xm(tipo):
            tipo_str = str(tipo).upper()
            if any(x in tipo_str for x in ['HIDRAULICA', 'HIDRO', 'PCH', 'PEQUEÑA CENTRAL']):
                return 'Hidráulica'
            elif any(x in tipo_str for x in ['EOLICA', 'EOLIC', 'WIND', 'VIENTO']):
                return 'Eólica'
            elif any(x in tipo_str for x in ['SOLAR', 'FOTOVOLTAICA', 'PHOTOVOLTAIC', 'FV']):
                return 'Solar'
            elif any(x in tipo_str for x in ['TERMICA', 'TERMO', 'GAS', 'CARBON', 'CICLO COMBINADO', 'VAPOR']):
                return 'Térmica'
            elif any(x in tipo_str for x in ['BIOMASA', 'COGENER', 'BAGAZO', 'BIOGAS', 'BIO']):
                return 'Biomasa'
            else:
                return 'Otras'
        
        # Obtener ListadoRecursos para mapear tipos
        objetoAPI = get_objetoAPI()
        if objetoAPI:
            try:
                # ✅ OPTIMIZADO: Usar obtener_datos_inteligente (SQLite)
                recursos_df, warning = obtener_datos_inteligente("ListadoRecursos", "Sistema", 
                                                                  fecha_inicio.strftime('%Y-%m-%d'), 
                                                                  fecha_fin.strftime('%Y-%m-%d'))
                if recursos_df is not None and not recursos_df.empty:
                    codigo_tipo = {}
                    for _, row in recursos_df.iterrows():
                        codigo = str(row.get('Values_Code', ''))
                        tipo = str(row.get('Values_Type', 'TERMICA')).upper()
                        if codigo:
                            codigo_tipo[codigo.upper()] = tipo
                    
                    codigo_col = None
                    for col in ['Values_code', 'Values_Code', 'Code']:
                        if col in df_gene.columns:
                            codigo_col = col
                            break
                    
                    if codigo_col:
                        df_gene['Tipo'] = df_gene[codigo_col].astype(str).str.upper().map(codigo_tipo).fillna('TERMICA')
                    else:
                        df_gene['Tipo'] = 'TERMICA'
                else:
                    df_gene['Tipo'] = 'TERMICA'
            except Exception as e:
                df_gene['Tipo'] = 'TERMICA'
        else:
            df_gene['Tipo'] = 'TERMICA'
        
        df_gene['Fuente'] = df_gene['Tipo'].apply(categorizar_fuente_xm)
        
        # Agrupar por fecha y fuente
        df_agrupado = df_gene.groupby(['Date', 'Fuente'], as_index=False)['Generacion_GWh'].sum()
        
        # Colores oficiales tipo SinergoX
        colores_xm = {
            'Hidráulica': '#1f77b4',    # Azul
            'Térmica': '#ff7f0e',       # Naranja
            'Eólica': '#2ca02c',        # Verde
            'Solar': '#ffbb33',         # Amarillo
            'Biomasa': '#17becf',       # Cian
            'Otras': '#7f7f7f'          # Gris
        }
        
        # Crear gráfica de barras apiladas
        fig = px.bar(
            df_agrupado, 
            x='Date', 
            y='Generacion_GWh', 
            color='Fuente',
            title="Generación Diaria por Fuente de Energía (SIN)",
            labels={'Generacion_GWh': 'Generación (GWh)', 'Date': 'Fecha', 'Fuente': 'Tipo de Fuente'},
            color_discrete_map=colores_xm,
            hover_data={'Generacion_GWh': ':.2f'}
        )
        
        # Personalizar hover template para mostrar información detallada
        fig.update_traces(
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'Fecha: %{x|%d/%m/%Y}<br>' +
                         'Generación: %{y:.2f} GWh<br>' +
                         'Fuente de Energía: %{fullData.name}<br>' +
                         '<extra></extra>'
        )
        
        fig.update_layout(
            hovermode='x unified',
            template='plotly_white',
            height=110,
            showlegend=True,
            xaxis_title="",
            yaxis_title="",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.01,
                xanchor="right",
                x=1,
                font=dict(size=7)
            ),
            margin=dict(l=30, r=10, t=5, b=25),
            xaxis=dict(tickfont=dict(size=7)),
            yaxis=dict(tickfont=dict(size=7))
        )
        
        return fig
        
    except Exception as e:
        return go.Figure().add_annotation(
            text=f"Error: {str(e)}",
            xref="paper", yref="paper", x=0.5, y=0.5
        )

def crear_grafica_area():
    """Crear gráfica de área temporal por fuente como en SinergoX"""
    try:
        px, go = get_plotly_modules()
        from infrastructure.external.xm_service import obtener_datos_inteligente
        
        fecha_fin = date.today() - timedelta(days=1)
        fecha_inicio = fecha_fin - timedelta(days=7)  # Últimos 7 días para mejor visualización horaria
        
        
        df_gene, warning = obtener_datos_inteligente('Gene', 'Recurso', 
                                                      fecha_inicio.strftime('%Y-%m-%d'), 
                                                      fecha_fin.strftime('%Y-%m-%d'))
        
        if df_gene is None or df_gene.empty:
            return go.Figure().add_annotation(
                text="No hay datos disponibles para la gráfica de área",
                xref="paper", yref="paper", x=0.5, y=0.5
            )
        
        # Procesar datos horarios correctamente
        df_gene['Date'] = pd.to_datetime(df_gene['Date'])
        
        # Mapear códigos XM a tipos de fuente usando listado de recursos
        try:
            recursos_df = obtener_listado_recursos()
            if recursos_df is not None and not recursos_df.empty:
                codigo_tipo_map = {}
                for _, row in recursos_df.iterrows():
                    codigo = row.get('Values_Code', row.get('Values_SIC', ''))
                    tipo = row.get('Values_Type', row.get('Values_Recurso', 'TERMICA'))
                    if codigo and tipo:
                        codigo_tipo_map[str(codigo).upper()] = str(tipo).upper()
                
                df_gene['Tipo'] = df_gene['Values_code'].map(
                    lambda x: codigo_tipo_map.get(str(x).upper(), 'TERMICA')
                )
            else:
                # Mapeo básico por código
                def mapear_basico(codigo):
                    codigo_str = str(codigo).upper()
                    if 'H' in codigo_str or 'PCH' in codigo_str:
                        return 'HIDRAULICA'
                    elif 'E' in codigo_str:
                        return 'EOLICA'
                    elif 'S' in codigo_str:
                        return 'SOLAR'
                    elif 'B' in codigo_str:
                        return 'BIOMASA'
                    else:
                        return 'TERMICA'
                
                df_gene['Tipo'] = df_gene['Values_code'].apply(mapear_basico)
                
        except Exception as e:
            return go.Figure().add_annotation(
                text="Error procesando códigos de fuente",
                xref="paper", yref="paper", x=0.5, y=0.5
            )
        
        # Expandir datos horarios con mejor procesamiento
        datos_expandidos = []
        horas_cols = [c for c in df_gene.columns if str(c).startswith('Values_Hour')]
        
        for _, row in df_gene.iterrows():
            for col_hora in horas_cols:
                if col_hora in df_gene.columns and not pd.isna(row[col_hora]) and row[col_hora] > 0:
                    # Extraer número de hora del nombre de columna (Values_Hour01, Values_Hour02, etc.)
                    hora_str = col_hora.replace('Values_Hour', '')
                    hora_num = int(hora_str) - 1  # Ajustar índice (01 -> 0, 02 -> 1, etc.)
                    fecha_hora = row['Date'] + timedelta(hours=hora_num)
                    
                    datos_expandidos.append({
                        'Fecha': fecha_hora,
                        'Tipo': row['Tipo'],
                        'Generacion_MW': row[col_hora]
                    })
        
        if not datos_expandidos:
            # Fallback a datos diarios si no hay horarios
            df_gene['Generacion_GWh'] = df_gene[horas_cols].fillna(0).sum(axis=1) / 1_000_000 if horas_cols else df_gene.get('Values_gwh', 0)  # ✅ FIX: kWh → GWh
            
            def categorizar_fuente_xm(tipo):
                tipo_str = str(tipo).upper()
                if any(x in tipo_str for x in ['HIDRAULICA', 'HIDRO', 'PCH']):
                    return 'Hidráulica'
                elif any(x in tipo_str for x in ['EOLICA', 'EOLIC', 'WIND']):
                    return 'Eólica'
                elif any(x in tipo_str for x in ['SOLAR', 'FOTOVOLTAICA', 'FV']):
                    return 'Solar'
                elif any(x in tipo_str for x in ['TERMICA', 'TERMO', 'GAS', 'CARBON']):
                    return 'Térmica'
                elif any(x in tipo_str for x in ['BIOMASA', 'COGENER', 'BAGAZO']):
                    return 'Biomasa'
                else:
                    return 'Otras'
            
            df_gene['Fuente'] = df_gene['Tipo'].apply(categorizar_fuente_xm)
            df_agrupado = df_gene.groupby(['Date', 'Fuente'], as_index=False)['Generacion_GWh'].sum()
            
            # Colores oficiales tipo SinergoX
            colores_xm = {
                'Hidráulica': '#1f77b4',
                'Térmica': '#ff7f0e', 
                'Eólica': '#2ca02c',
                'Solar': '#ffbb33',
                'Biomasa': '#17becf',
                'Otras': '#7f7f7f'
            }
            
            fig = px.area(
                df_agrupado, 
                x='Date', 
                y='Generacion_GWh', 
                color='Fuente',
                title="Evolución Diaria de la Generación por Fuente (SIN)",
                labels={'Generacion_GWh': 'Generación (GWh)', 'Date': 'Fecha'},
                color_discrete_map=colores_xm,
                hover_data={'Generacion_GWh': ':.2f'}
            )
            
            # Personalizar hover template
            fig.update_traces(
                hovertemplate='<b>%{fullData.name}</b><br>' +
                             'Fecha: %{x|%d/%m/%Y}<br>' +
                             'Generación: %{y:.2f} GWh<br>' +
                             'Tipo: Fuente %{fullData.name}<br>' +
                             '<extra></extra>'
            )
        else:
            # Procesar datos horarios expandidos
            df_expandido = pd.DataFrame(datos_expandidos)
            
            # Categorizar fuentes según clasificación oficial XM
            def categorizar_fuente_xm(tipo):
                tipo_str = str(tipo).upper()
                if any(x in tipo_str for x in ['HIDRAULICA', 'HIDRO', 'PCH']):
                    return 'Hidráulica'
                elif any(x in tipo_str for x in ['EOLICA', 'EOLIC', 'WIND']):
                    return 'Eólica'
                elif any(x in tipo_str for x in ['SOLAR', 'FOTOVOLTAICA', 'FV']):
                    return 'Solar'
                elif any(x in tipo_str for x in ['TERMICA', 'TERMO', 'GAS', 'CARBON']):
                    return 'Térmica'
                elif any(x in tipo_str for x in ['BIOMASA', 'COGENER', 'BAGAZO']):
                    return 'Biomasa'
                else:
                    return 'Otras'
            
            df_expandido['Fuente'] = df_expandido['Tipo'].apply(categorizar_fuente_xm)
            df_agrupado = df_expandido.groupby(['Fecha', 'Fuente'], as_index=False)['Generacion_MW'].sum()
            
            # Colores oficiales tipo SinergoX
            colores_xm = {
                'Hidráulica': '#1f77b4',
                'Térmica': '#ff7f0e',
                'Eólica': '#2ca02c',
                'Solar': '#ffbb33',
                'Biomasa': '#17becf',
                'Otras': '#7f7f7f'
            }
            
            fig = px.area(
                df_agrupado, 
                x='Fecha', 
                y='Generacion_MW', 
                color='Fuente',
                title="Evolución Horaria de la Generación por Fuente (SIN) - Últimos 7 días",
                labels={'Generacion_MW': 'Generación (MW)', 'Fecha': 'Fecha y Hora'},
                color_discrete_map=colores_xm,
                hover_data={'Generacion_MW': ':.1f'}
            )
            
            # Personalizar hover template para datos horarios
            fig.update_traces(
                hovertemplate='<b>%{fullData.name}</b><br>' +
                             'Fecha/Hora: %{x|%d/%m/%Y %H:%M}<br>' +
                             'Generación: %{y:.1f} MW<br>' +
                             'Equivalente: %{customdata:.3f} GWh<br>' +
                             '<extra></extra>',
                customdata=df_agrupado['Generacion_MW'] / 1000  # Convertir MW a GWh para mostrar
            )
        
        fig.update_layout(
            hovermode='x unified',
            template='plotly_white',
            height=110,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.01,
                xanchor="right",
                x=1,
                font=dict(size=7)
            ),
            xaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                tickfont=dict(size=7),
                title=""
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='lightgray',
                tickfont=dict(size=7),
                title=""
            ),
            margin=dict(l=30, r=10, t=5, b=25)
        )
        return fig
        
    except Exception as e:
        return go.Figure().add_annotation(
            text=f"Error: {str(e)}",
            xref="paper", yref="paper", x=0.5, y=0.5
        )

# FUNCIÓN ELIMINADA - causaba errores

def crear_tabla_resumen_todas_plantas_DISABLED(df, fecha_inicio, fecha_fin):
    """Crear tabla de plantas usando el DataFrame ya cargado del período seleccionado"""
    try:
        if df is None or df.empty:
            return html.Div("No hay datos disponibles", className="alert alert-warning")
        
        # Copiar para no modificar el original
        df_tabla = df.copy()
        
        # Validar columnas necesarias
        columnas_requeridas = ['Codigo', 'Planta', 'Generacion_GWh']
        if not all(col in df_tabla.columns for col in columnas_requeridas):
            return html.Div("Datos incompletos para mostrar la tabla", className="alert alert-warning")
        
        # Determinar columnas de agrupación (incluir Tipo si existe)
        cols_agrupacion = ['Codigo', 'Planta']
        if 'Tipo' in df_tabla.columns:
            cols_agrupacion.append('Tipo')
        
        # Agrupar por planta
        df_resumen = df_tabla.groupby(cols_agrupacion, as_index=False).agg({
            'Generacion_GWh': 'sum'
        })
        
        # Filtrar solo plantas con generación > 0
        df_resumen = df_resumen[df_resumen['Generacion_GWh'] > 0]
        
        # Ordenar por generación descendente
        df_resumen = df_resumen.sort_values('Generacion_GWh', ascending=False)
        
        # Calcular participación
        total_generacion = df_resumen['Generacion_GWh'].sum()
        df_resumen['Participacion'] = (df_resumen['Generacion_GWh'] / total_generacion * 100)
        
        # Agregar posición
        df_resumen.insert(0, 'Posición', range(1, len(df_resumen) + 1))
        
        # Renombrar columnas para display
        rename_dict = {
            'Generacion_GWh': 'Generación (GWh)',
            'Participacion': 'Participación (%)'
        }
        if 'Tipo' in df_resumen.columns:
            rename_dict['Tipo'] = 'Fuente'
        
        df_resumen = df_resumen.rename(columns=rename_dict)
        
        # Formatear valores numéricos
        df_resumen['Generación (GWh)'] = df_resumen['Generación (GWh)'].round(2)
        df_resumen['Participación (%)'] = df_resumen['Participación (%)'].round(2)
        
        # Definir colores por fuente
        color_map = {
            'Hidráulica': '#3498db',
            'Térmica': '#e74c3c',
            'Eólica': '#9b59b6',
            'Solar': '#f39c12',
            'Biomasa': '#27ae60'
        }
        
        # Función para aplicar color por fila
        def get_row_style(fuente):
            color = color_map.get(fuente, '#95a5a6')
            return {
                'backgroundColor': f'{color}15',
                'borderLeft': f'4px solid {color}'
            }
        
        # Definir columnas dinámicamente
        columnas_tabla = [
            {'name': 'Posición', 'id': 'Posición'},
            {'name': 'Planta', 'id': 'Planta'}
        ]
        
        # Agregar columna Fuente solo si existe
        if 'Fuente' in df_resumen.columns:
            columnas_tabla.append({'name': 'Fuente', 'id': 'Fuente'})
        
        columnas_tabla.extend([
            {'name': 'Generación (GWh)', 'id': 'Generación (GWh)', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Participación (%)', 'id': 'Participación (%)', 'type': 'numeric', 'format': {'specifier': '.2f'}}
        ])
        
        # Crear DataTable con estilos modernos
        tabla = dash_table.DataTable(
            data=df_resumen.to_dict('records'),
            columns=columnas_tabla,
            style_table={
                'overflowX': 'auto',
                'borderRadius': '8px',
                'boxShadow': '0 2px 8px rgba(0,0,0,0.1)'
            },
            style_cell={
                'textAlign': 'left',
                'padding': '12px 16px',
                'fontSize': '14px',
                'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif',
                'border': 'none',
                'borderBottom': '1px solid #e0e0e0'
            },
            style_header={
                'backgroundColor': '#f8f9fa',
                'color': '#2c3e50',
                'fontWeight': '600',
                'textAlign': 'center',
                'border': 'none',
                'borderBottom': '2px solid #dee2e6',
                'padding': '14px 16px'
            },
            style_data_conditional=[
                {
                    'if': {'filter_query': '{Fuente} = "Hidráulica"'},
                    'backgroundColor': f'{color_map["Hidráulica"]}15',
                    'borderLeft': f'4px solid {color_map["Hidráulica"]}'
                },
                {
                    'if': {'filter_query': '{Fuente} = "Térmica"'},
                    'backgroundColor': f'{color_map["Térmica"]}15',
                    'borderLeft': f'4px solid {color_map["Térmica"]}'
                },
                {
                    'if': {'filter_query': '{Fuente} = "Eólica"'},
                    'backgroundColor': f'{color_map["Eólica"]}15',
                    'borderLeft': f'4px solid {color_map["Eólica"]}'
                },
                {
                    'if': {'filter_query': '{Fuente} = "Solar"'},
                    'backgroundColor': f'{color_map["Solar"]}15',
                    'borderLeft': f'4px solid {color_map["Solar"]}'
                },
                {
                    'if': {'filter_query': '{Fuente} = "Biomasa"'},
                    'backgroundColor': f'{color_map["Biomasa"]}15',
                    'borderLeft': f'4px solid {color_map["Biomasa"]}'
                },
                {
                    'if': {'row_index': 'odd'},
                    'backgroundColor': '#fafafa'
                }
            ],
            page_size=10,
            sort_action='native',
            filter_action='native',
            style_as_list_view=True
        )
        
        # Formatear fechas para el encabezado (pueden venir como string o date)
        from datetime import date as date_type
        if isinstance(fecha_inicio, str):
            fecha_inicio_str = fecha_inicio
        else:
            fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
            
        if isinstance(fecha_fin, str):
            fecha_fin_str = fecha_fin
        else:
            fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')
        
        return html.Div([
            html.P(
                f"Período: {fecha_inicio_str} a {fecha_fin_str} | Total: {total_generacion:.2f} GWh | {len(df_resumen)} plantas",
                className="text-muted text-center mb-3"
            ),
            tabla
        ])
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return html.Div(f"Error generando tabla: {str(e)}", className="alert alert-danger")

def crear_tabla_resumen_todas_plantas():
    """Crear tabla resumen con todas las plantas de todas las fuentes (Top 20 por generación)"""
    try:
        from infrastructure.external.xm_service import obtener_datos_inteligente
        
        fecha_fin = date.today() - timedelta(days=1)
        fecha_inicio = fecha_fin - timedelta(days=7)  # Últimos 7 días
        
        
        df_gene, warning = obtener_datos_inteligente('Gene', 'Recurso', 
                                                      fecha_inicio.strftime('%Y-%m-%d'), 
                                                      fecha_fin.strftime('%Y-%m-%d'))
        
        if df_gene is None or df_gene.empty:
            return html.Div([
                dbc.Alert("No hay datos disponibles para la tabla de plantas", color="warning", className="text-center")
            ])
        
        # Procesar datos horarios para obtener generación total
        horas_cols = [c for c in df_gene.columns if str(c).startswith('Values_Hour')]
        
        if horas_cols:
            df_gene['Generacion_GWh'] = df_gene[horas_cols].fillna(0).sum(axis=1) / 1_000_000  # ✅ FIX: kWh → GWh
        else:
            df_gene['Generacion_GWh'] = df_gene.get('Values_gwh', 0)
        
        # Mapear códigos a tipos y obtener nombres de recursos
        try:
            recursos_df = obtener_listado_recursos()
            if recursos_df is not None and not recursos_df.empty:
                # Crear mapeo de código a tipo y nombre
                codigo_info_map = {}
                for _, row in recursos_df.iterrows():
                    codigo = row.get('Values_Code', row.get('Values_SIC', ''))
                    tipo = row.get('Values_Type', row.get('Values_Recurso', 'TERMICA'))
                    nombre = row.get('Values_Name', row.get('Values_Resource_Name', codigo))
                    if codigo:
                        codigo_info_map[str(codigo).upper()] = {
                            'tipo': str(tipo).upper(),
                            'nombre': str(nombre)
                        }
                
                
                # Aplicar mapeo
                df_gene['Tipo'] = df_gene['Values_code'].map(
                    lambda x: codigo_info_map.get(str(x).upper(), {}).get('tipo', 'TERMICA')
                )
                df_gene['Nombre_Recurso'] = df_gene['Values_code'].map(
                    lambda x: codigo_info_map.get(str(x).upper(), {}).get('nombre', str(x))
                )
                
                # Agrupar por código/nombre y tipo
                df_plantas = df_gene.groupby(['Nombre_Recurso', 'Tipo'], as_index=False)['Generacion_GWh'].sum()
                df_plantas.columns = ['Planta', 'Tipo', 'Generacion_GWh']
            else:
                # Usar códigos como nombres y mapeo básico para tipos
                def mapear_basico(codigo):
                    codigo_str = str(codigo).upper()
                    if 'H' in codigo_str:
                        return 'HIDRAULICA'
                    elif 'E' in codigo_str:
                        return 'EOLICA'
                    elif 'S' in codigo_str:
                        return 'SOLAR'
                    elif 'B' in codigo_str:
                        return 'BIOMASA'
                    else:
                        return 'TERMICA'
                
                df_gene['Tipo'] = df_gene['Values_code'].apply(mapear_basico)
                df_gene['Nombre_Recurso'] = df_gene['Values_code']  # Usar código como nombre
                
                df_plantas = df_gene.groupby(['Nombre_Recurso', 'Tipo'], as_index=False)['Generacion_GWh'].sum()
                df_plantas.columns = ['Planta', 'Tipo', 'Generacion_GWh']
                
        except Exception as e:
            return html.Div([
                dbc.Alert("Error procesando información de recursos", color="danger")
            ])
        df_plantas = df_plantas[df_plantas['Generacion_GWh'] > 0]  # Solo plantas con generación
        df_plantas = df_plantas.sort_values('Generacion_GWh', ascending=False)
        
        # Calcular participación
        total_gwh = df_plantas['Generacion_GWh'].sum()
        df_plantas['Participacion_%'] = (df_plantas['Generacion_GWh'] / total_gwh * 100).round(2)
        
        # Categorizar fuente usando clasificación oficial XM
        def categorizar_fuente_xm(tipo):
            tipo_str = str(tipo).upper()
            if any(x in tipo_str for x in ['HIDRAULICA', 'HIDRO', 'PCH']):
                return 'Hidráulica'
            elif any(x in tipo_str for x in ['EOLICA', 'EOLIC', 'WIND']):
                return 'Eólica'
            elif any(x in tipo_str for x in ['SOLAR', 'FOTOVOLTAICA', 'FV']):
                return 'Solar'
            elif any(x in tipo_str for x in ['TERMICA', 'TERMO', 'GAS', 'CARBON']):
                return 'Térmica'
            elif any(x in tipo_str for x in ['BIOMASA', 'COGENER', 'BAGAZO']):
                return 'Biomasa'
            else:
                return 'Otras'
        
        df_plantas['Fuente'] = df_plantas['Tipo'].apply(categorizar_fuente_xm)
        
        # Crear tabla estilo SinergoX
        tabla_data = []
        for i, (_, row) in enumerate(df_plantas.head(20).iterrows(), 1):
            tabla_data.append({
                'Posición': i,
                'Planta': row['Planta'],
                'Tipo': row['Tipo'],
                'Fuente': row['Fuente'],
                'Generación (GWh)': f"{row['Generacion_GWh']:,.2f}",
                'Participación (%)': f"{row['Participacion_%']:.2f}%"
            })
        
        # Crear DataTable con estilo mejorado
        from dash import dash_table
        tabla = dash_table.DataTable(
            data=tabla_data,
            columns=[
                {"name": "Pos.", "id": "Posición", "type": "numeric"},
                {"name": "Planta/Recurso", "id": "Planta", "type": "text"},
                {"name": "Tipo", "id": "Tipo", "type": "text"},
                {"name": "Fuente", "id": "Fuente", "type": "text"},
                {"name": "Generación (GWh)", "id": "Generación (GWh)", "type": "numeric"},
                {"name": "Participación (%)", "id": "Participación (%)", "type": "text"}
            ],
            style_cell={
                'textAlign': 'left',
                'fontFamily': 'Arial, sans-serif',
                'fontSize': '0.9rem',
                'padding': '12px 8px',
                'whiteSpace': 'normal',
                'height': 'auto'
            },
            style_header={
                'backgroundColor': '#f8f9fa',
                'fontWeight': 'bold',
                'textAlign': 'center',
                'border': '1px solid #dee2e6'
            },
            style_data={
                'backgroundColor': 'white',
                'border': '1px solid #dee2e6'
            },
            style_data_conditional=[
                {
                    'if': {'filter_query': '{Fuente} = Hidráulica'},
                    'backgroundColor': '#e3f2fd',
                    'color': 'black',
                },
                {
                    'if': {'filter_query': '{Fuente} = Eólica'},
                    'backgroundColor': '#e8f5e8',
                    'color': 'black',
                },
                {
                    'if': {'filter_query': '{Fuente} = Solar'},
                    'backgroundColor': '#fff8e1',
                    'color': 'black',
                },
                {
                    'if': {'filter_query': '{Fuente} = Térmica'},
                    'backgroundColor': '#ffebee',
                    'color': 'black',
                },
                {
                    'if': {'filter_query': '{Fuente} = Biomasa'},
                    'backgroundColor': '#e0f2f1',
                    'color': 'black',
                }
            ],
            sort_action="native",
            page_size=20,
            style_table={'overflowX': 'auto'}
        )
        
        return html.Div([
            html.H5("Top 20 Plantas por Generación - Últimos 7 días", 
                   className="mb-3 text-center text-primary"),
            tabla,
            html.P(f"Total generación período: {total_gwh:,.2f} GWh", 
                  className="text-muted text-center mt-2 small")
        ])
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return html.Div([
            dbc.Alert(f"Error generando tabla: {str(e)}", color="danger")
        ])

# Layout como función para ejecutar en cada carga
def layout():
    """Layout dinámico que se ejecuta cada vez que se carga la página"""
    
    return html.Div([
    # Estilos forzados para asegurar visibilidad de números KPI
    html.Link(rel='stylesheet', href='/assets/kpi-override.css'),
    # Interval que se ejecuta UNA VEZ al cargar para disparar callbacks
    # DESACTIVADO: API XM puede estar lenta - carga manual con botón
    # dcc.Interval(id='interval-carga-inicial', interval=500, n_intervals=0, max_intervals=1),
    
    # Store oculto para tracking
    dcc.Store(id='store-pagina-cargada', data={'loaded': True}),
    
    # ℹ️ Store 'store-datos-chatbot-generacion' ahora es GLOBAL (definido en app.py)
    # Todas las páginas pueden actualizarlo para dar contexto al chatbot
    
    # crear_navbar_horizontal(),
    
    # Contenido principal con padding reducido (sin zoom para evitar problemas de cursor)
    html.Div(id='generacion-fuentes-compact-wrapper', style={'maxWidth': '100%', 'padding': '5px'}, children=[
    dbc.Container([
        html.Div([
            dbc.Tabs(
                id="tabs-generacion-fuentes",
                active_tab="tab-analisis-general",
                children=[
                    dbc.Tab(label="Análisis General", tab_id="tab-analisis-general", tab_style={'padding': '0.3rem 0.8rem'}),
                    dbc.Tab(label="Comparación Anual", tab_id="tab-comparacion-anual", tab_style={'padding': '0.3rem 0.8rem'}),
                    dbc.Tab(label="Predicciones", tab_id="tab-predicciones", tab_style={'padding': '0.3rem 0.8rem'}),
                ],
                style={'fontSize': '0.8rem'}
            )
        ], style={'backgroundColor': 'white', 'padding': '3px 8px', 'borderRadius': '6px', 
                  'marginBottom': '8px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.08)'}),
        
        # ==================================================================
        # CONTENIDO TAB: ANÁLISIS GENERAL (contenido original completo)
        # ==================================================================
        html.Div(id='contenido-analisis-general', children=[
        
        # FILTROS UNIFICADOS EN UNA SOLA FILA HORIZONTAL
        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    # Selector de fuentes
                    dbc.Col([
                        html.Label("FUENTES:", style={'fontSize': '0.65rem', 'fontWeight': '600', 'marginBottom': '2px', 'color': '#2c3e50'}),
                        dcc.Dropdown(
                            id='tipo-fuente-dropdown',
                            options=[
                                {'label': '💧 Hidráulica', 'value': 'HIDRAULICA'},
                                {'label': '🔥 Térmica', 'value': 'TERMICA'},
                                {'label': '💨 Eólica', 'value': 'EOLICA'},
                                {'label': '☀️ Solar', 'value': 'SOLAR'},
                                {'label': '🌿 Biomasa', 'value': 'BIOMASA'},
                            ],
                            value=['HIDRAULICA', 'TERMICA', 'EOLICA', 'SOLAR', 'BIOMASA'],
                            multi=True,
                            placeholder="Seleccione fuentes...",
                            style={'fontSize': '0.75rem', 'minHeight': '32px'}
                        )
                    ], md=3),
                    
                    # Filtro de rango
                    dbc.Col([
                        html.Label("RANGO:", style={'fontSize': '0.65rem', 'fontWeight': '600', 'marginBottom': '2px', 'color': '#2c3e50'}),
                        dcc.Dropdown(
                            id='rango-fechas-fuentes',
                            options=[
                                {'label': 'Último mes', 'value': '1m'},
                                {'label': 'Últimos 6 meses', 'value': '6m'},
                                {'label': 'Último año', 'value': '1y'},
                                {'label': 'Últimos 2 años', 'value': '2y'},
                                {'label': 'Últimos 5 años', 'value': '5y'},
                                {'label': 'Personalizado', 'value': 'custom'}
                            ],
                            value='1y',
                            clearable=False,
                            style={'fontSize': '0.75rem', 'minHeight': '32px'}
                        )
                    ], md=2),
                    
                    # Fecha inicio (oculta por defecto)
                    dbc.Col([
                        html.Label("FECHA INICIO:", style={'fontSize': '0.65rem', 'fontWeight': '600', 'marginBottom': '2px', 'color': '#2c3e50'}),
                        dcc.DatePickerSingle(
                            id='fecha-inicio-fuentes',
                            date=(obtener_ultima_fecha_disponible() - timedelta(days=365)).strftime('%Y-%m-%d'),
                            display_format='DD/MM/YYYY',
                            style={'fontSize': '0.75rem'}
                        )
                    ], id='container-fecha-inicio-fuentes', md=2, style={'display': 'none'}),
                    
                    # Fecha fin (oculta por defecto)
                    dbc.Col([
                        html.Label("FECHA FIN:", style={'fontSize': '0.65rem', 'fontWeight': '600', 'marginBottom': '2px', 'color': '#2c3e50'}),
                        dcc.DatePickerSingle(
                            id='fecha-fin-fuentes',
                            date=obtener_ultima_fecha_disponible().strftime('%Y-%m-%d'),
                            display_format='DD/MM/YYYY',
                            style={'fontSize': '0.75rem'}
                        )
                    ], id='container-fecha-fin-fuentes', md=2, style={'display': 'none'}),
                    
                    # Botón actualizar
                    dbc.Col([
                        html.Label("\u00A0", style={'fontSize': '0.65rem', 'marginBottom': '2px', 'display': 'block'}),
                        dbc.Button(
                            [html.I(className="fas fa-sync-alt me-1"), "Actualizar"],
                            id="btn-actualizar-fuentes",
                            color="primary",
                            className="w-100",
                            style={'fontSize': '0.75rem', 'height': '32px'}
                        )
                    ], md=2)
                ], className="g-2 align-items-end")
            ], style={'padding': '8px 12px'})
        ], className="mb-2", style={'border': '1px solid #e0e0e0'}),
        
        # DEBUG: Div para verificar clics en botón
        html.Div(id='debug-clicks', style={'display': 'none'}),
        
        # FICHAS DE INDICADORES
        dcc.Loading(
            id="loading-fichas-generacion",
            type="circle",
            children=html.Div(id='contenedor-fichas-generacion', style={'marginBottom': '0'}, children=[
                # Mensaje inicial vacío - se llena con el callback
            ])
        ),
        
        # GRÁFICAS Y ANÁLISIS
        dcc.Loading(
            id="loading-fuentes",
            type="circle",
            children=html.Div(id="contenido-fuentes", style={'marginTop': '0'}, children=[
                dbc.Alert([
                    html.I(className="fas fa-spinner fa-spin me-2"),
                    html.Strong("⏳ Cargando datos de generación...")
                ], color="info", className="text-center py-3", style={'fontSize': '0.95rem'})
            ])
        ),
        
        ]),  # FIN contenido-analisis-general
        
        # ==================================================================
        # CONTENIDO TAB: COMPARACIÓN ANUAL
        # ==================================================================
        html.Div(id='contenido-comparacion-anual', style={'display': 'none'}, children=[
            
            # FILTRO MULTISELECTOR DE AÑOS (optimizado horizontalmente)
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.Small("Selecciona los años a comparar:", className="mb-1", 
                                   style={'fontWeight': '600', 'color': '#2c3e50', 'fontSize': '0.7rem'}),
                            dcc.Dropdown(
                                id='years-multiselector',
                                options=[{'label': str(y), 'value': y} for y in range(2021, 2026)],  # 2021-2025 (2020 datos incompletos)
                                value=[2024, 2025],  # Por defecto 2 años seleccionados
                                multi=True,  # Permite múltiples selecciones
                                placeholder="Selecciona uno o más años...",
                                clearable=False
                            ),
                            html.Small("Nota: Datos disponibles desde 2021 (año completo)", 
                                      className="text-muted", style={'fontSize': '0.7rem'})
                        ], md=9),
                        dbc.Col([
                            dbc.Button(
                                "Actualizar Comparación",
                                id='btn-actualizar-comparacion',
                                color="primary",
                                className="w-100",
                                style={'height': '38px'}
                            )
                        ], md=3, className="d-flex align-items-center")
                    ])
                ], className="p-2")
            ], className="mb-3"),
            
            # LAYOUT HORIZONTAL: Gráfica de líneas (70%) + Fichas por año (30%)
            dbc.Row([
                # COLUMNA IZQUIERDA: Gráfica de líneas temporales
                dbc.Col([
                    dcc.Loading(
                        id="loading-grafica-lineas-anual",
                        type="default",
                        children=html.Div([
                            html.H6("Evolución Temporal de Generación por Año", className="text-center mb-2",
                                   style={'fontWeight': '600', 'color': '#2c3e50', 'fontSize': '0.85rem'}),
                            dcc.Graph(id='grafica-lineas-temporal-anual', config={'displayModeBar': False})
                        ])
                    )
                ], md=8, className="pe-2"),
                
                # COLUMNA DERECHA: Fichas por año (scroll vertical si hay muchos años)
                dbc.Col([
                    html.H6("Resumen por Año", className="text-center mb-2",
                           style={'fontWeight': '600', 'color': '#2c3e50', 'fontSize': '0.85rem'}),
                    dcc.Loading(
                        id="loading-tortas-anuales",
                        type="default",
                        children=html.Div(
                            id='contenedor-tortas-anuales',
                            style={'maxHeight': '500px', 'overflowY': 'auto', 'paddingRight': '5px'}
                        )
                    )
                ], md=4, className="ps-2")
            ], className="mb-4")
        ]),  # FIN contenido-comparacion-anual
        
        # ==================================================================
        # CONTENIDO TAB: PREDICCIONES
        # ==================================================================
        html.Div(id='contenido-predicciones', style={'display': 'none'}, children=[
            
            # Título con botón de información
            html.Div([
                html.Div([
                    html.Span("Predicciones con Modelos de Machine Learning", 
                             style={'fontSize': '1.1rem', 'fontWeight': '600', 'color': '#2c3e50', 'marginRight': '10px'}),
                    html.Button(
                        "ℹ",
                        id="btn-info-predicciones",
                        style={
                            'background': '#F2C330',
                            'border': '2px solid #2C3E50',
                            'borderRadius': '50%',
                            'width': '28px',
                            'height': '28px',
                            'fontSize': '16px',
                            'fontWeight': 'bold',
                            'color': '#2C3E50',
                            'cursor': 'pointer',
                            'animation': 'pulse 2s ease-in-out infinite',
                            'padding': '0',
                            'display': 'inline-flex',
                            'alignItems': 'center',
                            'justifyContent': 'center'
                        },
                        n_clicks=0
                    )
                ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '15px'})
            ]),
            
            # Modal de información
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("INFORMACIÓN DEL SISTEMA DE PREDICCIONES")),
                dbc.ModalBody([
                    html.H6("Modelos utilizados:", style={'fontWeight': 'bold', 'marginTop': '10px'}),
                    html.Ul([
                        html.Li("Prophet: Análisis de tendencias y estacionalidad"),
                        html.Li("SARIMA: Validación estadística robusta")
                    ]),
                    
                    html.H6("Datos de entrenamiento:", style={'fontWeight': 'bold', 'marginTop': '15px'}),
                    html.Ul([
                        html.Li("Periodo histórico: 2020-2025 (5 años)"),
                        html.Li("Frecuencia de actualización: Diaria")
                    ]),
                    
                    html.H6("Predicciones generadas:", style={'fontWeight': 'bold', 'marginTop': '15px'}),
                    html.Ul([
                        html.Li("Horizonte: 90 días (3 meses adelante)"),
                        html.Li("Intervalo de confianza: 95%"),
                        html.Li("Las bandas sombreadas indican el rango probable del valor real")
                    ]),
                    
                    html.H6("Precisión actual (últimos 30 días):", style={'fontWeight': 'bold', 'marginTop': '15px'}),
                    html.Ul([
                        html.Li("Hidráulica: 91.4%"),
                        html.Li("Solar: 86.0%"),
                        html.Li("Térmica: 69.2%"),
                        html.Li("Eólica: 64.3%"),
                        html.Li("Biomasa: 82.0%")
                    ])
                ]),
                dbc.ModalFooter(
                    dbc.Button("Cerrar", id="close-modal-predicciones", className="ms-auto", n_clicks=0)
                )
            ], id="modal-info-predicciones", is_open=False, size="lg"),
            
            # MODAL: VALIDACIÓN DE PREDICCIÓN (CLICK EN PUNTO)
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle(id="titulo-modal-validacion")),
                dbc.ModalBody(id="contenido-modal-validacion", style={'padding': '15px'}),
                dbc.ModalFooter(
                    dbc.Button("Cerrar", id="close-modal-validacion", className="ms-auto", n_clicks=0)
                )
            ], id="modal-validacion-prediccion", is_open=False, size="xl"),
            
            # FILTROS DE PREDICCIÓN
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        # Selector de horizonte
                        dbc.Col([
                            html.Label("HORIZONTE DE PREDICCIÓN:", style={'fontSize': '0.65rem', 'fontWeight': '600', 'marginBottom': '2px', 'color': '#2c3e50'}),
                            dcc.Dropdown(
                                id='horizonte-prediccion',
                                options=[
                                    {'label': '📅 3 meses (Corto plazo)', 'value': 3},
                                    {'label': '📅 6 meses (Mediano plazo)', 'value': 6, 'disabled': True},
                                    {'label': '📅 12 meses (Largo plazo)', 'value': 12, 'disabled': True},
                                    {'label': '📅 24 meses (Muy largo plazo)', 'value': 24, 'disabled': True}
                                ],
                                value=3,
                                clearable=False,
                                style={'fontSize': '0.75rem', 'minHeight': '32px'}
                            ),
                            html.Small("Horizontes 6, 12 y 24 meses: En desarrollo", 
                                      className="text-muted", style={'fontSize': '0.65rem'})
                        ], md=4),
                        
                        # Selector de fuentes para predicción
                        dbc.Col([
                            html.Label("FUENTES A PREDECIR:", style={'fontSize': '0.65rem', 'fontWeight': '600', 'marginBottom': '2px', 'color': '#2c3e50'}),
                            dcc.Dropdown(
                                id='fuentes-prediccion',
                                options=[
                                    {'label': '💧 Hidráulica', 'value': 'Hidráulica'},
                                    {'label': '🔥 Térmica', 'value': 'Térmica'},
                                    {'label': '💨 Eólica', 'value': 'Eólica'},
                                    {'label': '☀️ Solar', 'value': 'Solar'},
                                    {'label': '🌿 Biomasa', 'value': 'Biomasa'},
                                ],
                                value=['Hidráulica', 'Térmica', 'Eólica', 'Solar', 'Biomasa'],
                                multi=True,
                                style={'fontSize': '0.75rem', 'minHeight': '32px'}
                            )
                        ], md=5),
                        
                        # Botón cargar predicciones
                        dbc.Col([
                            html.Label("\u00A0", style={'fontSize': '0.65rem', 'marginBottom': '2px', 'display': 'block'}),
                            dbc.Button(
                                [html.I(className="fas fa-magic me-1"), "Generar Predicciones"],
                                id="btn-cargar-predicciones",
                                color="success",
                                className="w-100",
                                style={'fontSize': '0.75rem', 'height': '32px'}
                            )
                        ], md=3)
                    ], className="g-2 align-items-end")
                ], style={'padding': '8px 12px'})
            ], className="mb-3", style={'border': '1px solid #e0e0e0'}),
            
            # FICHAS DE PREDICCIÓN
            dcc.Loading(
                id="loading-fichas-prediccion",
                type="circle",
                children=html.Div(id='contenedor-fichas-prediccion', style={'marginBottom': '10px'})
            ),
            
            # GRÁFICAS DE PREDICCIÓN
            dcc.Loading(
                id="loading-graficas-prediccion",
                type="circle",
                children=html.Div(id="contenido-graficas-prediccion", children=[
                    dbc.Alert([
                        html.I(className="fas fa-chart-line me-2"),
                        "Selecciona horizonte y fuentes, luego haz clic en 'Generar Predicciones'"
                    ], color="secondary", className="text-center py-2", style={'fontSize': '0.9rem'})
                ])
            ),
            
        ]),  # FIN contenido-predicciones
        
    ], fluid=True, style={'paddingTop': '0.5rem', 'paddingBottom': '0.5rem'})
    ])  # FIN wrapper compacto zoom
    
    ], style={'backgroundColor': COLORS['bg_main'], 'minHeight': '100vh'})
    
# Fin de la función layout() - Las fichas se generan directamente

# ==================================================================
# CALLBACK PRINCIPAL: Cambiar contenido según tab activo
# ==================================================================
@callback(
    [Output('contenido-analisis-general', 'style'),
     Output('contenido-comparacion-anual', 'style'),
     Output('contenido-predicciones', 'style')],
    [Input('tabs-generacion-fuentes', 'active_tab')]
)
def cambiar_contenido_tabs(active_tab):
    """Muestra/oculta contenido según el tab seleccionado"""
    if active_tab == 'tab-comparacion-anual':
        return {'display': 'none'}, {'display': 'block'}, {'display': 'none'}
    elif active_tab == 'tab-predicciones':
        return {'display': 'none'}, {'display': 'none'}, {'display': 'block'}
    else:  # tab-analisis-general (por defecto)
        return {'display': 'block'}, {'display': 'none'}, {'display': 'none'}

# Callbacks para gráficas principales

# Registrar callback del filtro de fechas
registrar_callback_filtro_fechas('fuentes')

@callback(
    Output("grafica-barras-apiladas", "figure"),
    Input("grafica-barras-apiladas", "id"),
    prevent_initial_call=True  # ⚡ NO ejecutar al cargar página
)
def cargar_grafica_barras_apiladas(_):
    """Cargar gráfica de barras apiladas - LAZY LOAD"""
    return crear_grafica_barras_apiladas()

@callback(
    Output('grafica-torta-fuentes', 'figure'),
    [Input('grafica-temporal-fuentes', 'clickData')],
    [State('store-datos-fuentes', 'data')],
    prevent_initial_call=True
)
def actualizar_torta_por_click(clickData, stored_data):
    """
    Actualiza el gráfico de torta cuando el usuario hace click en una barra del gráfico apilado.
    Muestra la composición por fuente para el día seleccionado.
    """
    
    if not clickData or not stored_data:
        raise PreventUpdate
    
    try:
        # Extraer la fecha del click
        fecha_click_str = clickData['points'][0]['x']
        fecha_click = pd.to_datetime(fecha_click_str).date()
        
        # Recuperar datos del store
        df_por_fuente = pd.read_json(StringIO(stored_data['df_por_fuente']), orient='split')
        df_por_fuente['Fecha'] = pd.to_datetime(df_por_fuente['Fecha']).dt.date
        grouping_col = stored_data['grouping_col']
        tipo_fuente = stored_data['tipo_fuente']
        
        
        # Crear nuevo gráfico de torta para la fecha seleccionada
        nueva_figura = crear_grafica_torta_fuentes(df_por_fuente, fecha_click, grouping_col, tipo_fuente)
        
        return nueva_figura
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise PreventUpdate


@callback(
    Output("grafica-area", "figure"),
    Input("grafica-area", "id"),
    prevent_initial_call=True  # ⚡ NO ejecutar al cargar página
)
def cargar_grafica_area(_):
    """Cargar gráfica de área - LAZY LOAD"""
    return crear_grafica_area()

@callback(
    Output("tabla-resumen-todas-plantas", "children"),
    Input("tabla-resumen-todas-plantas", "id"),
    prevent_initial_call=True  # ⚡ NO ejecutar al cargar página
)
def cargar_tabla_resumen(_):
    """Cargar tabla resumen de todas las plantas - LAZY LOAD"""
    return crear_tabla_resumen_todas_plantas()

# Callback UNIFICADO - Carga automática de FICHAS + GRÁFICAS + DATOS CHATBOT
@callback(
    [Output('contenedor-fichas-generacion', 'children'),
     Output('contenido-fuentes', 'children'),
     Output('store-datos-chatbot-generacion', 'data')],
    Input('btn-actualizar-fuentes', 'n_clicks'),
    [State('tipo-fuente-dropdown', 'value'),
     State('fecha-inicio-fuentes', 'date'),
     State('fecha-fin-fuentes', 'date')],
    prevent_initial_call=False  # ✅ Permite carga automática al inicio
)
def actualizar_tablero_fuentes(n_clicks, tipos_fuente, fecha_inicio, fecha_fin):
    debug_file = "/home/admonctrlxm/server/logs/debug_callback.log"
    with open(debug_file, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"CALLBACK TABLERO EJECUTADO\n")
        f.write(f"n_clicks={n_clicks}, tipos={tipos_fuente}\n")
        f.write(f"fechas={fecha_inicio} → {fecha_fin}\n")
        f.write(f"{'='*80}\n")
    
    logger.info("="*80)
    logger.info("CALLBACK TABLERO EJECUTADO") 
    logger.info(f"n_clicks={n_clicks}, tipos={tipos_fuente}, fechas={fecha_inicio}-{fecha_fin}")
    logger.info("="*80)
    
    # Validar que tipos_fuente sea una lista
    if not tipos_fuente:
        logger.warning("Sin tipos_fuente")
        alert = dbc.Alert("⚠️ Selecciona al menos una fuente de energía", color="warning", className="text-center")
        return (dbc.Alert("⏳ Inicializando...", color="info"), alert, {})
    
    # Si es string, convertir a lista
    if isinstance(tipos_fuente, str):
        tipos_fuente = [tipos_fuente]
    
    if not fecha_inicio or not fecha_fin:
        alert = dbc.Alert("Selecciona un rango de fechas válido", color="info")
        return (dbc.Alert("⏳ Inicializando...", color="info"), alert, {})
    
    try:
        # Convertir fechas
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
        
        # Informar sobre rango grande
        total_days = (fecha_fin_dt - fecha_inicio_dt).days
        if total_days > 180:
            logger.warning(f"⚠️ Rango grande: {total_days} días - puede tardar 30-60s")
        
        logger.info(f"📊 Iniciando carga de datos para: {', '.join(tipos_fuente)}")
        
        # ═══════════════════════════════════════════════════════════════
        # OPTIMIZACIÓN: Usar Gene con entidad Recurso (1 llamada = todas las plantas)
        # ═══════════════════════════════════════════════════════════════
        
        todas_fuentes = ['HIDRAULICA', 'TERMICA', 'EOLICA', 'SOLAR', 'BIOMASA']
        df_generacion_completo = pd.DataFrame()
        errores_api = []
        
        logger.info(f"🚀 Usando método optimizado Gene con entidad Recurso")
        logger.info(f"📅 Rango: {fecha_inicio_dt} a {fecha_fin_dt}")
        
        for fuente in todas_fuentes:
            try:
                logger.info(f"🔄 Procesando {fuente}...")
                # Consulta optimizada: 1 llamada API para todas las plantas del tipo
                df_agregado = obtener_generacion_agregada_por_tipo(
                    fecha_inicio_dt.strftime('%Y-%m-%d'),
                    fecha_fin_dt.strftime('%Y-%m-%d'),
                    fuente
                )
                
                logger.info(f"📊 {fuente}: DataFrame con {len(df_agregado)} filas")
                
                if not df_agregado.empty:
                    logger.info(f"🔍 {fuente} - Columnas: {list(df_agregado.columns)}")
                    logger.info(f"🔍 {fuente} - Tipo único: {df_agregado['Tipo'].unique() if 'Tipo' in df_agregado.columns else 'N/A'}")
                    df_generacion_completo = pd.concat([df_generacion_completo, df_agregado], ignore_index=True)
                    logger.info(f"✅ {fuente}: {df_agregado['Generacion_GWh'].sum():.2f} GWh agregados")
                else:
                    errores_api.append(f"{fuente} (sin datos)")
                    logger.warning(f"⚠️ {fuente}: DataFrame vacío")
                    
            except Exception as e:
                errores_api.append(f"{fuente} (error: {str(e)[:30]})")
                logger.error(f"❌ Error {fuente}: {e}", exc_info=True)
                continue
        
        # Validar que se obtuvieron datos
        if df_generacion_completo.empty:
            logger.error(f"❌ TODAS LAS FUENTES DEVOLVIERON VACÍO")
            logger.error(f"Errores: {errores_api}")
            
            alert = dbc.Alert([
                html.H5("⚠️ No se encontraron datos", className="mb-3"),
                html.P(f"Período: {fecha_inicio} a {fecha_fin}"),
                html.P(f"Fuentes intentadas: {', '.join(todas_fuentes)}"),
                html.Hr(),
                html.H6("Debug - Errores por fuente:"),
                html.Ul([html.Li(err) for err in errores_api])
            ], color="warning")
            return (alert, alert, {})
        
        # FILTRAR solo las fuentes seleccionadas para las gráficas
        # Convertir códigos a labels
        labels_seleccionadas = [TIPOS_FUENTE.get(tf, {}).get('label', tf) for tf in tipos_fuente]
        df_generacion = df_generacion_completo[df_generacion_completo['Tipo'].isin(labels_seleccionadas)].copy()
        
        if df_generacion.empty:
            alert = dbc.Alert(
                "No se encontraron datos para las fuentes seleccionadas",
                color="warning"
            )
            return (alert, alert, {})
        
        # NOTA: Con datos agregados, no hay dropdown de plantas individuales
        # (las plantas individuales se consultarían solo si el usuario necesita drill-down)
        # El dropdown de plantas fue eliminado en las mejoras del 19/11/2025
        planta_nombre = None
        
        # Preparar datos para gráficas (igual que en crear_grafica_temporal_negra)
        df_generacion_copy = df_generacion.copy()
        df_generacion_copy['Fecha'] = pd.to_datetime(df_generacion_copy['Fecha'])
        
        # Agrupar por fecha
        df_por_fecha = df_generacion_copy.groupby('Fecha', as_index=False)['Generacion_GWh'].sum().sort_values('Fecha')
        
        # Determinar columna de agrupación
        # Siempre agrupar por 'Tipo' cuando hay múltiples fuentes
        grouping_col = 'Tipo'
        
        # Agrupar por fecha y categoría
        df_por_fuente = df_generacion_copy.groupby(['Fecha', grouping_col], as_index=False)['Generacion_GWh'].sum().sort_values('Fecha')
        df_por_fuente = df_por_fuente.merge(df_por_fecha[['Fecha', 'Generacion_GWh']], on='Fecha', suffixes=('', '_Total'))
        df_por_fuente['Participacion_%'] = (df_por_fuente['Generacion_GWh'] / df_por_fuente['Generacion_GWh_Total']) * 100
        
        # Fecha para torta inicial (última fecha)
        ultima_fecha = df_por_fecha['Fecha'].max()
        
        # Preparar datos agregados por planta para la tabla (detalle de todas las plantas)
        df_tabla_plantas = df_generacion_copy.groupby(['Planta', 'Tipo'], as_index=False)['Generacion_GWh'].sum()
        total_generacion_tabla = df_tabla_plantas['Generacion_GWh'].sum()
        df_tabla_plantas['Participacion_%'] = (df_tabla_plantas['Generacion_GWh'] / total_generacion_tabla) * 100
        df_tabla_plantas = df_tabla_plantas.rename(columns={'Tipo': 'Fuente'})  # Renombrar Tipo a Fuente
        df_tabla_plantas['Estado'] = 'Operando'  # Agregar columna Estado
        
        # MAPEAR CÓDIGOS A NOMBRES usando catálogos
        try:
            from domain.services.generation_service import GenerationService
            gs = GenerationService()
            query_catalogos = """
                SELECT codigo, nombre 
                FROM catalogos 
                WHERE catalogo = 'ListadoRecursos'
            """
            df_catalogos = gs.repo.execute_dataframe(query_catalogos)
            if not df_catalogos.empty:
                # Crear diccionario código -> nombre
                mapa_nombres = dict(zip(df_catalogos['codigo'], df_catalogos['nombre']))
                # Aplicar mapeo: usar nombre si existe, si no mantener código
                df_tabla_plantas['Planta'] = df_tabla_plantas['Planta'].apply(
                    lambda x: mapa_nombres.get(x, x)
                )
                logger.info(f"✅ Mapeados {len(mapa_nombres)} códigos de planta a nombres")
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron mapear nombres de plantas: {e}")
        
        # Ordenar por generación descendente
        df_tabla_plantas = df_tabla_plantas.sort_values('Generacion_GWh', ascending=False).reset_index(drop=True)
        
        # Crear contenido - título basado en fuentes seleccionadas
        if len(tipos_fuente) == 5:
            # Todas las fuentes seleccionadas
            titulo_tipo = "Todas las Fuentes"
            icono_tipo = "fa-bolt"
            tipo_fuente = 'TODAS'
        elif len(tipos_fuente) == 1:
            # Una sola fuente
            tipo_fuente = tipos_fuente[0]
            if tipo_fuente in TIPOS_FUENTE:
                info_fuente = TIPOS_FUENTE[tipo_fuente]
                titulo_tipo = info_fuente['label']
                icono_tipo = info_fuente['icon']
            else:
                titulo_tipo = "Generación"
                icono_tipo = "fa-bolt"
        else:
            # Múltiples fuentes seleccionadas (pero no todas)
            titulo_tipo = f"Comparativa ({len(tipos_fuente)} fuentes)"
            icono_tipo = "fa-bolt"
            tipo_fuente = 'MULTIPLES'
        
        contenido = [
            # Layout horizontal: Torta + Temporal + Tabla (3 columnas en una fila)
            dbc.Row([
                # Columna 1: Gráfica de torta
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div("Participación por Fuente", style={'fontSize': '0.7rem', 'color': '#666', 'marginBottom': '2px', 'fontWeight': '500', 'textAlign': 'center'}),
                            html.Div([
                                dcc.Graph(
                                    id='grafica-torta-fuentes',
                                    figure=crear_grafica_torta_fuentes(df_por_fuente, ultima_fecha, grouping_col, tipo_fuente),
                                    config={'displayModeBar': False}
                                )
                            ], style={'height': '340px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}),
                            # Store para guardar los datos necesarios para el callback
                            dcc.Store(id='store-datos-fuentes', data={
                                'df_por_fuente': df_por_fuente.to_json(date_format='iso', orient='split'),
                                'grouping_col': grouping_col,
                                'tipo_fuente': tipo_fuente,
                                'tipos_fuente': tipos_fuente,
                                'ultima_fecha': ultima_fecha.isoformat()
                            })
                        ], className="p-1")
                    ])
                ], width=3, className="mb-2"),
                
                # Columna 2: Gráfica temporal (barras) - REDUCIDA A 5 COLUMNAS
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            dcc.Graph(
                                id='grafica-temporal-fuentes',
                                figure=crear_grafica_temporal_negra(df_generacion, planta_nombre, tipo_fuente),
                                config={'displayModeBar': False}
                            )
                        ], className="p-1")
                    ])
                ], width=5, className="mb-2"),
                
                # Columna 3: Tabla de detalle - AUMENTADA A 4 COLUMNAS
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            crear_tabla_participacion(df_tabla_plantas)
                        ], className="p-1")
                    ])
                ], width=4, className="mb-2")
            ], className="mb-2")
        ]
        
        # Verificar si API retornó menos datos de los solicitados
        if not df_por_fecha.empty:
            fecha_datos_min = df_por_fecha['Fecha'].min().date()
            fecha_datos_max = df_por_fecha['Fecha'].max().date()
            dias_solicitados = (fecha_fin_dt - fecha_inicio_dt).days
            dias_recibidos = (fecha_datos_max - fecha_datos_min).days
            
            if dias_recibidos < (dias_solicitados * 0.5):  # Si recibió menos del 50%
                contenido.insert(0, dbc.Alert([
                    html.I(className="fas fa-info-circle me-2"),
                    html.Strong("ℹ️ Datos limitados de la API XM: "),
                    html.Br(),
                    f"Solicitado: {fecha_inicio_dt.strftime('%d/%m/%Y')} - {fecha_fin_dt.strftime('%d/%m/%Y')} ({dias_solicitados} días)",
                    html.Br(),
                    f"Disponible: {fecha_datos_min.strftime('%d/%m/%Y')} - {fecha_datos_max.strftime('%d/%m/%Y')} ({dias_recibidos} días)"
                ], color="info", className="mb-3"))
        
        # Si hubo errores de API, mostrar advertencia
        if errores_api:
            contenido.insert(0, dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                html.Strong("⚠️ Algunas fuentes no se pudieron cargar: "),
                html.Br(),
                html.Small(", ".join(errores_api)),
                html.Br(),
                html.Small("La API de XM está experimentando lentitud o timeouts. Intenta de nuevo en unos minutos.")
            ], color="warning", className="mb-3"))
        
        logger.info(f"✅ Datos cargados exitosamente para {', '.join(tipos_fuente)}")
        
        # Generar fichas desde el DataFrame ya cargado (evita consulta duplicada)
        fichas = crear_fichas_desde_dataframe(df_generacion_completo, fecha_inicio_dt, fecha_fin_dt, 'TODAS')
        
        # ====================================================================
        # PREPARAR DATOS PARA CHATBOT (se actualiza automáticamente)
        # ====================================================================
        
        # Calcular totales para el chatbot
        total_gwh = df_generacion_completo['Generacion_GWh'].sum()
        
        # Participación por fuente
        participacion_fuentes = df_por_fuente.groupby(grouping_col)['Generacion_GWh'].sum().to_dict()
        participacion_pct = {fuente: (gwh / total_gwh * 100) for fuente, gwh in participacion_fuentes.items()}
        
        # Renovables vs No Renovables
        renovables = ['Hidráulica', 'Eólica', 'Solar', 'Biomasa']
        gen_renovable = sum([gwh for fuente, gwh in participacion_fuentes.items() if fuente in renovables])
        gen_no_renovable = participacion_fuentes.get('Térmica', 0)
        pct_renovable = (gen_renovable / total_gwh * 100) if total_gwh > 0 else 0
        pct_no_renovable = (gen_no_renovable / total_gwh * 100) if total_gwh > 0 else 0
        
        # Top 10 plantas
        top_plantas = df_tabla_plantas.head(10)[['Planta', 'Fuente', 'Generacion_GWh', 'Participacion_%']].to_dict('records')
        
        # Datos del chatbot
        datos_chatbot = {
            'seccion': 'Generación por Fuentes - Análisis General',
            'fecha_consulta': datetime.now().isoformat(),
            'periodo': {
                'inicio': fecha_inicio_dt.strftime('%Y-%m-%d'),
                'fin': fecha_fin_dt.strftime('%Y-%m-%d'),
                'dias': (fecha_fin_dt - fecha_inicio_dt).days
            },
            'filtros': {
                'fuentes_seleccionadas': tipos_fuente,
                'total_fuentes': len(tipos_fuente)
            },
            'fichas': {
                'generacion_total_gwh': round(total_gwh, 2),
                'generacion_renovable_gwh': round(gen_renovable, 2),
                'generacion_renovable_pct': round(pct_renovable, 2),
                'generacion_no_renovable_gwh': round(gen_no_renovable, 2),
                'generacion_no_renovable_pct': round(pct_no_renovable, 2)
            },
            'participacion_por_fuente': {
                fuente: {
                    'gwh': round(gwh, 2),
                    'porcentaje': round(participacion_pct[fuente], 2)
                } for fuente, gwh in participacion_fuentes.items()
            },
            'top_10_plantas': top_plantas,
            'total_plantas': len(df_tabla_plantas),
            'implicaciones_cu': {
                'componente_g': 'Generación',
                'impacto_renovables': f'Con {pct_renovable:.1f}% de generación renovable, se reduce la dependencia de combustibles fósiles',
                'impacto_termica': f'Generación térmica ({pct_no_renovable:.1f}%) incrementa costos variables por combustibles',
                'tendencia': 'Mayor hidrológica = menor costo unitario (CU)' if pct_renovable > 70 else 'Mayor térmica = mayor costo unitario (CU)'
            }
        }
        
        return (fichas, contenido, datos_chatbot)
        
    except TimeoutException as e:
        logger.error(f"⏱️ TIMEOUT GENERAL: {e}")
        error_alert = dbc.Alert([
            html.I(className="fas fa-clock me-2"),
            html.Strong("⏱️ La carga de datos excedió el tiempo límite"),
            html.Br(),
            html.Small("La API de XM está extremadamente lenta en este momento. Por favor intenta:"),
            html.Ul([
                html.Li("Reducir el rango de fechas (30-60 días máximo)"),
                html.Li("Seleccionar menos fuentes de energía"),
                html.Li("Intentar de nuevo en 5-10 minutos")
            ], className="mb-0 mt-2")
        ], color="danger", className="text-start")
        return (dbc.Alert("❌ Error", color="danger"), error_alert, {})
    
    except Exception as e:
        logger.exception(f"❌ Error en callback: {e}")
        error_alert = dbc.Alert([
            html.I(className="fas fa-exclamation-circle me-2"),
            html.Strong(f"❌ Error al procesar los datos"),
            html.Br(),
            html.Small(f"Detalles técnicos: {str(e)[:200]}")
        ], color="danger")
        return (dbc.Alert("❌ Error", color="danger"), error_alert, {})


# ═══════════════════════════════════════════════════════════════
# NOTA: Callback de fichas ELIMINADO - Ahora el callback principal unificado
# devuelve tanto fichas como gráficas en una sola ejecución (evita duplicación)
# ═══════════════════════════════════════════════════════════════

# Caché manual para fichas de generación
_cache_fichas = {}

def crear_fichas_desde_dataframe(df_generacion, fecha_inicio, fecha_fin, tipo_fuente='TODAS'):
    """
    OPTIMIZACIÓN: Crea fichas directamente desde DataFrame ya cargado (sin consultar API)
    
    Args:
        df_generacion: DataFrame con datos de generación ya procesados
        fecha_inicio: Fecha inicial del período
        fecha_fin: Fecha final del período
        tipo_fuente: Tipo de fuente para título
    
    Returns:
        dbc.Row con las 3 fichas de indicadores
    """
    try:
        if df_generacion.empty:
            return dbc.Alert("No hay datos disponibles para generar fichas", color="warning")
        
        # Clasificar renovable vs no renovable
        def es_renovable(tipo_str):
            tipo_upper = str(tipo_str).upper()
            renovables = ['HIDRÁULICA', 'HIDRAULICA', 'EÓLICA', 'EOLICA', 'SOLAR', 'BIOMASA']
            return any(ren in tipo_upper for ren in renovables)
        
        df_generacion['Es_Renovable'] = df_generacion['Tipo'].apply(es_renovable)
        
        # Calcular totales
        gen_total = float(df_generacion['Generacion_GWh'].sum())
        gen_renovable = float(df_generacion[df_generacion['Es_Renovable'] == True]['Generacion_GWh'].sum())
        gen_no_renovable = float(df_generacion[df_generacion['Es_Renovable'] == False]['Generacion_GWh'].sum())
        
        # Calcular porcentajes
        pct_renovable = float((gen_renovable / gen_total * 100) if gen_total > 0 else 0)
        pct_no_renovable = float((gen_no_renovable / gen_total * 100) if gen_total > 0 else 0)
        
        # Formatear valores
        valor_total = f"{gen_total:.1f}"
        valor_renovable = f"{gen_renovable:.1f}"
        valor_no_renovable = f"{gen_no_renovable:.1f}"
        porcentaje_renovable = f"{pct_renovable:.1f}"
        porcentaje_no_renovable = f"{pct_no_renovable:.1f}"
        
        # Formatear fechas
        fecha_inicio_str = fecha_inicio.strftime('%d/%m/%Y')
        fecha_fin_str = fecha_fin.strftime('%d/%m/%Y')
        periodo_texto = f"{fecha_inicio_str} - {fecha_fin_str}"
        
        # Título según tipo de fuente
        if tipo_fuente == 'TODAS':
            titulo_generacion = "Generación Total SIN"
        else:
            tipo_info = TIPOS_FUENTE.get(tipo_fuente, {})
            titulo_generacion = f"Generación {tipo_info.get('label', tipo_fuente)}"
        
        logger.info(f"✅ Fichas creadas desde DataFrame: {gen_total:.1f} GWh ({len(df_generacion)} registros)")
        
        # Crear fichas HTML COMPACTAS HORIZONTALES
        return dbc.Row([
            # Ficha Generación Total
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-bolt", style={'color': '#111827', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                            html.Span(titulo_generacion, style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                            html.Span(valor_total, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#111827', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Small(periodo_texto, style={'color': '#999', 'fontSize': '0.6rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '4px'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': '#ffffff', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, style={'marginBottom': '0'}),
            
            # Ficha Renovable
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-leaf", style={'color': '#000000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                            html.Span("Renovable", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                            html.Span(valor_renovable, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '6px'}),
                            html.Span(f"{porcentaje_renovable}% del total", className="badge bg-success", style={'fontSize': '0.6rem', 'padding': '0.15rem 0.4rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '4px'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, style={'marginBottom': '0'}),
            
            # Ficha No Renovable
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-industry", style={'color': '#000000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                            html.Span("No Renovable", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.7rem', 'marginRight': '8px'}),
                            html.Span(valor_no_renovable, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '6px'}),
                            html.Span(f"{porcentaje_no_renovable}% del total", className="badge bg-danger", style={'fontSize': '0.6rem', 'padding': '0.15rem 0.4rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start', 'gap': '4px'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, style={'marginBottom': '0'})
        ])
        
    except Exception as e:
        logger.error(f"Error creando fichas desde DataFrame: {e}")
        import traceback
        traceback.print_exc()
        return dbc.Alert(f"Error generando fichas: {str(e)}", color="danger")


# Función auxiliar que recibe las fechas y tipo de fuente como parámetros
def crear_fichas_generacion_xm_con_fechas(fecha_inicio, fecha_fin, tipo_fuente='TODAS'):
    """
    Crea las fichas de generación para el período especificado por el usuario
    
    Args:
        fecha_inicio: Fecha inicial del período
        fecha_fin: Fecha final del período  
        tipo_fuente: 'TODAS' o tipo específico ('HIDRAULICA', 'TERMICA', etc.)
    
    IMPORTANTE: Implementa caché para evitar consultas repetidas a la API
    """
    # Crear key de caché
    cache_key = f"{fecha_inicio}_{fecha_fin}_{tipo_fuente}"
    
    # Si está en caché, retornar directamente
    if cache_key in _cache_fichas:
        return _cache_fichas[cache_key]
    
    try:
        objetoAPI = get_objetoAPI()
        if objetoAPI is None:
            return dbc.Alert("API de XM no disponible", color="danger")
        
        
        # PASO 1: Obtener ListadoRecursos para mapear códigos
        # ✅ OPTIMIZADO: Usar obtener_datos_inteligente (SQLite)
        recursos_df, warning = obtener_datos_inteligente("ListadoRecursos", "Sistema", 
                                                          fecha_inicio.strftime('%Y-%m-%d'), 
                                                          fecha_fin.strftime('%Y-%m-%d'))
        
        if recursos_df is None or recursos_df.empty:
            return dbc.Alert("No se pudo obtener ListadoRecursos", color="warning")
        
        
        # Crear mapeo: código → {nombre, tipo}
        codigo_info = {}
        for _, row in recursos_df.iterrows():
            codigo = str(row.get('Values_Code', ''))
            if codigo:
                codigo_info[codigo.upper()] = {
                    'nombre': str(row.get('Values_Name', codigo)),
                    'tipo': str(row.get('Values_Type', 'TERMICA')).upper()
                }
        
        
        # PASO 2: Obtener datos de generación Gene/Recurso
        # ✅ OPTIMIZADO: Consulta inteligente SQLite (>=2020) vs API (<2020)
        df_gene, warning_msg = obtener_datos_inteligente("Gene", "Recurso", 
                                                          fecha_inicio, 
                                                          fecha_fin)
        
        # Mostrar advertencia si se consultaron datos históricos
        if warning_msg:
            pass # print(f"⚠️ {warning_msg}")
        
        if df_gene is None or df_gene.empty:
            return dbc.Alert("No se obtuvieron datos de generación", color="warning")
        
        
        # PASO 3: Sumar las 24 horas por cada planta y convertir a GWh
        horas_cols = [c for c in df_gene.columns if 'Hour' in str(c)]
        
        if not horas_cols:
            return dbc.Alert("No se encontraron columnas horarias en los datos", color="warning")
        
        
        # Identificar columna de código
        codigo_col = None
        for col in ['Values_code', 'Values_Code', 'Code']:
            if col in df_gene.columns:
                codigo_col = col
                break
        
        if not codigo_col:
            return dbc.Alert("No se encontró columna de código en los datos", color="warning")
        
        # Sumar 24 horas por cada fila (día) y convertir kWh → GWh
        df_gene['Generacion_Dia_GWh'] = df_gene[horas_cols].fillna(0).sum(axis=1) / 1_000_000
        
        # AGRUPAR por código y sumar TODOS LOS DÍAS del período
        df_agrupado = df_gene.groupby(codigo_col).agg({
            'Generacion_Dia_GWh': 'sum'  # Suma de todos los días
        }).reset_index()
        
        
        # Renombrar para compatibilidad
        df_agrupado.rename(columns={'Generacion_Dia_GWh': 'Generacion_GWh'}, inplace=True)
        df_gene = df_agrupado  # Reemplazar con datos agrupados
        
        # Mapear códigos a nombres y tipos
        df_gene['Codigo_Upper'] = df_gene[codigo_col].astype(str).str.upper()
        df_gene['Nombre_Planta'] = df_gene['Codigo_Upper'].map(lambda x: codigo_info.get(x, {}).get('nombre', x))
        df_gene['Tipo_Fuente'] = df_gene['Codigo_Upper'].map(lambda x: codigo_info.get(x, {}).get('tipo', 'TERMICA'))
        
        
        # FILTRAR POR TIPO DE FUENTE si no es "TODAS"
        if tipo_fuente != 'TODAS':
            df_gene = df_gene[df_gene['Tipo_Fuente'] == tipo_fuente]
            
            if df_gene.empty:
                return dbc.Alert(f"No hay datos para el tipo de fuente {tipo_fuente} en el período seleccionado", color="warning")
        
        # PASO 4: Clasificar renovable vs no renovable según XM
        
        def es_renovable_xm(tipo):
            """Clasificación oficial XM de fuentes renovables"""
            tipo_str = str(tipo).upper()
            renovables = ['HIDRAULICA', 'HIDRO', 'PCH', 'EOLICA', 'EOLIC', 
                         'SOLAR', 'FOTOVOLTAICA', 'FV', 'BIOMASA', 'COGENERADOR', 
                         'BAGAZO', 'BIOGAS']
            return any(ren in tipo_str for ren in renovables)
        
        df_gene['Es_Renovable'] = df_gene['Tipo_Fuente'].apply(es_renovable_xm)
        
        # PASO 5: Calcular totales
        
        # Calcular totales en GWh - CONVERSIÓN EXPLÍCITA A FLOAT
        gen_total = float(df_gene['Generacion_GWh'].sum())
        gen_renovable = float(df_gene[df_gene['Es_Renovable'] == True]['Generacion_GWh'].sum())
        gen_no_renovable = float(df_gene[df_gene['Es_Renovable'] == False]['Generacion_GWh'].sum())
        
        # Calcular porcentajes - CONVERSIÓN EXPLÍCITA A FLOAT
        pct_renovable = float((gen_renovable / gen_total * 100) if gen_total > 0 else 0)
        pct_no_renovable = float((gen_no_renovable / gen_total * 100) if gen_total > 0 else 0)
        
        
        # Formatear valores como strings simples
        valor_total = f"{gen_total:.1f}"
        valor_renovable = f"{gen_renovable:.1f}"
        valor_no_renovable = f"{gen_no_renovable:.1f}"
        porcentaje_renovable = f"{pct_renovable:.1f}"
        porcentaje_no_renovable = f"{pct_no_renovable:.1f}"
        
        
        # Formatear fechas como string
        fecha_inicio_str = fecha_inicio.strftime('%d/%m/%Y')
        fecha_fin_str = fecha_fin.strftime('%d/%m/%Y')
        periodo_texto = f"{fecha_inicio_str} - {fecha_fin_str}"
        
        
        # Determinar título según filtro
        if tipo_fuente == 'TODAS':
            titulo_generacion = "Generación Total SIN"
        else:
            tipo_info = TIPOS_FUENTE.get(tipo_fuente, {})
            titulo_generacion = f"Generación {tipo_info.get('label', tipo_fuente)}"
        
        
        # Crear las fichas HTML COMPACTAS con layout HORIZONTAL
        fichas_html = dbc.Row([
            # Ficha Generación Total
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-bolt", style={'color': '#0f172a', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                            html.Span(titulo_generacion, style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Span(valor_total, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#111827', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Small(periodo_texto, style={'color': '#999', 'fontSize': '0.6rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': '#ffffff', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, className="mb-2"),

            # Ficha Renovable
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-leaf", style={'color': '#000000', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                            html.Span("Renovable", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Span(valor_renovable, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '4px'}),
                            html.Span(f"{porcentaje_renovable}% del total", className="badge bg-success", style={'fontSize': '0.6rem', 'padding': '0.15rem 0.4rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, className="mb-2"),
            
            # Ficha No Renovable
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-industry", style={'color': '#000000', 'fontSize': '0.9rem', 'marginRight': '6px'}),
                            html.Span("No Renovable", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                            html.Span(valor_no_renovable, style={'fontWeight': 'bold', 'fontSize': '1.3rem', 'color': '#000000', 'marginRight': '4px'}),
                            html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem', 'marginRight': '4px'}),
                            html.Span(f"{porcentaje_no_renovable}% del total", className="badge bg-danger", style={'fontSize': '0.6rem', 'padding': '0.15rem 0.4rem'})
                        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
                    ], style={'padding': '0.4rem 0.8rem', 'background': 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)', 'borderRadius': '6px'})
                ], className="shadow-sm")
            ], lg=4, md=6, className="mb-2")
    ])

        
        # Guardar en caché antes de retornar
        _cache_fichas[cache_key] = fichas_html
        
        return fichas_html
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return dbc.Alert(f"Error al cargar las fichas de generación: {str(e)}", color="danger")


# ==================================================================
# CALLBACKS PARA COMPARACIÓN ANUAL (MULTISELECTOR)
# ==================================================================

@callback(
    [Output('grafica-lineas-temporal-anual', 'figure'),
     Output('contenedor-tortas-anuales', 'children')],
    Input('btn-actualizar-comparacion', 'n_clicks'),
    State('years-multiselector', 'value')
)
def actualizar_comparacion_anual(n_clicks, years_selected):
    """
    Callback para actualizar:
    1. Gráfica de líneas temporales (una línea por año)
    2. Gráficas de torta (una torta por año con participación % por fuente)
    
    Se carga automáticamente al inicio con años 2024 y 2025
    """
    px, go = get_plotly_modules()
    
    if not years_selected or len(years_selected) == 0:
        return (
            go.Figure().add_annotation(text="Selecciona al menos un año", xref="paper", yref="paper", x=0.5, y=0.5),
            dbc.Alert("Por favor selecciona al menos un año para comparar", color="warning")
        )
    
    try:
        # Colores únicos para cada año
        colores_años = {
            2020: '#1f77b4',
            2021: '#ff7f0e',
            2022: '#2ca02c',
            2023: '#d62728',
            2024: '#9467bd',
            2025: '#8c564b'
        }
        
        # ============================================================
        # 1. OBTENER DATOS DE GENERACIÓN PARA CADA AÑO SELECCIONADO
        # ============================================================
        datos_todos_años = []
        
        for year in sorted(years_selected):
            logger.info(f"📅 Obteniendo datos para año {year}...")
            
            # Definir fechas del año completo
            fecha_inicio = date(year, 1, 1)
            fecha_fin = date(year, 12, 31)
            
            # Si es el año actual, usar solo hasta hoy
            if year == date.today().year:
                fecha_fin = date.today() - timedelta(days=1)
            
            # Obtener datos de generación agregada por tipo
            # Usamos la función existente que consulta SQLite
            df_year_hidraulica = obtener_generacion_agregada_por_tipo(
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d'),
                'HIDRAULICA'
            )
            
            df_year_termica = obtener_generacion_agregada_por_tipo(
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d'),
                'TERMICA'
            )
            
            df_year_eolica = obtener_generacion_agregada_por_tipo(
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d'),
                'EOLICA'
            )
            
            df_year_solar = obtener_generacion_agregada_por_tipo(
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d'),
                'SOLAR'
            )
            
            df_year_biomasa = obtener_generacion_agregada_por_tipo(
                fecha_inicio.strftime('%Y-%m-%d'),
                fecha_fin.strftime('%Y-%m-%d'),
                'BIOMASA'
            )
            
            # Combinar todos los tipos de fuente para este año
            df_year_completo = pd.concat([
                df_year_hidraulica,
                df_year_termica,
                df_year_eolica,
                df_year_solar,
                df_year_biomasa
            ], ignore_index=True)
            
            if not df_year_completo.empty:
                df_year_completo['Año'] = year
                datos_todos_años.append(df_year_completo)
        
        if not datos_todos_años:
            return (
                go.Figure().add_annotation(text="No hay datos disponibles para los años seleccionados", 
                                         xref="paper", yref="paper", x=0.5, y=0.5),
                dbc.Alert("No se encontraron datos para los años seleccionados", color="warning")
            )
        
        # Combinar todos los años
        df_completo = pd.concat(datos_todos_años, ignore_index=True)
        df_completo['Fecha'] = pd.to_datetime(df_completo['Fecha'])
        
        # ============================================================
        # 2. CREAR GRÁFICA DE LÍNEAS TEMPORALES SUPERPUESTAS
        # ============================================================
        
        # Agregar por fecha y año (suma total de todas las fuentes por día)
        df_por_dia_año = df_completo.groupby(['Año', 'Fecha'], as_index=False)['Generacion_GWh'].sum()
        
        # Crear fecha normalizada (mismo año base 2024 para superposición)
        df_por_dia_año['MesDia'] = df_por_dia_año['Fecha'].dt.strftime('%m-%d')
        df_por_dia_año['FechaNormalizada'] = pd.to_datetime('2024-' + df_por_dia_año['MesDia'])
        
        # Crear gráfica de líneas superpuestas
        fig_lineas = go.Figure()
        
        for year in sorted(years_selected):
            df_year = df_por_dia_año[df_por_dia_año['Año'] == year].sort_values('FechaNormalizada')
            
            # Crear texto customizado para hover con fecha real
            hover_text = [
                f"<b>{year}</b><br>{fecha.strftime('%d de %B de %Y')}<br>Generación: {gen:.2f} GWh"
                for fecha, gen in zip(df_year['Fecha'], df_year['Generacion_GWh'])
            ]
            
            fig_lineas.add_trace(
                go.Scatter(
                    x=df_year['FechaNormalizada'],
                    y=df_year['Generacion_GWh'],
                    mode='lines',
                    name=str(year),
                    line=dict(color=colores_años.get(year, '#666'), width=2),
                    hovertext=hover_text,
                    hoverinfo='text'
                )
            )
        
        fig_lineas.update_layout(
            title="Generación Diaria Total (GWh)",
            xaxis_title="Fecha",
            yaxis_title="Generación (GWh)",
            hovermode='x unified',
            template='plotly_white',
            height=500,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            xaxis=dict(
                tickformat='%d %b',  # Formato: "01 Ene", "15 Feb", etc. (sin año)
                dtick='M1',  # Marca cada mes
                tickangle=-45
            )
        )
        
        # ============================================================
        # 3. CREAR GRÁFICAS DE TORTA (una por año)
        # ============================================================
        
        # Calcular altura dinámica según cantidad de años
        num_years = len(years_selected)
        if num_years <= 2:
            torta_height = 200  # Más grande para 1-2 años
        elif num_years == 3:
            torta_height = 120  # Media para 3 años
        else:
            torta_height = 80   # Pequeña para 4+ años
        
        tortas_anuales = []
        
        for year in sorted(years_selected):
            # Definir fechas del año específico para mostrar en las tarjetas
            fecha_inicio_year = date(year, 1, 1)
            fecha_fin_year = date(year, 12, 31)
            
            # Si es el año actual, usar solo hasta ayer
            if year == date.today().year:
                fecha_fin_year = date.today() - timedelta(days=1)
            
            # Filtrar datos del año
            df_year = df_completo[df_completo['Año'] == year]
            
            # Agrupar por tipo de fuente
            df_por_fuente = df_year.groupby('Tipo', as_index=False)['Generacion_GWh'].sum()
            
            # Calcular participación %
            total = df_por_fuente['Generacion_GWh'].sum()
            df_por_fuente['Participacion_%'] = (df_por_fuente['Generacion_GWh'] / total * 100).round(2)
            
            # Colores por fuente
            colores_fuente = {
                'Hidráulica': '#1f77b4',
                'Térmica': '#ff7f0e',
                'Eólica': '#2ca02c',
                'Solar': '#ffbb33',
                'Biomasa': '#17becf',
            }
            
            # Crear gráfica de torta
            fig_torta = go.Figure()
            fig_torta.add_trace(
                go.Pie(
                    labels=df_por_fuente['Tipo'],
                    values=df_por_fuente['Generacion_GWh'],
                    marker=dict(colors=[colores_fuente.get(tipo, '#666') for tipo in df_por_fuente['Tipo']]),
                    textposition='inside',
                    textinfo='label+percent',
                    hovertemplate='<b>%{label}</b><br>Participación: %{percent}<br>Generación: %{value:.1f} GWh<extra></extra>'
                )
            )
            
            fig_torta.update_layout(
                template='plotly_white',
                height=torta_height,  # Altura dinámica según cantidad de años
                showlegend=False,  # Sin leyenda para aprovechar mejor el espacio
                margin=dict(t=5, b=5, l=5, r=5)
            )
            
            # Calcular totales para KPIs
            # Renovables: Hidráulica + Eólica + Solar + Biomasa
            renovables = ['Hidráulica', 'Eólica', 'Solar', 'Biomasa']
            gen_renovable = df_por_fuente[df_por_fuente['Tipo'].isin(renovables)]['Generacion_GWh'].sum()
            gen_no_renovable = df_por_fuente[df_por_fuente['Tipo'] == 'Térmica']['Generacion_GWh'].sum()
            gen_total = total  # Ya calculado antes
            
            # Porcentajes
            pct_renovable = (gen_renovable / gen_total * 100) if gen_total > 0 else 0
            pct_no_renovable = (gen_no_renovable / gen_total * 100) if gen_total > 0 else 0
            
            # Agregar tarjeta con fichas compactas (sin columna, directo al contenedor)
            tortas_anuales.append(
                dbc.Card([
                    dbc.CardBody([
                        html.Small(f"{year}", style={'fontSize': '0.6rem', 'color': '#666', 'fontWeight': '600', 'display': 'block', 'textAlign': 'center', 'marginBottom': '4px'}),
                        
                        # Fichas horizontales compactas (3 en fila)
                        html.Div([
                            # Ficha Total SIN
                            html.Div([
                                html.I(className="fas fa-bolt", style={'color': '#000000', 'fontSize': '0.6rem', 'marginRight': '2px'}),
                                html.Span("Total", style={'fontSize': '0.45rem', 'marginRight': '2px', 'color': '#666'}),
                                html.Span(f"{gen_total:,.0f}", style={'fontSize': '0.7rem', 'fontWeight': '700', 'color': '#2c3e50'})
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'gap': '1px',
                                'padding': '2px 4px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '3px',
                                'flex': '1',
                                'justifyContent': 'center'
                            }),
                            
                            # Ficha Renovable
                            html.Div([
                                html.I(className="fas fa-leaf", style={'color': '#28a745', 'fontSize': '0.6rem', 'marginRight': '2px'}),
                                html.Span(f"{pct_renovable:.0f}%", style={'fontSize': '0.7rem', 'fontWeight': '700', 'color': '#28a745'})
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'gap': '1px',
                                'padding': '2px 4px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '3px',
                                'flex': '1',
                                'justifyContent': 'center'
                            }),
                            
                            # Ficha No Renovable
                            html.Div([
                                html.I(className="fas fa-industry", style={'color': '#dc3545', 'fontSize': '0.6rem', 'marginRight': '2px'}),
                                html.Span(f"{pct_no_renovable:.0f}%", style={'fontSize': '0.7rem', 'fontWeight': '700', 'color': '#dc3545'})
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'gap': '1px',
                                'padding': '2px 4px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '3px',
                                'flex': '1',
                                'justifyContent': 'center'
                            }),
                        ], style={'display': 'flex', 'gap': '3px', 'marginBottom': '4px'}),
                        
                        # Gráfica de torta (más grande)
                        dcc.Graph(figure=fig_torta, config={'displayModeBar': False}),
                        
                        # Fecha del período
                        html.Small(f"{fecha_inicio_year.strftime('%d/%m/%Y')} - {fecha_fin_year.strftime('%d/%m/%Y')}",
                                 className="text-center d-block text-muted",
                                 style={'fontSize': '0.5rem', 'marginTop': '2px'})
                    ], className="p-1")
                ], className="shadow-sm")
            )
        
        # Organizar fichas en cuadrícula 2x2 (como en Hidrología)
        filas_tortas = []
        for i in range(0, len(tortas_anuales), 2):
            cols = [dbc.Col(tortas_anuales[i], md=6)]
            if i + 1 < len(tortas_anuales):
                cols.append(dbc.Col(tortas_anuales[i + 1], md=6))
            filas_tortas.append(dbc.Row(cols, className="mb-3"))
        
        contenedor_tortas = html.Div(filas_tortas)
        
        return fig_lineas, contenedor_tortas
        
    except Exception as e:
        logger.error(f"❌ Error en comparación anual: {e}")
        traceback.print_exc()
        return (
            go.Figure().add_annotation(text=f"Error: {str(e)}", xref="paper", yref="paper", x=0.5, y=0.5),
            dbc.Alert(f"Error procesando datos: {str(e)}", color="danger")
        )

# ==================================================================
# CALLBACKS PARA PREDICCIONES
# ==================================================================

@callback(
    Output("modal-info-predicciones", "is_open"),
    [Input("btn-info-predicciones", "n_clicks"),
     Input("close-modal-predicciones", "n_clicks")],
    State("modal-info-predicciones", "is_open")
)
def toggle_modal_predicciones(n_open, n_close, is_open):
    """Abre/cierra modal de información de predicciones"""
    if n_open or n_close:
        return not is_open
    return is_open

@callback(
    [Output('contenedor-fichas-prediccion', 'children'),
     Output('contenido-graficas-prediccion', 'children')],
    [Input('btn-cargar-predicciones', 'n_clicks'),
     Input('tabs-generacion-fuentes', 'active_tab')],
    [State('horizonte-prediccion', 'value'),
     State('fuentes-prediccion', 'value')],
    prevent_initial_call=False
)
def generar_predicciones(n_clicks, active_tab, horizonte_meses, fuentes_seleccionadas):
    """
    Genera predicciones para las fuentes seleccionadas usando modelos ML
    FASE 2: Auto-carga al abrir tab + botón manual
    """
    # No cargar si no estamos en tab predicciones
    if active_tab != 'tab-predicciones':
        raise PreventUpdate
    
    # Si no hay fuentes seleccionadas, no mostrar nada
    if not fuentes_seleccionadas or len(fuentes_seleccionadas) == 0:
        return (
            html.Div([
                dbc.Alert("Selecciona al menos una fuente para predecir", color="warning")
            ]),
            html.Div([])
        )
    
    px, go = get_plotly_modules()
    
    try:
        logger.info(f"🔮 Generando predicciones: {fuentes_seleccionadas}, horizonte: {horizonte_meses} meses")
        
        # ==================================================================
        # FASE 2: CARGAR PREDICCIONES REALES DE LA BASE DE DATOS (FASE 1 COMPLETADA)
        # ==================================================================
        from datetime import datetime, timedelta
        
        # Calcular el horizonte en días (3 meses = 90 días, 6 meses = 180 días, etc.)
        horizonte_dias_calculado = horizonte_meses * 30  # Aproximación simple
        fecha_limite = datetime.now().date() + timedelta(days=horizonte_dias_calculado)
        
        # Cargar predicciones de la BD (todas tienen horizonte_dias=90)
        # No filtrar por horizonte, solo limitar por número de días necesarios
        query = """
        SELECT fecha_prediccion, fuente, valor_gwh_predicho, 
               intervalo_inferior, intervalo_superior, modelo, horizonte_dias
        FROM predictions
        WHERE fuente IN ({})
          AND fecha_prediccion <= %s
          AND fecha_prediccion >= CURRENT_DATE
        ORDER BY fecha_prediccion, fuente
        """.format(','.join(['%s' for _ in fuentes_seleccionadas]))
        
        params = fuentes_seleccionadas + [fecha_limite]
        df_pred = db_manager.query_df(query, params)
        
        if df_pred.empty:
            return (
                dbc.Alert([
                    "⚠️ No hay predicciones disponibles para las fuentes seleccionadas. ",
                    html.Br(),
                    html.B("Solución: "),
                    "Las predicciones se actualizan automáticamente cada domingo a las 2:00 AM. ",
                    html.Br(),
                    "Para actualizar manualmente, ejecute: ",
                    html.Code("./scripts/actualizar_predicciones.sh")
                ], color="warning"),
                dbc.Alert([
                    "⚠️ No hay predicciones disponibles. Sistema de predicciones automáticas activo. ",
                    html.Br(),
                    html.Small(f"Total predicciones en BD: 900 (10 categorías × 90 días). Última actualización: Revisar logs/alertas_energeticas.json")
                ], color="info")
            )
        
        # Convertir fecha
        df_pred['fecha_prediccion'] = pd.to_datetime(df_pred['fecha_prediccion'])
        modelo_utilizado = df_pred['modelo'].iloc[0]
        
        # ==================================================================
        # GENERAR FICHAS DE RESUMEN
        # ==================================================================
        
        # Calcular promedio DIARIO predicho (suma de todas las fuentes por día)
        # Agrupar por fecha y sumar todas las fuentes para cada día, luego promediar
        df_pred_total_diario = df_pred.groupby('fecha_prediccion')['valor_gwh_predicho'].sum()
        promedio_diario_predicho = df_pred_total_diario.mean()
        
        # Calcular promedio DIARIO actual (últimos 30 días) - suma de todas las fuentes por día
        tipo_mapa = {
            'Hidráulica': 'HIDRAULICA',
            'Térmica': 'TERMICA',
            'Eólica': 'EOLICA',
            'Solar': 'SOLAR',
            'Biomasa': 'COGENERADOR'
        }
        
        # Obtener suma diaria de todas las fuentes seleccionadas en los últimos 30 días
        tipos_list = [tipo_mapa.get(f, f.upper()) for f in fuentes_seleccionadas]
        placeholders = ','.join(['%s' for _ in tipos_list])
        query_hist = f"""
        SELECT m.fecha, SUM(m.valor_gwh) as total_dia
        FROM metrics m
        INNER JOIN catalogos c ON m.recurso = c.codigo
        WHERE m.metrica = 'Gene'
          AND c.catalogo = 'ListadoRecursos'
          AND c.tipo IN ({placeholders})
          AND m.fecha >= NOW() - INTERVAL '30 days'
        GROUP BY m.fecha
        """
        df_hist = db_manager.query_df(query_hist, params=tipos_list)
        
        promedio_diario_actual = 0
        if not df_hist.empty and 'total_dia' in df_hist.columns:
            promedio_diario_actual = df_hist['total_dia'].mean()
        
        # Comparar promedios diarios correctamente
        variacion = ((promedio_diario_predicho - promedio_diario_actual) / promedio_diario_actual * 100) if promedio_diario_actual > 0 else 0
        color_variacion = "success" if variacion >= 0 else "danger"
        icono_variacion = "↗" if variacion >= 0 else "↘"
        
        # Calcular fecha primera y última predicción
        fecha_primera = df_pred['fecha_prediccion'].min().strftime('%d/%m/%Y')
        fecha_ultima = df_pred['fecha_prediccion'].max().strftime('%d/%m/%Y')
        
        fichas = dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-calendar-alt", style={'color': '#7c3aed', 'fontSize': '1.2rem', 'marginRight': '8px'}),
                            html.Div([
                                html.Span("Periodo de Predicción", style={'fontSize': '0.7rem', 'color': '#666', 'display': 'block'}),
                                html.Span(f"{fecha_primera} → {fecha_ultima}", style={'fontSize': '1.1rem', 'fontWeight': 'bold', 'color': '#7c3aed'}),
                                html.Small("90 días (3 meses adelante)", style={'fontSize': '0.65rem', 'color': '#999', 'display': 'block'})
                            ])
                        ], style={'display': 'flex', 'alignItems': 'center'})
                    ], className="p-2")
                ], className="shadow-sm", style={'border': '2px solid #7c3aed'})
            ], md=4),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-bolt", style={'color': '#10b981', 'fontSize': '1.2rem', 'marginRight': '8px'}),
                            html.Div([
                                html.Span("Generación Diaria Estimada", style={'fontSize': '0.7rem', 'color': '#666', 'display': 'block'}),
                                html.Span(f"{promedio_diario_predicho:,.1f} GWh", style={'fontSize': '1.5rem', 'fontWeight': 'bold', 'color': '#10b981'}),
                                html.Small([
                                    html.Span(f"{icono_variacion} {abs(variacion):.1f}% vs actual (últimos 30 días)", 
                                             style={'color': '#10b981' if variacion >= 0 else '#ef4444'})
                                ], style={'fontSize': '0.65rem'})
                            ])
                        ], style={'display': 'flex', 'alignItems': 'center'})
                    ], className="p-2")
                ], className="shadow-sm")
            ], md=4),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-chart-line", style={'color': '#3b82f6', 'fontSize': '1.2rem', 'marginRight': '8px'}),
                            html.Div([
                                html.Span("Intervalo de Confianza", style={'fontSize': '0.7rem', 'color': '#666', 'display': 'block'}),
                                html.Span("95%", style={'fontSize': '1.5rem', 'fontWeight': 'bold', 'color': '#3b82f6'}),
                                html.Small("Áreas sombreadas en gráfica", style={'fontSize': '0.65rem', 'color': '#999'})
                            ])
                        ], style={'display': 'flex', 'alignItems': 'center'})
                    ], className="p-2")
                ], className="shadow-sm")
            ], md=4)
        ], className="mb-3")
        
        # ==================================================================
        # GENERAR GRÁFICAS DE PREDICCIÓN
        # ==================================================================
        
        # Gráfica temporal con intervalos de confianza
        fig_prediccion = go.Figure()
        
        colores = {
            'Hidráulica': '#1f77b4',
            'Térmica': '#ff7f0e',
            'Eólica': '#2ca02c',
            'Solar': '#ffbb33',
            'Biomasa': '#17becf'
        }
        
        # Calcular generación total por fecha
        df_total = df_pred.groupby('fecha_prediccion')['valor_gwh_predicho'].sum().reset_index()
        df_total.columns = ['fecha_prediccion', 'total_predicho']
        
        for fuente in fuentes_seleccionadas:
            df_fuente = df_pred[df_pred['fuente'] == fuente]
            if df_fuente.empty:
                continue
                
            color = colores.get(fuente, '#666')
            
            # Línea de predicción
            fig_prediccion.add_trace(go.Scatter(
                x=df_fuente['fecha_prediccion'],
                y=df_fuente['valor_gwh_predicho'],
                name=fuente,
                line=dict(color=color, width=2),
                mode='lines',
                hovertemplate=f'<b>{fuente}</b><br>Fecha: %{{x|%Y-%m-%d}}<br>Predicción: %{{y:.2f}} GWh<extra></extra>'
            ))
            
            # Banda de confianza
            fig_prediccion.add_trace(go.Scatter(
                x=df_fuente['fecha_prediccion'].tolist() + df_fuente['fecha_prediccion'].tolist()[::-1],
                y=df_fuente['intervalo_superior'].tolist() + df_fuente['intervalo_inferior'].tolist()[::-1],
                fill='toself',
                fillcolor=color,
                opacity=0.2,
                line=dict(color='rgba(255,255,255,0)'),
                showlegend=False,
                name=f'{fuente} IC 95%',
                hoverinfo='skip'
            ))
        
        # Línea de generación total (solo si se seleccionaron múltiples fuentes)
        if len(fuentes_seleccionadas) > 1:
            fig_prediccion.add_trace(go.Scatter(
                x=df_total['fecha_prediccion'],
                y=df_total['total_predicho'],
                name='⚡ TOTAL',
                line=dict(color='#000000', width=3, dash='dot'),
                mode='lines',
                hovertemplate='<b>TOTAL</b><br>Fecha: %{x|%Y-%m-%d}<br>Predicción: %{y:.2f} GWh<extra></extra>'
            ))
        
        fig_prediccion.update_layout(
            title=f'Predicciones de generación en {horizonte_meses} meses',
            xaxis_title='Fecha',
            yaxis_title='Generación (GWh/día)',
            template='plotly_white',
            height=500,
            hovermode='x unified',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        contenido_graficas = dbc.Row([
            dbc.Col([
                dcc.Graph(
                    id='grafico-predicciones-validacion',
                    figure=fig_prediccion, 
                    config={'displayModeBar': True}
                )
            ], md=12)
        ])
        
        return (fichas, contenido_graficas)
        
    except Exception as e:
        logger.error(f"❌ Error generando predicciones: {e}")
        traceback.print_exc()
        error_msg = dbc.Alert([
            html.I(className="fas fa-exclamation-circle me-2"),
            html.Strong("Error generando predicciones: "),
            html.Br(),
            html.Small(str(e))
        ], color="danger")
        return (error_msg, error_msg)

# ==================================================================
# CALLBACK: VALIDACIÓN DE PREDICCIONES (CLICK EN GRÁFICA)
# ==================================================================

@callback(
    Output("modal-validacion-prediccion", "is_open"),
    [Input("close-modal-validacion", "n_clicks")],
    State("modal-validacion-prediccion", "is_open")
)
def toggle_modal_validacion(n_close, is_open):
    """Cierra modal de validación"""
    if n_close:
        return not is_open
    return is_open


@callback(
    [Output('modal-validacion-prediccion', 'is_open', allow_duplicate=True),
     Output('titulo-modal-validacion', 'children'),
     Output('contenido-modal-validacion', 'children')],
    Input('grafico-predicciones-validacion', 'clickData'),
    prevent_initial_call=True
)
def mostrar_validacion_prediccion(clickData):
    """
    Muestra tabla de validación al hacer click en un punto de la gráfica
    Compara predicción vs datos reales (si la fecha ya pasó)
    """
    if not clickData:
        raise PreventUpdate
    
    try:
        from datetime import datetime
        
        # Obtener fecha del punto clickeado
        punto = clickData['points'][0]
        fecha_click = punto['x']
        fecha_dt = pd.to_datetime(fecha_click)
        fecha_str = fecha_dt.strftime('%Y-%m-%d')
        fecha_display = fecha_dt.strftime('%d de %B de %Y')
        
        # ==================================================================
        # 1. OBTENER PREDICCIONES PARA ESA FECHA
        # ==================================================================
        query_pred = """
        SELECT fuente, valor_gwh_predicho, intervalo_inferior, intervalo_superior
        FROM predictions
        WHERE DATE(fecha_prediccion) = %s
        ORDER BY 
            CASE fuente
                WHEN 'Hidráulica' THEN 1
                WHEN 'Térmica' THEN 2
                WHEN 'Solar' THEN 3
                WHEN 'Eólica' THEN 4
                WHEN 'Biomasa' THEN 5
            END
        """
        df_pred = db_manager.query_df(query_pred, params=[fecha_str])
        
        if df_pred.empty:
            return (True, 
                   f"Fecha: {fecha_display}",
                   dbc.Alert("No hay predicciones disponibles para esta fecha", color="warning"))
        
        # ==================================================================
        # 2. VERIFICAR SI HAY DATOS REALES (fecha ya pasó)
        # ==================================================================
        hoy = datetime.now().date()
        fecha_comparar = fecha_dt.date()
        hay_datos_reales = fecha_comparar < hoy
        
        df_real = None
        if hay_datos_reales:
            # Obtener catálogo con clasificación
            catalogo = db_manager.query_df("""
                SELECT codigo, tipo
                FROM catalogos
                WHERE catalogo = 'ListadoRecursos' AND tipo IS NOT NULL
            """)
            
            # Normalizar y mapear tipos
            catalogo['tipo_norm'] = catalogo['tipo'].str.upper().str.strip()
            tipo_map = {
                'HIDRAULICA': 'Hidráulica',
                'TERMICA': 'Térmica',
                'SOLAR': 'Solar',
                'EOLICA': 'Eólica',
                'BIOMASA': 'Biomasa',
                'BIOMAS': 'Biomasa',
                'COGENER': 'Biomasa',
                'BAGAZO': 'Biomasa',
                'RESIDUO': 'Biomasa'
            }
            catalogo['fuente'] = catalogo['tipo_norm'].map(tipo_map)
            clasificados = catalogo[catalogo['fuente'].notna()]
            
            # Obtener generación real
            query_real = """
            SELECT recurso, SUM(valor_mwh) as valor_mwh
            FROM metrics_hourly
            WHERE metrica = 'Gene' AND entidad = 'Recurso' AND fecha = %s
            GROUP BY recurso
            """
            df_gene = db_manager.query_df(query_real, params=[fecha_str])
            
            if not df_gene.empty:
                # Clasificar recursos
                df_gene_clasificado = df_gene.merge(
                    clasificados[['codigo', 'fuente']],
                    left_on='recurso',
                    right_on='codigo',
                    how='left'
                )
                
                # Agrupar por fuente
                df_real = df_gene_clasificado[df_gene_clasificado['fuente'].notna()].groupby('fuente').agg({
                    'valor_mwh': 'sum'
                }).reset_index()
                df_real['valor_gwh'] = df_real['valor_mwh'] / 1000.0
        
        # ==================================================================
        # 3. GENERAR TABLA DE COMPARACIÓN
        # ==================================================================
        
        # Merge predicciones con datos reales
        if hay_datos_reales and df_real is not None and not df_real.empty:
            df_comparacion = df_pred.merge(
                df_real[['fuente', 'valor_gwh']],
                on='fuente',
                how='left'
            )
            df_comparacion['diferencia'] = df_comparacion['valor_gwh'] - df_comparacion['valor_gwh_predicho']
            df_comparacion['error_pct'] = (abs(df_comparacion['diferencia']) / df_comparacion['valor_gwh'] * 100)
            df_comparacion['en_intervalo'] = (
                (df_comparacion['valor_gwh'] >= df_comparacion['intervalo_inferior']) &
                (df_comparacion['valor_gwh'] <= df_comparacion['intervalo_superior'])
            )
        else:
            df_comparacion = df_pred.copy()
            df_comparacion['valor_gwh'] = None
            df_comparacion['diferencia'] = None
            df_comparacion['error_pct'] = None
            df_comparacion['en_intervalo'] = None
        
        # Generar filas de la tabla
        tabla_filas = []
        for _, row in df_comparacion.iterrows():
            fuente = row['fuente']
            pred = row['valor_gwh_predicho']
            real = row['valor_gwh']
            diff = row['diferencia']
            error = row['error_pct']
            en_int = row['en_intervalo']
            
            # Columnas base
            fila = [
                html.Td(fuente, style={'fontWeight': 'bold'}),
                html.Td(f"{pred:.2f} GWh", style={'textAlign': 'center'}),
            ]
            
            if hay_datos_reales and real is not None and not pd.isna(real):
                # Colorear según error
                color_error = '#22c55e' if error < 5 else ('#f59e0b' if error < 10 else '#ef4444')
                
                fila.extend([
                    html.Td(f"{real:.2f} GWh", style={'textAlign': 'center', 'fontWeight': 'bold'}),
                    html.Td(f"{diff:+.2f} GWh", style={'textAlign': 'center', 'color': '#3b82f6'}),
                    html.Td(f"{error:.1f}%", style={'textAlign': 'center', 'fontWeight': 'bold', 'color': color_error})
                ])
            else:
                fila.extend([
                    html.Td("—", style={'textAlign': 'center', 'color': '#999'}),
                    html.Td("—", style={'textAlign': 'center', 'color': '#999'}),
                    html.Td("—", style={'textAlign': 'center', 'color': '#999'})
                ])
            
            tabla_filas.append(html.Tr(fila))
        
        # Fila de TOTAL
        total_pred = df_comparacion['valor_gwh_predicho'].sum()
        if hay_datos_reales and df_real is not None:
            total_real = df_comparacion['valor_gwh'].sum()
            total_diff = total_real - total_pred
            total_error = abs(total_diff) / total_real * 100 if total_real > 0 else 0
            color_total = '#22c55e' if total_error < 5 else ('#f59e0b' if total_error < 10 else '#ef4444')
            
            fila_total = html.Tr([
                html.Td("TOTAL", style={'fontWeight': 'bold', 'fontSize': '1.1rem', 'backgroundColor': '#f3f4f6'}),
                html.Td(f"{total_pred:.2f} GWh", style={'textAlign': 'center', 'fontWeight': 'bold', 'fontSize': '1.1rem', 'backgroundColor': '#f3f4f6'}),
                html.Td(f"{total_real:.2f} GWh", style={'textAlign': 'center', 'fontWeight': 'bold', 'fontSize': '1.1rem', 'backgroundColor': '#f3f4f6'}),
                html.Td(f"{total_diff:+.2f} GWh", style={'textAlign': 'center', 'fontSize': '1.1rem', 'backgroundColor': '#f3f4f6', 'color': '#3b82f6'}),
                html.Td(f"{total_error:.1f}%", style={'textAlign': 'center', 'fontWeight': 'bold', 'fontSize': '1.1rem', 'backgroundColor': '#f3f4f6', 'color': color_total})
            ])
        else:
            fila_total = html.Tr([
                html.Td("TOTAL", style={'fontWeight': 'bold', 'fontSize': '1.1rem', 'backgroundColor': '#f3f4f6'}),
                html.Td(f"{total_pred:.2f} GWh", style={'textAlign': 'center', 'fontWeight': 'bold', 'fontSize': '1.1rem', 'backgroundColor': '#f3f4f6'}),
                html.Td("—", style={'textAlign': 'center', 'backgroundColor': '#f3f4f6', 'color': '#999'}),
                html.Td("—", style={'textAlign': 'center', 'backgroundColor': '#f3f4f6', 'color': '#999'}),
                html.Td("—", style={'textAlign': 'center', 'backgroundColor': '#f3f4f6', 'color': '#999'})
            ])
        
        tabla_filas.append(fila_total)
        
        # Encabezados
        if hay_datos_reales and df_real is not None:
            encabezados = [
                html.Th("Fuente", style={'width': '20%'}),
                html.Th("Predicho", style={'textAlign': 'center', 'width': '20%'}),
                html.Th("Real (XM)", style={'textAlign': 'center', 'width': '20%'}),
                html.Th("Diferencia", style={'textAlign': 'center', 'width': '20%'}),
                html.Th("Error %", style={'textAlign': 'center', 'width': '20%'})
            ]
        else:
            encabezados = [
                html.Th("Fuente", style={'width': '20%'}),
                html.Th("Predicho", style={'textAlign': 'center', 'width': '20%'}),
                html.Th("Real (XM)", style={'textAlign': 'center', 'width': '20%'}),
                html.Th("Diferencia", style={'textAlign': 'center', 'width': '20%'}),
                html.Th("Error %", style={'textAlign': 'center', 'width': '20%'})
            ]
        
        # Tabla completa
        tabla = dbc.Table([
            html.Thead(html.Tr(encabezados)),
            html.Tbody(tabla_filas)
        ], bordered=True, hover=True, responsive=True, striped=True,
           style={'fontSize': '0.9rem', 'marginTop': '10px'})
        
        # Sin mensaje adicional - diseño minimalista
        contenido = tabla
        
        titulo = f"Validación de Predicción - {fecha_display}"
        
        return (True, titulo, contenido)
        
    except Exception as e:
        logger.error(f"Error en validación: {e}")
        traceback.print_exc()
        return (True,
               "Error",
               dbc.Alert(f"Error al cargar datos: {str(e)}", color="danger"))