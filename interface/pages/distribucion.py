
def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

import dash
from dash import dcc, html, Input, Output, State, callback, register_page, dash_table
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta, datetime
from io import StringIO
import warnings
import traceback

# Use the installed pydataxm package
try:
    PYDATAXM_AVAILABLE = True
except ImportError:
    PYDATAXM_AVAILABLE = False
    print("⚠️ pydataxm no está disponible. Algunos datos pueden no cargarse correctamente.")

# Imports locales
from interface.components.kpi_card import crear_kpi_row
from interface.components.chart_card import crear_chart_card, crear_page_header, crear_filter_bar
from core.constants import UIColors as COLORS
from domain.services.distribution_service import DistributionService
from infrastructure.database.manager import DatabaseManager
import logging

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")

# Instanciar el servicio
_service = DistributionService()

register_page(
    __name__,
    path="/distribucion",
    name="Distribución Eléctrica",
    title="Distribución Eléctrica - Demanda por Agente - Ministerio de Minas y Energía",
    order=10
)

def obtener_listado_agentes():
    """Obtener el listado de agentes usando el Servicio de Dominio"""
    return _service.get_agents_list()

def obtener_demanda_comercial(fecha_inicio, fecha_fin, codigos_agentes=None):
    """Obtener datos de demanda comercial (DemaCome)"""
    return _service.get_commercial_demand(fecha_inicio, fecha_fin, codigos_agentes)

def obtener_demanda_real(fecha_inicio, fecha_fin, codigos_agentes=None):
    """Obtener datos de demanda real por agente"""
    return _service.get_real_demand(fecha_inicio, fecha_fin, codigos_agentes)

# NOTA: procesar_datos_horarios eliminado, lógica movida a DistributionService

def obtener_datos_inteligente(metrica, entidad, fecha_inicio, fecha_fin):
    """
    Función de compatibilidad para obtener datos vía Service.
    Emula el comportamiento de la función legacy (df, warning).
    """
    try:
        # Normalizar fechas a objetos date
        if isinstance(fecha_inicio, str):
            fecha_inicio = pd.to_datetime(fecha_inicio).date()
        if isinstance(fecha_fin, str):
            fecha_fin = pd.to_datetime(fecha_fin).date()
        
        # Llamar al servicio
        df = _service.get_distribution_data(metrica, fecha_inicio, fecha_fin, entity=entidad)
        
        if df.empty:
            return pd.DataFrame(), "Sin datos"
            
        # Adaptar columnas al formato esperado por el código legacy
        # Servicio retorna: fecha, valor, unidad, agente (recurso)
        # Legacy espera: Date, Value, Name (para recurso)
        df_adapted = df.rename(columns={
            'fecha': 'Date',
            'valor': 'Value',
            'agente': 'Name'
        })
        
        return df_adapted, None
        
    except Exception as e:
        logger.error(f"Error en obtener_datos_inteligente: {e}")
        return pd.DataFrame(), str(e)

def obtener_demanda_no_atendida(fecha_inicio, fecha_fin):
    """Obtener datos de Demanda No Atendida Programada por Área"""
    try:
        # ✅ OPTIMIZADO: Usar obtener_datos_inteligente (PostgreSQL)
        df, warning = obtener_datos_inteligente('DemaNoAtenProg', 'Area', 
                                                 fecha_inicio.strftime('%Y-%m-%d') if hasattr(fecha_inicio, 'strftime') else fecha_inicio,
                                                 fecha_fin.strftime('%Y-%m-%d') if hasattr(fecha_fin, 'strftime') else fecha_fin)
        
        if df is None or df.empty:
            print("No se obtuvieron datos de Demanda No Atendida")
            return pd.DataFrame()
        
        # Filtrar entradas genéricas (recurso='Area') para obtener solo áreas específicas
        if 'Name' in df.columns:
            df = df[df['Name'] != 'Area'].copy()
        
        # Renombrar columnas para mayor claridad
        # NOTA: Los datos de PostgreSQL ya vienen en GWh (no dividir de nuevo)
        df_resultado = pd.DataFrame({
            'Fecha': pd.to_datetime(df['Date']),
            'Area': df['Name'],
            'Demanda_No_Atendida_GWh': df['Value']  # Ya en GWh desde BD local
        })
        
        # Ordenar por fecha descendente
        df_resultado = df_resultado.sort_values('Fecha', ascending=False)
        
        return df_resultado
        
    except Exception as e:
        print(f"Error obteniendo demanda no atendida: {e}")
        traceback.print_exc()
        return pd.DataFrame()

def obtener_demanda_no_atendida_no_programada(fecha_inicio, fecha_fin):
    """Obtener datos de Demanda No Atendida NO Programada por Área"""
    try:
        df, warning = obtener_datos_inteligente('DemaNoAtenNoProg', 'Area', 
                                                 fecha_inicio.strftime('%Y-%m-%d') if hasattr(fecha_inicio, 'strftime') else fecha_inicio,
                                                 fecha_fin.strftime('%Y-%m-%d') if hasattr(fecha_fin, 'strftime') else fecha_fin)
        
        if df is None or df.empty:
            print("No se obtuvieron datos de Demanda No Atendida No Programada")
            return pd.DataFrame()
        
        # Filtrar entradas genéricas (recurso='Area') para obtener solo áreas específicas
        if 'Name' in df.columns:
            df = df[df['Name'] != 'Area'].copy()
        
        df_resultado = pd.DataFrame({
            'Fecha': pd.to_datetime(df['Date']),
            'Area': df['Name'],
            'Demanda_No_Atendida_GWh': df['Value']
        })
        
        df_resultado = df_resultado.sort_values('Fecha', ascending=False)
        return df_resultado
        
    except Exception as e:
        print(f"Error obteniendo demanda no atendida no programada: {e}")
        traceback.print_exc()
        return pd.DataFrame()

def crear_grafica_lineas_demanda(df_demanda_come, df_demanda_real, agente_nombre=None):
    """
    Crear gráfica de líneas comparando DemaCome y DemaReal con barras de diferencia porcentual
    
    Args:
        df_demanda_come: DataFrame con demanda comercial
        df_demanda_real: DataFrame con demanda real
        agente_nombre: Nombre del agente para el título
    """
    px, go = get_plotly_modules()
    
    fig = go.Figure()
    
    # Preparar datos agregados
    df_come_agg = None
    df_real_agg = None
    
    # Agregar línea de Demanda Comercial
    if not df_demanda_come.empty:
        df_come_agg = df_demanda_come.groupby('Fecha', as_index=False)['Demanda_GWh'].sum()
        df_come_agg = df_come_agg.sort_values('Fecha')
        
        fig.add_trace(go.Scatter(
            x=df_come_agg['Fecha'],
            y=df_come_agg['Demanda_GWh'],
            mode='lines+markers',
            name='Demanda Comercial',
            line=dict(color=COLORS.get('primary', '#0d6efd'), width=2),
            marker=dict(size=6),
            hovertemplate='<b>Demanda Comercial</b><br>Fecha: %{x}<br>Demanda: %{y:.4f} GWh<extra></extra>',
            yaxis='y'
        ))
    
    # Agregar línea de Demanda Real
    if not df_demanda_real.empty:
        df_real_agg = df_demanda_real.groupby('Fecha', as_index=False)['Demanda_GWh'].sum()
        df_real_agg = df_real_agg.sort_values('Fecha')
        
        fig.add_trace(go.Scatter(
            x=df_real_agg['Fecha'],
            y=df_real_agg['Demanda_GWh'],
            mode='lines+markers',
            name='Demanda Real',
            line=dict(color=COLORS.get('success', '#28a745'), width=2, dash='dot'),
            marker=dict(size=6),
            hovertemplate='<b>Demanda Real</b><br>Fecha: %{x}<br>Demanda: %{y:.4f} GWh<extra></extra>',
            yaxis='y'
        ))
    
    # Calcular y agregar barras de diferencia porcentual (en valor absoluto)
    if df_come_agg is not None and df_real_agg is not None and not df_come_agg.empty and not df_real_agg.empty:
        # Merge para calcular diferencia
        df_merged = pd.merge(
            df_come_agg.rename(columns={'Demanda_GWh': 'Come_GWh'}),
            df_real_agg.rename(columns={'Demanda_GWh': 'Real_GWh'}),
            on='Fecha',
            how='inner'
        )
        
        # Calcular diferencia porcentual en valor absoluto
        # |((Real - Comercial) / Comercial) * 100|
        df_merged['Diferencia_Pct'] = abs(
            ((df_merged['Real_GWh'] - df_merged['Come_GWh']) / df_merged['Come_GWh']) * 100
        )
        
        # Calcular diferencia absoluta en GWh para el tooltip
        df_merged['Diferencia_GWh'] = abs(df_merged['Real_GWh'] - df_merged['Come_GWh'])
        
        # Agregar barras de diferencia porcentual en eje Y secundario
        fig.add_trace(go.Bar(
            x=df_merged['Fecha'],
            y=df_merged['Diferencia_Pct'],
            name='Diferencia Absoluta (%)',
            marker=dict(
                color='rgba(158, 158, 158, 0.4)',  # Gris semitransparente
                line=dict(color='rgba(128, 128, 128, 0.6)', width=1)
            ),
            hovertemplate=(
                '<b>Diferencia</b><br>'
                'Fecha: %{x}<br>'
                'Diferencia: %{customdata[0]:.4f} GWh<br>'
                'Diferencia %: %{y:.2f}%<br>'
                '<i>(|Real - Comercial| / Comercial)</i>'
                '<extra></extra>'
            ),
            customdata=df_merged[['Diferencia_GWh']].values,
            yaxis='y2'
        ))
    
    titulo = "Evolución Temporal - Demanda por Agente"
    if agente_nombre:
        titulo = f"Evolución Temporal - {agente_nombre}"
    
    fig.update_layout(
        xaxis_title="Fecha",
        yaxis=dict(
            title="Demanda (GWh)",
            side='left'
        ),
        yaxis2=dict(
            title="Diferencia Absoluta (%)",
            overlaying='y',
            side='right',
            showgrid=False
        ),
        hovermode='x unified',
        template='plotly_white',
        height=280,
        font=dict(family='Inter, sans-serif'),
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=50, r=50, t=30, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

def crear_grafica_barras_dna_por_area(df_dna_prog, df_dna_no_prog):
    """Crear gráfico de barras agrupadas de demanda no atendida por área con línea de total"""
    px, go = get_plotly_modules()
    
    fig = go.Figure()
    
    if df_dna_prog.empty and df_dna_no_prog.empty:
        fig.add_annotation(
            text="No hay datos disponibles",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="#666")
        )
        return fig
    
    # Agrupar por área y sumar
    df_prog_agg = df_dna_prog.groupby('Area', as_index=False)['Demanda_No_Atendida_GWh'].sum() if not df_dna_prog.empty else pd.DataFrame()
    
    # Para DemaNoAtenNoProg: si solo tiene datos genéricos 'Area', distribuir proporcionalmente
    if not df_dna_no_prog.empty:
        # Verificar si solo tiene datos genéricos
        if 'Area' in df_dna_no_prog['Area'].values and df_dna_no_prog['Area'].nunique() == 1:
            # Distribuir proporcionalmente según DemaNoAtenProg
            total_no_prog = df_dna_no_prog['Demanda_No_Atendida_GWh'].sum()
            if not df_prog_agg.empty and total_no_prog > 0:
                total_prog = df_prog_agg['Demanda_No_Atendida_GWh'].sum()
                if total_prog > 0:
                    # Distribuir proporcionalmente
                    df_prog_agg['No_Programada'] = (df_prog_agg['Demanda_No_Atendida_GWh'] / total_prog) * total_no_prog
                else:
                    df_prog_agg['No_Programada'] = 0
                df_merged = df_prog_agg.rename(columns={'Demanda_No_Atendida_GWh': 'Programada'})
            else:
                df_merged = df_prog_agg.rename(columns={'Demanda_No_Atendida_GWh': 'Programada'}) if not df_prog_agg.empty else pd.DataFrame()
                if not df_merged.empty:
                    df_merged['No_Programada'] = 0
        else:
            # Tiene datos específicos por área
            df_no_prog_agg = df_dna_no_prog.groupby('Area', as_index=False)['Demanda_No_Atendida_GWh'].sum()
            df_merged = pd.merge(
                df_prog_agg.rename(columns={'Demanda_No_Atendida_GWh': 'Programada'}),
                df_no_prog_agg.rename(columns={'Demanda_No_Atendida_GWh': 'No_Programada'}),
                on='Area', how='outer'
            )
    elif not df_prog_agg.empty:
        df_merged = df_prog_agg.rename(columns={'Demanda_No_Atendida_GWh': 'Programada'})
        df_merged['No_Programada'] = 0
    else:
        return fig
    
    if df_merged.empty:
        return fig
    
    df_merged = df_merged.fillna(0)
    df_merged['Total'] = df_merged['Programada'] + df_merged['No_Programada']
    df_merged = df_merged.sort_values('Total', ascending=False)
    
    # Barra apilada 1: Demanda No Atendida Programada (base)
    fig.add_trace(go.Bar(
        x=df_merged['Area'],
        y=df_merged['Programada'],
        name='Programada',
        marker=dict(color='#FFA500'),  # Naranja
        text=df_merged['Programada'].apply(lambda x: f"{x:.2f}" if x > 0 else ""),
        textposition='inside',
        textfont=dict(color='white', size=10),
        hovertemplate='<b>%{x}</b><br>Programada: %{y:.4f} GWh<extra></extra>'
    ))
    
    # Barra apilada 2: Demanda No Atendida No Programada (encima de Programada)
    fig.add_trace(go.Bar(
        x=df_merged['Area'],
        y=df_merged['No_Programada'],
        name='No Programada',
        marker=dict(color='#FF6B6B'),  # Rojo claro
        text=df_merged['No_Programada'].apply(lambda x: f"{x:.2f}" if x > 0 else ""),
        textposition='inside',
        textfont=dict(color='white', size=10),
        hovertemplate='<b>%{x}</b><br>No Programada: %{y:.4f} GWh<extra></extra>'
    ))
    
    # Línea negra del total
    fig.add_trace(go.Scatter(
        x=df_merged['Area'],
        y=df_merged['Total'],
        mode='lines+markers+text',
        name='Total',
        line=dict(color='#000000', width=2.5),
        marker=dict(color='#000000', size=8, symbol='circle'),
        text=df_merged['Total'].apply(lambda x: f"{x:.2f}"),
        textposition='top center',
        textfont=dict(color='#000000', size=11, family='Arial Black'),
        hovertemplate='<b>%{x}</b><br>Total: %{y:.4f} GWh<extra></extra>'
    ))
    
    fig.update_layout(
        xaxis=dict(
            title='Área',
            tickangle=-45,
            tickfont=dict(size=11)
        ),
        yaxis=dict(
            title='Demanda No Atendida (GWh)',
            tickfont=dict(size=11)
        ),
        barmode='stack',
        bargap=0.2,
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='center',
            x=0.5
        ),
        template='plotly_white',
        height=280,
        font=dict(family='Inter, sans-serif'),
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=50, r=30, t=30, b=80)
    )
    
    return fig


def crear_grafica_torta_dna_por_region(df_dna_prog, df_dna_no_prog):
    """Crear gráfico de torta de demanda no atendida por región"""
    px, go = get_plotly_modules()
    
    fig = go.Figure()
    
    if df_dna_prog.empty and df_dna_no_prog.empty:
        fig.add_annotation(
            text="No hay datos",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=12, color="#666")
        )
        return fig
    
    # Combinar ambos dataframes y agrupar por área
    df_total = pd.concat([df_dna_prog, df_dna_no_prog], ignore_index=True) if not df_dna_prog.empty and not df_dna_no_prog.empty else (df_dna_prog if not df_dna_prog.empty else df_dna_no_prog)
    
    if df_total.empty:
        return fig
    
    # Agrupar por área
    df_region = df_total.groupby('Area', as_index=False)['Demanda_No_Atendida_GWh'].sum()
    df_region = df_region.sort_values('Demanda_No_Atendida_GWh', ascending=False)
    
    # Crear gráfico de torta
    fig = go.Figure(data=[go.Pie(
        labels=df_region['Area'],
        values=df_region['Demanda_No_Atendida_GWh'],
        hole=0.3,
        textinfo='percent',
        textposition='inside',
        hovertemplate='<b>%{label}</b><br>%{value:.2f} GWh<br>%{percent}<extra></extra>',
        marker=dict(
            colors=['#FF6B6B', '#FFA500', '#FFD93D', '#6BCF7F', '#4ECDC4', '#45B7D1', '#5B8FF9'],
            line=dict(color='white', width=2)
        )
    )])
    
    fig.update_layout(
        showlegend=False,
        height=280,
        font=dict(family='Inter, sans-serif'),
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=10, r=10, t=10, b=10)
    )
    
    return fig
def crear_tabla_demanda_no_atendida(df_dna, page_current=0, page_size=10):
    """
    Crear tabla de Demanda No Atendida Programada con paginación
    
    Args:
        df_dna: DataFrame con demanda no atendida
        page_current: Página actual (0-indexed)
        page_size: Número de filas por página
    """
    if df_dna.empty:
        return html.Div([
            html.P("No hay datos de Demanda No Atendida disponibles", 
                   className="text-muted text-center")
        ])


    # Agrupar por área y sumar la demanda no atendida
    df_agrupado = df_dna.groupby('Area', as_index=False)['Demanda_No_Atendida_GWh'].sum()
    # Ordenar de mayor a menor
    df_agrupado = df_agrupado.sort_values('Demanda_No_Atendida_GWh', ascending=False)
    df_agrupado['Demanda_No_Atendida_GWh'] = df_agrupado['Demanda_No_Atendida_GWh'].apply(lambda x: f"{x:.4f}")

    # Renombrar columnas para display
    df_tabla = df_agrupado[['Area', 'Demanda_No_Atendida_GWh']]
    df_tabla.columns = ['Área', 'Demanda No Atendida (GWh)']

    # Nota sobre "AREA NO DEFINIDA"
    nota_area_no_definida = None
    if 'AREA NO DEFINIDA' in df_tabla['Área'].values:
        nota_area_no_definida = html.Div([
            html.Span("Nota: 'AREA NO DEFINIDA' corresponde a registros donde XM no asignó un área específica en la fuente de datos.", style={'color': COLORS.get('warning', '#ffc107'), 'fontSize': '1rem'})
        ], className="mt-2")

    # Calcular total
    total_gwh = df_dna['Demanda_No_Atendida_GWh'].sum()

    tabla = dash_table.DataTable(
        id='tabla-demanda-no-atendida',
        columns=[{"name": col, "id": col} for col in df_tabla.columns],
        data=df_tabla.to_dict('records'),
        page_current=page_current,
        page_size=page_size,
        page_action='native',
        style_table={'overflowX': 'auto'},
        style_cell={
            'textAlign': 'left',
            'padding': '12px',
            'fontFamily': 'Arial, sans-serif',
            'fontSize': '14px'
        },
        style_header={
            'backgroundColor': COLORS.get('primary', '#0d6efd'),
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'center'
        },
        style_data_conditional=[  # type: ignore[arg-type]
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#f8f9fa'  # type: ignore[typeddict-unknown-key]
            }
        ]
    )

    # Fila de total
    total_row = html.Div([
        html.Strong("Total Demanda No Atendida: "),
        html.Span(f"{total_gwh:.4f} GWh", 
                 style={'color': COLORS.get('danger', '#dc3545'), 'fontSize': '1.1rem'})
    ], className="mt-3 text-end", style={'padding': '10px'})

    if nota_area_no_definida:
        return html.Div([tabla, total_row, nota_area_no_definida])
    else:
        return html.Div([tabla, total_row])

# ==================== MAPA DEPARTAMENTAL ====================

def _crear_mapa_distribucion():
    """Choropleth de demanda eléctrica por departamento. Pesos UPME 2023."""
    import json
    import os
    px, go = get_plotly_modules()
    try:
        df = _service.get_demanda_por_departamento()
        geojson_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "assets",
            "departamentos_colombia.geojson",
        )
        with open(geojson_path, encoding="utf-8") as f:
            geojson = json.load(f)

        fig = px.choropleth(
            df,
            geojson=geojson,
            locations="codigo_dpto",
            featureidkey="properties.DPTO",
            color="demanda_gwh_dia",
            color_continuous_scale="Blues",
            labels={
                "demanda_gwh_dia": "Demanda (GWh/día)",
                "participacion_pct": "Participación (%)",
            },
            hover_name="departamento",
            hover_data={
                "participacion_pct": True,
                "demanda_gwh_anual": True,
                "codigo_dpto": False,
            },
            title="Distribución de Demanda Eléctrica — Colombia",
        )
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(
            height=550,
            margin=dict(l=0, r=0, t=50, b=0),
            coloraxis_colorbar=dict(title="GWh/día", thickness=15),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", size=12),
        )

        top5 = df.head(5)[["departamento", "demanda_gwh_dia", "categoria"]]
        rows_top5 = [
            html.Tr([html.Td(r["departamento"]),
                     html.Td(f"{r['demanda_gwh_dia']:.1f} GWh/día"),
                     html.Td(r["categoria"])])
            for _, r in top5.iterrows()
        ]

        return html.Div([
            dbc.Alert([
                html.I(className="fas fa-circle-info me-2"),
                "Estimación basada en factores de participación UPME Balance Energético 2023 "
                "aplicados a la demanda nacional calculada de la BD. "
                "No representa medición directa por departamento.",
            ], color="info", className="mb-3 small"),
            dbc.Row([
                dbc.Col(
                    dcc.Graph(figure=fig, config={"displayModeBar": False}),
                    md=8,
                ),
                dbc.Col([
                    html.H6("🔵 Top 5 Mayor Demanda", className="mb-2 fw-bold"),
                    dbc.Table(
                        [html.Thead(html.Tr([
                            html.Th("Departamento"),
                            html.Th("Demanda"),
                            html.Th("Categoría"),
                        ])),
                         html.Tbody(rows_top5)],
                        bordered=True, hover=True, size="sm",
                    ),
                    html.Small(
                        "Fuente: UPME Balance Energético 2023. "
                        "Demanda base calculada de BD (30d avg).",
                        className="text-muted fst-italic d-block mt-2",
                        style={"fontSize": "0.75rem"},
                    ),
                ], md=4),
            ]),
        ])
    except Exception as e:
        logger.error("Error mapa departamental distribución: %s", e, exc_info=True)
        return dbc.Alert(f"Error cargando mapa: {e}", color="danger")


# ==================== LAYOUT ====================

def layout(**kwargs):
    """Layout principal de la página de distribución"""
    
    # Initialize with defaults in case the try block fails
    fecha_fin = date.today() - timedelta(days=1)
    fecha_inicio = fecha_fin - timedelta(days=365)
    df_dna = pd.DataFrame()
    df_demanda_real = pd.DataFrame()
    agentes_df = pd.DataFrame()

    # Obtener datos iniciales
    try:
        fecha_fin = date.today() - timedelta(days=1)
        fecha_inicio = fecha_fin - timedelta(days=365)  # ✅ Último año por defecto (igual que generación)
        
        # Obtener listado de agentes (ya ordenados por cantidad de datos)
        agentes_df = obtener_listado_agentes()
        
        # Opciones para el dropdown con advertencias
        if not agentes_df.empty and 'Values_Code' in agentes_df.columns and 'Values_Name' in agentes_df.columns:
            opciones_agentes = []
            for _, row in agentes_df.iterrows():
                # Construir etiqueta con advertencia si existe
                label = f"{row['Values_Code']} - {row['Values_Name']}"
                if 'advertencia' in row and row['advertencia']:
                    label += f" {row['advertencia']}"
                
                opciones_agentes.append({
                    'label': label,
                    'value': row['Values_Code']
                })
            
            # Agregar opción "Todos" al inicio
            opciones_agentes.insert(0, {'label': '📊 TODOS LOS AGENTES', 'value': 'TODOS'})
            
            logger.info(f"✅ Dropdown creado con {len(opciones_agentes)-1} agentes (ordenados por datos)")
        else:
            opciones_agentes = [{'label': '⚠️ No hay agentes disponibles', 'value': None}]
        
        # Obtener datos de demanda para todos los agentes inicialmente
        df_demanda_come = obtener_demanda_comercial(fecha_inicio, fecha_fin)
        df_demanda_real = obtener_demanda_real(fecha_inicio, fecha_fin)
        df_dna = obtener_demanda_no_atendida(fecha_inicio, fecha_fin)
        df_dna_no_prog = obtener_demanda_no_atendida_no_programada(fecha_inicio, fecha_fin)
        
        # Crear gráficas iniciales
        fig_lineas = crear_grafica_lineas_demanda(df_demanda_come, df_demanda_real)
        fig_barras = crear_grafica_barras_dna_por_area(df_dna, df_dna_no_prog)
        fig_torta = crear_grafica_torta_dna_por_region(df_dna, df_dna_no_prog)
        
        # Crear tabla inicial
        tabla_dna = crear_tabla_demanda_no_atendida(df_dna)
        
    except Exception as e:
        print(f"Error cargando datos iniciales: {e}")
        traceback.print_exc()
        opciones_agentes = []
        go = get_plotly_modules()[1]
        fig_lineas = go.Figure()
        fig_barras = go.Figure()
        fig_torta = go.Figure()
        tabla_dna = html.Div("Error cargando datos")
    
    # FICHAS: Demanda No Atendida Nacional y Participaciones
    total_dna_nacional = df_dna['Demanda_No_Atendida_GWh'].sum() if not df_dna.empty else 0.0

    # Demanda Real total
    demanda_real_total = df_demanda_real['Demanda_GWh'].sum() if not df_demanda_real.empty else 0.0
    # Demanda Real Regulado
    df_reg, _ = obtener_datos_inteligente('DemaRealReg', 'Sistema', fecha_inicio, fecha_fin)
    demanda_regulada = df_reg['Value'].sum() if df_reg is not None and not df_reg.empty else 0.0
    # Demanda Real No Regulado
    df_noreg, _ = obtener_datos_inteligente('DemaRealNoReg', 'Sistema', fecha_inicio, fecha_fin)
    demanda_no_regulada = df_noreg['Value'].sum() if df_noreg is not None and not df_noreg.empty else 0.0

    # Porcentajes
    porcentaje_regulado = (demanda_regulada / demanda_real_total * 100) if demanda_real_total > 0 else 0.0
    porcentaje_no_regulado = (demanda_no_regulada / demanda_real_total * 100) if demanda_real_total > 0 else 0.0

    # FICHAS: KPIs via design system
    kpis_iniciales = crear_kpi_row([
        {"titulo": "DNA Nacional", "valor": f"{total_dna_nacional:.2f}", "unidad": "GWh", "icono": "fas fa-bolt", "color": "purple"},
        {"titulo": "Mercado Regulado", "valor": f"{porcentaje_regulado:.2f}", "unidad": "%", "icono": "fas fa-check-circle", "color": "green"},
        {"titulo": "Mercado No Regulado", "valor": f"{porcentaje_no_regulado:.2f}", "unidad": "%", "icono": "fas fa-industry", "color": "blue"},
    ], columnas=3)

    return html.Div([
        html.Div(className="t-page", children=[

        crear_page_header(
            titulo="Distribución Eléctrica",
            icono="fas fa-network-wired",
            breadcrumb="Inicio / Distribución",
        ),

        # FILTROS
        crear_filter_bar(
            html.Div([
                html.Label("RANGO:", className="t-filter-label"),
                dcc.Dropdown(
                    id='rango-fechas-distribucion',
                    options=[
                        {'label': 'Último mes', 'value': '1m'},
                        {'label': 'Últimos 6 meses', 'value': '6m'},
                        {'label': 'Último año', 'value': '1y'},
                        {'label': 'Últimos 2 años', 'value': '2y'},
                        {'label': 'Últimos 5 años', 'value': '5y'},
                        {'label': 'Personalizado', 'value': 'custom'}
                    ],
                    value='6m',
                    clearable=False,
                    style={'width': '160px', 'fontSize': '0.75rem'}
                )
            ]),
            html.Div([
                html.Label("INICIO:", className="t-filter-label"),
                dcc.DatePickerSingle(
                    id='fecha-inicio-distribucion',
                    date=(date.today() - timedelta(days=180)).strftime('%Y-%m-%d'),
                    display_format='DD/MM/YYYY',
                    style={'fontSize': '0.75rem'}
                )
            ], id='container-fecha-inicio-distribucion', style={'display': 'none'}),
            html.Div([
                html.Label("FIN:", className="t-filter-label"),
                dcc.DatePickerSingle(
                    id='fecha-fin-distribucion',
                    date=date.today().strftime('%Y-%m-%d'),
                    display_format='DD/MM/YYYY',
                    style={'fontSize': '0.75rem'}
                )
            ], id='container-fecha-fin-distribucion', style={'display': 'none'}),
            html.Div([
                html.Label("AGENTE:", className="t-filter-label"),
                dcc.Dropdown(
                    id='selector-agente-distribucion',
                    options=opciones_agentes,
                    value='TODOS',
                    placeholder="Agente...",
                    clearable=False,
                    style={'width': '280px', 'fontSize': '0.75rem'}
                )
            ]),
            html.Button(
                [html.I(className="fas fa-sync-alt me-1"), "Actualizar"],
                id='btn-actualizar-distribucion',
                className="t-btn-filter",
            ),
            dbc.Button(
                [html.I(className="fas fa-file-excel me-1"), "Excel"],
                id='btn-excel-distribucion', color="success", size="sm", outline=True,
            ),
        ),

        # KPIs
        html.Div(kpis_iniciales, id='kpis-distribucion', style={'marginBottom': '12px'}),

        # Charts row: líneas (7) + barras (3) + torta (2)
        html.Div([
            html.Div([
                crear_chart_card(
                    titulo="Evolución Temporal – Demanda Comercial vs Real",
                    graph_id='grafica-lineas-demanda',
                    height=280,
                ),
            ], style={'flex': '7'}),
            html.Div([
                crear_chart_card(
                    titulo="DNA por Área",
                    graph_id='grafica-barras-dna',
                    height=280,
                ),
            ], style={'flex': '3'}),
            html.Div([
                crear_chart_card(
                    titulo="DNA por Región",
                    graph_id='grafica-torta-dna-region',
                    height=280,
                ),
            ], style={'flex': '2'}),
        ], style={'display': 'flex', 'gap': '12px', 'marginBottom': '12px'}),

        # Mapa departamental de demanda
        html.Div([
            html.H5("🗺️ Demanda Eléctrica por Departamento",
                    className="mb-3 text-secondary fw-semibold"),
            _crear_mapa_distribucion(),
        ], style={'marginBottom': '12px'}),

        # Stores & Modal
        dcc.Store(id='store-datos-distribucion'),
        dcc.Store(id='store-agentes-distribucion', data=agentes_df.to_json(date_format='iso', orient='split') if not agentes_df.empty else None),
        dcc.Download(id='download-excel-distribucion'),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(id="modal-title-demanda")),
            dbc.ModalBody([
                html.P(id="modal-description-demanda", className="mb-3"),
                html.Div(id="modal-table-content-demanda")
            ]),
            dbc.ModalFooter(
                dbc.Button("Cerrar", id="close-modal-demanda", className="ms-auto", n_clicks=0)
            )
        ], id="modal-detalle-demanda", is_open=False, size="xl"),

        ])  # end t-page
    ])

# ==================== CALLBACKS ====================

@callback(
    [Output('fecha-inicio-distribucion', 'date'),
     Output('fecha-fin-distribucion', 'date'),
     Output('container-fecha-inicio-distribucion', 'style'),
     Output('container-fecha-fin-distribucion', 'style')],
    [Input('rango-fechas-distribucion', 'value')],
    [State('fecha-inicio-distribucion', 'date'),
     State('fecha-fin-distribucion', 'date')]
)
def actualizar_fechas_por_rango(rango, fecha_inicio_actual, fecha_fin_actual):
    """Actualizar fechas según el rango seleccionado"""
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate

    today = date.today()
    display_none = {'display': 'none'}
    display_block = {'display': 'block'}

    if rango == 'custom':
        # Mantener fechas actuales, mostrar selectores
        return fecha_inicio_actual, fecha_fin_actual, display_block, display_block
    
    # Calcular nueva fecha de inicio
    fecha_fin = today.strftime('%Y-%m-%d')
    
    if rango == '1m':
        dt = today - timedelta(days=30)
    elif rango == '6m':
        dt = today - timedelta(days=180)
    elif rango == '1y':
        dt = today - timedelta(days=365)
    elif rango == '2y':
        dt = today - timedelta(days=730)
    elif rango == '5y':
        dt = today - timedelta(days=1825)
    else:
        dt = today - timedelta(days=180)
        
    fecha_inicio = dt.strftime('%Y-%m-%d')
    
    return fecha_inicio, fecha_fin, display_none, display_none

@callback(
    [Output('grafica-lineas-demanda', 'figure'),
     Output('grafica-barras-dna', 'figure'),
     Output('grafica-torta-dna-region', 'figure'),
     Output('store-datos-distribucion', 'data'),
     Output('kpis-distribucion', 'children')],
    [Input('btn-actualizar-distribucion', 'n_clicks')],
    [State('selector-agente-distribucion', 'value'),
     State('fecha-inicio-distribucion', 'date'),
     State('fecha-fin-distribucion', 'date'),
     State('store-agentes-distribucion', 'data')],
    prevent_initial_call=False
)
def actualizar_datos_distribucion(n_clicks, codigo_agente, fecha_inicio_str, fecha_fin_str, agentes_json):
    """Callback para actualizar la gráfica y tabla según los filtros seleccionados"""
    
    px, go = get_plotly_modules()
    
    # Fallback de fechas por defecto si los States no llegan (primer render o hidden)
    if not fecha_fin_str:
        fecha_fin_str = date.today().strftime('%Y-%m-%d')
    if not fecha_inicio_str:
        fecha_inicio_str = (date.today() - timedelta(days=180)).strftime('%Y-%m-%d')

    # Debug: Log cuando se ejecuta el callback
    logger.info(f"🔄 Callback actualizar_datos_distribucion ejecutado - n_clicks: {n_clicks}, agente: {codigo_agente}, fechas: {fecha_inicio_str} a {fecha_fin_str}")
    
    try:
        # Convertir fechas
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        
        # Determinar códigos de agentes a consultar
        codigos_agentes = None
        agente_nombre = "Todos los Agentes"
        
        if codigo_agente and codigo_agente != 'TODOS':
            codigos_agentes = [codigo_agente]
            
            # Obtener nombre del agente
            if agentes_json:
                agentes_df = pd.read_json(StringIO(agentes_json), orient='split')
                agente_row = agentes_df[agentes_df['Values_Code'] == codigo_agente]
                if not agente_row.empty:
                    agente_nombre = agente_row.iloc[0]['Values_Name']
        
        # Obtener datos
        df_demanda_come = obtener_demanda_comercial(fecha_inicio, fecha_fin, codigos_agentes)
        df_demanda_real = obtener_demanda_real(fecha_inicio, fecha_fin, codigos_agentes)
        df_dna = obtener_demanda_no_atendida(fecha_inicio, fecha_fin)
        df_dna_no_prog = obtener_demanda_no_atendida_no_programada(fecha_inicio, fecha_fin)
        
        # Crear gráfica de líneas
        fig_lineas = crear_grafica_lineas_demanda(df_demanda_come, df_demanda_real, agente_nombre)
        
        # Crear gráfica de barras
        fig_barras = crear_grafica_barras_dna_por_area(df_dna, df_dna_no_prog)
        
        # Crear gráfica de torta
        fig_torta = crear_grafica_torta_dna_por_region(df_dna, df_dna_no_prog)
        
        # Guardar datos en store
        store_data = {
            'demanda_come': df_demanda_come.to_json(date_format='iso', orient='split') if not df_demanda_come.empty else None,
            'demanda_real': df_demanda_real.to_json(date_format='iso', orient='split') if not df_demanda_real.empty else None,
            'dna': df_dna.to_json(date_format='iso', orient='split') if not df_dna.empty else None
        }
        
        # Calcular valores para las fichas
        total_dna_nacional = df_dna['Demanda_No_Atendida_GWh'].sum() if not df_dna.empty else 0.0
        demanda_real_total = df_demanda_real['Demanda_GWh'].sum() if not df_demanda_real.empty else 0.0
        
        # Obtener datos de demanda regulada y no regulada
        # IMPORTANTE: DemaRealReg solo existe a nivel Sistema, no por Agente
        # DemaRealNoReg existe tanto a nivel Sistema como por Agente
        if codigo_agente and codigo_agente != 'TODOS':
            # Para un agente específico:
            # - Demanda regulada: Calcular como (DemaReal - DemaRealNoReg) del agente
            # - Demanda no regulada: Consultar directamente DemaRealNoReg del agente
            
            # Obtener demanda no regulada del agente (existe por agente)
            df_noreg, _ = obtener_datos_inteligente('DemaRealNoReg', 'Agente', fecha_inicio, fecha_fin)
            if df_noreg is not None and not df_noreg.empty:
                # Detección robusta de columna de código
                code_column = None
                for col in ['Values_code', 'Values_Code', 'recurso', 'code', 'Code']:
                    if col in df_noreg.columns:
                        code_column = col
                        break
                
                if code_column:
                    logger.info(f"🔍 Filtrando DemaRealNoReg por agente {codigo_agente}, columna: {code_column}")
                    df_noreg = df_noreg[df_noreg[code_column] == codigo_agente]
                    demanda_no_regulada = df_noreg['Value'].sum() if not df_noreg.empty else 0.0
                else:
                    logger.warning(f"⚠️ No se encontró columna de código en DemaRealNoReg. Columnas: {df_noreg.columns.tolist()}")
                    demanda_no_regulada = 0.0
            else:
                demanda_no_regulada = 0.0
            
            # Calcular demanda regulada como: DemaReal - DemaRealNoReg
            # (DemaReal del agente ya está calculada en demanda_real_total)
            demanda_regulada = max(0.0, demanda_real_total - demanda_no_regulada)
            
            logger.info(f"📊 Agente {codigo_agente}: Real={demanda_real_total:.2f} GWh, NoReg={demanda_no_regulada:.2f} GWh, Reg={demanda_regulada:.2f} GWh")
        else:
            # Todos los agentes - consultar a nivel sistema
            df_reg, _ = obtener_datos_inteligente('DemaRealReg', 'Sistema', fecha_inicio, fecha_fin)
            demanda_regulada = df_reg['Value'].sum() if df_reg is not None and not df_reg.empty else 0.0  # Ya en GWh desde BD local
            
            df_noreg, _ = obtener_datos_inteligente('DemaRealNoReg', 'Sistema', fecha_inicio, fecha_fin)
            demanda_no_regulada = df_noreg['Value'].sum() if df_noreg is not None and not df_noreg.empty else 0.0  # Ya en GWh desde BD local
        
        # Porcentajes
        porcentaje_regulado = (demanda_regulada / demanda_real_total * 100) if demanda_real_total > 0 else 0.0
        porcentaje_no_regulado = (demanda_no_regulada / demanda_real_total * 100) if demanda_real_total > 0 else 0.0
        
        # Build KPIs via design system
        kpis = crear_kpi_row([
            {"titulo": "DNA Nacional", "valor": f"{total_dna_nacional:.2f}", "unidad": "GWh", "icono": "fas fa-bolt", "color": "purple"},
            {"titulo": "Mercado Regulado", "valor": f"{porcentaje_regulado:.2f}", "unidad": "%", "icono": "fas fa-check-circle", "color": "green"},
            {"titulo": "Mercado No Regulado", "valor": f"{porcentaje_no_regulado:.2f}", "unidad": "%", "icono": "fas fa-industry", "color": "blue"},
        ], columnas=3)
        
        return (
            fig_lineas, 
            fig_barras,
            fig_torta,
            store_data,
            kpis
        )
        
    except Exception as e:
        print(f"Error en actualizar_datos_distribucion: {e}")
        traceback.print_exc()
        
        fig_error = go.Figure().add_annotation(
            text=f"Error al cargar datos: {str(e)[:100]}",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="red")
        )
        
        return (
            fig_error, 
            fig_error,
            fig_error,
            None,
            crear_kpi_row([
                {"titulo": "DNA Nacional", "valor": "—", "unidad": "", "icono": "fas fa-bolt", "color": "purple"},
                {"titulo": "Mercado Regulado", "valor": "—", "unidad": "", "icono": "fas fa-check-circle", "color": "green"},
                {"titulo": "Mercado No Regulado", "valor": "—", "unidad": "", "icono": "fas fa-industry", "color": "blue"},
            ], columnas=3)
        )

@callback(
    [Output('modal-detalle-demanda', 'is_open'),
     Output('modal-table-content-demanda', 'children'),
     Output('modal-title-demanda', 'children'),
     Output('modal-description-demanda', 'children')],
    [Input('grafica-lineas-demanda', 'clickData'),
     Input('close-modal-demanda', 'n_clicks')],
    [State('store-datos-distribucion', 'data'),
     State('store-agentes-distribucion', 'data'),
     State('modal-detalle-demanda', 'is_open')],
    prevent_initial_call=True
)
def mostrar_detalle_horario(clickData, n_clicks_close, datos_store, agentes_json, is_open):
    """
    Callback para mostrar tabla detallada HORARIA al hacer click en un punto de la gráfica
    
    La tabla muestra 24 filas (una por hora) con:
    - Hora (01 a 24)
    - Demanda Comercial (GWh)
    - Demanda Real (GWh)
    - Diferencia (%) = ((Real - Comercial) / Comercial * 100)
    - Participación Horaria (%) = (Demanda_hora / Total_día * 100)
    """
    
    import dash
    
    # Instanciar DatabaseManager
    db_manager = DatabaseManager()
    
    ctx = dash.callback_context
    
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Si se cerró el modal
    if trigger_id == 'close-modal-demanda':
        return False, None, "", ""
    
    # Si se hizo click en la gráfica
    if trigger_id == 'grafica-lineas-demanda' and clickData:
        try:
            logger.info("="*80)
            logger.info("🚀 CALLBACK MOSTRAR_DETALLE_HORARIO EJECUTADO")
            logger.info("="*80)
            
            # Obtener datos del punto clickeado
            point_data = clickData['points'][0]
            fecha_seleccionada = point_data['x']
            
            # Convertir fecha a formato YYYY-MM-DD
            fecha_dt = pd.to_datetime(fecha_seleccionada)
            fecha_str = fecha_dt.strftime('%Y-%m-%d')
            
            logger.info(f"🎯 Click en gráfica - Fecha: {fecha_str}")
            
            # =========================================================================
            # OBTENER DATOS HORARIOS AGREGADOS DE PostgreSQL (suma de todos los agentes)
            # =========================================================================
            df_horas_come_raw = db_manager.get_hourly_data_aggregated('DemaCome', 'Agente', fecha_str)
            df_horas_real_raw = db_manager.get_hourly_data_aggregated('DemaReal', 'Agente', fecha_str)
            
            if df_horas_come_raw.empty and df_horas_real_raw.empty:
                return False, html.Div("No hay datos horarios disponibles para esta fecha"), "Sin datos", ""
            
            # ✅ FIX: AGREGAR datos por hora (suma de todos los agentes)
            if not df_horas_come_raw.empty:
                logger.info(f"📥 DemaCome RAW: {len(df_horas_come_raw)} filas antes de agregar")
                df_horas_come = df_horas_come_raw.groupby('hora')['valor_mwh'].sum().reset_index()
                logger.info(f"✅ DemaCome AGREGADO: {len(df_horas_come)} filas, primer valor: {df_horas_come.iloc[0]['valor_mwh']:.2f} MWh")
            else:
                df_horas_come = pd.DataFrame()
            
            if not df_horas_real_raw.empty:
                logger.info(f"📥 DemaReal RAW: {len(df_horas_real_raw)} filas antes de agregar")
                df_horas_real = df_horas_real_raw.groupby('hora')['valor_mwh'].sum().reset_index()
                logger.info(f"✅ DemaReal AGREGADO: {len(df_horas_real)} filas, primer valor: {df_horas_real.iloc[0]['valor_mwh']:.2f} MWh")
            else:
                df_horas_real = pd.DataFrame()
            
            # =========================================================================
            # CREAR DATAFRAME CON 24 HORAS
            # =========================================================================
            df_horas = pd.DataFrame({'hora': range(1, 25)})
            
            # Merge con datos de demanda comercial
            if not df_horas_come.empty:
                df_horas = df_horas.merge(
                    df_horas_come[['hora', 'valor_mwh']].rename(columns={'valor_mwh': 'DemaCome_MWh'}),
                    on='hora',
                    how='left'
                )
            else:
                df_horas['DemaCome_MWh'] = 0.0
            
            # Merge con datos de demanda real
            if not df_horas_real.empty:
                df_horas = df_horas.merge(
                    df_horas_real[['hora', 'valor_mwh']].rename(columns={'valor_mwh': 'DemaReal_MWh'}),
                    on='hora',
                    how='left'
                )
            else:
                df_horas['DemaReal_MWh'] = 0.0
            
            # Rellenar NaN con 0
            df_horas['DemaCome_MWh'] = df_horas['DemaCome_MWh'].fillna(0)
            df_horas['DemaReal_MWh'] = df_horas['DemaReal_MWh'].fillna(0)
            
            # Convertir MWh → GWh
            df_horas['DemaCome_GWh'] = df_horas['DemaCome_MWh'] / 1000
            df_horas['DemaReal_GWh'] = df_horas['DemaReal_MWh'] / 1000
            
            logger.info(f"🔢 Primeros valores en GWh - Hora 1: DemaCome={df_horas.iloc[0]['DemaCome_GWh']:.3f}, DemaReal={df_horas.iloc[0]['DemaReal_GWh']:.3f}")
            
            # =========================================================================
            # CALCULAR DIFERENCIA EN PORCENTAJE
            # =========================================================================
            def calcular_diferencia_porcentaje(row):
                if row['DemaCome_GWh'] > 0:
                    return ((row['DemaReal_GWh'] - row['DemaCome_GWh']) / row['DemaCome_GWh'] * 100)
                elif row['DemaReal_GWh'] > 0:
                    return 100.0  # Si no hay comercial pero sí real, 100% de diferencia
                else:
                    return 0.0
            
            df_horas['Diferencia_%'] = df_horas.apply(calcular_diferencia_porcentaje, axis=1)
            
            # =========================================================================
            # CALCULAR PARTICIPACIÓN HORARIA (% del total del día)
            # =========================================================================
            total_dia_come = df_horas['DemaCome_GWh'].sum()
            total_dia_real = df_horas['DemaReal_GWh'].sum()
            
            if total_dia_come > 0:
                df_horas['Participacion_%'] = (df_horas['DemaCome_GWh'] / total_dia_come * 100)
            elif total_dia_real > 0:
                df_horas['Participacion_%'] = (df_horas['DemaReal_GWh'] / total_dia_real * 100)
            else:
                df_horas['Participacion_%'] = 0.0
            
            # =========================================================================
            # FORMATEAR TABLA PARA DISPLAY
            # =========================================================================
            df_tabla = df_horas.copy()
            
            # Formatear columna de hora
            df_tabla['Hora'] = df_tabla['hora'].apply(lambda x: f"Hora {x:02d}")
            
            # Formatear números
            df_tabla['Demanda Comercial (GWh)'] = df_tabla['DemaCome_GWh'].apply(lambda x: f"{x:.4f}")
            df_tabla['Demanda Real (GWh)'] = df_tabla['DemaReal_GWh'].apply(lambda x: f"{x:.4f}")
            df_tabla['Diferencia (%)'] = df_tabla['Diferencia_%'].apply(lambda x: f"{x:+.2f}%")
            df_tabla['Participación Horaria (%)'] = df_tabla['Participacion_%'].apply(lambda x: f"{x:.2f}%")
            
            # Seleccionar columnas finales
            df_tabla = df_tabla[[
                'Hora',
                'Demanda Comercial (GWh)',
                'Demanda Real (GWh)',
                'Diferencia (%)',
                'Participación Horaria (%)'
            ]]
            
            # Agregar fila de TOTAL
            total_row = {
                'Hora': 'TOTAL',
                'Demanda Comercial (GWh)': f"{total_dia_come:.4f}",
                'Demanda Real (GWh)': f"{total_dia_real:.4f}",
                'Diferencia (%)': f"{((total_dia_real - total_dia_come) / total_dia_come * 100) if total_dia_come > 0 else 0:+.2f}%",
                'Participación Horaria (%)': '100.00%'
            }
            
            data_with_total = df_tabla.to_dict('records') + [total_row]
            
            # Crear tabla horaria
            tabla = dash_table.DataTable(
                id='tabla-detalle-horario',
                data=data_with_total,  # type: ignore[arg-type]
                columns=[{"name": col, "id": col} for col in df_tabla.columns],
                css=[{
                    'selector': '.dash-spreadsheet td.cell--selected',
                    'rule': 'background-color: inherit !important;'
                }],
                style_cell={
                    'textAlign': 'left',
                    'padding': '12px',
                    'fontFamily': 'Arial, sans-serif',
                    'fontSize': '14px',
                    'whiteSpace': 'normal',
                    'height': 'auto'
                },
                style_header={
                    'backgroundColor': COLORS.get('primary', '#0d6efd'),
                    'color': 'white',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                style_data={
                    'backgroundColor': '#f8f9fa'
                },
                style_data_conditional=[  # type: ignore[arg-type]
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': 'white'
                    },
                    {
                        # Diferencia positiva en verde (solo si NO es fila TOTAL)
                        'if': {
                            'filter_query': '{Diferencia (%)} contains "+" && {Hora} != "TOTAL"',
                            'column_id': 'Diferencia (%)'
                        },
                        'color': COLORS.get('success', '#28a745'),
                        'fontWeight': 'bold'
                    },
                    {
                        # Diferencia negativa en rojo (solo si NO es fila TOTAL)
                        'if': {
                            'filter_query': '{Diferencia (%)} contains "-" && {Hora} != "TOTAL"',
                            'column_id': 'Diferencia (%)'
                        },
                        'color': COLORS.get('danger', '#dc3545'),
                        'fontWeight': 'bold'
                    },
                    {
                        # Alinear columnas numéricas a la derecha (excepto TOTAL)
                        'if': {
                            'column_id': 'Demanda Comercial (GWh)',
                            'filter_query': '{Hora} != "TOTAL"'
                        },
                        'textAlign': 'right'
                    },
                    {
                        'if': {
                            'column_id': 'Demanda Real (GWh)',
                            'filter_query': '{Hora} != "TOTAL"'
                        },
                        'textAlign': 'right'
                    },
                    {
                        'if': {
                            'column_id': 'Diferencia (%)',
                            'filter_query': '{Hora} != "TOTAL"'
                        },
                        'textAlign': 'right'
                    },
                    {
                        'if': {
                            'column_id': 'Participación Horaria (%)',
                            'filter_query': '{Hora} != "TOTAL"'
                        },
                        'textAlign': 'right'
                    },
                    {
                        # Centrar columna Hora (excepto TOTAL)
                        'if': {
                            'column_id': 'Hora',
                            'filter_query': '{Hora} != "TOTAL"'
                        },
                        'textAlign': 'center',
                        'fontWeight': '500'
                    },
                    {
                        # Fila TOTAL - fondo azul y letras blancas
                        'if': {'filter_query': '{Hora} = "TOTAL"'},
                        'backgroundColor': COLORS.get('primary', '#0d6efd'),
                        'color': 'white',
                        'fontWeight': 'bold',
                        'textAlign': 'center'
                    }
                ],
                page_size=25,  # Mostrar todas las 24 horas + TOTAL sin scroll
                page_action='native',
                sort_action='native',
                filter_action='native',
                export_format='xlsx',
                export_headers='display'
            )
            
            # Título y descripción
            fecha_formateada = pd.to_datetime(fecha_seleccionada).strftime('%d/%m/%Y')
            
            titulo = f"🕐 Detalle Horario - {fecha_formateada}"
            descripcion = f"Distribución horaria de demanda para el día {fecha_formateada}. Se muestran 24 horas con demanda comercial y real, diferencia porcentual entre ambas, y participación de cada hora en el total diario."
            
            return True, tabla, titulo, descripcion
            
        except Exception as e:
            print(f"❌ Error en mostrar_detalle_por_agente: {e}")
            traceback.print_exc()
            return False, html.Div(f"Error: {str(e)[:200]}"), "Error", ""
    
    raise PreventUpdate


# Fase G — Excel export (desde Store, sin re-consultar)
@callback(
    Output('download-excel-distribucion', 'data'),
    Input('btn-excel-distribucion', 'n_clicks'),
    [State('store-datos-distribucion', 'data'),
     State('store-agentes-distribucion', 'data')],
    prevent_initial_call=True,
)
def exportar_excel_distribucion(n_clicks, store_data, store_agentes):
    import io
    from io import StringIO
    try:
        if not store_data and not store_agentes:
            return dash.no_update
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            if store_data:
                for key in ('demanda_come', 'demanda_real', 'dna'):
                    json_str = store_data.get(key) if isinstance(store_data, dict) else None
                    if json_str:
                        try:
                            df = pd.read_json(StringIO(json_str), orient='split')
                            sheet = key.replace('demanda_', 'Demanda_').replace('dna', 'DNA').title()
                            df.to_excel(writer, sheet_name=sheet[:31], index=False)
                        except Exception:
                            pass
            if store_agentes:
                try:
                    df_ag = pd.read_json(StringIO(store_agentes), orient='split')
                    df_ag.to_excel(writer, sheet_name='Agentes', index=False)
                except Exception:
                    pass
        buf.seek(0)
        return dcc.send_bytes(buf.read(), "distribucion.xlsx")
    except Exception as e:
        logger.error("Error Excel distribucion: %s", e)
        return dash.no_update
