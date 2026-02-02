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

    def get_reservas_hidricas(self, fecha: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Calcula las reservas hídricas del SIN para una fecha específica.
        Delega en la función unificada de cálculo de volumen útil.
        
        Args:
            fecha: Fecha en formato 'YYYY-MM-DD'
            
        Returns:
            tuple: (porcentaje, valor_GWh) o (None, None) si hay error
        """
        resultado = self.calcular_volumen_util_unificado(fecha)
        if resultado:
            return resultado['porcentaje'], resultado['volumen_gwh']
        else:
            return None, None

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
                
                # - Media histórica: Es un valor CONSTANTE por río (se repite cada día)
                #   Tomar solo la PRIMERA FECHA y sumar por río
                primera_fecha_media = df_media['fecha'].min()
                df_media_un_dia = df_media[df_media['fecha'] == primera_fecha_media]
                media_valor = df_media_un_dia['valor_gwh'].sum()
                logger.info(f"✅ Media histórica: {len(df_media_un_dia)} ríos, total {media_valor:.1f} GWh")
                
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

            # Obtener catálogo de embalses (caché inteligente)
            today = datetime.now().strftime('%Y-%m-%d')
            prev_day = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            embalses_info, _ = obtener_datos_inteligente('ListadoEmbalses','Sistema', prev_day, today)
            
            # Mapeo de regiones
            if embalses_info is not None and not embalses_info.empty:
                embalses_info['Values_Name'] = embalses_info['Values_Name'].str.strip().str.upper()
                embalses_info['Values_HydroRegion'] = embalses_info['Values_HydroRegion'].str.strip().str.upper()
                embalse_region_dict = dict(zip(embalses_info['Values_Name'], embalses_info['Values_HydroRegion']))
                
                df_vol['Region'] = df_vol['Embalse'].map(embalse_region_dict)
                df_cap['Region'] = df_cap['Embalse'].map(embalse_region_dict)
            else:
                return None

            # Filtros
            if region:
                reg_norm = region.strip().upper()
                df_vol = df_vol[df_vol['Region'] == reg_norm]
                df_cap = df_cap[df_cap['Region'] == reg_norm]
            
            if embalse:
                emb_norm = embalse.strip().upper()
                df_vol = df_vol[df_vol['Embalse'] == emb_norm]
                df_cap = df_cap[df_cap['Embalse'] == emb_norm]

            if df_vol.empty or df_cap.empty:
                return None

            # Cálculo final
            # Misma lógica que el dashboard original: SQLite devuelve Wh, convertir a GWh (1e9)
            total_vol = df_vol['Value'].sum() / 1e9 
            total_cap = df_cap['Value'].sum() / 1e9
            
            embalses_incluidos = list(set(df_vol['Embalse'].tolist()) & set(df_cap['Embalse'].tolist()))

            pct = (total_vol / total_cap * 100) if total_cap > 0 else 0
            
            return {
                'porcentaje': pct,
                'volumen_gwh': total_vol,
                'capacidad_gwh': total_cap,
                'fecha_datos': fecha_vol.strftime('%Y-%m-%d'),
                'embalses': embalses_incluidos
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
