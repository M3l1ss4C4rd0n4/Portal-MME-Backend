"""
Hidrología - Mapas Geográficos
================================

Funciones para crear mapas de Colombia (embalses por región, choropleth).
"""

import pandas as pd
import json

from dash import dcc, html
import dash_bootstrap_components as dbc

from infrastructure.logging.logger import setup_logger
from domain.services.geo_service import REGIONES_COORDENADAS, obtener_coordenadas_region

from .utils import (
    logger, get_plotly_modules, _GEOJSON_CACHE, _cargar_geojson_cache,
    normalizar_region,
)
from .data_services import (
    obtener_datos_embalses_por_region,
    calcular_semaforo_embalse_local,
)

def crear_mapa_embalses_por_region():
    """
    Crea el mapa interactivo de Colombia con puntos por región hidrológica
    """
    import plotly.graph_objects as go
    
    regiones_data = obtener_datos_embalses_por_region()
    
    if regiones_data is None or len(regiones_data) == 0:
        return dbc.Alert([
            html.H5("⚠️ No hay datos disponibles", className="alert-heading"),
            html.P("No se pudieron cargar los datos de los embalses. Intente nuevamente más tarde.")
        ], color="warning")
    
    # Crear figura del mapa
    fig = go.Figure()
    
    # Agregar puntos por región
    for region, data in regiones_data.items():
        # Crear texto del tooltip con lista de embalses
        embalses_texto = "<br>".join([
            f"• {emb['codigo']}: {emb['volumen_pct']:.1f}% {emb['icono']}"
            for emb in sorted(data['embalses'], key=lambda x: x['volumen_pct'])[:10]  # Mostrar máximo 10
        ])
        
        if data['total_embalses'] > 10:
            embalses_texto += f"<br>... y {data['total_embalses'] - 10} más"
        
        hover_text = (
            f"<b>{data['nombre']}</b><br>" +
            f"Total embalses: {data['total_embalses']}<br>" +
            f"Riesgo máximo: <b>{data['riesgo_max']}</b><br><br>" +
            f"<b>Embalses:</b><br>{embalses_texto}"
        )
        
        # Tamaño según cantidad de embalses
        tamaño = min(15 + data['total_embalses'] * 3, 40)
        
        fig.add_trace(go.Scattergeo(
            lon=[data['lon']],
            lat=[data['lat']],
            text=[data['nombre']],
            mode='markers+text',
            marker=dict(
                size=tamaño,
                color=data['color'],
                line=dict(width=3, color='white'),
                symbol='circle'
            ),
            textposition='top center',
            textfont=dict(size=10, color='#2c3e50', family='Arial Black'),
            name=f"{data['nombre']} ({data['riesgo_max']})",
            hovertext=hover_text,
            hoverinfo='text',
            showlegend=True
        ))
    
    # Configurar el mapa centrado en Colombia
    fig.update_geos(
        center=dict(lon=-74, lat=4.5),
        projection_type='mercator',
        showcountries=True,
        countrycolor='lightgray',
        showcoastlines=True,
        coastlinecolor='gray',
        showland=True,
        landcolor='#f5f5f5',
        showlakes=True,
        lakecolor='lightblue',
        showrivers=True,
        rivercolor='lightblue',
        lonaxis_range=[-79, -66],
        lataxis_range=[-4.5, 13],
        bgcolor='#e8f4f8'
    )
    
    fig.update_layout(
        title={
            'text': '🗺️ Mapa de Embalses por Región Hidrológica',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18, 'color': COLORS['text_primary'], 'family': 'Arial Black'}
        },
        height=600,
        margin=dict(l=0, r=0, t=60, b=0),
        legend=dict(
            title=dict(text='Regiones', font=dict(size=12, family='Arial Black')),
            orientation='v',
            yanchor='top',
            y=0.98,
            xanchor='left',
            x=0.01,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='gray',
            borderwidth=1,
            font=dict(size=10)
        ),
        hoverlabel=dict(
            bgcolor='white',
            font_size=11,
            font_family='Arial'
        )
    )
    
    return dcc.Graph(figure=fig, config={'displayModeBar': True, 'displaylogo': False})



def crear_mapa_embalses_directo(regiones_totales, df_completo_embalses):
    """Crea el mapa mostrando CADA EMBALSE como un círculo/bolita individual de color sobre mapa real de Colombia."""
    try:
        import plotly.graph_objects as go
        import random
        from math import sin, cos, radians
        
        if regiones_totales is None or regiones_totales.empty:
            return dbc.Alert("No hay datos de regiones disponibles", color="warning")
        
        if df_completo_embalses is None or df_completo_embalses.empty:
            return dbc.Alert("No hay datos de embalses disponibles", color="warning")
        
        logger.info("Creando mapa con bolitas individuales por embalse sobre mapa real de Colombia...")
        logger.debug(f"Total embalses en df_completo_embalses: {len(df_completo_embalses)}")
        
        # Crear figura con mapa base de Colombia
        fig = go.Figure()
        
        # Usar cache de GeoJSON (archivos estáticos cargados UNA vez)
        try:
            cache = _cargar_geojson_cache()
            
            if cache is None or not cache['loaded']:
                logger.error("❌ Cache de GeoJSON no disponible")
                # Continuar sin mapa base
                colombia_geojson = None
                DEPARTAMENTOS_A_REGIONES = {}
            else:
                # Obtener datos del cache (ya cargados en memoria)
                colombia_geojson = cache['colombia_geojson']
                regiones_config = cache['regiones_config']
                DEPARTAMENTOS_A_REGIONES = cache['departamentos_a_regiones']
                
                logger.info(f"✅ Usando cache de GeoJSON: {len(regiones_config['regiones'])} regiones")
            
            # Solo dibujar mapa base si tenemos los datos
            if colombia_geojson and DEPARTAMENTOS_A_REGIONES:
                # Agregar el mapa de Colombia como fondo con colores por región natural
                departamentos_dibujados = 0
                for feature in colombia_geojson['features']:
                    # Obtener nombre del departamento y normalizarlo
                    nombre_dpto_original = feature['properties'].get('NOMBRE_DPT', '')
                    nombre_dpto = nombre_dpto_original.upper().strip()
                    
                    # Normalizar nombres especiales
                    if 'BOGOTA' in nombre_dpto or 'D.C' in nombre_dpto:
                        nombre_dpto = 'CUNDINAMARCA'
                    elif 'SAN ANDRES' in nombre_dpto:
                        nombre_dpto = 'SAN ANDRES Y PROVIDENCIA'
                    elif 'NARIÑO' in nombre_dpto_original:
                        nombre_dpto = 'NARIÑO'
                    elif 'BOYACÁ' in nombre_dpto_original:
                        nombre_dpto = 'BOYACA'
                    elif 'CÓRDOBA' in nombre_dpto_original:
                        nombre_dpto = 'CORDOBA'
                    
                    # Determinar color según región natural
                    if nombre_dpto in DEPARTAMENTOS_A_REGIONES:
                        info_region = DEPARTAMENTOS_A_REGIONES[nombre_dpto]
                        fillcolor = info_region['color']
                        bordercolor = info_region['border']
                        region_nombre = info_region['region']
                        hovertext = f"<b>{nombre_dpto_original}</b><br>{region_nombre}"
                    else:
                        fillcolor = 'rgba(220, 220, 220, 0.2)'
                        bordercolor = '#999999'
                        hovertext = f"<b>{nombre_dpto_original}</b>"
                    
                    # Manejar Polygon y MultiPolygon
                    geometry_type = feature['geometry']['type']
                    coords_list = []
                    
                    if geometry_type == 'Polygon':
                        coords_list = [feature['geometry']['coordinates'][0]]
                    elif geometry_type == 'MultiPolygon':
                        coords_list = [poly[0] for poly in feature['geometry']['coordinates']]
                    
                    # Dibujar cada polígono del departamento
                    for coords in coords_list:
                        lons = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        
                        fig.add_trace(go.Scattergeo(
                            lon=lons,
                            lat=lats,
                            mode='lines',
                            line=dict(width=1.5, color=bordercolor),
                            fill='toself',
                            fillcolor=fillcolor,
                            hoverinfo='text',
                            hovertext=hovertext,
                            showlegend=False
                        ))
                    
                    departamentos_dibujados += 1
                
                logger.info(f"Mapa de Colombia cargado: {departamentos_dibujados} departamentos")
                
        except Exception as e:
            logger.warning(f"Error al cargar mapa base: {e}")
        
        # Procesar embalses
        leyenda_mostrada = {'ALTO': False, 'MEDIO': False, 'BAJO': False}
        embalses_mapeados = 0
        
        for idx, row in df_completo_embalses.iterrows():
            nombre_embalse = str(row.get('Embalse', '')).strip()
            region_embalse = str(row.get('Región', '')).strip()
            
            if not nombre_embalse or not region_embalse:
                continue
            
            region_normalizada = region_embalse.upper()
            
            if region_normalizada not in REGIONES_COORDENADAS:
                continue
            
            participacion = float(row.get('Participación (%)', 0))
            volumen_pct = float(row.get('Volumen Útil (%)', 0))
            
            riesgo, color, icono = calcular_semaforo_embalse_local(participacion, volumen_pct)
            
            coords_region = REGIONES_COORDENADAS[region_normalizada]
            lat_centro = coords_region['lat']
            lon_centro = coords_region['lon']
            
            # Posición aleatoria pero consistente
            seed_value = hash(nombre_embalse + region_normalizada) % 100000
            random.seed(seed_value)
            
            radio_lat = 0.5
            radio_lon = 0.6
            
            angulo = random.uniform(0, 360)
            distancia = random.uniform(0.4, 1.0)
            
            offset_lat = distancia * radio_lat * sin(radians(angulo))
            offset_lon = distancia * radio_lon * cos(radians(angulo))
            
            lat_embalse = lat_centro + offset_lat
            lon_embalse = lon_centro + offset_lon
            
            hover_text = (
                f"<b>{nombre_embalse}</b><br>"
                f"Región: {coords_region['nombre']}<br>"
                f"Participación: {participacion:.2f}%<br>"
                f"Volumen Útil: {volumen_pct:.1f}%<br>"
                f"<b>Riesgo: {riesgo}</b> {icono}"
            )
            
            tamaño = max(12, min(10 + participacion * 0.8, 35))
            
            mostrar_leyenda = not leyenda_mostrada[riesgo]
            if mostrar_leyenda:
                leyenda_mostrada[riesgo] = True
                nombre_leyenda = f"{icono} Riesgo {riesgo}"
            else:
                nombre_leyenda = nombre_embalse
            
            fig.add_trace(go.Scattergeo(
                lon=[lon_embalse],
                lat=[lat_embalse],
                mode='markers',
                marker=dict(
                    size=tamaño,
                    color=color,
                    line=dict(width=2, color='white'),
                    symbol='circle',
                    opacity=0.9
                ),
                name=nombre_leyenda,
                hovertext=hover_text,
                hoverinfo='text',
                showlegend=mostrar_leyenda,
                legendgroup=riesgo
            ))
            
            embalses_mapeados += 1
        
        if embalses_mapeados == 0:
            return dbc.Alert("No se pudieron mapear los embalses", color="warning")
        
        # Configurar el mapa
        fig.update_geos(
            projection_type='mercator',
            scope='south america',
            center=dict(lon=-73.5, lat=4.5),
            showcoastlines=True,
            coastlinecolor='#333333',
            coastlinewidth=2,
            showland=True,
            landcolor='#f5f5f5',
            showcountries=True,
            countrycolor='#000000',
            countrywidth=2.5,
            showlakes=True,
            lakecolor='#b3d9ff',
            lonaxis_range=[-79.5, -66.5],
            lataxis_range=[-4.5, 13],
            bgcolor='#ffffff',
            resolution=50
        )
        
        fig.update_layout(
            height=455,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor='white',
            geo=dict(projection_scale=2.8),
            legend=dict(
                title=dict(text='Nivel de Riesgo', font=dict(size=10)),
                orientation='v',
                yanchor='top',
                y=0.98,
                xanchor='left',
                x=0.01,
                bgcolor='rgba(255,255,255,0.95)',
                bordercolor='#cccccc',
                borderwidth=2,
                font=dict(size=9)
            ),
            hoverlabel=dict(
                bgcolor='white',
                font_size=12,
                font_family='Arial',
                bordercolor='#666666'
            )
        )
        
        logger.info(f"Mapa creado exitosamente: {embalses_mapeados} embalses")
        return dcc.Graph(
            figure=fig, 
            config={
                'displayModeBar': True, 
                'displaylogo': False,
                'scrollZoom': True,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d']
            },
            style={'height': '100%', 'touchAction': 'auto'}
        )
        
    except Exception as e:
        logger.error(f"Error creando mapa: {e}", exc_info=True)
        return dbc.Alert(f"Error al crear el mapa: {str(e)}", color="danger")


# Callback principal para consultar y mostrar datos filtrando por río y fechas


