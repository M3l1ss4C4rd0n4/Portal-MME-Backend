"""
Hidrología - Servicios de Datos
================================

Funciones de obtención y procesamiento de datos desde la API XM
y el servicio de hidrología.
"""

import pandas as pd
from datetime import date, datetime, timedelta

from infrastructure.external.xm_service import obtener_datos_inteligente, get_objetoAPI

from .utils import (
    logger, normalizar_codigo, normalizar_region, 
    ensure_rio_region_loaded, clasificar_riesgo_embalse,
    obtener_estilo_riesgo, obtener_pictograma_riesgo,
    calcular_volumen_util_unificado,
)

def get_aportes_hidricos_por_region(fecha, region):
    """
    Calcula los aportes hídricos filtrados por región específica.
    Replica el método de XM: promedio acumulado mensual de aportes energía por región
    
    Args:
        fecha: Fecha en formato 'YYYY-MM-DD'
        region: Nombre de la región hidrológica
        
    Returns:
        tuple: (porcentaje, valor_GWh) o (None, None) si hay error
    """
    
    try:
        # Calcular el rango desde el primer día del mes hasta la fecha final
        fecha_final = pd.to_datetime(fecha)
        fecha_inicio = fecha_final.replace(day=1)
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
        fecha_final_str = fecha_final.strftime('%Y-%m-%d')
        
        # Obtener aportes energía por río desde PostgreSQL
        aportes_data, warning = obtener_datos_inteligente('AporEner', 'Rio', fecha_inicio_str, fecha_final_str)
        
        if aportes_data is not None and not aportes_data.empty:
            # Asignar región a cada río
            rio_region = ensure_rio_region_loaded()
            aportes_data['Region'] = aportes_data['Name'].map(rio_region)
            
            # Filtrar por región específica (normalizar región)
            # ✅ FIX ERROR #3: UPPER en lugar de title
            region_normalized = region.strip().upper()
            aportes_region = aportes_data[aportes_data['Region'] == region_normalized]
            
            if not aportes_region.empty:
                # CORRECCIÓN: Suma total del período (aportes acumulativos)
                aportes_total_region = aportes_region['Value'].sum()
                
                # Obtener media histórica para la región
                media_historica_data, warning = obtener_datos_inteligente('AporEnerMediHist', 'Rio', fecha_inicio_str, fecha_final_str)
                
                if media_historica_data is not None and not media_historica_data.empty:
                    media_historica_data['Region'] = media_historica_data['Name'].map(rio_region)
                    media_historica_region = media_historica_data[media_historica_data['Region'] == region_normalized]
                    
                    if not media_historica_region.empty:
                        # CORRECCIÓN: Suma total del período histórico
                        media_total_region = media_historica_region['Value'].sum()
                        
                        
                        if media_total_region > 0:
                            # Fórmula exacta de XM por región
                            porcentaje = round((aportes_total_region / media_total_region) * 100, 2)
                            return porcentaje, aportes_total_region
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error obteniendo aportes hídricos por región: {e}", exc_info=True)
        return None, None


def get_reservas_hidricas_por_region(fecha, region):
    """
    Calcula las reservas hídricas filtradas por región hidrológica.
    Usa calcular_volumen_util_unificado con parámetro de región.
    
    Args:
        fecha: Fecha en formato 'YYYY-MM-DD'
        region: Nombre de la región hidrológica
        
    Returns:
        tuple: (porcentaje, valor_GWh) o (None, None) si hay error
    """
    try:
        resultado = calcular_volumen_util_unificado(fecha, region=region)
        if resultado:
            return resultado['porcentaje'], resultado['volumen_gwh']
        return None, None
    except Exception as e:
        logger.error(f"Error obteniendo reservas hídricas por región '{region}': {e}", exc_info=True)
        return None, None


def get_aportes_hidricos_por_rio(fecha, rio):
    """
    Calcula los aportes hídricos de un río específico.
    
    Args:
        fecha: Fecha en formato 'YYYY-MM-DD'
        rio: Nombre del río
        
    Returns:
        tuple: (porcentaje, valor_m3s) o (None, None) si hay error
    """
    
    try:
        # Obtener aportes del río específico desde PostgreSQL
        aportes_data, warning = obtener_datos_inteligente('AporEner', 'Rio', fecha, fecha)
        
        if aportes_data is not None and not aportes_data.empty:
            # Buscar el río específico
            rio_data = aportes_data[aportes_data['Name'] == rio]
            
            if not rio_data.empty:
                aportes_rio = rio_data['Value'].iloc[0]
                
                # Para el porcentaje, comparar con la media de todos los ríos
                media_total_rios = aportes_data['Value'].mean()
                
                if media_total_rios > 0:
                    porcentaje = round((aportes_rio / media_total_rios) * 100, 2)
                    return porcentaje, aportes_rio
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error obteniendo aportes hídricos por río: {e}", exc_info=True)
        return None, None


# Obtener la relación río-región directamente desde la API XM


def get_all_rios_api():
    try:
        df, warning = obtener_datos_inteligente('AporEner', 'Rio', '2000-01-01', date.today().strftime('%Y-%m-%d'))
        if df is not None and 'Name' in df.columns:
            rios = sorted(df['Name'].dropna().unique())
            return rios
        else:
            return []
    except Exception:
        return []



def get_rio_options(region=None):
    try:
        df, warning = obtener_datos_inteligente('AporEner', 'Rio', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'), date.today().strftime('%Y-%m-%d'))
        if df is not None and 'Name' in df.columns:
            rios = sorted(df['Name'].dropna().unique())
            if region:
                rio_region = ensure_rio_region_loaded()
                rios = [r for r in rios if rio_region.get(r) == region]
            return rios
        else:
            return []
    except Exception as e:
        logger.error(f"Error obteniendo opciones de Río: {e}", exc_info=True)
        return []



def calcular_semaforo_embalse_local(participacion, volumen_pct):
    """
    Calcula el nivel de riesgo según la lógica del semáforo hidrológico de XM:
    
    Factor 1: Importancia Estratégica (participación > 10%)
    Factor 2: Disponibilidad Hídrica (% volumen útil)
    
    RIESGO ALTO (🔴): Embalses estratégicos (>10%) con volumen crítico (<30%)
    RIESGO MEDIO (🟡): Embalses estratégicos con volumen bajo (30-70%) o embalses pequeños con volumen crítico
    RIESGO BAJO (🟢): Embalses con volumen adecuado (≥70%) independientemente de su tamaño
    
    Args:
        participacion: % de participación en el sistema (0-100)
        volumen_pct: % de volumen útil disponible (0-100)
    
    Returns:
        tuple: (nivel_riesgo, color, mensaje)
    """
    es_estrategico = participacion >= 10
    
    if volumen_pct >= 70:
        return 'BAJO', '#28a745', '✓'
    elif volumen_pct >= 30:
        if es_estrategico:
            return 'MEDIO', '#ffc107', '!'
        else:
            return 'BAJO', '#28a745', '✓'
    else:  # volumen_pct < 30
        if es_estrategico:
            return 'ALTO', '#dc3545', '⚠'
        else:
            return 'MEDIO', '#ffc107', '!'



def obtener_datos_embalses_por_region():
    """
    Obtiene los datos de embalses agrupados por región hidrológica.
    Valida completitud: n_vol/n_cap >= 80% para evitar datos parciales.
    
    Returns:
        dict: {region: {embalses: [...], riesgo_max: str, color: str, lat: float, lon: float}}
    """
    try:
        # Obtener fecha actual y buscar últimos datos disponibles
        fecha_hoy = date.today()
        
        # Buscar la fecha más reciente con datos COMPLETOS en últimos 7 días
        fecha_valida = None
        df_vol = None
        df_cap = None
        df_listado = None
        
        for dias_atras in range(7):
            fecha_busqueda = fecha_hoy - timedelta(days=dias_atras)
            
            df_vol_tmp, fecha_vol = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_busqueda, dias_busqueda=1)
            df_cap_tmp, fecha_cap = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_busqueda, dias_busqueda=1)
            
            if df_vol_tmp is None or df_vol_tmp.empty or df_cap_tmp is None or df_cap_tmp.empty:
                continue
            if fecha_vol != fecha_cap:
                continue
            
            # Validar completitud: n_vol / n_cap >= 0.80
            # Contar embalses distintos en cada métrica
            col_embalse_vol = next((c for c in ['Embalse', 'recurso', 'Values_code', 'Values_Code'] if c in df_vol_tmp.columns), None)
            col_embalse_cap = next((c for c in ['Embalse', 'recurso', 'Values_code', 'Values_Code'] if c in df_cap_tmp.columns), None)
            
            if col_embalse_vol and col_embalse_cap:
                n_vol = df_vol_tmp[col_embalse_vol].nunique()
                n_cap = df_cap_tmp[col_embalse_cap].nunique()
                
                if n_cap > 0 and n_vol / n_cap < 0.80:
                    logger.warning(f"Embalses incompletos {fecha_busqueda}: n_vol={n_vol}, n_cap={n_cap}, ratio={n_vol/n_cap:.2f}")
                    continue
            
            # Datos completos encontrados
            df_vol = df_vol_tmp
            df_cap = df_cap_tmp
            fecha_valida = fecha_vol
            break
        
        if fecha_valida is None or df_vol is None or df_cap is None:
            logger.error("No se encontraron datos completos de embalses en últimos 7 días")
            return None
        
        # Obtener listado de embalses
        df_listado, fecha_listado = obtener_datos_desde_bd('ListadoEmbalses', 'Sistema', fecha_hoy)
        
        if df_listado is None:
            logger.error("No se pudo obtener ListadoEmbalses")
            return None
        
        fecha_str = fecha_valida.strftime('%Y-%m-%d')
        logger.info(f"Datos completos de embalses obtenidos para {fecha_str}")
        
        # Detectar nombre de columnas (mismo código que en las tablas)
        col_value_vol = None
        col_value_cap = None
        col_name_vol = None
        
        # Buscar columna de valores
        for col in ['Values_code', 'Value', 'Values_Code']:
            if col in df_vol.columns:
                col_value_vol = col
                break
        
        for col in ['Values_code', 'Value', 'Values_Code']:
            if col in df_cap.columns:
                col_value_cap = col
                break
        
        # Buscar columna de nombre/código
        for col in ['Values_code', 'Values_Code', 'Name']:
            if col in df_vol.columns:
                col_name_vol = col
                break
        
        if not col_value_vol or not col_value_cap or not col_name_vol:
            logger.error(f"Columnas no encontradas. df_vol: {df_vol.columns.tolist()}")
            return None
        
        logger.debug(f"Columnas detectadas - vol_value: {col_value_vol}, cap_value: {col_value_cap}, name: {col_name_vol}")
        
        # Crear diccionario de región por embalse
        embalse_region = {}
        col_name_listado = None
        for col in ['Values_Code', 'Values_code', 'Name']:
            if col in df_listado.columns:
                col_name_listado = col
                break
        
        if col_name_listado and 'Values_HydroRegion' in df_listado.columns:
            for _, row in df_listado.iterrows():
                codigo = row[col_name_listado]
                region = row['Values_HydroRegion']
                embalse_region[codigo] = region
        else:
            logger.error(f"Columnas del listado: {df_listado.columns.tolist()}")
            return None
        
        # Hacer copias antes de renombrar para evitar modificar los originales
        df_vol_copy = df_vol.copy()
        df_cap_copy = df_cap.copy()
        
        # Renombrar columnas en las copias
        df_vol_copy = df_vol_copy.rename(columns={col_value_vol: 'volumen_wh', col_name_vol: 'codigo'})
        df_cap_copy = df_cap_copy.rename(columns={col_value_cap: 'capacidad_wh'})
        
        # Buscar columna de nombre/código en df_cap
        col_name_cap = None
        for col in ['Values_code', 'Values_Code', 'Name']:
            if col in df_cap.columns:
                col_name_cap = col
                break
        
        df_cap_copy = df_cap_copy.rename(columns={col_name_cap: 'codigo'})
        
        logger.debug(f"Columnas df_vol_copy: {df_vol_copy.columns.tolist()}")
        logger.debug(f"Columnas df_cap_copy: {df_cap_copy.columns.tolist()}")
        
        # Verificar que las columnas existen
        if 'volumen_wh' not in df_vol_copy.columns or 'codigo' not in df_vol_copy.columns:
            logger.error("Error: columnas faltantes en df_vol_copy")
            return None
        
        if 'capacidad_wh' not in df_cap_copy.columns or 'codigo' not in df_cap_copy.columns:
            logger.error("Error: columnas faltantes en df_cap_copy")
            return None
        
        df_merged = pd.merge(
            df_vol_copy[['codigo', 'volumen_wh']],
            df_cap_copy[['codigo', 'capacidad_wh']],
            on='codigo',
            how='inner'
        )
        
        # Calcular porcentajes
        df_merged['volumen_pct'] = (df_merged['volumen_wh'] / df_merged['capacidad_wh']) * 100
        capacidad_total = df_merged['capacidad_wh'].sum()
        df_merged['participacion'] = (df_merged['capacidad_wh'] / capacidad_total) * 100
        
        # Agregar región
        df_merged['region'] = df_merged['codigo'].map(embalse_region)
        
        # Agrupar por región
        regiones_data = {}
        for region in df_merged['region'].unique():
            if pd.isna(region) or region not in REGIONES_COORDENADAS:
                continue
            
            df_region = df_merged[df_merged['region'] == region]
            
            # Crear lista de embalses de la región
            embalses_lista = []
            riesgo_max = 'BAJO'
            orden_riesgo = {'ALTO': 3, 'MEDIO': 2, 'BAJO': 1}
            
            for _, row in df_region.iterrows():
                riesgo, color, icono = calcular_semaforo_embalse_local(row['participacion'], row['volumen_pct'])
                
                embalses_lista.append({
                    'codigo': row['codigo'],
                    'volumen_pct': row['volumen_pct'],
                    'volumen_gwh': row['volumen_wh'] / 1e9,
                    'capacidad_gwh': row['capacidad_wh'] / 1e9,
                    'participacion': row['participacion'],
                    'riesgo': riesgo,
                    'color': color,
                    'icono': icono
                })
                
                # Actualizar riesgo máximo de la región
                if orden_riesgo[riesgo] > orden_riesgo[riesgo_max]:
                    riesgo_max = riesgo
            
            # Determinar color de la región según el riesgo máximo
            color_region = {'ALTO': '#dc3545', 'MEDIO': '#ffc107', 'BAJO': '#28a745'}[riesgo_max]
            
            coords = REGIONES_COORDENADAS[region]
            
            regiones_data[region] = {
                'embalses': embalses_lista,
                'riesgo_max': riesgo_max,
                'color': color_region,
                'lat': coords['lat'],
                'lon': coords['lon'],
                'nombre': coords['nombre'],
                'total_embalses': len(embalses_lista)
            }
        
        return regiones_data
    
    except Exception as e:
        logger.error(f"Error obteniendo datos para mapa por región: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return None



def get_participacion_embalses(df_embalses):
    """
    Calcula la participación porcentual de cada embalse respecto al total e incluye columna de riesgo.
    """
    if df_embalses.empty or 'Capacidad_GWh_Internal' not in df_embalses.columns:
        return pd.DataFrame(columns=['Embalse', 'Participación (%)', 'Riesgo'])
    
    df_participacion = df_embalses.copy()
    total = df_participacion['Capacidad_GWh_Internal'].sum()
    
    if total > 0:
        # Calcular porcentajes sin redondear primero
        porcentajes = (df_participacion['Capacidad_GWh_Internal'] / total * 100)
        
        # Ajustar el último valor para que la suma sea exactamente 100%
        porcentajes_redondeados = porcentajes.round(2)
        diferencia = 100 - porcentajes_redondeados.sum()
        
        # Si hay diferencia por redondeo, ajustar el valor más grande
        if abs(diferencia) > 0.001:
            idx_max = porcentajes_redondeados.idxmax()
            porcentajes_redondeados.loc[idx_max] += diferencia
            
        df_participacion['Participación (%)'] = porcentajes_redondeados.round(2)
    else:
        df_participacion['Participación (%)'] = 0
    
    # 🆕 Agregar columna de riesgo usando las funciones existentes
    df_con_riesgo = agregar_columna_riesgo_a_tabla(df_participacion)
    
    # Ordenar de mayor a menor por participación
    df_con_riesgo = df_con_riesgo.sort_values('Participación (%)', ascending=False)
    
    # Solo devolver las columnas necesarias (SIN capacidad, CON riesgo)
    df_final = df_con_riesgo[['Embalse', 'Participación (%)', 'Riesgo']].reset_index(drop=True)
    
    # Agregar fila TOTAL
    total_row = pd.DataFrame({
        'Embalse': ['TOTAL'],
        'Participación (%)': [100.0],
        'Riesgo': ['⚡']  # 🆕 Ícono especial para TOTAL
    })
    
    df_final = pd.concat([df_final, total_row], ignore_index=True)
    
    return df_final



def get_embalses_completa_para_tabla(region=None, start_date=None, end_date=None, embalses_df_preconsultado=None):
    """
    Función unificada que combina participación y volumen útil en UNA SOLA tabla.
    Retorna: Embalse, Participación (%), Volumen Útil (%), Riesgo
    USA LAS FUNCIONES QUE YA FUNCIONAN (get_tabla_regiones_embalses)
    
    Args:
        region: Región a filtrar (opcional)
        start_date: Fecha inicio (opcional)
        end_date: Fecha fin (opcional)
        embalses_df_preconsultado: DataFrame ya consultado de get_embalses_capacidad() para evitar consultas redundantes (opcional)
    """
# print(f"🔥🔥🔥 [INIT] get_embalses_completa_para_tabla LLAMADA: region={region}, dates={start_date} to {end_date}, preconsultado={'SÍ' if embalses_df_preconsultado is not None else 'NO'}")
    try:
        # ⚡ OPTIMIZACIÓN: Si ya se pasaron datos pre-consultados, usarlos directamente
        if embalses_df_preconsultado is not None and not embalses_df_preconsultado.empty:
# print(f"⚡ [OPTIMIZADO] Usando datos pre-consultados: {len(embalses_df_preconsultado)} embalses")
            df_embalses = embalses_df_preconsultado.copy()
            
            # El DataFrame pre-consultado ya tiene las columnas necesarias
            # Solo necesitamos filtrar por región si aplica
            if region and region != "__ALL_REGIONS__":
                region_normalized = region.strip().upper()
                if 'Región' in df_embalses.columns:
                    df_embalses = df_embalses[df_embalses['Región'] == region_normalized]
# print(f"🔥 [FILTER] Filtrado por región {region_normalized}: {len(df_embalses)} embalses")
        else:
            # Consultar datos si no se pasaron pre-consultados
# print(f"📊 [CONSULTA] Consultando datos de embalses...")
            regiones_totales, df_embalses = get_tabla_regiones_embalses(start_date, end_date)
            
# print(f"🔥 [AFTER_CALL] get_tabla_regiones_embalses retornó: {len(df_embalses)} embalses")
            
            # Filtrar por región si se especificó
            if region and region != "__ALL_REGIONS__":
                # ✅ FIX ERROR #3: UPPER en lugar de title
                region_normalized = region.strip().upper()
                df_embalses = df_embalses[df_embalses['Región'] == region_normalized]
# print(f"🔥 [FILTER] Filtrado por región {region_normalized}: {len(df_embalses)} embalses")
        
        if df_embalses.empty:
# print(f"⚠️ [RETURN_EMPTY] DataFrame vacío")
            return []
        
        if df_embalses.empty:
# print(f"⚠️ [RETURN_EMPTY] No hay embalses en región {region}")
            return []
        
        # Preparar datos para la tabla combinada
        table_data = []
        for _, row in df_embalses.iterrows():
            # Ya tiene Participación (%) calculado por get_tabla_regiones_embalses
            participacion_val = row.get('Participación (%)', 0)
            volumen_val = row.get('Volumen Útil (%)', None)
            
            # Formatear volumen útil
            if pd.notna(volumen_val):
                volumen_formatted = f"{float(volumen_val):.1f}%"
            else:
                volumen_formatted = "N/D"
            
            # Formatear participación
            participacion_formatted = f"{float(participacion_val):.2f}%"
            
            # Clasificar riesgo usando función existente
            riesgo = clasificar_riesgo_embalse(participacion_val, volumen_val if pd.notna(volumen_val) else 0)
            
            formatted_row = {
                'Embalse': row['Embalse'],
                'Participación (%)': participacion_formatted,
                'Volumen Útil (%)': volumen_formatted,
                'Riesgo': riesgo
            }
            table_data.append(formatted_row)
        
        # Ordenar por participación descendente
        table_data.sort(key=lambda x: float(x['Participación (%)'].replace('%', '')), reverse=True)
        
# print(f"✅ [SUCCESS] Tabla generada con {len(table_data)} filas")
        
        # Agregar fila TOTAL
        if table_data:
            # Calcular promedio de volumen útil
            volumenes = [float(row['Volumen Útil (%)'].replace('%', '')) for row in table_data if row['Volumen Útil (%)'] != 'N/D']
            avg_volume = sum(volumenes) / len(volumenes) if volumenes else None
            
            total_row = {
                'Embalse': 'TOTAL',
                'Participación (%)': '100.00%',
                'Volumen Útil (%)': f"{avg_volume:.1f}%" if avg_volume is not None else "N/D",
                'Riesgo': '⚡'
            }
            table_data.append(total_row)
        
# print(f"🎯 [FINAL] Total final: {len(table_data)} filas (incluye TOTAL)")
        return table_data
        
    except Exception as e:
# print(f"❌ [ERROR] Exception: {e}")
        logger.error(f"❌ Error en get_embalses_completa_para_tabla: {e}")
        import traceback
        traceback.print_exc()
        return []

# --- Función para clasificar riesgo según participación y volumen útil ---


def clasificar_riesgo_embalse_local(participacion, volumen_util):
    """
    Clasifica el riesgo de un embalse basado en participación y volumen útil
    
    Args:
        participacion (float): Participación porcentual en el sistema (0-100)
        volumen_util (float): Volumen útil disponible (0-100)
    
    Returns:
        str: '🟢' (bajo riesgo), '🟡' (riesgo medio), '🔴' (alto riesgo)
    """
    # MATRIZ DE RIESGO CORREGIDA: Combinar participación Y volumen
    
    # Caso 1: Embalses muy importantes (participación >= 15%)
    if participacion >= 15:
        if volumen_util < 30:
            return '🔴'  # Embalse importante con poco volumen = ALTO RIESGO
        elif volumen_util < 70:
            return '🟡'  # Embalse importante con volumen moderado = RIESGO MEDIO
        else:
            return '🟢'  # Embalse importante con buen volumen = BAJO RIESGO
    
    # Caso 2: Embalses importantes (participación >= 10%)
    elif participacion >= 10:
        if volumen_util < 20:
            return '🔴'  # Embalse importante con muy poco volumen = ALTO RIESGO
        elif volumen_util < 60:
            return '🟡'  # Embalse importante con volumen bajo-moderado = RIESGO MEDIO
        else:
            return '🟢'  # Embalse importante con buen volumen = BAJO RIESGO
    
    # Caso 3: Embalses moderadamente importantes (participación >= 5%)
    elif participacion >= 5:
        if volumen_util < 15:
            return '🔴'  # Embalse moderado con muy poco volumen = ALTO RIESGO
        elif volumen_util < 50:
            return '🟡'  # Embalse moderado con volumen bajo = RIESGO MEDIO
        else:
            return '🟢'  # Embalse moderado con volumen adecuado = BAJO RIESGO
    
    # Caso 4: Embalses menos importantes (participación < 5%)
    else:
        if volumen_util < 25:
            return '🟡'  # Embalse pequeño con poco volumen = RIESGO MEDIO
        else:
            return '🟢'  # Embalse pequeño con volumen adecuado = BAJO RIESGO



def obtener_estilo_riesgo_local(nivel_riesgo):
    """
    Obtiene el estilo CSS para el nivel de riesgo
    
    Args:
        nivel_riesgo (str): 'high', 'medium', 'low'
    
    Returns:
        dict: Estilo CSS para DataTable
    """
    estilos = {
        'high': {
            'backgroundColor': '#fee2e2',  # Rojo claro
            'color': '#991b1b',           # Rojo oscuro
            'fontWeight': 'bold'
        },
        'medium': {
            'backgroundColor': '#fef3c7',  # Amarillo claro
            'color': '#92400e',           # Amarillo oscuro
            'fontWeight': 'bold'
        },
        'low': {
            'backgroundColor': '#d1fae5',  # Verde claro
            'color': '#065f46'            # Verde oscuro
        }
    }
    return estilos.get(nivel_riesgo, estilos['low'])



def obtener_pictograma_riesgo_local(nivel_riesgo):
    """
    Obtiene el pictograma para el nivel de riesgo
    
    Args:
        nivel_riesgo (str): 'high', 'medium', 'low'
    
    Returns:
        str: Emoji o símbolo para el nivel de riesgo
    """
    pictogramas = {
        'high': '🔴',     # Círculo rojo
        'medium': '🟡',   # Círculo amarillo  
        'low': '🟢'       # Círculo verde
    }
    return pictogramas.get(nivel_riesgo, '🟢')



def agregar_columna_riesgo_a_tabla(df_embalses):
    """
    Agrega la columna de riesgo con pictogramas a una tabla de embalses
    
    Args:
        df_embalses (DataFrame): DataFrame con datos de embalses que debe incluir:
                                - 'Embalse': nombre del embalse
                                - 'Capacidad_GWh_Internal': para calcular participación
                                - 'Volumen Útil (%)': para evaluar riesgo
    
    Returns:
        DataFrame: DataFrame con columna 'Riesgo' agregada
    """
    if df_embalses.empty:
        return df_embalses
    
    # Crear una copia para no modificar el original
    df_con_riesgo = df_embalses.copy()
    
    # Calcular participación si no existe
    if 'Participación (%)' not in df_con_riesgo.columns and 'Capacidad_GWh_Internal' in df_con_riesgo.columns:
        # Filtrar filas que no sean TOTAL para calcular participación
        df_no_total = df_con_riesgo[df_con_riesgo['Embalse'] != 'TOTAL'].copy()
        if not df_no_total.empty:
            total_capacidad = df_no_total['Capacidad_GWh_Internal'].sum()
            if total_capacidad > 0:
                df_con_riesgo.loc[df_no_total.index, 'Participación (%)'] = (
                    df_no_total['Capacidad_GWh_Internal'] / total_capacidad * 100
                ).round(2)
            else:
                df_con_riesgo.loc[df_no_total.index, 'Participación (%)'] = 0
    
    # Inicializar columna de riesgo
    df_con_riesgo['Riesgo'] = ''
    
    # Calcular riesgo para cada embalse (excepto TOTAL)
    for idx, row in df_con_riesgo.iterrows():
        if row['Embalse'] != 'TOTAL':
            participacion = row.get('Participación (%)', 0)
            
            # Extraer valor numérico del volumen útil (puede estar como "45.2%", 45.2, o None)
            volumen_util = row.get('Volumen Útil (%)', 0)
            
            # Manejar diferentes tipos de datos
            if volumen_util is None or (isinstance(volumen_util, str) and volumen_util == 'N/D'):
                volumen_util = 0
            elif isinstance(volumen_util, str):
                # Si es string como "45.2%", extraer el número
                try:
                    volumen_util = float(volumen_util.replace('%', '').replace(',', '.').strip())
                except (ValueError, AttributeError):
                    volumen_util = 0
            elif pd.isna(volumen_util):
                volumen_util = 0
            else:
                # Ya es un número, asegurarse de que sea float
                volumen_util = float(volumen_util)
            
            # Clasificar riesgo
            nivel_riesgo = clasificar_riesgo_embalse(participacion, volumen_util)
            pictograma = obtener_pictograma_riesgo(nivel_riesgo)
            
            df_con_riesgo.at[idx, 'Riesgo'] = pictograma
        else:
            # Para la fila TOTAL, usar un ícono especial
            df_con_riesgo.at[idx, 'Riesgo'] = '⚡'
    
    return df_con_riesgo



def generar_estilos_condicionales_riesgo(df_con_riesgo):
    """
    Genera los estilos condicionales para colorear las filas según el nivel de riesgo
    
    Args:
        df_con_riesgo (DataFrame): DataFrame que incluye columnas de riesgo
    
    Returns:
        list: Lista de estilos condicionales para DataTable
    """
    estilos_condicionales = []
    
    # Recorrer cada fila para crear estilos específicos por embalse
    for idx, row in df_con_riesgo.iterrows():
        embalse = row['Embalse']
        
        if embalse != 'TOTAL':
            participacion = row.get('Participación (%)', 0)
            
            # Extraer valor numérico del volumen útil
            volumen_util = row.get('Volumen Útil (%)', 0)
            
            # Manejar diferentes tipos de datos
            if volumen_util is None or (isinstance(volumen_util, str) and volumen_util == 'N/D'):
                volumen_util = 0
            elif isinstance(volumen_util, str):
                try:
                    volumen_util = float(volumen_util.replace('%', '').replace(',', '.').strip())
                except (ValueError, AttributeError):
                    volumen_util = 0
            elif pd.isna(volumen_util):
                volumen_util = 0
            else:
                volumen_util = float(volumen_util)
            
            # Clasificar riesgo
            nivel_riesgo = clasificar_riesgo_embalse(participacion, volumen_util)
            estilo_riesgo = obtener_estilo_riesgo(nivel_riesgo)
            
            # Crear estilo condicional para este embalse específico
            estilo_embalse = {
                'if': {'filter_query': f'{{Embalse}} = "{embalse}"'},
                'backgroundColor': estilo_riesgo['backgroundColor'],
                'color': estilo_riesgo['color'],
                'fontWeight': estilo_riesgo.get('fontWeight', 'normal')
            }
            estilos_condicionales.append(estilo_embalse)
    
    # Estilo para la fila TOTAL
    estilo_total = {
        'if': {'filter_query': '{Embalse} = "TOTAL"'},
        'backgroundColor': '#007bff',
        'color': 'white',
        'fontWeight': 'bold'
    }
    estilos_condicionales.append(estilo_total)
    
    return estilos_condicionales

# Layout con almacenamiento local


def get_tabla_con_participacion(df_embalses):
    """
    Crea una tabla que combina la capacidad útil con la participación porcentual.
    """
    if df_embalses.empty or 'Capacidad_GWh_Internal' not in df_embalses.columns:
        return pd.DataFrame(columns=['Embalse', 'Participación (%)'])
    
    df_resultado = df_embalses.copy()
    total = df_resultado['Capacidad_GWh_Internal'].sum()
    
    if total > 0:
        # Calcular porcentajes sin redondear primero
        porcentajes = (df_resultado['Capacidad_GWh_Internal'] / total * 100)
        
        # Ajustar el último valor para que la suma sea exactamente 100%
        porcentajes_redondeados = porcentajes.round(2)
        diferencia = 100 - porcentajes_redondeados.sum()
        
        # Si hay diferencia por redondeo, ajustar el valor más grande
        if abs(diferencia) > 0.001:
            idx_max = porcentajes_redondeados.idxmax()
            porcentajes_redondeados.loc[idx_max] += diferencia
            
        df_resultado['Participación (%)'] = porcentajes_redondeados.round(2)
    else:
        df_resultado['Participación (%)'] = 0
    
    # Ordenar de mayor a menor por participación
    df_resultado = df_resultado.sort_values('Participación (%)', ascending=False)
    
    return df_resultado[['Embalse', 'Participación (%)', 'Volumen Útil (%)']].reset_index(drop=True)

# --- Función para crear tabla jerárquica de regiones con embalses ---


def get_embalses_by_region(region, df_completo):
    """
    Obtiene los embalses de una región específica con participación dentro de esa región.
    """
    # Usar la columna correcta 'Región' en lugar de 'Values_HydroRegion'
    embalses_region = df_completo[df_completo['Región'] == region].copy()
    if embalses_region.empty:
        return pd.DataFrame()
    
    total_region = embalses_region['Capacidad_GWh_Internal'].sum()
    if total_region > 0:
        embalses_region['Participación (%)'] = (embalses_region['Capacidad_GWh_Internal'] / total_region * 100).round(2)
        # Ajustar para que sume exactamente 100%
        diferencia = 100 - embalses_region['Participación (%)'].sum()
        if abs(diferencia) > 0.001:
            idx_max = embalses_region['Participación (%)'].idxmax()
            embalses_region.loc[idx_max, 'Participación (%)'] += diferencia
            embalses_region['Participación (%)'] = embalses_region['Participación (%)'].round(2)
    else:
        embalses_region['Participación (%)'] = 0
    
    # Formatear para mostrar como sub-elementos - usar la columna correcta 'Embalse'
    if 'Embalse' in embalses_region.columns:
        # Agregar columna de volumen útil si está disponible
        columns_to_include = ['Embalse', 'Capacidad_GWh_Internal', 'Participación (%)']
        if 'Volumen Útil (%)' in embalses_region.columns:
            columns_to_include.append('Volumen Útil (%)')
        
        resultado = embalses_region[columns_to_include].copy()
        resultado = resultado.rename(columns={
            'Embalse': 'Región', 
            'Capacidad_GWh_Internal': 'Total (GWh)',
            'Volumen Útil (%)': 'Volumen Útil (%)'
        })
        resultado['Región'] = '    └─ ' + resultado['Región'].astype(str)  # Identar embalses
        resultado['Tipo'] = 'embalse'
        return resultado
    else:
        logger.warning(f"Columnas disponibles en df_completo: {embalses_region.columns.tolist()}")
        return pd.DataFrame()


def get_embalses_data_for_table(region=None, start_date=None, end_date=None):
    """
    Función simple que obtiene datos de embalses con columnas formateados para la tabla.
    Retorna Embalse, Volumen Útil (%) y Riesgo para visualización, manteniendo cálculos internos.
    """
    try:
        # Obtener datos frescos con todas las columnas para cálculos
        df_fresh = get_embalses_capacidad(region, start_date, end_date)
        
        # 🔍 LOG: Datos obtenidos
        logger.info(f"🔍 [get_embalses_data_for_table] Región={region}, Registros={len(df_fresh)}")
        
        if df_fresh.empty:
            return []
        
        # Agregar columna de riesgo usando los datos completos
        df_con_riesgo = agregar_columna_riesgo_a_tabla(df_fresh)
        
        # Crear datos formateados para la tabla (solo columnas visibles)
        table_data = []
        
        for _, row in df_con_riesgo.iterrows():
            if row['Embalse'] != 'TOTAL':  # Procesar solo embalses, no TOTAL
                volumen_val = row['Volumen Útil (%)']
                
                # 🔍 LOG CRÍTICO: Valor RAW de Volumen Útil
                logger.info(f"🔍 [TABLE_DATA] {row['Embalse']}: Volumen RAW={volumen_val} (tipo={type(volumen_val).__name__})")
                
                # Solo formatear si es numérico, no reformatear strings
                if isinstance(volumen_val, str):
                    volumen_formatted = volumen_val  # Ya está formateado
                elif pd.notna(volumen_val) and isinstance(volumen_val, (int, float)):
                    volumen_formatted = f"{float(volumen_val):.1f}%"
                else:
                    volumen_formatted = "N/D"
                
                # 🔍 LOG CRÍTICO: Valor formateado final
                logger.info(f"🔍 [TABLE_DATA] {row['Embalse']}: Volumen FORMATTED={volumen_formatted}")
                
                formatted_row = {
                    'Embalse': row['Embalse'],
                    'Volumen Útil (%)': volumen_formatted,
                    'Riesgo': row['Riesgo']
                }
                table_data.append(formatted_row)
        
        # Agregar fila TOTAL (mantener cálculo interno de capacidad pero no mostrarla)
        total_capacity = df_fresh['Capacidad_GWh_Internal'].sum()
        valid_volume_data = df_fresh[df_fresh['Volumen Útil (%)'].notna()]
        avg_volume = valid_volume_data['Volumen Útil (%)'].mean() if not valid_volume_data.empty else None
        
        total_row = {
            'Embalse': 'TOTAL',
            'Volumen Útil (%)': f"{avg_volume:.1f}%" if avg_volume is not None else "N/D",
            'Riesgo': '⚡'  # Ícono especial para TOTAL
        }
        table_data.append(total_row)
        
        return table_data
        
    except Exception as e:
        return []



def get_embalses_capacidad(region=None, start_date=None, end_date=None):
    """
    Obtiene la capacidad útil diaria de energía por embalse desde la API XM (CapaUtilDiarEner) 
    y calcula el porcentaje de volumen útil usando la función unificada.
    Si se pasa una región, filtra los embalses de esa región.
    Solo incluye embalses que tienen datos de capacidad activos.
    
    IMPORTANTE: Usa solo end_date (fecha final) para los cálculos de volumen útil.
    """
    try:
        objetoAPI = get_objetoAPI()
        
        # Si no se proporcionan fechas, usar fecha actual
        if not start_date or not end_date:
            today = datetime.now().strftime('%Y-%m-%d')
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            start_date, end_date = yesterday, today
        
        # USAR SOLO LA FECHA FINAL para los cálculos de volumen útil
        fecha_para_calculo = end_date
        
        # Consultar datos de capacidad
        df_capacidad, warning = obtener_datos_inteligente('CapaUtilDiarEner','Embalse', fecha_para_calculo, fecha_para_calculo)
# print(f"� DEBUG CAPACIDAD: Datos de capacidad obtenidos: {len(df_capacidad) if df_capacidad is not None else 0} registros")
        
        # Si no hay datos para la fecha exacta, buscar fecha anterior con datos (igual que la función unificada)
        if df_capacidad is None or df_capacidad.empty:
            logger.debug("DEBUG CAPACIDAD: Buscando fecha anterior con datos...")
            # Usar helper para buscar fecha con datos disponibles
            fecha_obj = datetime.strptime(fecha_para_calculo, '%Y-%m-%d').date()
            df_capacidad, fecha_encontrada = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_obj)
            
            if fecha_encontrada is None or df_capacidad is None:
# print("❌ DEBUG CAPACIDAD: No se encontraron datos en los últimos 7 días")
                return pd.DataFrame()
            
            fecha_para_calculo = fecha_encontrada.strftime('%Y-%m-%d')
            logger.debug(f"DEBUG CAPACIDAD: Usando fecha con datos: {fecha_para_calculo}")
        
        logger.debug(f"DEBUG CAPACIDAD: Datos finales obtenidos: {len(df_capacidad)} registros")
        
        if 'Name' in df_capacidad.columns and 'Value' in df_capacidad.columns:
            # Obtener información de embalses desde API XM (fuente de verdad)
            today = datetime.now().strftime('%Y-%m-%d')
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            embalses_info, warning = obtener_datos_inteligente('ListadoEmbalses','Sistema', yesterday, today)
            
            # ✅ NORMALIZAR usando funciones unificadas
            embalses_info['Values_Name'] = normalizar_codigo(embalses_info['Values_Name'])
            embalses_info['Values_HydroRegion'] = normalizar_region(embalses_info['Values_HydroRegion'])
            embalse_region_dict = dict(zip(embalses_info['Values_Name'], embalses_info['Values_HydroRegion']))
            
            # ✅ FIX: obtener_datos_desde_bd retorna 'Embalse', NO 'Name'
            # NORMALIZAR códigos en df_capacidad ANTES de mapear
            df_capacidad['Name_Upper'] = normalizar_codigo(df_capacidad['Embalse'])
            logger.debug(f"Códigos normalizados: {df_capacidad['Name_Upper'].unique()[:5].tolist()}")
            
            if region:
                embalses_en_region = [e for e, r in embalse_region_dict.items() if r == region]
            
            # ✅ FIX: Usar 'Embalse' en lugar de 'Name'
            # Solo incluir embalses que tienen datos de capacidad
            embalses_con_datos = set(df_capacidad['Embalse'].unique())
            embalse_region_dict_filtrado = {
                embalse: region_emb for embalse, region_emb in embalse_region_dict.items() 
                if embalse in embalses_con_datos
            }
            
            # Procesar datos de capacidad usando código normalizado
            df_capacidad['Region'] = df_capacidad['Name_Upper'].map(embalse_region_dict)
            logger.debug(f"Regiones mapeadas: {df_capacidad['Region'].value_counts().to_dict()}")
            
            if region:
                # ✅ FIX ERROR #3: UPPER en lugar de title
                region_normalized = region.strip().upper()
                antes_filtro = len(df_capacidad)
                df_capacidad = df_capacidad[df_capacidad['Region'] == region_normalized]
            
            # ✅ NO CONVERTIR: obtener_datos_inteligente ya devuelve valores en GWh cuando viene de PostgreSQL
            # Los datos de la API XM vienen en Wh, pero obtener_datos_inteligente los convierte automáticamente
            df_capacidad['Value_GWh'] = df_capacidad['Value']
            
            df_capacidad_grouped = df_capacidad.groupby('Name')['Value_GWh'].sum().reset_index()
            df_capacidad_grouped = df_capacidad_grouped.rename(columns={'Name': 'Embalse', 'Value_GWh': 'Capacidad_GWh_Internal'})
            
            logger.debug(f"DEBUG CAPACIDAD CORREGIDA: Valores después de conversión a GWh:")
# print(df_capacidad_grouped.head().to_string())
            
            # Obtener datos de volumen útil
            df_volumen, warning_vol = obtener_datos_inteligente('VoluUtilDiarEner','Embalse', fecha_para_calculo, fecha_para_calculo)
            
            if df_volumen is None or df_volumen.empty:
                # Buscar fecha anterior con datos
                fecha_obj = datetime.strptime(fecha_para_calculo, '%Y-%m-%d').date()
                df_volumen, fecha_vol = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_obj)
                if fecha_vol:
                    fecha_para_calculo_vol = fecha_vol.strftime('%Y-%m-%d')
                    logger.debug(f"Usando fecha alternativa para volumen: {fecha_para_calculo_vol}")
            
            # Procesar datos de volumen
            df_final = df_capacidad_grouped.copy()
            
            if df_volumen is not None and not df_volumen.empty and 'Name' in df_volumen.columns and 'Value' in df_volumen.columns:
                # ✅ NO CONVERTIR: obtener_datos_inteligente ya devuelve valores en GWh
                df_volumen['Value_GWh'] = df_volumen['Value']
                df_volumen_grouped = df_volumen.groupby('Name')['Value_GWh'].sum().reset_index()
                df_volumen_grouped = df_volumen_grouped.rename(columns={'Name': 'Embalse'})
                
                # Merge con capacidad
                df_final = df_final.merge(df_volumen_grouped, on='Embalse', how='left')
                
                # Calcular porcentaje: (Volumen / Capacidad) * 100 - IGUAL que en get_tabla_regiones_embalses
                df_final['Volumen Útil (%)'] = df_final.apply(
                    lambda row: round((row['Value_GWh'] / row['Capacidad_GWh_Internal'] * 100), 1)
                    if pd.notna(row.get('Value_GWh')) and row['Capacidad_GWh_Internal'] > 0 
                    else None,
                    axis=1
                )
                
                # Limpiar columna temporal
                df_final = df_final.drop(columns=['Value_GWh'])
                
                logger.info(f"✅ Volumen útil calculado: {df_final['Volumen Útil (%)'].notna().sum()}/{len(df_final)} embalses")
            else:
                df_final['Volumen Útil (%)'] = None
                logger.warning("⚠️ No hay datos de volumen útil disponibles")

            # IMPORTANTE: NO formatear aquí, dejar valores numéricos (o None)
            # El formateo se hace solo una vez en las funciones que crean las tablas
            
# print(df_final.head())

            return df_final.sort_values('Embalse')
        else:
            # Si no hay datos de capacidad, mostrar DataFrame vacío pero con columnas correctas
            return pd.DataFrame(columns=['Embalse', 'Capacidad_GWh_Internal', 'Volumen Útil (%)'])
    except Exception as e:
        logger.error(f"Error obteniendo datos de embalses: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return pd.DataFrame(columns=['Embalse', 'Capacidad_GWh_Internal', 'Volumen Útil (%)'])



def get_porcapor_data(fecha_inicio, fecha_fin):
    """Obtener datos de la métrica PorcApor - Aportes % por río"""
    try:
        objetoAPI = get_objetoAPI()
        data, warning = obtener_datos_inteligente('PorcApor', 'Rio', fecha_inicio, fecha_fin)
        if not data.empty:
            # Multiplicar por 100 para convertir a porcentaje
            if 'Value' in data.columns:
                data['Value'] = data['Value'] * 100
            return data
        else:
            logger.warning("No se encontraron datos de PorcApor")
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()



