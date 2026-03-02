"""
Hidrología - Componentes de Tablas
===================================

Funciones para crear tablas Dash (DataTable, HTML tables) 
para embalses, regiones y aportes.
"""

import pandas as pd
from dash import html, dash_table
import dash_bootstrap_components as dbc

from infrastructure.logging.logger import setup_logger

from .utils import (
    logger, format_number, format_date,
    calcular_semaforo_embalse, clasificar_riesgo_embalse,
    obtener_estilo_riesgo, obtener_pictograma_riesgo,
)
from .data_services import (
    obtener_datos_embalses_por_region,
    get_participacion_embalses,
    get_embalses_completa_para_tabla,
    get_embalses_data_for_table,
    get_embalses_capacidad,
    get_embalses_by_region,
    calcular_semaforo_embalse_local,
    clasificar_riesgo_embalse_local,
    obtener_estilo_riesgo_local,
    obtener_pictograma_riesgo_local,
    agregar_columna_riesgo_a_tabla,
    generar_estilos_condicionales_riesgo,
    get_tabla_con_participacion,
)

def crear_estilos_condicionales_para_tabla_estatica(start_date=None, end_date=None):
    """
    Crea estilos condicionales para la tabla estática basados en riesgo
    """
    try:
        # Obtener datos frescos para calcular estilos
        df_fresh = get_embalses_capacidad(None, start_date, end_date)
        if df_fresh.empty:
            return [
                {
                    "if": {"filter_query": "{Embalse} = \"TOTAL\""}, 
                    "backgroundColor": "#007bff",
                    "color": "white",
                    "fontWeight": "bold"
                }
            ]
        
        # Agregar riesgo y generar estilos
        df_con_riesgo = agregar_columna_riesgo_a_tabla(df_fresh)
        estilos = generar_estilos_condicionales_riesgo(df_con_riesgo)
        return estilos
        
    except Exception as e:
        logger.error(f"Error generando estilos condicionales: {e}", exc_info=True)
        return [
            {
                "if": {"filter_query": "{Embalse} = \"TOTAL\""}, 
                "backgroundColor": "#007bff",
                "color": "white",
                "fontWeight": "bold"
            }
        ]


# ============================================================================
# FUNCIONES PARA MAPA DE EMBALSES POR REGIÓN
# ============================================================================



def crear_tabla_embalses_por_region():
    """
    Crea la tabla detallada de embalses agrupada por región
    """
    regiones_data = obtener_datos_embalses_por_region()
    
    if regiones_data is None or len(regiones_data) == 0:
        return dbc.Alert("No hay datos disponibles", color="warning")
    
    # Ordenar regiones por riesgo máximo
    orden_riesgo = {'ALTO': 0, 'MEDIO': 1, 'BAJO': 2}
    regiones_ordenadas = sorted(
        regiones_data.items(),
        key=lambda x: (orden_riesgo[x[1]['riesgo_max']], x[0])
    )
    
    # Crear acordeón con una sección por región
    acordeon_items = []
    
    for region, data in regiones_ordenadas:
        # Ordenar embalses por volumen (menor a mayor)
        embalses_ordenados = sorted(data['embalses'], key=lambda x: x['volumen_pct'])
        
        # Crear filas de tabla para esta región
        filas_region = []
        for emb in embalses_ordenados:
            filas_region.append(
                html.Tr([
                    html.Td(html.Span(emb['icono'], style={'fontSize': '1.2rem'}), className="text-center"),
                    html.Td(emb['codigo'], style={'fontWeight': '600'}),
                    html.Td(f"{emb['volumen_pct']:.1f}%", 
                           style={'color': emb['color'], 'fontWeight': '700'}),
                    html.Td(f"{emb['volumen_gwh']:.0f} GWh"),
                    html.Td(f"{emb['capacidad_gwh']:.0f} GWh"),
                    html.Td(f"{emb['participacion']:.1f}%"),
                    html.Td(emb['riesgo'], 
                           style={
                               'color': emb['color'],
                               'fontWeight': 'bold',
                               'backgroundColor': emb['color'] + '20',
                               'padding': '5px 10px',
                               'borderRadius': '4px'
                           })
                ])
            )
        
        tabla_region = dbc.Table([
            html.Thead([
                html.Tr([
                    html.Th("", className="text-center", style={'width': '50px'}),
                    html.Th("Embalse"),
                    html.Th("Volumen %"),
                    html.Th("Volumen"),
                    html.Th("Capacidad"),
                    html.Th("Participación %"),
                    html.Th("Riesgo")
                ], style={'backgroundColor': data['color'], 'color': 'white', 'fontSize': '0.9rem'})
            ]),
            html.Tbody(filas_region)
        ], bordered=True, hover=True, responsive=True, striped=True, size='sm')
        
        # Título del acordeón con color según riesgo
        titulo_acordeon = html.Div([
            html.Span(f"📍 {data['nombre']}", style={'fontWeight': '600', 'fontSize': '1.1rem'}),
            html.Span(
                f" ({data['total_embalses']} embalses - Riesgo {data['riesgo_max']})",
                style={'color': data['color'], 'fontWeight': 'bold', 'marginLeft': '10px'}
            )
        ])
        
        acordeon_items.append(
            dbc.AccordionItem(
                tabla_region,
                title=titulo_acordeon,
                item_id=f"region-{region}"
            )
        )
    
    return dbc.Accordion(acordeon_items, start_collapsed=True, always_open=True)

# ============================================================================
# NUEVAS TABLAS JERÁRQUICAS SIMPLIFICADAS (usando dbc.Table directamente)
# ============================================================================





def build_embalses_hierarchical_view(regiones_totales, df_completo_embalses, expanded_regions):
    """
    Construye vista jerárquica de la tabla pequeña de embalses con expansión/contracción.
    Similar a build_hierarchical_table_view() pero para la tabla de 4 columnas.
    """
    try:
        if regiones_totales is None or regiones_totales.empty or df_completo_embalses.empty:
            return dash_table.DataTable(
                data=[],
                columns=[
                    {"name": "Embalse", "id": "embalse"},
                    {"name": "Part.", "id": "participacion"},
                    {"name": "Vol.", "id": "volumen"},
                    {"name": "⚠️", "id": "riesgo"}
                ]
            )
        
        table_data = []
        style_data_conditional = []
        
        # Ordenar regiones por participación descendente
        regiones_sorted = regiones_totales.sort_values('Participación (%)', ascending=False)
        
        for _, row_region in regiones_sorted.iterrows():
            region_name = row_region['Región']
            participacion_region = row_region['Participación (%)']
            volumen_region = row_region['Volumen Útil (%)']
            
            is_expanded = region_name in expanded_regions
            button_icon = "⊟" if is_expanded else "⊞"
            
            # Clasificar riesgo de la región (usar el peor caso de sus embalses)
            embalses_region = df_completo_embalses[df_completo_embalses['Región'] == region_name]
            riesgos = []
            for _, emb in embalses_region.iterrows():
                riesgo = clasificar_riesgo_embalse(
                    emb.get('Participación (%)', 0),
                    emb.get('Volumen Útil (%)', 0)
                )
                riesgos.append(riesgo)
            
            # Determinar el peor riesgo de la región
            if 'high' in riesgos:
                riesgo_region = '🔴'
            elif 'medium' in riesgos:
                riesgo_region = '🟡'
            else:
                riesgo_region = '🟢'
            
            # Fila de región
            row_index = len(table_data)
            table_data.append({
                "embalse": f"{button_icon} {region_name}",
                "participacion": f"{participacion_region:.2f}%",
                "volumen": f"{volumen_region:.1f}%",
                "riesgo": riesgo_region
            })
            
            # Estilo para fila de región
            style_data_conditional.append({
                'if': {'row_index': row_index},
                'backgroundColor': '#e3f2fd',
                'fontWeight': 'bold',
                'cursor': 'pointer',
                'border': '2px solid #2196f3'
            })
            
            # Si está expandida, agregar embalses
            if is_expanded:
                embalses_sorted = embalses_region.sort_values('Participación (%)', ascending=False)
                
                for _, emb in embalses_sorted.iterrows():
                    embalse_name = emb['Embalse']
                    participacion_val = emb.get('Participación (%)', 0)
                    volumen_val = emb.get('Volumen Útil (%)', 0)
                    
                    # Clasificar riesgo
                    riesgo = clasificar_riesgo_embalse(participacion_val, volumen_val)
                    if riesgo == 'high':
                        riesgo_icon = '🔴'
                    elif riesgo == 'medium':
                        riesgo_icon = '🟡'
                    else:
                        riesgo_icon = '🟢'
                    
                    # Agregar fila de embalse
                    emb_row_index = len(table_data)
                    table_data.append({
                        "embalse": f"    └─ {embalse_name}",
                        "participacion": f"{participacion_val:.2f}%",
                        "volumen": f"{volumen_val:.1f}%" if pd.notna(volumen_val) else "N/D",
                        "riesgo": riesgo_icon
                    })
                    
                    # Estilo condicional por riesgo
                    if riesgo == 'high':
                        bg_color = '#ffe6e6'
                    elif riesgo == 'medium':
                        bg_color = '#fff9e6'
                    else:
                        bg_color = '#e6ffe6'
                    
                    style_data_conditional.append({
                        'if': {'row_index': emb_row_index},
                        'backgroundColor': bg_color
                    })
        
        # Agregar fila TOTAL
        total_participacion = regiones_totales['Participación (%)'].sum()
        
        # Calcular volumen total ponderado
        total_volumen_gwh = regiones_totales['Volumen Util (GWh)'].sum()
        total_capacidad_gwh = regiones_totales['Total (GWh)'].sum()
        promedio_volumen_general = (total_volumen_gwh / total_capacidad_gwh) * 100 if total_capacidad_gwh > 0 else 0
        
        total_row_index = len(table_data)
        table_data.append({
            "embalse": "TOTAL",
            "participacion": "100.00%",
            "volumen": f"{promedio_volumen_general:.1f}%",
            "riesgo": "⚡"
        })
        
        style_data_conditional.append({
            'if': {'row_index': total_row_index},
            'backgroundColor': '#e3f2fd',
            'fontWeight': 'bold'
        })
        
        # Crear DataTable
        return dash_table.DataTable(
            id="tabla-embalses-jerarquica",
            data=table_data,
            columns=[
                {"name": "Embalse", "id": "embalse"},
                {"name": "Part.", "id": "participacion"},
                {"name": "Vol.", "id": "volumen"},
                {"name": "⚠️", "id": "riesgo"}
            ],
            style_cell={'textAlign': 'left', 'padding': '4px', 'fontSize': '0.7rem'},
            style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold', 'fontSize': '0.7rem', 'padding': '4px'},
            style_data_conditional=style_data_conditional,
            page_action="none",
            style_table={'maxHeight': '480px', 'overflowY': 'auto'}
        )
        
    except Exception as e:
        logger.error(f"❌ Error en build_embalses_hierarchical_view: {e}", exc_info=True)
        return dash_table.DataTable(data=[], columns=[
            {"name": "Embalse", "id": "embalse"},
            {"name": "Part.", "id": "participacion"},
            {"name": "Vol.", "id": "volumen"},
            {"name": "⚠️", "id": "riesgo"}
        ])




def crear_tablas_jerarquicas_directas(regiones_totales):
    """
    Crea las tablas jerárquicas de Participación y Volumen Útil usando dbc.Table
    (mismo patrón que la tabla que SÍ funciona)
    
    Args:
        regiones_totales: DataFrame con datos de regiones (ya calculado)
    """
    try:
        if regiones_totales is None or regiones_totales.empty:
            return (
                dbc.Alert("No hay datos de regiones disponibles", color="warning"),
                dbc.Alert("No hay datos de regiones disponibles", color="warning")
            )
        
        # TABLA 1: Participación Porcentual
        filas_participacion = []
        
        # Ordenar regiones por participación descendente
        regiones_sorted = regiones_totales.sort_values('Participación (%)', ascending=False)
        
        for _, row_region in regiones_sorted.iterrows():
            region_name = row_region['Región']
            participacion_region = row_region['Participación (%)']
            
            # Fila de región (colapsada inicialmente)
            filas_participacion.append(
                html.Tr([
                    html.Td(
                        html.Span(f"⊞ {region_name}", style={'fontWeight': 'bold', 'cursor': 'pointer'}),
                        colSpan=2
                    ),
                    html.Td(f"{participacion_region:.2f}%", style={'fontWeight': 'bold', 'textAlign': 'right'})
                ], style={'backgroundColor': '#e3f2fd'})
            )
        
        # Fila TOTAL
        filas_participacion.append(
            html.Tr([
                html.Td("TOTAL SISTEMA", colSpan=2, style={'fontWeight': 'bold'}),
                html.Td("100.0%", style={'fontWeight': 'bold', 'textAlign': 'right'})
            ], style={'backgroundColor': '#007bff', 'color': 'white'})
        )
        
        tabla_participacion = dbc.Table([
            html.Thead([
                html.Tr([
                    html.Th("Región / Embalse", colSpan=2),
                    html.Th("Participación (%)", style={'textAlign': 'right'})
                ], style={'backgroundColor': '#667eea', 'color': 'white'})
            ]),
            html.Tbody(filas_participacion)
        ], bordered=True, hover=True, responsive=True, striped=True, size='sm', className="table-modern")
        
        # TABLA 2: Volumen Útil
        filas_volumen = []
        
        # Ordenar regiones por volumen útil descendente
        regiones_sorted_vol = regiones_totales.sort_values('Volumen Útil (%)', ascending=False)
        
        for _, row_region in regiones_sorted_vol.iterrows():
            region_name = row_region['Región']
            volumen_region = row_region['Volumen Útil (%)']
            
            # Fila de región
            filas_volumen.append(
                html.Tr([
                    html.Td(
                        html.Span(f"⊞ {region_name}", style={'fontWeight': 'bold', 'cursor': 'pointer'}),
                        colSpan=2
                    ),
                    html.Td(f"{volumen_region:.1f}%", style={'fontWeight': 'bold', 'textAlign': 'right'})
                ], style={'backgroundColor': '#e8f5e8'})
            )
        
        # Calcular volumen útil total
        total_volumen_gwh = regiones_totales['Volumen Util (GWh)'].sum()
        total_capacidad_gwh = regiones_totales['Total (GWh)'].sum()
        promedio_volumen_general = (total_volumen_gwh / total_capacidad_gwh) * 100 if total_capacidad_gwh > 0 else 0
        
        # Fila TOTAL
        filas_volumen.append(
            html.Tr([
                html.Td("TOTAL SISTEMA", colSpan=2, style={'fontWeight': 'bold'}),
                html.Td(f"{promedio_volumen_general:.1f}%", style={'fontWeight': 'bold', 'textAlign': 'right'})
            ], style={'backgroundColor': '#28a745', 'color': 'white'})
        )
        
        tabla_volumen = dbc.Table([
            html.Thead([
                html.Tr([
                    html.Th("Región / Embalse", colSpan=2),
                    html.Th("Volumen Útil (%)", style={'textAlign': 'right'})
                ], style={'backgroundColor': '#28a745', 'color': 'white'})
            ]),
            html.Tbody(filas_volumen)
        ], bordered=True, hover=True, responsive=True, striped=True, size='sm', className="table-modern")
        
        logger.info(f"✅ Tablas jerárquicas creadas exitosamente con {len(regiones_totales)} regiones")
        return tabla_participacion, tabla_volumen
        
    except Exception as e:
        logger.error(f"❌ Error creando tablas jerárquicas directas: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return (
            dbc.Alert(f"Error: {str(e)}", color="danger"),
            dbc.Alert(f"Error: {str(e)}", color="danger")
        )

# ============================================================================




def build_hierarchical_table_view(data_complete, expanded_regions, view_type="participacion"):
    """Construir vista de tabla jerárquica con botones integrados y sistema de semáforo CORREGIDO"""
    if not data_complete:
        return dash_table.DataTable(
            data=[],
            columns=[
                {"name": "Región / Embalse", "id": "nombre"},
                {"name": "Participación (%)" if view_type == "participacion" else "Volumen Útil (%)", "id": "valor"}
            ]
        )
    
    table_data = []
    processed_regions = set()
    style_data_conditional = []
    
    # Obtener todas las regiones únicas
    all_regions = set()
    for item in data_complete:
        if item.get('tipo') == 'region':
            region_name = item.get('region_name')
            if region_name:
                all_regions.add(region_name)
    
    # Crear lista de regiones con sus valores para ordenar de mayor a menor
    region_items = []
    for item in data_complete:
        if item.get('tipo') == 'region':
            region_name = item.get('region_name')
            if region_name and region_name not in processed_regions:
                # Obtener el valor para ordenar
                valor_str = item.get('participacion', item.get('capacidad', '0'))
                try:
                    # Extraer valor numérico del string (ej: "25.5%" -> 25.5)
                    if isinstance(valor_str, str):
                        valor_num = float(valor_str.replace('%', '').replace(',', '').strip())
                    else:
                        valor_num = float(valor_str) if valor_str else 0
                except (ValueError, AttributeError, TypeError) as e:
                    logger.debug(f"No se pudo convertir valor a numérico: {valor_str} - {e}")
                    valor_num = 0
                
                region_items.append({
                    'item': item,
                    'region_name': region_name,
                    'valor_num': valor_num
                })
                processed_regions.add(region_name)
    
    # Ordenar regiones por valor de mayor a menor
    region_items.sort(key=lambda x: x['valor_num'], reverse=True)
    
    # Procesar cada región en orden descendente
    for region_data in region_items:
        region_item = region_data['item']
        region_name = region_data['region_name']
        
        is_expanded = region_name in expanded_regions
        
        # Fila de región con botón integrado en el nombre
        button_icon = "⊟" if is_expanded else "⊞"  # Símbolos más elegantes
        table_data.append({
            "nombre": f"{button_icon} {region_name}",
            "valor": region_item.get('participacion', region_item.get('capacidad', ''))
        })
        
        # Si está expandida, agregar embalses ordenados de mayor a menor
        if is_expanded:
            # SOLUCIÓN DIRECTA: Crear diccionario unificado directamente desde data_complete
            embalses_unificados = {}
            
            for item in data_complete:
                if (item.get('tipo') == 'embalse' and 
                    item.get('region_name') == region_name):
                    embalse_name = item.get('nombre', '').replace('    └─ ', '').strip()
                    
                    if embalse_name not in embalses_unificados:
                        # CREAR ENTRADA COMPLETA con todos los datos necesarios
                        embalses_unificados[embalse_name] = {
                            'nombre': embalse_name,
                            'participacion_valor': item.get('participacion_valor', 0),
                            'volumen_valor': item.get('volumen_valor', 0),
                            'valor_display': item.get('participacion' if view_type == "participacion" else 'capacidad', ''),
                            'valor_num': 0
                        }
                        
                        # Calcular valor numérico para ordenar
                        valor_str = embalses_unificados[embalse_name]['valor_display']
                        try:
                            if isinstance(valor_str, str):
                                embalses_unificados[embalse_name]['valor_num'] = float(valor_str.replace('%', '').replace(',', '').strip())
                            else:
                                embalses_unificados[embalse_name]['valor_num'] = float(valor_str) if valor_str else 0
                        except (ValueError, AttributeError, TypeError) as e:
                            logger.debug(f"No se pudo convertir valor a numérico: {valor_str} - {e}")
                            embalses_unificados[embalse_name]['valor_num'] = 0
            
            # Convertir a lista y ordenar
            embalses_lista = list(embalses_unificados.values())
            embalses_lista.sort(key=lambda x: x.get('valor_num', 0), reverse=True)
            
            # 🔍 LOG: Verificar datos antes de construir tabla
            logger.info(f"🔍 [BUILD_TABLE] Región={region_name}, View={view_type}, Embalses={len(embalses_lista)}")
            
            # Procesar cada embalse con datos ya unificados
            for embalse_data in embalses_lista:
                embalse_name = embalse_data['nombre']
                valor_embalse = embalse_data['valor_display']
                participacion_val = embalse_data.get('participacion_valor', 0)
                volumen_val = embalse_data.get('volumen_valor', 0)
                
                # 🔍 LOG CRÍTICO: Valores que se mostrarán en la tabla
                logger.info(f"🔍 [TABLE_DISPLAY] {embalse_name} ({view_type}): Display={valor_embalse}, Part={participacion_val}%, Vol={volumen_val}%")
                
                
                # Clasificar riesgo con ambos valores CORRECTOS
                nivel_riesgo = clasificar_riesgo_embalse(participacion_val, volumen_val)
                
                # Agregar fila del embalse
                row_index = len(table_data)
                table_data.append({
                    "nombre": f"    └─ {embalse_name}",
                    "valor": valor_embalse
                })
                
                # Agregar estilo condicional para el semáforo solo en tabla de participación
                if view_type == "participacion":
                    estilo = obtener_estilo_riesgo(nivel_riesgo)
                    style_data_conditional.append({
                        'if': {'row_index': row_index},
                        **estilo
                    })
    
    # Agregar fila TOTAL
    total_item = None
    for item in data_complete:
        if item.get('tipo') == 'total':
            total_item = item
            break
    
    if total_item:
        table_data.append({
            "nombre": "TOTAL SISTEMA",
            "valor": total_item.get('participacion', total_item.get('capacidad', ''))
        })
    
    # Crear tabla con estructura de 2 columnas
    return dash_table.DataTable(
        id=f"tabla-{view_type}-jerarquica-display",
        data=table_data,
        columns=[
            {"name": "Región / Embalse", "id": "nombre"},
            {"name": "Participación (%)" if view_type == "participacion" else "Volumen Útil (%)", "id": "valor"}
        ],
        style_cell={
            'textAlign': 'left',
            'padding': '8px',
            'fontFamily': 'Inter, Arial, sans-serif',
            'fontSize': 13,
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #dee2e6'
        },
        style_header={
            'backgroundColor': '#667eea' if view_type == 'participacion' else '#28a745',
            'color': 'white',
            'fontWeight': 'bold',
            'fontSize': 14,
            'textAlign': 'center',
            'border': f'1px solid {"#5a6cf0" if view_type == "participacion" else "#218838"}'
        },
        style_data_conditional=style_data_conditional + [
            {
                'if': {'filter_query': '{nombre} contains "⊞" || {nombre} contains "⊟"'},
                'backgroundColor': '#e3f2fd' if view_type == 'participacion' else '#e8f5e8',
                'fontWeight': 'bold',
                'cursor': 'pointer',
                'border': f'2px solid {"#2196f3" if view_type == "participacion" else "#28a745"}'
            },
            {
                'if': {'filter_query': '{nombre} = "TOTAL SISTEMA"'},
                'backgroundColor': '#007bff',
                'color': 'white',
                'fontWeight': 'bold'
            }
        ],
        page_action="none"
    )

# Callback para inicializar las vistas HTML desde los stores (DEBE IR PRIMERO - sin allow_duplicate)


def get_tabla_regiones_embalses(start_date=None, end_date=None):
    """
    Crea una tabla jerárquica que muestra primero las regiones y permite expandir para ver embalses.
    """
    try:
        objetoAPI = get_objetoAPI()
        
        # Obtener información de embalses desde API XM (fuente de verdad para regiones)
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        embalses_info, warning = obtener_datos_inteligente('ListadoEmbalses','Sistema', yesterday, today)
        
        # ✅ NORMALIZAR usando funciones unificadas
        embalses_info['Values_Name'] = normalizar_codigo(embalses_info['Values_Name'])
        embalses_info['Values_HydroRegion'] = normalizar_region(embalses_info['Values_HydroRegion'])
        
        # ✅ FIX: Limpiar duplicados y entradas sin región (causa de "inflated values" / duplicados visuales)
        # Priorizar entradas con región válida
        if not embalses_info.empty:
            # Eliminar registros con región vacía o nula
            embalses_info = embalses_info[embalses_info['Values_HydroRegion'].notna() & (embalses_info['Values_HydroRegion'] != '')]
            # Eliminar duplicados de nombre
            embalses_info = embalses_info.drop_duplicates(subset=['Values_Name'])
            logger.info(f"Listado embalses filtrado: {len(embalses_info)} registros únicos con región")

        # CREAR MAPEO CÓDIGO → REGIÓN (fuente única de verdad)
        embalse_region_map = dict(zip(embalses_info['Values_Name'], embalses_info['Values_HydroRegion']))
        logger.debug(f"Mapeo embalse-región creado: {len(embalse_region_map)} embalses")

        # Obtener fecha con datos COMPLETOS (n_vol/n_cap >= 80%)
        fecha_solicitada = end_date if end_date else start_date
        today = datetime.now().strftime('%Y-%m-%d')
        fecha_obj = datetime.strptime(fecha_solicitada if fecha_solicitada else today, '%Y-%m-%d').date()
        
        # Buscar fecha con datos completos en últimos 7 días
        fecha_encontrada = None
        df_vol_test = None
        df_cap_test = None
        
        for dias_atras in range(7):
            fecha_busq = fecha_obj - timedelta(days=dias_atras)
            df_vol_tmp, f_vol = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_busq, dias_busqueda=1)
            df_cap_tmp, f_cap = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_busq, dias_busqueda=1)
            
            if df_vol_tmp is None or df_vol_tmp.empty or df_cap_tmp is None or df_cap_tmp.empty:
                continue
            if f_vol != f_cap:
                continue
            
            # Validar completitud
            col_emb_v = next((c for c in ['Embalse', 'recurso', 'Values_code'] if c in df_vol_tmp.columns), None)
            col_emb_c = next((c for c in ['Embalse', 'recurso', 'Values_code'] if c in df_cap_tmp.columns), None)
            
            if col_emb_v and col_emb_c:
                n_v = df_vol_tmp[col_emb_v].nunique()
                n_c = df_cap_tmp[col_emb_c].nunique()
                if n_c > 0 and n_v / n_c < 0.80:
                    logger.warning(f"get_tabla_regiones: datos incompletos {fecha_busq}: n_vol={n_v}, n_cap={n_c}")
                    continue
            
            fecha_encontrada = f_vol
            df_vol_test = df_vol_tmp
            df_cap_test = df_cap_tmp
            break
        
        if fecha_encontrada is None or df_vol_test is None or df_cap_test is None:
            logger.warning("No se encontraron datos en ninguna fecha reciente")
            return pd.DataFrame(), pd.DataFrame()
        
        fecha = fecha_encontrada.strftime('%Y-%m-%d')
        logger.debug(f"[DEBUG] Usando fecha con datos disponibles para cálculo de embalses: {fecha} ({len(df_vol_test)} embalses con volumen)")

        if not fecha:
            logger.warning("No se encontraron datos en ninguna fecha reciente")
            return pd.DataFrame(), pd.DataFrame()

        # DataFrame detallado de embalses usando la fecha con datos
        logger.debug(f"Construyendo tabla de embalses para fecha: {fecha}")
        embalses_detalle = []

        # Consultar datos de volumen y capacidad para la fecha encontrada
        df_vol, _ = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_encontrada)
        df_cap, _ = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_encontrada)

        # ✅ NO CONVERTIR: obtener_datos_inteligente ya devuelve valores en GWh cuando viene de PostgreSQL
        # Los datos de la API XM vienen en Wh, pero se convierten en obtener_datos_inteligente
        # Por lo tanto, 'Value' ya está en GWh aquí
        df_vol['Value_GWh'] = df_vol['Value']
        df_cap['Value_GWh'] = df_cap['Value']

        # ✅ SIEMPRE incluir TODOS los embalses del listado maestro (25 embalses)
        # Si no tienen datos, mostrar 0 o N/D
        for _, embalse_info in embalses_info.iterrows():
            embalse_name = embalse_info['Values_Name']
            region_name = embalse_info['Values_HydroRegion']

            # Buscar datos de este embalse
            # ✅ FIX ERROR #1: obtener_datos_desde_bd retorna columna 'Embalse', NO 'Name'
            vol_data = df_vol[df_vol['Embalse'] == embalse_name]
            cap_data = df_cap[df_cap['Embalse'] == embalse_name]

            # ✅ CAMBIO CRÍTICO: Incluir embalse aunque NO tenga datos
            if not vol_data.empty and not cap_data.empty:
                vol_gwh = vol_data['Value_GWh'].iloc[0]
                cap_gwh = cap_data['Value_GWh'].iloc[0]
                pct = (vol_gwh / cap_gwh * 100) if cap_gwh > 0 else 0
            else:
                # Si no tiene datos, usar 0 para permitir su visualización
                vol_gwh = 0.0
                cap_gwh = 0.0
                pct = 0.0
                logger.debug(f"⚠️ Embalse {embalse_name} sin datos - incluido con valores 0")

            embalses_detalle.append({
                'Embalse': embalse_name,
                'Región': region_name,
                'VoluUtilDiarEner (GWh)': vol_gwh,
                'CapaUtilDiarEner (GWh)': cap_gwh,
                'Volumen Útil (%)': pct
            })

        df_embalses = pd.DataFrame(embalses_detalle)
        
        # ✅ FIX #1B: Eliminar duplicados (API puede retornar mismo embalse múltiples veces)
        if not df_embalses.empty:
            registros_antes = len(df_embalses)
            df_embalses = df_embalses.drop_duplicates(subset=['Embalse'], keep='first')
            registros_despues = len(df_embalses)
            if registros_antes != registros_despues:
                logger.info(f"🔍 Eliminados {registros_antes - registros_despues} embalses duplicados (quedan {registros_despues} únicos)")
        
        logger.debug("Primeras filas df_embalses:")
        logger.debug(f"\n{df_embalses[['Región', 'VoluUtilDiarEner (GWh)', 'CapaUtilDiarEner (GWh)']].head(10)}")

        # Procesar datos si tenemos embalses
        if not df_embalses.empty:
            # ✅ FIX ERROR #1: Calcular participación a nivel NACIONAL (no por región)
            # Esto evita embalses duplicados y garantiza que la suma sea 100% a nivel nacional
            df_embalses['Capacidad_GWh_Internal'] = df_embalses['CapaUtilDiarEner (GWh)']

            # Calcular participación NACIONAL (todos los embalses suman 100%)
            total_cap_nacional = df_embalses['Capacidad_GWh_Internal'].sum()
            if total_cap_nacional > 0:
                df_embalses['Participación (%)'] = (
                    df_embalses['Capacidad_GWh_Internal'] / total_cap_nacional * 100
                ).round(2)
            else:
                df_embalses['Participación (%)'] = 0.0

            # Crear tabla resumen por región usando los datos YA OBTENIDOS (no llamar a función externa)
            regiones_resumen = []
            regiones_unicas = [r for r in df_embalses['Región'].unique() if r and r.strip() and r.strip().lower() not in ['sin nacional', 'rios estimados', '']]
            
            for region in regiones_unicas:
                # Filtrar embalses de esta región
                embalses_region = df_embalses[df_embalses['Región'] == region]
                
                if not embalses_region.empty:
                    # Calcular totales directamente de los datos que ya tenemos
                    total_capacidad = embalses_region['CapaUtilDiarEner (GWh)'].sum()
                    total_volumen = embalses_region['VoluUtilDiarEner (GWh)'].sum()
                    
                    # Calcular porcentaje
                    if total_capacidad > 0:
                        porcentaje_volumen = (total_volumen / total_capacidad) * 100
                    else:
                        porcentaje_volumen = 0.0
                    
                    regiones_resumen.append({
                        'Región': region,
                        'Total (GWh)': round(total_capacidad, 2),
                        'Volumen Util (GWh)': round(total_volumen, 2),
                        'Volumen Útil (%)': round(porcentaje_volumen, 1)
                    })
                else:
                    regiones_resumen.append({
                        'Región': region,
                        'Total (GWh)': 0.00,
                        'Volumen Util (GWh)': 0.00,
                        'Volumen Útil (%)': 0.00
                    })
            
            regiones_totales = pd.DataFrame(regiones_resumen)
            
            # 🆕 Calcular participación porcentual de cada región respecto al total nacional
            # La participación se basa en la capacidad útil total de cada región
            total_capacidad_nacional = regiones_totales['Total (GWh)'].sum()
            
            if total_capacidad_nacional > 0:
                regiones_totales['Participación (%)'] = (
                    regiones_totales['Total (GWh)'] / total_capacidad_nacional * 100
                ).round(2)
            else:
                regiones_totales['Participación (%)'] = 0.0
            
            logger.debug(f"Tabla de regiones creada con {len(regiones_totales)} regiones")
            logger.debug(f"Participación por región: {regiones_totales[['Región', 'Participación (%)']].to_dict('records')}")
        else:
            # Si no hay datos, crear DataFrame vacío con estructura correcta
            regiones_totales = pd.DataFrame(columns=['Región', 'Total (GWh)', 'Volumen Util (GWh)', 'Volumen Útil (%)', 'Participación (%)'])
            logger.warning("No se pudieron obtener datos de embalses para las fechas disponibles")

        # (No agregar fila TOTAL SISTEMA aquí, se agregará manualmente en la tabla de participación)
        return regiones_totales, df_embalses
    except Exception as e:
# print(f"[ERROR] get_tabla_regiones_embalses: {e}")
        return pd.DataFrame(), pd.DataFrame()



def create_collapsible_regions_table(start_date=None, end_date=None):
    """
    Crea una tabla expandible elegante con regiones que se pueden plegar/desplegar para ver embalses.
    """
    try:
        # Usar fecha actual si no se proporcionan parámetros
        if not end_date:
            end_date = date.today().strftime('%Y-%m-%d')
        
        regiones_totales, df_completo_embalses = get_tabla_regiones_embalses(start_date, end_date)
        
        if regiones_totales.empty:
            return dbc.Alert("No se encontraron datos de regiones.", color="warning", className="text-center")
        
        # Crear componentes colapsables elegantes para cada región
        region_components = []
        
        for idx, region_row in regiones_totales.iterrows():
            region_name = region_row['Región']
            total_gwh = region_row['Total (GWh)']
            participacion = region_row['Participación (%)']
            
            # Obtener embalses de la región
            embalses_region = get_embalses_by_region(region_name, df_completo_embalses)
            
            # Contar embalses para mostrar en el header
            num_embalses = len(embalses_region) if not embalses_region.empty else 0
            
            # Crear contenido de embalses con las dos tablas lado a lado
            if not embalses_region.empty:
                # Preparar datos para las tablas con formateo
                embalses_data_formatted = []
                embalses_data_raw = []  # Para cálculos
                for _, embalse_row in embalses_region.iterrows():
                    embalse_name = embalse_row['Región'].replace('    └─ ', '')
                    embalse_capacidad = embalse_row['Total (GWh)']
                    embalse_participacion = embalse_row['Participación (%)']
                    
                    # Para la tabla de capacidad ya no incluimos la columna de GWh
                    embalses_data_formatted.append({
                        'Embalse': embalse_name,
                        'Participación (%)': embalse_participacion
                    })
                    
                    embalses_data_raw.append({
                        'Embalse': embalse_name,
                        'Capacidad_GWh_Internal': embalse_capacidad,  # Sin formatear para cálculos
                        'Participación (%)': embalse_participacion
                    })
                
                # Calcular total para la tabla de capacidad
                total_capacidad = sum([row['Capacidad_GWh_Internal'] for row in embalses_data_raw])
                
                # Crear tabla de participación porcentual
                tabla_participacion = dash_table.DataTable(
                    data=[{
                        'Embalse': row['Embalse'],
                        'Participación (%)': row['Participación (%)']
                    } for row in embalses_data_formatted] + [{'Embalse': 'TOTAL', 'Participación (%)': '100.0%'}],
                    columns=[
                        {"name": "Embalse", "id": "Embalse"},
                        {"name": "Participación (%)", "id": "Participación (%)"}
                    ],
                    style_cell={
                        'textAlign': 'left',
                        'padding': '8px',
                        'fontFamily': 'Inter, Arial, sans-serif',
                        'fontSize': 13,
                        'backgroundColor': '#f8f9fa',
                        'border': '1px solid #dee2e6'
                    },
                    style_header={
                        'backgroundColor': '#667eea',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'fontSize': 14,
                        'textAlign': 'center',
                        'border': '1px solid #5a6cf0'
                    },
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{Embalse} = "TOTAL"'},
                            'backgroundColor': '#007bff',
                            'color': 'white',
                            'fontWeight': 'bold'
                        }
                    ],
                    page_action="none"
                )
                
                # Crear tabla de capacidad detallada
                # Crear DataFrame temporal para obtener las columnas correctas
                temp_df = pd.DataFrame([{
                    'Embalse': row['Embalse'],
                    'Participación (%)': row['Participación (%)']
                } for row in embalses_data_formatted])
                
                tabla_capacidad = dash_table.DataTable(
                    data=embalses_data_formatted + [{
                        'Embalse': 'TOTAL',
                        'Participación (%)': ''
                    }],
                    columns=create_embalse_table_columns(temp_df),
                    style_cell={
                        'textAlign': 'left',
                        'padding': '8px',
                        'fontFamily': 'Inter, Arial, sans-serif',
                        'fontSize': 13,
                        'backgroundColor': '#f8f9fa',
                        'border': '1px solid #dee2e6'
                    },
                    style_header={
                        'backgroundColor': '#28a745',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'fontSize': 14,
                        'textAlign': 'center',
                        'border': '1px solid #218838'
                    },
                    style_data_conditional=[
                        {
                            'if': {'filter_query': '{Embalse} = "TOTAL"'},
                            'backgroundColor': '#007bff',
                            'color': 'white',
                            'fontWeight': 'bold'
                        }
                    ],
                    page_action="none"
                )
                
                embalses_content = html.Div([
                    html.Div([
                        html.I(className="bi bi-building me-2", style={"color": "#28a745"}),
                        html.Strong(f"Análisis Detallado - {region_name}", 
                                  className="text-success", style={"fontSize": "1.1rem"})
                    ], className="mb-4 d-flex align-items-center"),
                    
                    # Las dos tablas lado a lado
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardHeader([
                                    html.I(className="bi bi-pie-chart me-2", style={"color": "#667eea"}),
                                    html.Strong("📊 Participación Porcentual por Embalse")
                                ], style={"background": "linear-gradient(135deg, #e3f2fd 0%, #f3f4f6 100%)",
                                         "border": "none", "borderRadius": "8px 8px 0 0"}),
                                dbc.CardBody([
                                    html.P("Distribución porcentual de la capacidad energética entre embalses. La tabla incluye una fila TOTAL que suma exactamente 100%.", 
                                          className="text-muted mb-3", style={"fontSize": "0.85rem"}),
                                    tabla_participacion
                                ], className="p-3")
                            ], className="card-modern h-100")
                        ], md=6),
                        
                        dbc.Col([
                            dbc.Card([
                                dbc.CardHeader([
                                    html.I(className="bi bi-battery-full me-2", style={"color": "#28a745"}),
                                    html.Strong("🏭 Capacidad Detallada por Embalse")
                                ], style={"background": "linear-gradient(135deg, #e8f5e8 0%, #f3f4f6 100%)",
                                         "border": "none", "borderRadius": "8px 8px 0 0"}),
                                dbc.CardBody([
                                    html.P(f"Valores específicos de capacidad útil diaria en GWh para los {num_embalses} embalses de la región.", 
                                          className="text-muted mb-3", style={"fontSize": "0.85rem"}),
                                    tabla_capacidad
                                ], className="p-3")
                            ], className="card-modern h-100")
                        ], md=6)
                    ], className="g-3")
                ])
            else:
                embalses_content = dbc.Alert([
                    html.I(className="bi bi-exclamation-triangle me-2"),
                    f"No se encontraron embalses para la región {region_name}."
                ], color="light", className="text-center my-3 alert-modern")
            
            # Crear card principal elegante para la región
            region_card = dbc.Card([
                # Header clickeable de la región
                dbc.CardHeader([
                    dbc.Button([
                        html.Div([
                            html.Div([
                                html.I(className="bi bi-chevron-right me-3", 
                                       id={"type": "chevron-region", "index": idx},
                                       style={"fontSize": "1.1rem", "color": "#007bff", "transition": "transform 0.3s ease"}),
                                html.I(className="bi bi-geo-alt-fill me-2", style={"color": "#28a745"}),
                                html.Strong(region_name, style={"fontSize": "1.1rem", "color": "#2d3748"})
                            ], className="d-flex align-items-center"),
                            html.Div([
                                dbc.Badge(f"{format_number(total_gwh)} GWh", color="primary", className="me-2 px-2 py-1"),
                                dbc.Badge(f"{participacion}%", color="success", className="px-2 py-1"),
                                html.Small(f" • {num_embalses} embalse{'s' if num_embalses != 1 else ''}", 
                                         className="text-muted ms-2")
                            ], className="d-flex align-items-center mt-1")
                        ], className="d-flex justify-content-between align-items-start w-100")
                    ], 
                    id={"type": "toggle-region", "index": idx},
                    className="w-100 text-start border-0 bg-transparent p-0",
                    style={"background": "transparent !important"}
                    )
                ], className="border-0 bg-gradient", 
                style={
                    "background": f"linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)",
                    "borderRadius": "12px 12px 0 0",
                    "padding": "1rem"
                }),
                
                # Contenido colapsable
                dbc.Collapse([
                    dbc.CardBody([
                        html.Hr(className="mt-0 mb-3", style={"borderColor": "#dee2e6"}),
                        embalses_content
                    ], className="pt-0", style={"backgroundColor": "#fdfdfe"})
                ],
                id={"type": "collapse-region", "index": idx},
                is_open=False
                )
            ], className="mb-3 shadow-sm",
            style={
                "border": "1px solid #e3e6f0",
                "borderRadius": "12px",
                "transition": "all 0.3s ease",
                "overflow": "hidden"
            })
            
            region_components.append(region_card)
        
        return html.Div([
            # Header explicativo elegante
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Strong("Capacidad Útil Diaria de Energía por Región Hidrológica", style={"fontSize": "1.2rem"})
                    ], className="d-flex align-items-center mb-2"),
                    html.P([
                        "Haz clic en cualquier región para expandir y ver sus tablas detalladas. ",
                        html.Strong("Cada región muestra dos tablas lado a lado:", className="text-primary"),
                        " participación porcentual de embalses y capacidad energética detallada en GWh."
                    ], className="mb-0 text-dark", style={"fontSize": "0.95rem"})
                ], className="py-3")
            ], className="mb-4", 
            style={
                "background": "linear-gradient(135deg, #e3f2fd 0%, #f3f4f6 100%)",
                "border": "1px solid #bbdefb",
                "borderRadius": "12px"
            }),
            
            # Container de regiones
            html.Div(region_components, id="regions-container")
        ])
        
    except Exception as e:
# print(f"Error creando tabla colapsable: {e}")
        return dbc.Alert(f"Error al crear tabla: {str(e)}", color="danger")


# Callback elegante para manejar el pliegue/despliegue de regiones


def create_embalse_table_columns(df):
    """Crea las columnas para la tabla de embalses dinámicamente según las columnas disponibles"""
    columns = []
    logger.debug(f"Creando columnas para tabla - DataFrame tiene: {list(df.columns) if not df.empty else 'VACÍO'}")
    if not df.empty:
        for col in df.columns:
            if col == "Embalse":
                columns.append({"name": "Embalse", "id": "Embalse"})
            elif col == "Volumen Útil (%)":
                columns.append({"name": "Volumen Útil (%)", "id": "Volumen Útil (%)"})
            elif col == "Participación (%)":
                columns.append({"name": "Participación (%)", "id": "Participación (%)"})
            elif col == "Riesgo":
                columns.append({"name": "🚨 Riesgo", "id": "Riesgo"})
            # Nota: La columna 'Capacidad_GWh_Internal' ha sido eliminada de las tablas jerárquicas
    logger.debug(f"Total de columnas creadas: {len(columns)}")
    return columns



def create_initial_embalse_table():
    """Crea la tabla inicial de embalses con la nueva columna"""
    try:
        logger.info("Creando tabla inicial de embalses...")
        
        # Obtener datos directamente usando fechas actuales
        df = get_embalses_capacidad()
        
        if df.empty:
            return dbc.Alert("No hay datos de embalses para mostrar.", color="warning")
        
        # Formatear datos (mantener la capacidad para cálculos internos)
        df_formatted = df.copy()
        
        if 'Volumen Útil (%)' in df.columns:
            # Solo formatear valores numéricos, no reformatear strings
            df_formatted['Volumen Útil (%)'] = df['Volumen Útil (%)'].apply(
                lambda x: x if isinstance(x, str) else (f"{x:.1f}%" if pd.notna(x) and isinstance(x, (int, float)) else "N/D")
            )
            logger.info("Columna 'Volumen Útil (%)' formateada en tabla inicial")
        
        # Calcular totales para la fila TOTAL (usando los datos originales)
        total_capacity = df['Capacidad_GWh_Internal'].sum() if 'Capacidad_GWh_Internal' in df.columns else 0
        total_row_data = {
            'Embalse': ['TOTAL']
        }
        
        if 'Volumen Útil (%)' in df.columns:
            valid_data = df[df['Volumen Útil (%)'].notna()]
            avg_volume_pct = valid_data['Volumen Útil (%)'].mean() if not valid_data.empty else None
            total_row_data['Volumen Útil (%)'] = [f"{avg_volume_pct:.1f}%" if avg_volume_pct is not None else "N/D"]
        
        total_row = pd.DataFrame(total_row_data)
        
        # Crear DataFrame para mostrar (sin columna de capacidad)
        display_columns = ['Embalse']
        if 'Volumen Útil (%)' in df_formatted.columns:
            display_columns.append('Volumen Útil (%)')
        
        df_display = df_formatted[display_columns].copy()
        df_display = pd.concat([df_display, total_row], ignore_index=True)
        
        # 🆕 AGREGAR COLUMNA DE RIESGO CON PICTOGRAMAS
        df_display_con_riesgo = agregar_columna_riesgo_a_tabla(df.copy())  # Usar df original con capacidad
        
        # Crear DataFrame final para mostrar solo con las columnas necesarias + riesgo
        final_columns = ['Embalse']
        if 'Volumen Útil (%)' in df_display_con_riesgo.columns:
            # Formatear volumen útil para mostrar
            df_display_con_riesgo['Volumen Útil (%)'] = df_display_con_riesgo['Volumen Útil (%)'].apply(
                lambda x: f"{x:.1f}%" if pd.notna(x) and x != 'N/D' and not isinstance(x, str) else (x if isinstance(x, str) else "N/D")
            )
            final_columns.append('Volumen Útil (%)')
        final_columns.append('Riesgo')
        
        # Agregar fila TOTAL con riesgo
        total_row_riesgo = {
            'Embalse': 'TOTAL',
            'Volumen Útil (%)': total_row_data['Volumen Útil (%)'][0] if 'Volumen Útil (%)' in total_row_data else 'N/D',
            'Riesgo': '⚡'
        }
        
        # Filtrar solo embalses (sin TOTAL) y agregar TOTAL al final
        df_embalses_only = df_display_con_riesgo[df_display_con_riesgo['Embalse'] != 'TOTAL'][final_columns].copy()
        df_total_row = pd.DataFrame([total_row_riesgo])
        df_final_display = pd.concat([df_embalses_only, df_total_row], ignore_index=True)
        
        
        return create_dynamic_embalse_table(df_final_display)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return dbc.Alert(f"Error: {str(e)}", color="danger")



def create_dynamic_embalse_table(df_formatted):
    """Crea una tabla de embalses dinámicamente con todas las columnas disponibles"""
    logger.debug(f"INICIO create_dynamic_embalse_table - DataFrame: {df_formatted.shape if not df_formatted.empty else 'VACÍO'}")
    
    if df_formatted.empty:
        logger.warning("DataFrame vacío - retornando alerta")
        return dbc.Alert("No hay datos de embalses para mostrar.", color="warning")
    
    logger.debug(f"Creando tabla dinámica de embalses con {len(df_formatted)} filas y columnas: {list(df_formatted.columns)}")
    
    # Crear columnas dinámicamente
    columns = create_embalse_table_columns(df_formatted)
    logger.debug(f"Columnas creadas: {len(columns)}")
    
    # 🆕 Generar estilos condicionales basados en riesgo
    estilos_condicionales = []
    if 'Riesgo' in df_formatted.columns:
        estilos_condicionales = generar_estilos_condicionales_riesgo(df_formatted)
        logger.debug(f"Estilos condicionales de riesgo generados: {len(estilos_condicionales)}")
    else:
        # Estilo básico para TOTAL si no hay columna de riesgo
        estilos_condicionales = [
            {
                'if': {'filter_query': '{Embalse} = "TOTAL"'},
                'backgroundColor': '#007bff',
                'color': 'white',
                'fontWeight': 'bold'
            }
        ]
    
    # Crear la tabla
    table = dash_table.DataTable(
        id="tabla-capacidad-embalse",
        data=df_formatted.to_dict('records'),
        columns=columns,
        style_cell={'textAlign': 'left', 'padding': '6px', 'fontFamily': 'Arial', 'fontSize': 14},
        style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold'},
        style_data={'backgroundColor': '#f8f8f8'},
        style_data_conditional=estilos_condicionales,
        page_action="none"
    )
    
    return table
    


def create_data_table(data):
    """Tabla paginada de datos de energía con participación porcentual y total integrado"""
    if data is None or data.empty:
        return dbc.Alert("No hay datos para mostrar en la tabla.", color="warning")
    
    # Crear una copia del dataframe para modificar
    df_with_participation = data.copy()
    
    # Formatear fechas si existe columna de fecha
    date_columns = [col for col in df_with_participation.columns if 'fecha' in col.lower() or 'date' in col.lower()]
    for col in date_columns:
        df_with_participation[col] = df_with_participation[col].apply(format_date)
    
    # Si tiene columna 'GWh', calcular participación
    total_value = 0
    num_registros = len(df_with_participation)
    if 'GWh' in df_with_participation.columns:
        # Filtrar filas que no sean TOTAL para calcular el porcentaje
        df_no_total = df_with_participation[df_with_participation['GWh'] != 'TOTAL'].copy()
        if not df_no_total.empty:
            # Asegurar que los valores son numéricos
            df_no_total['GWh'] = pd.to_numeric(df_no_total['GWh'], errors='coerce')
            total_value = df_no_total['GWh'].sum()
            
            if total_value > 0:
                # Calcular porcentajes
                porcentajes = (df_no_total['GWh'] / total_value * 100).round(2)
                
                # Ajustar para que sume exactamente 100%
                diferencia = 100 - porcentajes.sum()
                if abs(diferencia) > 0.001 and len(porcentajes) > 0:
                    idx_max = porcentajes.idxmax()
                    porcentajes.loc[idx_max] += diferencia
                
                # Agregar la columna de participación
                df_with_participation.loc[df_no_total.index, 'Participación (%)'] = porcentajes.round(2)
            else:
                df_with_participation['Participación (%)'] = 0
        else:
            df_with_participation['Participación (%)'] = 0
    
    # Formatear columnas numéricas (GWh, capacidades, etc.)
    numeric_columns = [col for col in df_with_participation.columns 
                      if any(keyword in col.lower() for keyword in ['gwh', 'capacidad', 'energia', 'valor', 'value'])]
    
    for col in numeric_columns:
        if col != 'Participación (%)':  # No formatear porcentajes
            df_with_participation[col] = df_with_participation[col].apply(
                lambda x: format_number(x) if pd.notnull(x) and x != 'TOTAL' else x
            )
    
    # Agregar fila de TOTAL al final del DataFrame
    total_row = {}
    for col in df_with_participation.columns:
        if 'fecha' in col.lower() or 'date' in col.lower():
            total_row[col] = f"📊 TOTAL ({num_registros} registros)"
        elif col == 'GWh':
            total_row[col] = format_number(total_value)
        elif col == 'Participación (%)':
            total_row[col] = '100.00'
        else:
            total_row[col] = ''
    
    df_with_participation = pd.concat([df_with_participation, pd.DataFrame([total_row])], ignore_index=True)
    
    # Crear tabla paginada con total integrado
    return dash_table.DataTable(
        data=df_with_participation.to_dict('records'),
        columns=[{"name": i, "id": i} for i in df_with_participation.columns],
        style_cell={
            'textAlign': 'left', 
            'padding': '4px 8px',  # Reducido verticalmente
            'fontFamily': 'Inter, Arial, sans-serif', 
            'fontSize': '12px',  # Reducido de 13px a 12px
            'whiteSpace': 'normal',
            'height': 'auto'
        },
        style_header={
            'backgroundColor': '#2c3e50', 
            'fontWeight': 'bold',
            'color': 'white',
            'border': '1px solid #34495e',
            'fontSize': '11px',  # Encabezado más pequeño
            'padding': '6px 8px'  # Padding reducido en header
        },
        style_data={
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #dee2e6'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#ffffff'
            },
            {
                # Estilo especial para la fila de TOTAL (última fila)
                'if': {'row_index': len(df_with_participation) - 1},
                'backgroundColor': '#e3f2fd',
                'fontWeight': 'bold',
                'borderTop': '3px solid #007bff',
                'borderBottom': '3px solid #007bff',
                'color': '#0056b3'
            }
        ],
        page_size=8,  # Mostrar 8 filas por página
        page_action='native',  # Paginación nativa
        page_current=0,
        style_table={
            'maxHeight': '400px',
            'overflowY': 'auto',
            'overflowX': 'auto'
        }
    )



def create_region_filtered_participacion_table(region, start_date, end_date):
    """
    Crea una tabla de participación porcentual filtrada por región específica,
    incluyendo el sistema de semáforo de riesgo.
    """
    try:
        
        # Obtener datos de embalses filtrados por región
        df_embalses = get_embalses_capacidad(region, start_date, end_date)
        
        if df_embalses.empty:
            return html.Div("No hay datos disponibles para esta región.", className="text-center text-muted")
        
        # Calcular participación porcentual
        df_participacion = get_participacion_embalses(df_embalses)
        
        # Crear datos para la tabla con semáforo
        table_data = []
        for _, row in df_participacion.iterrows():
            if row['Embalse'] == 'TOTAL':
                continue  # Saltamos el total para procesarlo al final
            
            embalse_name = row['Embalse']
            participacion_valor = row['Participación (%)']
            
            # Manejar tanto valores numéricos como strings con formato
            if isinstance(participacion_valor, str) and '%' in participacion_valor:
                participacion_num = float(participacion_valor.replace('%', ''))
                participacion_str = participacion_valor
            else:
                participacion_num = float(participacion_valor)
                participacion_str = f"{participacion_num:.2f}%"
            
            # Obtener volumen útil del embalse
            embalse_data = df_embalses[df_embalses['Embalse'] == embalse_name]
            volumen_util_raw = embalse_data['Volumen Útil (%)'].iloc[0] if not embalse_data.empty else 0
            
            # Convertir volumen_util a número (no reformatear si ya es string)
            if volumen_util_raw is None or (isinstance(volumen_util_raw, str) and volumen_util_raw == 'N/D'):
                volumen_util = 0
            elif isinstance(volumen_util_raw, str):
                # Si ya es string con %, extraer solo el número para cálculos de riesgo
                try:
                    volumen_util = float(volumen_util_raw.replace('%', '').replace(',', '.').strip())
                except (ValueError, AttributeError):
                    volumen_util = 0
            elif pd.isna(volumen_util_raw):
                volumen_util = 0
            else:
                volumen_util = float(volumen_util_raw)
            
            # Clasificar riesgo
            nivel_riesgo = clasificar_riesgo_embalse(participacion_num, volumen_util)
            estilo_riesgo = obtener_estilo_riesgo(nivel_riesgo)
            
            
            table_data.append({
                'Embalse': embalse_name,
                'Participación (%)': participacion_str,
                'Riesgo': "🔴" if nivel_riesgo == "high" else "🟡" if nivel_riesgo == "medium" else "🟢"
            })
        
        # Agregar fila TOTAL
        total_row = df_participacion[df_participacion['Embalse'] == 'TOTAL']
        if not total_row.empty:
            total_participacion = total_row['Participación (%)'].iloc[0]
            if isinstance(total_participacion, str) and '%' in total_participacion:
                total_str = total_participacion
            else:
                total_str = f"{float(total_participacion):.2f}%"
            
            table_data.append({
                'Embalse': 'TOTAL',
                'Participación (%)': total_str,
                'Riesgo': "⚡"  # Icono especial para el total
            })
        
        
        # Crear DataTable con semáforo
        return dash_table.DataTable(
            data=table_data,
            columns=[
                {"name": "Embalse", "id": "Embalse"},
                {"name": "Participación (%)", "id": "Participación (%)"},
                {"name": "🚦 Riesgo", "id": "Riesgo"}
            ],
            style_cell={'textAlign': 'left', 'padding': '8px', 'fontFamily': 'Inter, Arial', 'fontSize': 13},
            style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold'},
            style_data={'backgroundColor': '#f8f8f8'},
            style_data_conditional=[
                # Estilos de semáforo con pictogramas
                {
                    'if': {'filter_query': '{Riesgo} = 🔴'},
                    'backgroundColor': '#ffebee',
                    'color': '#c62828',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                {
                    'if': {'filter_query': '{Riesgo} = 🟡'},
                    'backgroundColor': '#fff8e1',
                    'color': '#f57c00',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                {
                    'if': {'filter_query': '{Riesgo} = 🟢'},
                    'backgroundColor': '#e8f5e8',
                    'color': '#2e7d32',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                # Estilo para fila TOTAL
                {
                    'if': {'filter_query': '{Embalse} = "TOTAL"'},
                    'backgroundColor': '#007bff',
                    'color': 'white',
                    'fontWeight': 'bold'
                }
            ],
            page_action="none",
            export_format="xlsx",
            export_headers="display"
        )
        
    except Exception as e:
        logger.error(f"❌ Error en create_region_filtered_participacion_table: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return html.Div(f"Error al cargar los datos: {str(e)}", className="text-center text-danger")



def create_region_filtered_capacidad_table(region, start_date, end_date):
    """
    Crea una tabla de capacidad útil filtrada por región específica,
    incluyendo el sistema de semáforo de riesgo.
    """
    try:
        # Obtener datos de embalses filtrados por región
        df_embalses = get_embalses_capacidad(region, start_date, end_date)
        
        if df_embalses.empty:
            return html.Div("No hay datos disponibles para esta región.", className="text-center text-muted")
        
        # Calcular participación para el semáforo
        df_participacion = get_participacion_embalses(df_embalses)
        
        # Crear datos para la tabla con semáforo
        table_data = []
        
        for _, row in df_embalses.iterrows():
            embalse_name = row['Embalse']
            capacidad = row['Capacidad_GWh_Internal']  # Solo para cálculos internos
            volumen_util_raw = row['Volumen Útil (%)']
            
            # Convertir volumen_util a número y preservar formato original si ya está formateado
            volumen_util_formatted = None
            if volumen_util_raw is None or (isinstance(volumen_util_raw, str) and volumen_util_raw == 'N/D'):
                volumen_util = 0
                volumen_util_formatted = "N/D"
            elif isinstance(volumen_util_raw, str):
                # Si ya es string, preservar formato original y extraer número
                try:
                    volumen_util = float(volumen_util_raw.replace('%', '').replace(',', '.').strip())
                    volumen_util_formatted = volumen_util_raw  # Usar formato original
                except (ValueError, AttributeError):
                    volumen_util = 0
                    volumen_util_formatted = "N/D"
            elif pd.isna(volumen_util_raw):
                volumen_util = 0
                volumen_util_formatted = "N/D"
            else:
                volumen_util = float(volumen_util_raw)
                volumen_util_formatted = None  # Formatear después
            
            # Obtener participación del embalse
            participacion_row = df_participacion[df_participacion['Embalse'] == embalse_name]
            participacion_num = 0
            if not participacion_row.empty:
                participacion_valor = participacion_row['Participación (%)'].iloc[0]
                # Manejar tanto valores numéricos como strings con formato
                if isinstance(participacion_valor, str) and '%' in participacion_valor:
                    participacion_num = float(participacion_valor.replace('%', ''))
                else:
                    participacion_num = float(participacion_valor)
            
            # Clasificar riesgo
            nivel_riesgo = clasificar_riesgo_embalse(participacion_num, volumen_util)
            
            
            # NO incluir la columna de capacidad GWh en la tabla
            table_data.append({
                'Embalse': embalse_name,
                'Volumen Útil (%)': volumen_util_formatted if volumen_util_formatted else (f"{volumen_util:.1f}%" if pd.notna(volumen_util) else "N/D"),
                'Riesgo': "🔴" if nivel_riesgo == "high" else "🟡" if nivel_riesgo == "medium" else "🟢"
            })
        
        # Agregar fila TOTAL (sin mostrar capacidad)
        total_capacity = df_embalses['Capacidad_GWh_Internal'].sum()  # Solo para cálculos
        valid_volume_data = df_embalses[df_embalses['Volumen Útil (%)'].notna()]
        avg_volume = valid_volume_data['Volumen Útil (%)'].mean() if not valid_volume_data.empty else None
        
        table_data.append({
            'Embalse': 'TOTAL',
            'Volumen Útil (%)': f"{avg_volume:.1f}%" if avg_volume is not None else "N/D",
            'Riesgo': "⚡"  # Icono especial para el total
        })
        
        # Crear DataTable con semáforo (SIN columna de GWh)
        return dash_table.DataTable(
            data=table_data,
            columns=[
                {"name": "Embalse", "id": "Embalse"},
                {"name": "Volumen Útil (%)", "id": "Volumen Útil (%)"},
                {"name": "🚦 Riesgo", "id": "Riesgo"}
            ],
            style_cell={'textAlign': 'left', 'padding': '8px', 'fontFamily': 'Inter, Arial', 'fontSize': 13},
            style_header={'backgroundColor': '#e3e3e3', 'fontWeight': 'bold'},
            style_data={'backgroundColor': '#f8f8f8'},
            style_data_conditional=[
                # Estilos de semáforo
                {
                    'if': {'filter_query': '{Riesgo} = 🔴'},
                    'backgroundColor': '#ffebee',
                    'color': '#c62828',
                    'textAlign': 'center',
                    'fontWeight': 'bold'
                },
                {
                    'if': {'filter_query': '{Riesgo} = 🟡'},
                    'backgroundColor': '#fff8e1',
                    'color': '#f57c00',
                    'textAlign': 'center',
                    'fontWeight': 'bold'
                },
                {
                    'if': {'filter_query': '{Riesgo} = 🟢'},
                    'backgroundColor': '#e8f5e8',
                    'color': '#2e7d32',
                    'textAlign': 'center',
                    'fontWeight': 'bold'
                },
                # Estilo para fila TOTAL
                {
                    'if': {'filter_query': '{Embalse} = "TOTAL"'},
                    'backgroundColor': '#007bff',
                    'color': 'white',
                    'fontWeight': 'bold'
                }
            ],
            page_action="none",
            export_format="xlsx",
            export_headers="display"
        )
        
    except Exception as e:
        logger.error(f"❌ Error en create_region_filtered_capacidad_table: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return html.Div(f"Error al cargar los datos: {str(e)}", className="text-center text-danger")

# NOTA: Los callbacks de tabla de embalses fueron eliminados para implementación directa en layout

# Callback para cargar opciones de regiones dinámicamente


