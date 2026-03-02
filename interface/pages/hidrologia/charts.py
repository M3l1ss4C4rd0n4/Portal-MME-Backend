"""
Hidrología - Gráficos y Visualizaciones
=========================================

Funciones para crear gráficos Plotly (líneas, barras, timelines)
para datos hidrológicos.
"""

import pandas as pd
from datetime import datetime

from infrastructure.logging.logger import setup_logger

from .utils import (
    logger, get_plotly_modules, format_number, format_date,
    agregar_datos_hidrologia_inteligente,
)

def create_line_chart(data, rio_name=None, start_date=None, end_date=None):
    """Gráfico de líneas moderno de energía con media histórica"""
    if data is None or data.empty:
        return dbc.Alert("No se pueden crear gráficos con estos datos.", color="warning", className="alert-modern")
    
    # Buscar columnas de fecha y valor (pueden tener nombres diferentes)
    date_col = None
    value_col = None
    
    # Detectar columna de fecha
    for col in data.columns:
        if any(keyword in col.lower() for keyword in ['fecha', 'date']):
            date_col = col
            break
    
    # Detectar columna de valor
    for col in data.columns:
        if any(keyword in col.lower() for keyword in ['energia', 'value', 'gwh']):
            value_col = col
            break
    
    if date_col and value_col:
        # Determinar la etiqueta del eje Y basada en el nombre de la columna
        if 'gwh' in value_col.lower() or 'energia' in value_col.lower():
            y_label = "Energía (GWh)"
        else:
            y_label = value_col
        
        # Crear figura base con plotly graph objects
        px, go = get_plotly_modules()
        fig = go.Figure()
        
        # Agregar línea de valores reales (negra para consistencia)
        fig.add_trace(go.Scatter(
            x=data[date_col],
            y=data[value_col],
            mode='lines+markers',
            name='Aportes Reales',
            line=dict(width=1.5, color='black'),
            marker=dict(size=4, color='black', line=dict(width=0.8, color='white')),
            hovertemplate=f'<b>Fecha:</b> %{{x}}<br><b>{y_label}:</b> %{{y:.2f}}<extra></extra>'
        ))
        
        # Obtener media histórica si tenemos nombre de río y fechas
        tiene_media = False
        if rio_name and start_date and end_date:
            try:
                # Convertir fechas a string si es necesario
                if hasattr(start_date, 'strftime'):
                    fecha_inicio_str = start_date.strftime('%Y-%m-%d')
                else:
                    fecha_inicio_str = str(start_date)
                
                if hasattr(end_date, 'strftime'):
                    fecha_fin_str = end_date.strftime('%Y-%m-%d')
                else:
                    fecha_fin_str = str(end_date)
                
                # Obtener media histórica
                media_hist_data, _ = obtener_datos_inteligente('AporEnerMediHist', 'Rio', fecha_inicio_str, fecha_fin_str)
                
                if media_hist_data is not None and not media_hist_data.empty:
                    # Filtrar por el río específico
                    media_hist_rio = media_hist_data[media_hist_data['Name'] == rio_name]
                    
                    if not media_hist_rio.empty and 'Value' in media_hist_rio.columns:
                        # ⚠️ NO convertir - fetch_metric_data YA convierte a GWh automáticamente
                        
                        # Combinar datos reales e históricos para colorear según estado
                        # Necesitamos preparar los datos reales en formato adecuado
                        datos_reales = data[[date_col, value_col]].copy()
                        datos_reales.columns = ['Date', 'Value_real']
                        datos_reales['Date'] = pd.to_datetime(datos_reales['Date'])
                        
                        media_hist_rio['Date'] = pd.to_datetime(media_hist_rio['Date'])
                        
                        # Merge para comparación
                        merged_data = datos_reales.merge(
                            media_hist_rio[['Date', 'Value']], 
                            on='Date', 
                            how='inner'
                        )
                        merged_data.rename(columns={'Value': 'Value_hist'}, inplace=True)
                        
                        if not merged_data.empty:
                            # Calcular porcentaje
                            merged_data['porcentaje'] = (merged_data['Value_real'] / merged_data['Value_hist']) * 100
                            
                            # Agregar línea histórica con colores dinámicos
                            for i in range(len(merged_data) - 1):
                                # ✅ FIX: Convertir a float antes de usar en formato
                                porcentaje = float(merged_data.iloc[i]['porcentaje'])
                                
                                # Determinar color según porcentaje
                                if porcentaje >= 100:
                                    color = '#28a745'  # Verde - Húmedo
                                    estado = 'Húmedo'
                                elif porcentaje >= 90:
                                    color = '#17a2b8'  # Cyan - Normal
                                    estado = 'Normal'
                                elif porcentaje >= 70:
                                    color = '#ffc107'  # Amarillo - Moderadamente seco
                                    estado = 'Moderadamente seco'
                                else:
                                    color = '#dc3545'  # Rojo - Muy seco
                                    estado = 'Muy seco'
                                
                                # Agregar segmento de línea
                                fig.add_trace(go.Scatter(
                                    x=merged_data['Date'].iloc[i:i+2],
                                    y=merged_data['Value_hist'].iloc[i:i+2],
                                    mode='lines',
                                    name='Media Histórica' if i == 0 else None,
                                    showlegend=(i == 0),
                                    line=dict(width=3, color=color, dash='dash'),
                                    hovertemplate=f'<b>Fecha:</b> %{{x}}<br><b>Media Histórica:</b> %{{y:.2f}} GWh<br><b>Estado:</b> {estado} ({porcentaje:.1f}%)<extra></extra>',
                                    legendgroup='media_historica'
                                ))
                            tiene_media = True
                        else:
                            # Fallback: línea azul simple si no hay datos para comparar
                            fig.add_trace(go.Scatter(
                                x=media_hist_rio['Date'],
                                y=media_hist_rio['Value'],
                                mode='lines',
                                name='Media Histórica',
                                line=dict(width=3, color='#1e90ff', dash='dash'),
                                hovertemplate=f'<b>Fecha:</b> %{{x}}<br><b>Media Histórica:</b> %{{y:.2f}} GWh<extra></extra>'
                            ))
                            tiene_media = True
            except Exception as e:
                logger.warning(f"No se pudo obtener media histórica para río {rio_name}: {e}")
        
        # Aplicar tema moderno
        fig.update_layout(
            height=325,  # Reducido para compensar eliminación de zoom
            margin=dict(l=50, r=20, t=40, b=50),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Inter, Arial, sans-serif", size=12),
            title_font_size=16,
            xaxis=dict(
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128,128,128,0.2)',
                showline=True,
                linewidth=2,
                linecolor='rgba(128,128,128,0.3)',
                title="Fecha"
            ),
            yaxis=dict(
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128,128,128,0.2)',
                showline=True,
                linewidth=2,
                linecolor='rgba(128,128,128,0.3)',
                title=y_label
            ),
            showlegend=tiene_media,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        # ✅ Eliminar CardHeader - solo retornar el gráfico
        return dcc.Graph(figure=fig)
    else:
        return dbc.Alert("No se pueden crear gráficos con estos datos.", color="warning", className="alert-modern")



def create_bar_chart(data, metric_name):
    """Crear gráfico de líneas moderno por región o río"""
    # Detectar columnas categóricas y numéricas
    cat_cols = [col for col in data.columns if data[col].dtype == 'object']
    num_cols = [col for col in data.columns if data[col].dtype in ['float64', 'int64']]
    
    if not cat_cols or not num_cols:
        return dbc.Alert("No se pueden crear gráficos de líneas con estos datos.", 
                        color="warning", className="alert-modern")
    
    cat_col = cat_cols[0]
    num_col = num_cols[0]
    
    # Si los datos tienen información de región, crear líneas por región
    if 'Region' in data.columns:
        # Agrupar por región y fecha para crear series temporales por región
        if 'Date' in data.columns:
            # Datos diarios por región - series temporales
            fig = px.line(
                data,
                x='Date',
                y='Value', 
                color='Region',
                title="Aportes Energéticos por Región Hidrológica",
                labels={'Value': "Energía (GWh)", 'Date': "Fecha", 'Region': "Región"},
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            # Asegurar que cada línea tenga información de región para el click
            fig.for_each_trace(lambda t: t.update(legendgroup=t.name, customdata=[t.name] * len(t.x)))
        else:
            # Datos agregados por región - convertir a líneas también
            region_data = data.groupby('Region')[num_col].sum().reset_index()
            region_data = region_data.sort_values(by=num_col, ascending=False)
            
            fig = px.line(
                region_data,
                x='Region',
                y=num_col,
                title="Contribución Total por Región Hidrológica",
                labels={num_col: "Energía (GWh)", 'Region': "Región"},
                markers=True,
                color_discrete_sequence=['#667eea']
            )
    else:
        # Agrupar y ordenar datos de mayor a menor - usar líneas en lugar de barras
        grouped_data = data.groupby(cat_col)[num_col].sum().reset_index()
        grouped_data = grouped_data.sort_values(by=num_col, ascending=False)
        
        fig = px.line(
            grouped_data.head(15),  # Top 15 para mejor visualización
            x=cat_col,
            y=num_col,
            title="Aportes Energéticos por Río",
            labels={num_col: "Energía (GWh)", cat_col: "Río"},
            markers=True,
            color_discrete_sequence=['#667eea']
        )
    
    # Aplicar estilo moderno
    fig.update_layout(
        height=360,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter, Arial, sans-serif", size=12),
        title=dict(
            font_size=16,
            x=0.5,
            xanchor='center',
            font_color='#2d3748'
        ),
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.2)',
            showline=True,
            linewidth=2,
            linecolor='rgba(128,128,128,0.3)',
            tickangle=-45
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.2)',
            showline=True,
            linewidth=2,
            linecolor='rgba(128,128,128,0.3)'
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Mejorar el estilo para todos los gráficos de líneas
    fig.update_traces(
        marker=dict(size=10, line=dict(width=2, color='white')),
        line=dict(width=4),
        hovertemplate='<b>%{fullData.name}</b><br>Valor: %{y:.2f} GWh<extra></extra>'
    )
    
    chart_title = "Aportes de Energía por Región" if 'Region' in data.columns else "Aportes de Energía por Río"
    
    return dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="bi bi-graph-up me-2", style={"color": "#667eea"}),
                html.Strong(chart_title, style={"fontSize": "1.2rem"})
            ], className="d-flex align-items-center"),
            html.Small("Haz clic en cualquier punto para ver detalles", className="text-muted")
        ]),
        dbc.CardBody([
            dcc.Graph(id="rio-detail-graph", figure=fig, clear_on_unhover=True)
        ], className="p-2")
    ], className="card-modern chart-container shadow-lg")



def create_total_timeline_chart(data, metric_name, region_filter=None, rio_filter=None):
    """
    Crear gráfico de línea temporal con total nacional/regional/río por día incluyendo media histórica filtrada
    """
    if data is None or data.empty:
        return dbc.Alert("No se pueden crear gráficos con estos datos.", 
                        color="warning", className="alert-modern")
    
    # Verificar que tengamos las columnas necesarias
    if 'Date' not in data.columns or 'Value' not in data.columns:
        return dbc.Alert("No se encuentran las columnas necesarias (Date, Value).", 
                        color="warning", className="alert-modern")
    
    # LOGGING: Ver qué datos recibimos ANTES de agrupar
    try:
        logger.info(f"🔍 create_total_timeline_chart recibió {len(data)} registros")
        logger.info(f"🔍 Columnas: {list(data.columns)}")
        logger.info(f"🔍 Fechas únicas: {data['Date'].nunique()}")
        logger.info(f"🔍 Suma total de Value ANTES de agrupar: {data['Value'].sum():.2f} GWh")
    except Exception as log_error:
        logger.warning(f"⚠️ Error en logging: {log_error}")
    
    # Agrupar por fecha y sumar todos los valores
    daily_totals = data.groupby('Date')['Value'].sum().reset_index()
    daily_totals = daily_totals.sort_values('Date')
    
    logger.info(f"🔍 DESPUÉS de agrupar: {len(daily_totals)} fechas, Total: {daily_totals['Value'].sum():.2f} GWh")
    
    # Obtener media histórica y calcular indicador
    tiene_media = False  # ✅ Inicializar antes del try
    media_hist_totals = None  # ✅ Inicializar para evitar NameError fuera del try
    porcentaje_vs_historico = None
    promedio_real = None
    promedio_historico = None
    
    try:
        # ✅ FIX ERROR #2: Convertir a string de forma segura (puede ser datetime o string)
        fecha_min = daily_totals['Date'].min()
        fecha_max = daily_totals['Date'].max()
        
        if hasattr(fecha_min, 'strftime'):
            fecha_inicio = fecha_min.strftime('%Y-%m-%d')
        else:
            fecha_inicio = str(fecha_min)
            
        if hasattr(fecha_max, 'strftime'):
            fecha_fin = fecha_max.strftime('%Y-%m-%d')
        else:
            fecha_fin = str(fecha_max)  # ✅ FIX: usar fecha_max, NO fecha_fin
        
        # Obtener datos de media histórica de energía por río
        media_hist_data, warning_msg = obtener_datos_inteligente('AporEnerMediHist', 'Rio', fecha_inicio, fecha_fin)
        if warning_msg:
            logger.info(f"✅ Usando media_hist_data recibida como parámetro (sin query duplicado)")
        
        logger.debug(f"Datos recibidos de AporEnerMediHist: {len(media_hist_data) if media_hist_data is not None else 0} registros")
        if media_hist_data is not None and not media_hist_data.empty:
            logger.debug(f"Columnas disponibles: {media_hist_data.columns.tolist()}")
            logger.debug(f"Primeras 3 filas completas:")
# print(media_hist_data.head(3))
            logger.debug(f"Valores de muestra ANTES de conversión: {media_hist_data['Value'].head(3).tolist()}")
            logger.debug(f"Rango de valores: min={media_hist_data['Value'].min()}, max={media_hist_data['Value'].max()}")
            logger.debug(f"Nombres de ríos únicos: {media_hist_data['Name'].unique()[:5].tolist() if 'Name' in media_hist_data.columns else 'Sin columna Name'}")
        
        if media_hist_data is not None and not media_hist_data.empty and 'Value' in media_hist_data.columns:
            # ✅ La conversión kWh→GWh ahora se hace automáticamente en fetch_metric_data()
            # Los valores ya vienen en GWh desde el cache
            valor_promedio = media_hist_data['Value'].mean()
            logger.debug(f"AporEnerMediHist promedio: {valor_promedio:.2f} GWh")
            logger.debug(f"Valores de muestra: {media_hist_data['Value'].head(3).tolist()}")
            
            # ✅ FIX: Filtrar registros con Name NULL ANTES de intentar mapear regiones
            if 'Name' in media_hist_data.columns:
                registros_antes = len(media_hist_data)
                media_hist_data = media_hist_data[media_hist_data['Name'].notna()]
                registros_despues = len(media_hist_data)
                if registros_antes != registros_despues:
                    logger.info(f"🔍 Filtrados {registros_antes - registros_despues} registros con Name=NULL (quedan {registros_despues})")
            
            # FILTRAR por región o río si se especifica
            if region_filter:
                # Agregar mapeo de región
                rio_region = ensure_rio_region_loaded()
                # ✅ NORMALIZAR usando función unificada
                media_hist_data['Name_Upper'] = normalizar_codigo(media_hist_data['Name'])
                media_hist_data['Region'] = media_hist_data['Name_Upper'].map(rio_region)
                
                # ✅ FIX ERROR #3: UPPER para coincidir con normalizar_region()
                region_filter_normalized = region_filter.strip().upper() if isinstance(region_filter, str) else region_filter
                
                # Filtrar por región
                antes_filtro = len(media_hist_data)
                logger.info(f"🔍 ANTES filtro región '{region_filter}' (normalizado: '{region_filter_normalized}'): {antes_filtro} registros")
                logger.info(f"🔍 Regiones disponibles: {sorted(media_hist_data['Region'].dropna().unique())}")
                media_hist_data = media_hist_data[media_hist_data['Region'] == region_filter_normalized]
                logger.info(f"🔍 DESPUÉS filtro región '{region_filter_normalized}': {len(media_hist_data)} registros")
                if media_hist_data.empty:
                    logger.error(f"❌ ERROR: No hay datos históricos después del filtro para región '{region_filter_normalized}'")
                    logger.error(f"   Regiones disponibles eran: {sorted(media_hist_data['Region'].dropna().unique()) if 'Region' in media_hist_data.columns else 'N/A'}")
            elif rio_filter:
                # Filtrar por río específico
                antes_filtro = len(media_hist_data)
                media_hist_data = media_hist_data[media_hist_data['Name'] == rio_filter]
                logger.debug(f"Media histórica filtrada por río '{rio_filter}': {antes_filtro} → {len(media_hist_data)} registros")
            
            # Agrupar por fecha y sumar
            if not media_hist_data.empty:
                media_hist_totals = media_hist_data.groupby('Date')['Value'].sum().reset_index()
                media_hist_totals = media_hist_totals.sort_values('Date')
                tiene_media = True
                
                logger.info(f"✅ Media histórica agregada por fecha: {len(media_hist_totals)} días")
                logger.info(f"✅ tiene_media = {tiene_media} - LA LÍNEA DEBERÍA APARECER")
                logger.debug(f"Valores agregados de muestra: {media_hist_totals['Value'].head(3).tolist()}")
                logger.debug(f"Total agregado: min={media_hist_totals['Value'].min():.2f}, max={media_hist_totals['Value'].max():.2f}, suma={media_hist_totals['Value'].sum():.2f} GWh")
                
                # CORRECCIÓN: Calcular porcentaje con SUMA TOTAL del período (no promedio)
                total_real = daily_totals['Value'].sum()  # SUMA TOTAL
                total_historico = media_hist_totals['Value'].sum()  # SUMA TOTAL
                
                # ✅ FIX: Convertir a float explícitamente para evitar error de formato
                total_real = float(total_real)
                total_historico = float(total_historico)
                
                logger.info(f"📊 CÁLCULO PORCENTAJE: Real={total_real:.2f} GWh, Histórico={total_historico:.2f} GWh")
                
                if total_historico > 0:
                    # ✅ FIX CRÍTICO: Convertir a float Python nativo inmediatamente
                    porcentaje_vs_historico = float((total_real / total_historico) * 100)
                    logger.info(f"✅ Porcentaje calculado: {porcentaje_vs_historico:.1f}%")
                else:
                    logger.error(f"❌ ERROR: total_historico = 0, no se puede calcular porcentaje")
                    porcentaje_vs_historico = None
            else:
                tiene_media = False
                logger.warning(f"No hay datos después del filtrado")
        else:
            tiene_media = False
            logger.warning(f"No se recibieron datos válidos de AporEnerMediHist")
    except Exception as e:
        logger.error(f"❌ ERROR obteniendo media histórica: {e}")
        logger.error(f"   Tipo de error: {type(e).__name__}")
        logger.error(f"   Detalles: {str(e)}")
        import traceback
        traceback.print_exc()
        tiene_media = False
        # Mostrar mensaje más visible en consola
# print(f"\n⚠️ ADVERTENCIA: No se pudo cargar línea de media histórica")
# print(f"   Razón: {str(e)}")
# print(f"   La gráfica se mostrará solo con datos reales\n")
    
    # Crear figura base
    from plotly.subplots import make_subplots
    px, go = get_plotly_modules()
    
    fig = go.Figure()
    
    # Agregar línea de valores reales (negra) - optimizada para mejor visualización
    fig.add_trace(go.Scatter(
        x=daily_totals['Date'],
        y=daily_totals['Value'],
        mode='lines+markers',
        name='Aportes Reales',
        line=dict(width=1.5, color='black'),
        marker=dict(size=4, color='black', line=dict(width=0.8, color='white')),
        hovertemplate=(
            '<b>📅 Fecha:</b> %{x|%d/%m/%Y}<br>'
            '<b>⚡ Aportes Reales:</b> %{y:.2f} GWh<br>'
            '<b>━━━━━━━━━━━━━━━━</b><br>'
            '<i>Pasa el cursor sobre la línea histórica<br>para ver la comparación detallada</i>'
            '<extra></extra>'
        )
    ))
    
    # Agregar línea de media histórica con colores dinámicos según estado hidrológico
    logger.info(f"🎨 DIBUJANDO GRÁFICA: tiene_media={tiene_media}, media_hist_totals={'EXISTE' if media_hist_totals is not None else 'NULL'}")
    if tiene_media and media_hist_totals is not None:
        logger.info(f"✅ INICIANDO DIBUJO de línea de media histórica con {len(media_hist_totals)} puntos")
        # Combinar datos reales e históricos por fecha para comparación
        merged_data = daily_totals.merge(
            media_hist_totals, 
            on='Date', 
            how='inner', 
            suffixes=('_real', '_hist')
        )
        logger.info(f"🔗 Datos combinados: {len(merged_data)} fechas coincidentes")
        
        if not merged_data.empty:
            # Calcular porcentaje: (real / histórico) * 100
            merged_data['porcentaje'] = (merged_data['Value_real'] / merged_data['Value_hist']) * 100
            
            # ✅ COLOREADO DINÁMICO COMPLETO (restaurado)
            # Verde: > 100% (húmedo), Cyan: 90-100% (normal), Naranja: 70-90% (seco moderado), Rojo: < 70% (muy seco)
            logger.info(f"✅ Usando COLOREADO DINÁMICO para {len(merged_data)} puntos")
            
            for i in range(len(merged_data) - 1):
                    # ✅ FIX: Convertir a float explícitamente para evitar errores de formato
                    porcentaje = float(merged_data.iloc[i]['porcentaje'])
                    valor_real = float(merged_data.iloc[i]['Value_real'])
                    valor_hist = float(merged_data.iloc[i]['Value_hist'])
                    
                    # Calcular variación porcentual (formato estándar)
                    variacion = float(porcentaje - 100)
                    signo = '+' if variacion >= 0 else ''
                    
                    # Determinar color según porcentaje
                    if porcentaje >= 100:
                        color = '#28a745'  # Verde - Húmedo
                        estado = 'Húmedo'
                        emoji = '💧'
                    elif porcentaje >= 90:
                        color = '#17a2b8'  # Cyan - Normal
                        estado = 'Normal'
                        emoji = '✓'
                    elif porcentaje >= 70:
                        color = '#ffc107'  # Amarillo/Naranja - Moderadamente seco
                        estado = 'Moderadamente seco'
                        emoji = '⚠️'
                    else:
                        color = '#dc3545'  # Rojo - Muy seco
                        estado = 'Muy seco'
                        emoji = '🔴'
                    
                    # Tooltip mejorado con formato estándar de variación porcentual
                    hover_text = (
                        f'<b>📅 Fecha:</b> %{{x|%d/%m/%Y}}<br>'
                        f'<b>📊 Media Histórica:</b> %{{y:.2f}} GWh<br>'
                        f'<b>⚡ Aportes Reales:</b> {valor_real:.2f} GWh<br>'
                        f'<b>━━━━━━━━━━━━━━━━</b><br>'
                        f'<b>{emoji} Estado:</b> {estado}<br>'
                        f'<b>📈 Variación:</b> {signo}{variacion:.1f}% vs histórico<br>'
                        f'<b>📐 Fórmula:</b> ({valor_real:.1f} / {valor_hist:.1f}) × 100 = {porcentaje:.1f}%<br>'
                        f'<b>🧮 Diferencia:</b> {porcentaje:.1f}% - 100% = {signo}{variacion:.1f}%'
                        f'<extra></extra>'
                    )
                    
                    # Agregar segmento de línea
                    fig.add_trace(go.Scatter(
                        x=merged_data['Date'].iloc[i:i+2],
                        y=merged_data['Value_hist'].iloc[i:i+2],
                        mode='lines',
                        name='Media Histórica' if i == 0 else None,  # Solo mostrar leyenda una vez
                        showlegend=(i == 0),
                        line=dict(width=3, color=color, dash='dash'),
                        hovertemplate=hover_text,
                        legendgroup='media_historica'
                    ))
        else:
            # Fallback: línea azul simple si no hay datos para comparar
            fig.add_trace(go.Scatter(
                x=media_hist_totals['Date'],
                y=media_hist_totals['Value'],
                mode='lines',
                name='Media Histórica',
                line=dict(width=3, color='#1e90ff', dash='dash'),
                hovertemplate='<b>Fecha:</b> %{x}<br><b>Media Histórica:</b> %{y:.2f} GWh<extra></extra>'
            ))
    else:
        logger.warning(f"⚠️ NO SE DIBUJÓ línea de media histórica: tiene_media={tiene_media}, media_hist_totals={'None' if media_hist_totals is None else f'{len(media_hist_totals)} registros'}")
    
    # Determinar título dinámico según filtros
    if rio_filter:
        titulo_grafica = f"Aportes de Energía - Río {rio_filter}"
    elif region_filter:
        titulo_grafica = f"Aportes de Energía - Región {region_filter}"
    else:
        titulo_grafica = "Total Nacional de Aportes de Energía por Día"
    
    # Estilo moderno con márgenes optimizados
    fig.update_layout(
        height=500,
        margin=dict(l=50, r=20, t=60, b=50),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter, Arial, sans-serif", size=12),
        title=dict(
            text=titulo_grafica,
            font_size=16,
            x=0.5,
            xanchor='center',
            font_color='#2d3748'
        ),
        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.2)',
            showline=True,
            linewidth=2,
            linecolor='rgba(128,128,128,0.3)',
            title="Fecha"
        ),
        yaxis=dict(
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.2)',
            showline=True,
            linewidth=2,
            linecolor='rgba(128,128,128,0.3)',
            title="Energía (GWh)"
        ),
        showlegend=tiene_media,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Crear indicador visual de comparación
    indicador_badge = None
    if porcentaje_vs_historico is not None:
        # ✅ FIX: Asegurar que porcentaje_vs_historico sea float
        try:
            porcentaje_vs_historico = float(porcentaje_vs_historico)
        except (ValueError, TypeError):
            logger.error(f"❌ No se pudo convertir porcentaje_vs_historico a float: {porcentaje_vs_historico}")
            porcentaje_vs_historico = None
    
    if porcentaje_vs_historico is not None:
        # Determinar color y emoji según el porcentaje
        if porcentaje_vs_historico >= 100:
            # Por encima del histórico (húmedo)
            color_badge = "success"
            icono = "💧"
            diferencia = float(porcentaje_vs_historico - 100)
            texto_badge = f"{icono} +{diferencia:.1f}% vs Histórico"
            texto_contexto = "Condiciones más húmedas que el promedio histórico"
        elif porcentaje_vs_historico >= 90:
            # Cerca del histórico (normal)
            color_badge = "info"
            icono = "✓"
            diferencia = float(100 - porcentaje_vs_historico)
            texto_badge = f"{icono} -{diferencia:.1f}% vs Histórico"
            texto_contexto = "Condiciones cercanas al promedio histórico"
        elif porcentaje_vs_historico >= 70:
            # Moderadamente bajo (alerta)
            color_badge = "warning"
            icono = "⚠️"
            diferencia = float(100 - porcentaje_vs_historico)
            texto_badge = f"{icono} -{diferencia:.1f}% vs Histórico"
            texto_contexto = "Condiciones más secas que el promedio histórico"
        else:
            # Muy bajo (crítico)
            color_badge = "danger"
            icono = "🔴"
            diferencia = float(100 - porcentaje_vs_historico)
            texto_badge = f"{icono} -{diferencia:.1f}% vs Histórico"
            texto_contexto = "Condiciones significativamente más secas que el histórico"
        
        indicador_badge = html.Div([
            dbc.Badge(
                texto_badge,
                color=color_badge,
                className="me-2",
                style={"fontSize": "0.9rem", "fontWeight": "600"}
            ),
            html.Small(texto_contexto, className="text-muted", style={"fontSize": "0.85rem"})
        ], className="d-flex align-items-center mt-2")
    
    # ✅ Header eliminado - solo retornar el gráfico sin card header
    return dcc.Graph(id="total-timeline-graph", figure=fig, clear_on_unhover=True)
# Callback para mostrar el modal con la tabla diaria al hacer click en un punto de la línea


def create_stats_summary(data):
    """Crear resumen estadístico"""
    numeric_data = data.select_dtypes(include=['float64', 'int64'])
    
    if numeric_data.empty:
        return dbc.Alert("No hay datos numéricos para análisis estadístico.", color="warning")
    
    stats = numeric_data.describe()
    
    return dbc.Card([
        dbc.CardHeader([
            html.H6([
                html.I(className="bi bi-calculator me-2"),
                "Resumen Estadístico"
            ], className="mb-0")
        ]),
        dbc.CardBody([
            dash_table.DataTable(
                data=stats.round(2).reset_index().to_dict('records'),
                columns=[{"name": i, "id": i} for i in stats.reset_index().columns],
                style_cell={
                    'textAlign': 'center',
                    'padding': '10px',
                    'fontFamily': 'Arial'
                },
                style_header={
                    'backgroundColor': '#3498db',
                    'color': 'white',
                    'fontWeight': 'bold'
                },
                style_data={'backgroundColor': '#f8f9fa'}
            )
        ])
    ], className="mt-3")

# === FUNCIONES PARA TABLAS FILTRADAS POR REGIÓN CON SEMÁFORO ===



