"""Helper ligero para inicializar la conexión a pydataxm de forma perezosa (lazy).

IMPORTANTE: Sistema de caché ELIMINADO - Ahora usamos ETL-SQLite para datos históricos.
La función fetch_metric_data() consulta directamente la API XM cuando es necesario.
"""
from typing import Optional
import logging
from datetime import date, datetime, timedelta
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from pydataxm.pydataxm import ReadDB
    _PYDATAXM_AVAILABLE = True
except Exception:
    ReadDB = None
    _PYDATAXM_AVAILABLE = False

_objetoAPI = None

def get_objetoAPI():
    """Retorna una instancia única de ReadDB si está disponible, o None."""
    global _objetoAPI
    if _objetoAPI is not None:
        return _objetoAPI

    logger = logging.getLogger('xm_helper')
    if not _PYDATAXM_AVAILABLE:
        logger.warning('pydataxm no disponible (get_objetoAPI)')
        _objetoAPI = None
        return None

    try:
        logger.info('Iniciando conexión a API XM...')
        _objetoAPI = ReadDB()
        logger.info('✅ pydataxm ReadDB inicializada correctamente')
    except Exception as e:
        logger.exception('❌ Error inicializando ReadDB: %s', e)
        _objetoAPI = None
    return _objetoAPI


def fetch_metric_data(metric: str, entity: str, start_date, end_date):
    """
    Consultar datos directamente desde API XM (sin caché).
    
    Args:
        metric: Métrica (ej: 'PrecBolsNaci', 'Gene')
        entity: Entidad (ej: 'Sistema', 'Recurso')
        start_date: Fecha inicio
        end_date: Fecha fin
    
    Returns:
        DataFrame o None
    """
    logger = logging.getLogger('xm_helper')
    objetoAPI = get_objetoAPI()
    
    if objetoAPI is None:
        logger.warning(f'❌ API XM no disponible para {metric}/{entity}')
        return None
    
    try:
        logger.info(f'🔍 API XM: {metric}/{entity} {start_date} a {end_date}')
        
        def _fetch():
            return objetoAPI.request_data(metric, entity, start_date, end_date)
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch)
            data = future.result(timeout=30)
        
        if data is not None and not data.empty:
            logger.info(f'✅ API XM: {len(data)} registros')
            return data
        else:
            logger.warning(f'⚠️ API XM: Sin datos')
            return None
            
    except FutureTimeoutError:
        logger.error(f'⏱️ Timeout (30s) {metric}/{entity}')
        return None
    except Exception as e:
        logger.exception(f'❌ Error: {e}')
        return None


def obtener_datos_desde_bd(metric: str, entity: str, fecha_fin, dias_busqueda: int = 7, recurso: str = None):
    """
    Consultar datos desde base de datos con fallback automático hacia atrás.
    """
    from infrastructure.database.repositories.metrics_repository import MetricsRepository
    logger = logging.getLogger('xm_helper')
    
    if isinstance(fecha_fin, str):
        fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    elif isinstance(fecha_fin, datetime):
        fecha_fin = fecha_fin.date()
    
    repo = MetricsRepository()
    
    for dias_atras in range(dias_busqueda):
        fecha_inicio = fecha_fin - timedelta(days=dias_atras)
        fecha_str = fecha_inicio.strftime('%Y-%m-%d')
        
        # FIX: Usar get_metric_data_by_entity para traer columna recurso/entidad
        df = repo.get_metric_data_by_entity(
            metric_id=metric,
            entity=entity,
            start_date=fecha_str,
            end_date=fecha_str,
            resource=recurso
        )
        
        if df is not None and not df.empty:
            if dias_atras > 0:
                logger.info(f"✅ [SQLite] {metric}/{entity} en {fecha_str} ({dias_atras}d atrás)")
            else:
                logger.info(f"✅ [SQLite] {metric}/{entity} en {fecha_str}")
            
            if 'valor_gwh' in df.columns:
                df = df.rename(columns={'valor_gwh': 'Value', 'fecha': 'Date'})
            
            if 'recurso' in df.columns and df['recurso'].notna().any():
                if entity == 'Embalse':
                    df = df.rename(columns={'recurso': 'Embalse'})
                elif entity == 'Rio':
                    df = df.rename(columns={'recurso': 'Rio'})
                elif entity == 'Recurso':
                    df = df.rename(columns={'recurso': 'Resources'})
                elif entity == 'Agente':
                    df = df.rename(columns={'recurso': 'Agente'})
            
            return df, fecha_inicio
    
    logger.warning(f"❌ [SQLite] Sin datos {metric}/{entity} últimos {dias_busqueda}d")
    return None, None
def obtener_datos_inteligente(metric: str, entity: str, fecha_inicio, fecha_fin, recurso: str = None):
    """
    Consulta inteligente de datos: SQLite (>=2020, rápido) vs API XM (<2020, lento con advertencia).
    
    Esta función decide automáticamente la fuente de datos basándose en el rango de fechas:
    - Si fecha_inicio >= 2020-01-01: Consulta SQLite (rápido, <5s)
    - Si fecha_inicio < 2020-01-01: Consulta API XM directo (lento, 30-60s, muestra advertencia)
    
    Args:
        metric: Métrica XM (ej: 'Gene', 'AporEner', 'VoluUtilDiarEner')
        entity: Entidad (ej: 'Sistema', 'Embalse', 'Rio', 'Recurso')
        fecha_inicio: Fecha inicial del rango (str 'YYYY-MM-DD' o date/datetime object)
        fecha_fin: Fecha final del rango (str 'YYYY-MM-DD' o date/datetime object)
        recurso: Filtro opcional por recurso (ej: 'SOLAR', 'EOLICA')
    
    Returns:
        tuple: (DataFrame con datos, str mensaje de advertencia o None)
    
    Ejemplos:
        # Consulta reciente (>= 2020) - Usa SQLite
        df, warning = obtener_datos_inteligente('Gene', 'Sistema', '2023-01-01', '2024-01-01')
        # warning = None, consulta rápida
        
        # Consulta histórica (< 2020) - Usa API XM
        df, warning = obtener_datos_inteligente('Gene', 'Sistema', '2015-01-01', '2016-01-01')
        # warning = "⚠️ Consultando datos históricos (antes de 2020) directamente..."
    """
    from datetime import datetime, date
    from infrastructure.database.repositories.metrics_repository import MetricsRepository
    
    logger = logging.getLogger('xm_helper')
    
    # Fecha límite: datos antes del 2020 no están en SQLite
    FECHA_LIMITE_SQLITE = date(2020, 1, 1)
    
    # Convertir fechas a objetos date
    if isinstance(fecha_inicio, str):
        fecha_inicio_date = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    elif isinstance(fecha_inicio, datetime):
        fecha_inicio_date = fecha_inicio.date()
    else:
        fecha_inicio_date = fecha_inicio
    
    if isinstance(fecha_fin, str):
        fecha_fin_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    elif isinstance(fecha_fin, datetime):
        fecha_fin_date = fecha_fin.date()
    else:
        fecha_fin_date = fecha_fin
    
    # Convertir a strings para las consultas
    fecha_inicio_str = fecha_inicio_date.strftime('%Y-%m-%d')
    fecha_fin_str = fecha_fin_date.strftime('%Y-%m-%d')
    
    # Decisión: SQLite vs API XM
    if fecha_inicio_date >= FECHA_LIMITE_SQLITE:
        # CASO 1: Datos recientes (>= 2020) - Usar SQLite (rápido)
        logger.info(f"📊 [SQLite] Consultando {metric}/{entity} desde {fecha_inicio_str} hasta {fecha_fin_str}")
        
        # Para métricas de nivel Sistema, usar recurso='_SISTEMA_' para evitar duplicados
        recurso_filtro = recurso
        if entity == 'Sistema' and recurso is None:
            recurso_filtro = '_SISTEMA_'
            logger.info(f"🔍 [Filtro] Aplicando recurso='_SISTEMA_' para evitar datos duplicados")
        
        repo = MetricsRepository()
        df = repo.get_metric_data_by_entity(
            metric_id=metric,
            entity=entity,
            start_date=fecha_inicio_str,
            end_date=fecha_fin_str,
            resource=recurso_filtro
        )
        
        if df is not None and not df.empty:
            # Renombrar columnas para compatibilidad con código existente
            # SQLite: fecha, metrica, entidad, recurso, valor_gwh, unidad
            # API XM: Date, Name, Value, Id
            
            if 'valor_gwh' in df.columns:
                df = df.rename(columns={'valor_gwh': 'Value'})
            
            if 'fecha' in df.columns:
                df = df.rename(columns={'fecha': 'Date'})
            
            # MAPEO DE CÓDIGOS A NOMBRES usando tabla catalogos
            if 'recurso' in df.columns:
                # Intentar mapear códigos a nombres desde catálogos
                catalogo_nombre = None
                if entity == 'Recurso':
                    catalogo_nombre = 'ListadoRecursos'
                elif entity == 'Embalse':
                    catalogo_nombre = 'ListadoEmbalses'
                elif entity == 'Rio':
                    catalogo_nombre = 'ListadoRios'
                elif entity == 'Agente':
                    catalogo_nombre = 'ListadoAgentes'
                
                if catalogo_nombre:
                    try:
                        # Obtener mapeo código → nombre
                        mapeo = repo.get_catalogue_mapping(catalogo_nombre)
                        if mapeo:
                            # Aplicar mapeo: si el código existe en catálogo, usar nombre; si no, mantener código
                            df['Name'] = df['recurso'].apply(lambda x: mapeo.get(str(x).upper(), x) if pd.notna(x) else x)
                            logger.info(f"✅ [Mapeo] {len(mapeo)} códigos mapeados desde {catalogo_nombre}")
                        else:
                            # Sin mapeo, usar código tal cual
                            df['Name'] = df['recurso']
                            logger.warning(f"⚠️ [Mapeo] {catalogo_nombre} vacío, usando códigos directamente")
                    except Exception as e:
                        logger.warning(f"⚠️ [Mapeo] Error obteniendo {catalogo_nombre}: {e}")
                        df['Name'] = df['recurso']
                else:
                    # Sin catálogo, renombrar directamente
                    df['Name'] = df['recurso']
                
                # ==============================================================================
                # PARCHE DE COMPATIBILIDAD (Backend -> Frontend Legacy)
                # ==============================================================================
                # Asegurar que existan los alias que espera la UI antigua (Values_Code, Values_Name)
                
                # 1. Alias para Código
                if 'recurso' in df.columns:
                    if 'Values_Code' not in df.columns:
                        df['Values_Code'] = df['recurso']  # Alias principal
                    if 'Values_code' not in df.columns:
                        df['Values_code'] = df['recurso']  # Alias lowercase
                        
                # 2. Alias para Nombre
                if 'Name' in df.columns and 'Values_Name' not in df.columns:
                    df['Values_Name'] = df['Name']
                elif 'recurso' in df.columns and 'Values_Name' not in df.columns:
                    df['Values_Name'] = df['recurso']
                
                # 3. Alias por entidad específica
                if entity == 'Embalse' and 'Name' in df.columns:
                    df['Embalse'] = df['Name']
                elif entity == 'Rio' and 'Name' in df.columns:
                    df['Rio'] = df['Name']
                elif entity == 'Recurso' and 'Name' in df.columns:
                    df['Resources'] = df['Name']
                elif entity == 'Agente' and 'Name' in df.columns:
                    df['Agente'] = df['Name']
            
            # VERIFICAR: Si todos los valores de Name son None, usar API como fallback
            if 'Name' in df.columns and df['Name'].isna().all():
                logger.warning(f"⚠️ [SQLite] Columna 'Name' vacía, fallback a API XM")
                # No retornar estos datos vacíos, dejar que consulte API
                df = None
            
            if df is not None:
                logger.info(f"✅ [SQLite] {len(df)} registros obtenidos con nombres mapeados")
                return df, None  # Sin advertencia
        
        # Si no hay datos en SQLite o están incompletos, usar API XM
        logger.info(f"📡 [Fallback] Consultando API XM para {metric}/{entity}")
    
    # CASO 2: Datos históricos (< 2020) o fallback desde SQLite
    mensaje_advertencia = None
    if fecha_inicio_date < FECHA_LIMITE_SQLITE:
        mensaje_advertencia = (
            f"⚠️ **Consultando datos históricos** (antes de 2020) directamente desde API XM. "
            f"Esta operación puede tardar 30-60 segundos..."
        )
        logger.warning(f"🐌 [API XM] Consultando datos históricos {metric}/{entity} desde {fecha_inicio_str}")
    else:
        logger.info(f"📡 [API XM] Fallback desde SQLite, consultando {metric}/{entity}")
    
    try:
        df = fetch_metric_data(
            metric=metric,
            entity=entity,
            start_date=fecha_inicio_str,
            end_date=fecha_fin_str
        )
        
        if df is not None and not df.empty:
            logger.info(f"✅ [API XM] {len(df)} registros obtenidos")
            
            # POST-PROCESAMIENTO: Convertir datos horarios a valores diarios
            # Si el DF tiene columnas Values_Hour01-24 pero no 'Value', agregarlo
            hour_cols = [f'Values_Hour{i:02d}' for i in range(1, 25)]
            existing_hour_cols = [col for col in hour_cols if col in df.columns]
            
            if existing_hour_cols and 'Value' not in df.columns:
                # Detectar si es métrica de energía o potencia
                # Pérdidas y Generación: SUMAR (kWh → GWh)
                # Disponibilidad: PROMEDIAR (kW → MW)
                if 'Perdidas' in metric or 'Gene' in metric or 'Dema' in metric:
                    # Energía: SUMAR valores horarios en kWh → GWh
                    df['Value'] = df[existing_hour_cols].sum(axis=1) / 1_000_000
                    logger.info(f"🔄 [Post-procesamiento] Sumando {len(existing_hour_cols)} horas (kWh → GWh)")
                elif 'Dispo' in metric:
                    # Potencia: PROMEDIAR valores horarios en kW → MW
                    df['Value'] = df[existing_hour_cols].mean(axis=1) / 1_000
                    logger.info(f"🔄 [Post-procesamiento] Promediando {len(existing_hour_cols)} horas (kW → MW)")
                else:
                    # Por defecto: SUMAR
                    df['Value'] = df[existing_hour_cols].sum(axis=1) / 1_000_000
                    logger.info(f"🔄 [Post-procesamiento] Sumando {len(existing_hour_cols)} horas (conversión genérica)")
            
            return df, mensaje_advertencia
        else:
            logger.warning(f"⚠️ [API XM] No hay datos para {metric}/{entity} en el rango solicitado")
            return None, mensaje_advertencia
    
    except Exception as e:
        logger.error(f"❌ [API XM] Error al consultar datos: {e}")
        return None, mensaje_advertencia

def fetch_gene_recurso_chunked(start_date, end_date):
    """
    Obtiene generación por recurso en el rango de fechas.
    Wrapper de compatibilidad.
    """
    return fetch_metric_data('Gene', 'Recurso', start_date, end_date)

class XMService:
    """Clase wrapper para compatibilidad con Clean Architecture"""
    
    METRIC_ENTITY_MAP = {
        # Precios
        'PrecBolsNaci': 'Sistema',
        'PrecBolsCTG': 'Sistema',
        'PrecEsca': 'Sistema',
        'PrecEscaAct': 'Sistema',
        'PrecEscaSup': 'Sistema',
        'PrecEscaInf': 'Sistema',
        
        # Comercialización
        'CONTRATO': 'Sistema', 
        'LIQUIDACION': 'Sistema',
        
        # Demanda
        'DemaCome': 'Agente',
        'DemaReal': 'Agente',
        
        # Distribución / Otros
        'TXR': 'Sistema',
        'PERCOM': 'Sistema', 
        'CONSUM': 'Sistema',
        'PERD': 'Sistema',
        'Gene': 'Recurso'
    }

    def get_metric_data(self, metric: str, start_date, end_date):
        entity = self.METRIC_ENTITY_MAP.get(metric, 'Sistema')
        return fetch_metric_data(metric, entity, start_date, end_date)
