
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
import numpy as np
from datetime import date, timedelta, datetime
from io import StringIO
import warnings
import traceback

# Use the installed pydataxm package
try:
    from pydataxm.pydataxm import ReadDB
    PYDATAXM_AVAILABLE = True
except ImportError:
    PYDATAXM_AVAILABLE = False
    print("⚠️ pydataxm no está disponible. Algunos datos pueden no cargarse correctamente.")

# Imports locales
from utils.components import crear_navbar_horizontal, crear_filtro_fechas_compacto, registrar_callback_filtro_fechas, crear_boton_regresar
from utils.config import COLORS
from utils._xm import get_objetoAPI, fetch_metric_data, obtener_datos_inteligente
import logging

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")

register_page(
    __name__,
    path="/distribucion",
    name="Distribución Eléctrica",
    title="Distribución Eléctrica - Demanda por Agente - Ministerio de Minas y Energía",
    order=10
)

def obtener_listado_agentes():
    """Obtener el listado de agentes ordenados por cantidad de datos y con advertencias"""
    try:
        import sqlite3
        from utils.db_manager import DB_PATH
        
        # Paso 1: Obtener estadísticas de datos por agente
        conn = sqlite3.connect(str(DB_PATH))
        query = """
        SELECT 
            recurso as code,
            COUNT(*) as total_registros,
            COUNT(DISTINCT fecha) as dias_unicos,
            COUNT(DISTINCT metrica) as metricas_distintas,
            MIN(fecha) as fecha_min,
            MAX(fecha) as fecha_max
        FROM metrics
        WHERE entidad = 'Agente' 
        AND metrica IN ('DemaCome', 'DemaReal', 'DemaRealReg', 'DemaRealNoReg')
        AND recurso IS NOT NULL
        GROUP BY recurso
        ORDER BY total_registros DESC, dias_unicos DESC
        """
        
        agentes_estadisticas = pd.read_sql_query(query, conn)
        conn.close()
        
        if agentes_estadisticas.empty:
            logger.warning("⚠️ No se encontraron agentes con datos en la base")
            return pd.DataFrame()
        
        logger.info(f"📊 {len(agentes_estadisticas)} agentes con datos encontrados")
        
        # Calcular advertencias para cada agente
        fecha_actual = date.today()
        dias_del_ano = (fecha_actual - date(fecha_actual.year, 1, 1)).days + 1
        
        def generar_advertencia(row):
            advertencias = []
            
            # Verificar si tiene menos de 100 días de datos
            if row['dias_unicos'] < 100:
                advertencias.append(f"⚠️ Solo {row['dias_unicos']} días")
            
            # Verificar si le faltan métricas (debería tener al menos 2: DemaCome y DemaReal)
            if row['metricas_distintas'] < 2:
                advertencias.append("⚠️ Datos incompletos")
            
            # Verificar si los datos son muy antiguos (último dato hace más de 30 días)
            try:
                fecha_max = pd.to_datetime(row['fecha_max']).date()
                dias_desde_ultimo = (fecha_actual - fecha_max).days
                if dias_desde_ultimo > 30:
                    advertencias.append(f"⚠️ Último dato: {dias_desde_ultimo} días atrás")
            except:
                pass
            
            return " | ".join(advertencias) if advertencias else ""
        
        agentes_estadisticas['advertencia'] = agentes_estadisticas.apply(generar_advertencia, axis=1)
        
        # Paso 2: Obtener catálogo para mapear códigos a nombres
        fecha_fin = date.today() - timedelta(days=1)
        fecha_inicio = fecha_fin - timedelta(days=7)
        
        catalogo, warning = obtener_datos_inteligente("ListadoAgentes", "Sistema", 
                                                      fecha_inicio.strftime('%Y-%m-%d'), 
                                                      fecha_fin.strftime('%Y-%m-%d'))
        
        if catalogo is not None and not catalogo.empty and 'Values_Code' in catalogo.columns:
            # Hacer merge para agregar nombres
            agentes = agentes_estadisticas.merge(
                catalogo[['Values_Code', 'Values_Name', 'Values_State']], 
                left_on='code', 
                right_on='Values_Code', 
                how='left'
            )
            
            # Filtrar solo agentes activos
            if 'Values_State' in agentes.columns:
                agentes = agentes[agentes['Values_State'] == 'OPERACION'].copy()
            
            # Asegurar que tenga las columnas necesarias
            if 'Values_Code' not in agentes.columns:
                agentes['Values_Code'] = agentes['code']
            if 'Values_Name' not in agentes.columns:
                agentes['Values_Name'] = agentes['code']
            
            # Ordenar por total de registros (descendente)
            agentes = agentes.sort_values('total_registros', ascending=False)
            
            logger.info(f"✅ {len(agentes)} agentes disponibles (ordenados por cantidad de datos)")
            return agentes
        else:
            # Si no hay catálogo, usar códigos directamente
            agentes_estadisticas['Values_Code'] = agentes_estadisticas['code']
            agentes_estadisticas['Values_Name'] = agentes_estadisticas['code']
            logger.info(f"✅ {len(agentes_estadisticas)} agentes disponibles (solo códigos)")
            return agentes_estadisticas
            
    except Exception as e:
        logger.error(f"❌ Error obteniendo listado de agentes: {e}")
        traceback.print_exc()
    return pd.DataFrame()

def obtener_demanda_comercial(fecha_inicio, fecha_fin, codigos_agentes=None):
    """Obtener datos de demanda comercial (DemaCome) por agente"""
    try:
        # ✅ OPTIMIZADO: Consulta inteligente SQLite (>=2020) vs API (<2020)
        # La conversión kWh→GWh se hace después del filtrado
        df, warning_msg = obtener_datos_inteligente('DemaCome', 'Agente', 
                               fecha_inicio.strftime('%Y-%m-%d') if hasattr(fecha_inicio, 'strftime') else fecha_inicio,
                               fecha_fin.strftime('%Y-%m-%d') if hasattr(fecha_fin, 'strftime') else fecha_fin)
        if warning_msg:
            logger.info(f"⚠️ {warning_msg}")
        
        if df is None or df.empty:
            print("No se obtuvieron datos de DemaCome")
            return pd.DataFrame()
        
        # Filtrar por códigos si se proporcionan
        if codigos_agentes:
            logger.info(f"🔍 Filtrando DemaCome por agentes: {codigos_agentes}")
            logger.info(f"🔍 Registros antes del filtro: {len(df)}")
            
            # Buscar la columna correcta (puede ser Values_code o Values_Code)
            code_column = None
            if 'Values_code' in df.columns:
                code_column = 'Values_code'
            elif 'Values_Code' in df.columns:
                code_column = 'Values_Code'
            
            if code_column:
                # Mostrar algunos códigos disponibles para debug
                codigos_disponibles = df[code_column].unique()
                logger.info(f"📊 Códigos disponibles (primeros 10): {codigos_disponibles[:10].tolist()}")
                
                df = df[df[code_column].isin(codigos_agentes)].copy()
                logger.info(f"✅ Registros después del filtro: {len(df)}")
                
                if len(df) == 0:
                    logger.warning(f"⚠️ No se encontraron datos para agentes: {codigos_agentes}")
            else:
                logger.error(f"❌ No se encontró columna de código en DemaCome")
                logger.error(f"❌ Columnas disponibles: {df.columns.tolist()}")
        
        # Procesar datos horarios
        df_procesado = procesar_datos_horarios(df, 'DemaCome')
        
        return df_procesado
        
    except Exception as e:
        print(f"Error obteniendo demanda comercial: {e}")
        traceback.print_exc()
        return pd.DataFrame()

def obtener_demanda_real(fecha_inicio, fecha_fin, codigos_agentes=None):
    """Obtener datos de demanda real por agente"""
    try:
        # ✅ OPTIMIZADO: Usar obtener_datos_inteligente (SQLite)
        # La conversión kWh→GWh se hace después del filtrado
        df, warning = obtener_datos_inteligente('DemaReal', 'Agente', 
                                                 fecha_inicio.strftime('%Y-%m-%d') if hasattr(fecha_inicio, 'strftime') else fecha_inicio,
                                                 fecha_fin.strftime('%Y-%m-%d') if hasattr(fecha_fin, 'strftime') else fecha_fin)
        
        if df is None or df.empty:
            print("No se obtuvieron datos de DemaReal")
            return pd.DataFrame()
        
        # Filtrar por códigos si se proporcionan
        if codigos_agentes:
            logger.info(f"🔍 Filtrando DemaReal por agentes: {codigos_agentes}")
            logger.info(f"🔍 Registros antes del filtro: {len(df)}")
            
            # Buscar la columna correcta (puede ser Values_code o Values_Code)
            code_column = None
            if 'Values_code' in df.columns:
                code_column = 'Values_code'
            elif 'Values_Code' in df.columns:
                code_column = 'Values_Code'
            
            if code_column:
                # Mostrar algunos códigos disponibles para debug
                codigos_disponibles = df[code_column].unique()
                logger.info(f"📊 Códigos disponibles (primeros 10): {codigos_disponibles[:10].tolist()}")
                
                df = df[df[code_column].isin(codigos_agentes)].copy()
                logger.info(f"✅ Registros después del filtro: {len(df)}")
                
                if len(df) == 0:
                    logger.warning(f"⚠️ No se encontraron datos para agentes: {codigos_agentes}")
            else:
                logger.error(f"❌ No se encontró columna de código en DemaReal")
                logger.error(f"❌ Columnas disponibles: {df.columns.tolist()}")
        
        # Procesar datos horarios
        df_procesado = procesar_datos_horarios(df, 'DemaReal')
        
        return df_procesado
        
    except Exception as e:
        print(f"Error obteniendo demanda real: {e}")
        traceback.print_exc()
        return pd.DataFrame()

def procesar_datos_horarios(df, tipo_metrica):
    """
    Procesar datos horarios: sumar las 24 horas y convertir de kWh a GWh
    
    Args:
        df: DataFrame con columnas Values_Hour01 a Values_Hour24 O con columna Value ya agregada
        tipo_metrica: 'DemaCome' o 'DemaReal'
    
    Returns:
        DataFrame con columnas: Fecha, Codigo_Agente, Demanda_GWh, Tipo
    """
    if df.empty:
        return pd.DataFrame()
    
    # Identificar si los datos vienen con columnas horarias o ya agregados
    cols_horas = [col for col in df.columns if 'Hour' in col]
    
    if cols_horas:
        # CASO 1: Datos de API XM con columnas horarias (Values_Hour01-24)
        # Reemplazar NaN con 0
        df[cols_horas] = df[cols_horas].fillna(0)
        
        # Sumar las 24 horas para obtener total diario en kWh
        df['Total_kWh'] = df[cols_horas].sum(axis=1)
        
        # Convertir de kWh a GWh
        df['Demanda_GWh'] = df['Total_kWh'] / 1_000_000
    elif 'Value' in df.columns:
        # CASO 2: Datos de SQLite con valor ya agregado en GWh
        df['Demanda_GWh'] = df['Value']
    else:
        logger.error(f"❌ procesar_datos_horarios: No se encontraron columnas horarias ni Value")
        return pd.DataFrame()
    
    # Detectar columna de código de agente
    codigo_col = None
    for col_name in ['Values_code', 'recurso', 'Name']:
        if col_name in df.columns:
            codigo_col = col_name
            break
    
    if codigo_col is None:
        logger.error(f"❌ procesar_datos_horarios: No se encontró columna de código de agente")
        return pd.DataFrame()
    
    # Preparar DataFrame resultado
    df_resultado = pd.DataFrame({
        'Fecha': pd.to_datetime(df['Date']),
        'Codigo_Agente': df[codigo_col],
        'Demanda_GWh': df['Demanda_GWh'],
        'Tipo': tipo_metrica
    })
    
    return df_resultado

def obtener_demanda_no_atendida(fecha_inicio, fecha_fin):
    """Obtener datos de Demanda No Atendida Programada por Área"""
    try:
        # ✅ OPTIMIZADO: Usar obtener_datos_inteligente (SQLite)
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
        # NOTA: Los datos de SQLite ya vienen en GWh (no dividir de nuevo)
        df_resultado = pd.DataFrame({
            'Fecha': pd.to_datetime(df['Date']),
            'Area': df['Name'],
            'Demanda_No_Atendida_GWh': df['Value']  # Ya en GWh desde SQLite
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
        title=titulo,
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
        height=290,
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
        barmode='stack',  # Barras apiladas
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
        height=400,
        margin=dict(l=60, r=30, t=50, b=100)
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
        title={
            'text': 'DNA<br>por Región',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 11, 'color': '#2c3e50'}
        },
        showlegend=False,
        height=400,
        margin=dict(l=10, r=10, t=60, b=10)
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
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#f8f9fa'
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

# ==================== LAYOUT ====================

def layout(**kwargs):
    """Layout principal de la página de distribución"""
    
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

    ficha_dna_nacional = dbc.Card([
        dbc.CardBody([
            html.Div([
                html.I(className="fas fa-bolt", style={'color': '#8B5CF6', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                html.Span("DNA Nacional", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                html.Span(f"{total_dna_nacional:.2f}", id='valor-dna-nacional', style={'fontWeight': 'bold', 'fontSize': '1.2rem', 'color': '#8B5CF6', 'marginRight': '4px'}),
                html.Span("GWh", style={'color': '#666', 'fontSize': '0.65rem'})
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
        ], style={'padding': '0.3rem 0.6rem'})
    ], className="shadow-sm")

    ficha_regulado = dbc.Card([
        dbc.CardBody([
            html.Div([
                html.I(className="fas fa-check-circle", style={'color': '#10B981', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                html.Span("Mercado Regulado", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                html.Span(f"{porcentaje_regulado:.2f}", id='valor-regulado', style={'fontWeight': 'bold', 'fontSize': '1.2rem', 'color': '#10B981', 'marginRight': '4px'}),
                html.Span("%", style={'color': '#666', 'fontSize': '0.65rem'})
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
        ], style={'padding': '0.3rem 0.6rem'})
    ], className="shadow-sm")

    ficha_no_regulado = dbc.Card([
        dbc.CardBody([
            html.Div([
                html.I(className="fas fa-industry", style={'color': '#3B82F6', 'fontSize': '0.8rem', 'marginRight': '6px'}),
                html.Span("Mercado No Regulado", style={'fontWeight': '500', 'color': '#666', 'fontSize': '0.65rem', 'marginRight': '8px'}),
                html.Span(f"{porcentaje_no_regulado:.2f}", id='valor-no-regulado', style={'fontWeight': 'bold', 'fontSize': '1.2rem', 'color': '#3B82F6', 'marginRight': '4px'}),
                html.Span("%", style={'color': '#666', 'fontSize': '0.65rem'})
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'flex-start'})
        ], style={'padding': '0.3rem 0.6rem'})
    ], className="shadow-sm")

    return html.Div([
        crear_navbar_horizontal(),
        html.Div(style={'maxWidth': '100%', 'padding': '5px'}, children=[
        dbc.Container([
            crear_boton_regresar(),
            
            # FILTROS UNIFICADOS EN UNA SOLA FILA HORIZONTAL
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        # Rango de fechas
                        dbc.Col([
                            html.Label("RANGO:", style={'fontWeight': '600', 'fontSize': '0.65rem', 'marginBottom': '2px', 'color': '#2c3e50'}),
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
                                style={'fontSize': '0.75rem', 'minHeight': '32px'}
                            )
                        ], md=3),
                        
                        # Fecha inicio (oculta)
                        dbc.Col([
                            html.Label("INICIO:", style={'fontWeight': '600', 'fontSize': '0.65rem', 'marginBottom': '2px', 'color': '#2c3e50'}),
                            dcc.DatePickerSingle(
                                id='fecha-inicio-distribucion',
                                date=(date.today() - timedelta(days=180)).strftime('%Y-%m-%d'),
                                display_format='DD/MM/YYYY',
                                style={'fontSize': '0.75rem'}
                            )
                        ], id='container-fecha-inicio-distribucion', md=2, style={'display': 'none'}),
                        
                        # Fecha fin (oculta)
                        dbc.Col([
                            html.Label("FIN:", style={'fontWeight': '600', 'fontSize': '0.65rem', 'marginBottom': '2px', 'color': '#2c3e50'}),
                            dcc.DatePickerSingle(
                                id='fecha-fin-distribucion',
                                date=date.today().strftime('%Y-%m-%d'),
                                display_format='DD/MM/YYYY',
                                style={'fontSize': '0.75rem'}
                            )
                        ], id='container-fecha-fin-distribucion', md=2, style={'display': 'none'}),
                        
                        # Selector de agente
                        dbc.Col([
                            html.Label("AGENTE:", style={'fontWeight': '600', 'fontSize': '0.65rem', 'marginBottom': '2px', 'color': '#2c3e50'}),
                            dcc.Dropdown(
                                id='selector-agente-distribucion',
                                options=opciones_agentes,
                                value='TODOS',
                                placeholder="Agente...",
                                clearable=False,
                                style={'fontSize': '0.75rem', 'minHeight': '32px'}
                            )
                        ], md=4),
                        
                        # Botón actualizar
                        dbc.Col([
                            html.Label("\u00A0", style={'fontSize': '0.65rem', 'marginBottom': '2px', 'display': 'block'}),
                            dbc.Button(
                                [html.I(className="fas fa-sync-alt me-1"), "Actualizar"],
                                id='btn-actualizar-distribucion',
                                color="primary",
                                className="w-100",
                                style={'height': '32px', 'fontSize': '0.75rem'}
                            )
                        ], md=1)
                    ], className="g-2 align-items-end")
                ], style={'padding': '8px 12px'})
            ], style={'marginBottom': '8px', 'border': '1px solid #e0e0e0'}),
            
            # Fichas en la misma fila (después de los filtros)
            dbc.Row([
                dbc.Col([ficha_dna_nacional], md=4),
                dbc.Col([ficha_regulado], md=4),
                dbc.Col([ficha_no_regulado], md=4),
            ], style={'marginBottom': '4px'}),
            # Gráfica de líneas (izquierda) + Barras DNA (centro) + Torta DNA por Región (derecha)
            dbc.Row([
                # Gráfica de evolución temporal (izquierda 60%)
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Div([
                                html.I(className="fas fa-chart-line", style={'fontSize': '0.6rem', 'marginRight': '4px', 'color': '#666'}),
                                html.Span("Evolución Temporal - Demanda Comercial vs Demanda Real", style={'fontSize': '0.65rem', 'color': '#2c3e50'})
                            ], style={'display': 'flex', 'alignItems': 'center'})
                        ], style={'padding': '3px 6px', 'backgroundColor': '#f8f9fa'}),
                        dbc.CardBody([
                            dcc.Loading(
                                id="loading-grafica-distribucion",
                                type="default",
                                children=[
                                    dcc.Graph(
                                        id='grafica-lineas-demanda',
                                        figure=fig_lineas,
                                        config={'displayModeBar': True}
                                    )
                                ]
                            )
                        ], className="p-2")
                    ], className="shadow-sm")
                ], md=7),
                
                # Gráfica de barras de Demanda No Atendida (centro 25%)
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Div([
                                html.I(className="fas fa-chart-bar", style={'fontSize': '0.6rem', 'marginRight': '4px', 'color': '#666'}),
                                html.Span("Demanda No Atendida por Área", style={'fontSize': '0.65rem', 'color': '#2c3e50'})
                            ], style={'display': 'flex', 'alignItems': 'center'})
                        ], style={'padding': '3px 6px', 'backgroundColor': '#f8f9fa'}),
                        dbc.CardBody([
                            dcc.Loading(
                                id="loading-grafica-dna",
                                type="default",
                                children=[
                                    dcc.Graph(
                                        id='grafica-barras-dna',
                                        figure=fig_barras,
                                        config={'displayModeBar': False}
                                    )
                                ]
                            )
                        ], className="p-2")
                    ], className="shadow-sm")
                ], md=3),
                
                # Gráfica de torta DNA por Región (derecha 15%)
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Div([
                                html.I(className="fas fa-chart-pie", style={'fontSize': '0.6rem', 'marginRight': '4px', 'color': '#666'}),
                                html.Span("DNA por Región", style={'fontSize': '0.65rem', 'color': '#2c3e50'})
                            ], style={'display': 'flex', 'alignItems': 'center'})
                        ], style={'padding': '3px 6px', 'backgroundColor': '#f8f9fa'}),
                        dbc.CardBody([
                            dcc.Loading(
                                id="loading-grafica-dna-torta",
                                type="default",
                                children=[
                                    dcc.Graph(
                                        id='grafica-torta-dna-region',
                                        figure=fig_torta,
                                        config={'displayModeBar': False}
                                    )
                                ]
                            )
                        ], className="p-2")
                    ], className="shadow-sm")
                ], md=2)
            ], className="mb-3"),
            # ...existing code...
            dcc.Store(id='store-datos-distribucion'),
            dcc.Store(id='store-agentes-distribucion', data=agentes_df.to_json(date_format='iso', orient='split') if not agentes_df.empty else None),
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle(id="modal-title-demanda")),
                dbc.ModalBody([
                    html.P(id="modal-description-demanda", className="mb-3"),
                    html.Div(id="modal-table-content-demanda")
                ]),
                dbc.ModalFooter(
                    dbc.Button("Cerrar", id="close-modal-demanda", className="ms-auto", n_clicks=0)
                )
            ], id="modal-detalle-demanda", is_open=False, size="xl")
        ], fluid=True, className="py-4")
        ])
    ])

# ==================== CALLBACKS ====================

@callback(
    [Output('grafica-lineas-demanda', 'figure'),
     Output('grafica-barras-dna', 'figure'),
     Output('grafica-torta-dna-region', 'figure'),
     Output('store-datos-distribucion', 'data'),
     Output('valor-dna-nacional', 'children'),
     Output('fecha-dna-nacional', 'children'),
     Output('valor-regulado', 'children'),
     Output('fecha-regulado', 'children'),
     Output('valor-no-regulado', 'children'),
     Output('fecha-no-regulado', 'children')],
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
                code_column = 'Values_code' if 'Values_code' in df_noreg.columns else 'Values_Code'
                logger.info(f"🔍 Filtrando DemaRealNoReg por agente {codigo_agente}, columna: {code_column}")
                logger.info(f"📊 Registros antes del filtro: {len(df_noreg)}")
                df_noreg = df_noreg[df_noreg[code_column] == codigo_agente]
                logger.info(f"✅ Registros después del filtro: {len(df_noreg)}")
                demanda_no_regulada = df_noreg['Value'].sum() if not df_noreg.empty else 0.0
            else:
                demanda_no_regulada = 0.0
            
            # Calcular demanda regulada como: DemaReal - DemaRealNoReg
            # (DemaReal del agente ya está calculada en demanda_real_total)
            demanda_regulada = max(0.0, demanda_real_total - demanda_no_regulada)
            
            logger.info(f"📊 Agente {codigo_agente}: Real={demanda_real_total:.2f} GWh, NoReg={demanda_no_regulada:.2f} GWh, Reg={demanda_regulada:.2f} GWh")
        else:
            # Todos los agentes - consultar a nivel sistema
            df_reg, _ = obtener_datos_inteligente('DemaRealReg', 'Sistema', fecha_inicio, fecha_fin)
            demanda_regulada = df_reg['Value'].sum() if df_reg is not None and not df_reg.empty else 0.0  # Ya en GWh desde SQLite
            
            df_noreg, _ = obtener_datos_inteligente('DemaRealNoReg', 'Sistema', fecha_inicio, fecha_fin)
            demanda_no_regulada = df_noreg['Value'].sum() if df_noreg is not None and not df_noreg.empty else 0.0  # Ya en GWh desde SQLite
        
        # Porcentajes
        porcentaje_regulado = (demanda_regulada / demanda_real_total * 100) if demanda_real_total > 0 else 0.0
        porcentaje_no_regulado = (demanda_no_regulada / demanda_real_total * 100) if demanda_real_total > 0 else 0.0
        
        # Textos de fechas
        texto_fecha = f"Rango de fechas: {fecha_inicio.strftime('%Y-%m-%d')} a {fecha_fin.strftime('%Y-%m-%d')}"
        
        return (
            fig_lineas, 
            fig_barras,
            fig_torta,
            store_data,
            f"{total_dna_nacional:.2f} GWh",
            texto_fecha,
            f"{porcentaje_regulado:.2f}%",
            texto_fecha,
            f"{porcentaje_no_regulado:.2f}%",
            texto_fecha
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
            "Error",
            "Error en fechas",
            "Error",
            "Error en fechas",
            "Error",
            "Error en fechas"
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
    from utils import db_manager
    
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
            # Obtener datos del punto clickeado
            point_data = clickData['points'][0]
            fecha_seleccionada = point_data['x']
            
            # Convertir fecha a formato YYYY-MM-DD
            fecha_dt = pd.to_datetime(fecha_seleccionada)
            fecha_str = fecha_dt.strftime('%Y-%m-%d')
            
            logger.info(f"🎯 Click en gráfica - Fecha: {fecha_str}")
            
            # =========================================================================
            # OBTENER DATOS HORARIOS AGREGADOS DE SQLite (suma de todos los agentes)
            # =========================================================================
            df_horas_come = db_manager.get_hourly_data_aggregated('DemaCome', 'Agente', fecha_str)
            df_horas_real = db_manager.get_hourly_data_aggregated('DemaReal', 'Agente', fecha_str)
            
            if df_horas_come.empty and df_horas_real.empty:
                return False, html.Div("No hay datos horarios disponibles para esta fecha"), "Sin datos", ""
            
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
                data=data_with_total,
                columns=[{"name": col, "id": col} for col in df_tabla.columns],
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
                style_data_conditional=[
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': 'white'
                    },
                    {
                        # Destacar fila TOTAL
                        'if': {'filter_query': '{Hora} = "TOTAL"'},
                        'backgroundColor': COLORS.get('primary', '#0d6efd'),
                        'color': 'white',
                        'fontWeight': 'bold'
                    },
                    {
                        # Diferencia positiva en verde
                        'if': {
                            'filter_query': '{Diferencia (%)} contains "+"',
                            'column_id': 'Diferencia (%)'
                        },
                        'color': COLORS.get('success', '#28a745'),
                        'fontWeight': 'bold'
                    },
                    {
                        # Diferencia negativa en rojo
                        'if': {
                            'filter_query': '{Diferencia (%)} contains "-"',
                            'column_id': 'Diferencia (%)'
                        },
                        'color': COLORS.get('danger', '#dc3545'),
                        'fontWeight': 'bold'
                    },
                    {
                        # Alinear columnas numéricas a la derecha
                        'if': {'column_id': 'Demanda Comercial (GWh)'},
                        'textAlign': 'right'
                    },
                    {
                        'if': {'column_id': 'Demanda Real (GWh)'},
                        'textAlign': 'right'
                    },
                    {
                        'if': {'column_id': 'Diferencia (%)'},
                        'textAlign': 'right'
                    },
                    {
                        'if': {'column_id': 'Participación Horaria (%)'},
                        'textAlign': 'right'
                    },
                    {
                        # Centrar columna Hora
                        'if': {'column_id': 'Hora'},
                        'textAlign': 'center',
                        'fontWeight': '500'
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
