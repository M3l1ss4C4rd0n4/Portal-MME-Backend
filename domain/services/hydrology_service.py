from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
import pandas as pd
import logging
from infrastructure.external.xm_service import obtener_datos_inteligente, obtener_datos_desde_bd, get_objetoAPI

# Instanciar logger del servicio
logger = logging.getLogger(__name__)

class HydrologyService:
    """
    Servicio de Dominio para Hidrología.
    Centraliza toda la lógica de negocio y acceso a datos de métricas hídricas.
    Migrado progresivamente desde generacion_hidraulica_hidrologia.py
    """

    def __init__(self):
        pass

    def get_reservas_hidricas(self, fecha: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        Calcula las reservas hídricas del SIN para una fecha específica.
        Delega en la función unificada de cálculo de volumen útil.
        
        Args:
            fecha: Fecha en formato 'YYYY-MM-DD'
            
        Returns:
            tuple: (porcentaje, valor_GWh, fecha_datos) o (None, None, None) si hay error
                   fecha_datos es la fecha real del último dato disponible en BD (YYYY-MM-DD)
        """
        resultado = self.calcular_volumen_util_unificado(fecha)
        if resultado:
            return resultado['porcentaje'], resultado['volumen_gwh'], resultado.get('fecha_datos')
        else:
            return None, None, None

    def get_aportes_hidricos(self, fecha: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Calcula los aportes hídricos del SIN para una fecha específica.
        Fórmula XM: (Suma Mes Aportes Energía / Suma Mes Media Histórica) * 100
        
        CORRECCIÓN CRÍTICA: Los aportes vienen por 'Rio', NO por 'Sistema'.
        Debemos AGREGAR todos los ríos para obtener el total nacional.
        
        Args:
            fecha: Fecha en formato 'YYYY-MM-DD'
            
        Returns:
            tuple: (porcentaje, valor_GWh) o (None, None) si hay error
        """
        try:
            # Calcular el rango desde el primer día del mes hasta la fecha final
            fecha_final = pd.to_datetime(fecha)
            fecha_inicio = fecha_final.replace(day=1)
            fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
            fecha_final_str = fecha_final.strftime('%Y-%m-%d')

            # NUEVO: Obtener datos desde SQLite directamente (más confiable)
            from infrastructure.database.repositories.metrics_repository import MetricsRepository
            repo = MetricsRepository()
            
            # 1. Aportes de energía POR RÍO (agregar todos)
            df_aportes = repo.get_metric_data_by_entity(
                metric_id='AporEner',
                entity='Rio',  # ✅ FIX APLICADO: Consultar todos los ríos
                start_date=fecha_inicio_str,
                end_date=fecha_final_str
            )
            
            # 2. Media histórica POR RÍO (agregar todos)
            df_media = repo.get_metric_data_by_entity(
                metric_id='AporEnerMediHist',
                entity='Rio',  # ✅ FIX APLICADO: Consultar todos los ríos
                start_date=fecha_inicio_str,
                end_date=fecha_final_str
            )

            if df_aportes is not None and not df_aportes.empty and \
               df_media is not None and not df_media.empty:
                
                # AGREGACIÓN CORRECTA:
                # - Aportes diarios: SUMAR todos los días y todos los ríos
                aportes_valor = df_aportes['valor_gwh'].sum()
                num_rios_aportes = df_aportes['recurso'].nunique() if 'recurso' in df_aportes.columns else len(df_aportes)
                logger.info(f"✅ Aportes: {num_rios_aportes} ríos, total {aportes_valor:.1f} GWh")
                
                # - Media histórica: Sumar TODOS los días y ríos del mismo rango
                #   (La media se repite cada día, así que sumar N días da N × media_diaria,
                #    lo cual es correcto porque aportes también suma N días)
                media_valor = df_media['valor_gwh'].sum()
                num_rios_media = df_media['recurso'].nunique() if 'recurso' in df_media.columns else len(df_media)
                num_dias_media = df_media['fecha'].nunique() if 'fecha' in df_media.columns else 1
                logger.info(f"✅ Media histórica: {num_rios_media} ríos, {num_dias_media} días, total {media_valor:.1f} GWh")
                
                if media_valor == 0:
                    logger.warning(f"Media histórica = 0 para {fecha}")
                    return 0.0, aportes_valor
                    
                porcentaje = (aportes_valor / media_valor) * 100
                
                # ✅ VALIDACIÓN CON VALIDATORS
                from domain.services.validators import MetricValidators
                if not MetricValidators.validate('AportesHidricos', porcentaje):
                    logger.error(f"❌ Aportes inválidos: {porcentaje:.1f}%, rechazando dato")
                    return None, None  # Rechazar dato claramente erróneo
                
                logger.info(f"✅ Aportes hídricos: {porcentaje:.1f}% ({aportes_valor:.1f} GWh / {media_valor:.1f} GWh)")
                return porcentaje, aportes_valor
            
            logger.warning(f"No se pudieron calcular aportes para {fecha}")
            return None, None

        except Exception as e:
            logger.error(f"Error obteniendo aportes hídricos: {e}", exc_info=True)
            return None, None

    def calcular_volumen_util_unificado(self, fecha: str, region: str = None, embalse: str = None) -> Optional[Dict[str, Any]]:
        """
        Función central para calcular el porcentaje de volumen útil.
        Fórmula: suma VoluUtilDiarEner / suma CapaUtilDiarEner * 100
        """
        logger.debug(f"Servicio calculando volumen útil - Fecha: {fecha}, Región: {region}")
        
        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            # Usar directamente el SQLite helper (infraestructura)
            df_vol, fecha_vol = obtener_datos_desde_bd('VoluUtilDiarEner', 'Embalse', fecha_obj)
            df_cap, fecha_cap = obtener_datos_desde_bd('CapaUtilDiarEner', 'Embalse', fecha_obj)
            
            # Verificar consistencia de fechas
            if not(df_vol is not None and df_cap is not None and fecha_vol == fecha_cap):
                return None

            # Intentar obtener catálogo de embalses para mapeo de regiones
            embalse_region_dict = {}
            try:
                # Primero intentar desde la tabla catalogos (fuente confiable)
                df_catalogo = self.get_embalses()
                if df_catalogo is not None and not df_catalogo.empty and 'region' in df_catalogo.columns:
                    df_catalogo['embalse'] = df_catalogo['embalse'].str.strip().str.upper()
                    df_catalogo['region'] = df_catalogo['region'].fillna('').str.strip().str.upper()
                    embalse_region_dict = dict(zip(df_catalogo['embalse'], df_catalogo['region']))
                    logger.debug(f"Catálogo de embalses cargado: {len(embalse_region_dict)} embalses")
            except Exception as e_cat:
                logger.warning(f"No se pudo cargar catálogo de embalses: {e_cat}")

            # Asignar regiones si hay mapeo disponible
            if embalse_region_dict:
                df_vol['Region'] = df_vol['Embalse'].str.strip().str.upper().map(embalse_region_dict)
                df_cap['Region'] = df_cap['Embalse'].str.strip().str.upper().map(embalse_region_dict)

            # Filtro por región (solo si hay mapeo de regiones)
            if region and embalse_region_dict:
                reg_norm = region.strip().upper()
                df_vol = df_vol[df_vol['Region'] == reg_norm]
                df_cap = df_cap[df_cap['Region'] == reg_norm]
            elif region and not embalse_region_dict:
                logger.warning(f"Filtro por región '{region}' solicitado pero no hay catálogo de regiones disponible. Calculando total nacional.")
            
            # Filtro por embalse específico
            if embalse:
                emb_norm = embalse.strip().upper()
                df_vol = df_vol[df_vol['Embalse'].str.strip().str.upper() == emb_norm]
                df_cap = df_cap[df_cap['Embalse'].str.strip().str.upper() == emb_norm]

            if df_vol.empty or df_cap.empty:
                return None

            # ── Validar completitud: VoluUtil debe tener al menos 80%
            #    de los embalses que CapaUtil reporta.
            #    Cuando XM publica datos parciales (ej: 4 de 24 embalses),
            #    el porcentaje resultante es erróneo (ej: 4% en vez de 74%).
            n_embalses_vol = df_vol['Embalse'].nunique()
            n_embalses_cap = df_cap['Embalse'].nunique()
            if n_embalses_cap > 0 and n_embalses_vol / n_embalses_cap < 0.80:
                logger.warning(
                    f"[EMBALSES] Dato incompleto en {fecha_vol}: "
                    f"VoluUtil tiene {n_embalses_vol} embalses vs "
                    f"CapaUtil {n_embalses_cap} — descartando."
                )
                return None

            # Calcular solo sobre embalses que aparecen en AMBOS conjuntos
            embalses_vol_set = set(df_vol['Embalse'].str.strip().str.upper())
            embalses_cap_set = set(df_cap['Embalse'].str.strip().str.upper())
            embalses_comunes = embalses_vol_set & embalses_cap_set

            if not embalses_comunes:
                return None

            df_vol_f = df_vol[df_vol['Embalse'].str.strip().str.upper().isin(embalses_comunes)]
            df_cap_f = df_cap[df_cap['Embalse'].str.strip().str.upper().isin(embalses_comunes)]

            # Cálculo final
            # Los datos de VoluUtilDiarEner y CapaUtilDiarEner ya vienen en GWh
            total_vol = df_vol_f['Value'].sum()
            total_cap = df_cap_f['Value'].sum()

            pct = (total_vol / total_cap * 100) if total_cap > 0 else 0
            
            return {
                'porcentaje': pct,
                'volumen_gwh': total_vol,
                'capacidad_gwh': total_cap,
                'fecha_datos': fecha_vol.strftime('%Y-%m-%d'),
                'embalses': list(embalses_comunes),
                'n_embalses': len(embalses_comunes),
            }

        except Exception as e:
            logger.error(f"Error en calcular_volumen_util_unificado: {e}", exc_info=True)
            return None

    def _fetch_metric_with_fallbacks(self, metricas: List[str], entidad: str, start: str, end: str):
        """Helper privado para intentar varias métricas hasta que una funcione"""
        for metrica in metricas:
            try:
                data, _ = obtener_datos_inteligente(metrica, entidad, start, end)
                if data is not None and not data.empty:
                    return data
            except Exception:
                continue
        return None

    def get_aportes_diarios(self, start_date, end_date, reservoir: str = 'Sistema') -> pd.DataFrame:
        """
        Obtiene aportes hídricos diarios para un rango de fechas.
        
        Args:
            start_date: Fecha inicial (date o str)
            end_date: Fecha final (date o str)
            reservoir: Embalse específico o 'Sistema' para total
        
        Returns:
            DataFrame con columnas: fecha, valor (en m³/s o GWh-día según disponibilidad)
        """
        try:
            from datetime import date as date_type
            
            # Convertir fechas
            if isinstance(start_date, date_type):
                start_str = start_date.strftime('%Y-%m-%d')
            else:
                start_str = str(start_date)
            
            if isinstance(end_date, date_type):
                end_str = end_date.strftime('%Y-%m-%d')
            else:
                end_str = str(end_date)
            
            # Intentar obtener aportes energía (AporEner)
            df, _ = obtener_datos_inteligente('AporEner', reservoir, start_str, end_str)
            
            if df is None or df.empty:
                # Fallback: agregar por ríos si es Sistema
                if reservoir == 'Sistema':
                    df, _ = obtener_datos_desde_bd('AporEner', 'Rio', start_str, end_str)
                    if df is not None and not df.empty:
                        # Agrupar por fecha
                        df = df.groupby('fecha').agg({'valor': 'sum'}).reset_index()
            
            if df is None or df.empty:
                logger.warning(f"⚠️ Sin datos de aportes para {reservoir}")
                return pd.DataFrame()
            
            # Asegurar que tenga las columnas correctas
            if 'fecha' in df.columns and 'valor' in df.columns:
                return df[['fecha', 'valor']]
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo aportes diarios: {e}")
            return pd.DataFrame()

    def get_embalses(self) -> pd.DataFrame:
        """
        Obtiene catálogo de embalses del SIN.
        
        Returns:
            DataFrame con columnas: embalse, capacidad_util_gwh, rio, region
        """
        try:
            from infrastructure.database.repositories.metrics_repository import MetricsRepository
            repo = MetricsRepository()
            
            query = """
                SELECT 
                    codigo as embalse,
                    CAST(valor_numerico as FLOAT) as capacidad_util_gwh,
                    atributo1 as rio,
                    atributo2 as region
                FROM catalogos
                WHERE catalogo = 'ListadoEmbalses'
                AND codigo IS NOT NULL
                ORDER BY codigo
            """
            
            df = repo.execute_dataframe(query)
            
            if df is None or df.empty:
                logger.warning("⚠️ No se encontraron embalses en catálogo")
                return pd.DataFrame()
            
            logger.info(f"✅ {len(df)} embalses encontrados")
            return df
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo embalses: {e}")
            return pd.DataFrame()

    def get_energia_embalsada(self, start_date, end_date) -> pd.DataFrame:
        """
        Obtiene energía embalsada del sistema.
        
        Returns:
            DataFrame con columnas: fecha, valor (en GWh-día)
        """
        try:
            from datetime import date as date_type
            
            # Convertir fechas
            if isinstance(start_date, date_type):
                start_str = start_date.strftime('%Y-%m-%d')
            else:
                start_str = str(start_date)
            
            if isinstance(end_date, date_type):
                end_str = end_date.strftime('%Y-%m-%d')
            else:
                end_str = str(end_date)
            
            # Intentar DERTOVe (Energía Útil Almacenada)
            df, _ = obtener_datos_inteligente('DERTOVe', 'Sistema', start_str, end_str)
            
            if df is None or df.empty:
                logger.warning("⚠️ Sin datos de energía embalsada")
                return pd.DataFrame()
            
            if 'fecha' in df.columns and 'valor' in df.columns:
                return df[['fecha', 'valor']]
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo energía embalsada: {e}")
            return pd.DataFrame()
