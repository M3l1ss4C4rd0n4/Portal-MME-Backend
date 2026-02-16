"""
Servicio de Análisis Inteligente del Sector Energético

Este servicio es el cerebro del orquestador para el chatbot.
Recopila datos de TODOS los servicios, detecta anomalías y genera
resúmenes inteligentes del estado del sector energético colombiano.

Autor: Portal Energético MME
Fecha: 9 de febrero de 2026
"""

import asyncio
import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import date, datetime, timedelta
from enum import Enum
import pandas as pd
import numpy as np

from domain.services.generation_service import GenerationService
from domain.services.hydrology_service import HydrologyService
from domain.services.metrics_service import MetricsService
from domain.services.transmission_service import TransmissionService
from domain.services.distribution_service import DistributionService
from domain.services.commercial_service import CommercialService
from domain.services.losses_service import LossesService
from domain.services.restrictions_service import RestrictionsService
from domain.services.validators import MetricValidators

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# ENUMS Y CONSTANTES
# ═══════════════════════════════════════════════════════════

class SeverityLevel(str, Enum):
    """Niveles de severidad para anomalías"""
    NORMAL = "normal"
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class TrendDirection(str, Enum):
    """Dirección de tendencia"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    UNKNOWN = "unknown"


# Umbrales de anomalías por métrica
THRESHOLDS = {
    "reservas_hidricas": {
        "critical_low": 30.0,
        "warning_low": 40.0,
        "optimal_min": 50.0,
        "optimal_max": 85.0,
        "warning_high": 95.0,
        "critical_high": 98.0
    },
    "aportes_hidricos": {
        "critical_low": 50.0,
        "warning_low": 70.0,
        "optimal_min": 80.0,
        "optimal_max": 120.0,
        "warning_high": 150.0,
        "critical_high": 200.0
    },
    "generacion_variacion": {
       "warning_change": 15.0,  # % cambio día a día
        "critical_change": 25.0
    },
    "demanda_variacion": {
        "warning_change": 15.0,
        "critical_change": 25.0
    },
    "perdidas": {
        "optimal_max": 10.0,
        "warning_high": 12.0,
        "critical_high": 15.0
    },
    "restricciones_incremento": {
        "warning_multiplier": 2.0,  # 2x vs semana anterior
        "critical_multiplier": 3.0
    }
}


# ═══════════════════════════════════════════════════════════
# CLASES DE DATOS
# ═══════════════════════════════════════════════════════════

class Anomalia:
    """Representa una anomalía detectada"""
    def __init__(
        self,
        sector: str,
        metric_name: str,
        severity: SeverityLevel,
        current_value: float,
        expected_value: Optional[float],
        description: str,
        affected_resources: List[str] = None
    ):
        self.sector = sector
        self.metric_name = metric_name
        self.severity = severity
        self.current_value = current_value
        self.expected_value = expected_value
        self.description = description
        self.affected_resources = affected_resources or []
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "sector": self.sector,
            "metric": self.metric_name,
            "severity": self.severity.value,
            "current_value": round(self.current_value, 2) if self.current_value else None,
            "expected_value": round(self.expected_value, 2) if self.expected_value else None,
            "description": self.description,
            "affected_resources": self.affected_resources,
            "timestamp": self.timestamp.isoformat()
        }


class SectorStatus:
    """Estado de un sector del sistema eléctrico"""
    def __init__(self, sector_name: str):
        self.sector_name = sector_name
        self.kpis: Dict[str, Any] = {}
        self.trends: Dict[str, TrendDirection] = {}
        self.anomalias: List[Anomalia] = []
        self.overall_status: SeverityLevel = SeverityLevel.NORMAL
        self.summary: str = ""
        self.last_update: datetime = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        return {
            "sector": self.sector_name,
            "estado": self.overall_status.value,  # español para compatibilidad
            "status": self.overall_status.value,  # inglés por si acaso
            "kpis": self.kpis,
            "tendencias": {k: v.value for k, v in self.trends.items()},  # español
            "trends": {k: v.value for k, v in self.trends.items()},  # inglés
            "anomalias": [a.to_dict() for a in self.anomalias],
            "anomalias_criticas": [a.to_dict() for a in self.anomalias if a.severity in [SeverityLevel.CRITICAL, SeverityLevel.ALERT]],
            "numero_anomalias": len(self.anomalias),
            "summary": self.summary,
            "last_update": self.last_update.isoformat()
        }


# ═══════════════════════════════════════════════════════════
# SERVICIO DE ANÁLISIS INTELIGENTE
# ═══════════════════════════════════════════════════════════

class IntelligentAnalysisService:
    """
    Servicio central de análisis inteligente del sector energético
    
    Funcionalidades:
    - Recopila datos de todos los servicios
    - Calcula indicadores derivados
    - Detecta anomalías automáticamente
    - Genera resúmenes textuales
    - Clasifica severidad de problemas
    """
    
    def __init__(self):
        """Inicializar todos los servicios necesarios"""
        self.generation_service = GenerationService()
        self.hydrology_service = HydrologyService()
        self.metrics_service = MetricsService()
            
        try:
            self.transmission_service = TransmissionService()
        except Exception as e:
            logger.warning(f"TransmissionService no disponible: {e}")
            self.transmission_service = None
            
        try:
            self.distribution_service = DistributionService()
        except Exception as e:
            logger.warning(f"DistributionService no disponible: {e}")
            self.distribution_service = None
            
        try:
            self.commercial_service = CommercialService()
        except Exception as e:
            logger.warning(f"CommercialService no disponible: {e}")
            self.commercial_service = None
            
        try:
            self.losses_service = LossesService()
        except Exception as e:
            logger.warning(f"LossesService no disponible: {e}")
            self.losses_service = None
            
        try:
            self.restrictions_service = RestrictionsService()
        except Exception as e:
            logger.warning(f"RestrictionsService no disponible: {e}")
            self.restrictions_service = None
    
    # ─────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL: ANÁLISIS COMPLETO DEL SECTOR
    # ─────────────────────────────────────────────────────────
    
    async def analyze_complete_sector(self) -> Dict[str, Any]:
        """
        Análisis completo del sector energético
        
        Returns:
            Dict con:
            - estado_general: SeverityLevel
            - sectores: Dict de SectorStatus por sector
            - anomalias_criticas: Lista de anomalías críticas
            - resumen_ejecutivo: Texto resumen
        """
        logger.info("[ANÁLISIS INTELIGENTE] Iniciando análisis completo del sector")
        
        # Ejecutar análisis de cada sector en paralelo
        tasks = [
            self.analyze_generation_sector(),
            self.analyze_hydrology_sector(),
            self.analyze_demand_sector(),
            self.analyze_losses_sector(),
            self.analyze_restrictions_sector(),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        sectores = {}
        todas_anomalias = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error en análisis de sector {i}: {result}")
                continue
            if isinstance(result, SectorStatus):
                sectores[result.sector_name] = result
                todas_anomalias.extend(result.anomalias)
        
        # Determinar estado general
        estado_general = self._calculate_overall_status(sectores)
        
        # Filtrar anomalías críticas
        anomalias_criticas = [
            a for a in todas_anomalias 
            if a.severity in [SeverityLevel.CRITICAL, SeverityLevel.ALERT]
        ]
        
        # Generar resumen ejecutivo
        resumen_ejecutivo = self._generate_executive_summary(sectores, anomalias_criticas)
        
        return {
            "estado_general": estado_general.value,
            "sectores": {k: v.to_dict() for k, v in sectores.items()},
            "anomalias_criticas": [a.to_dict() for a in anomalias_criticas],
            "resumen_ejecutivo": resumen_ejecutivo,
            "timestamp": datetime.utcnow().isoformat(),
            "total_anomalias": len(todas_anomalias),
            "anomalias_por_severidad": self._count_by_severity(todas_anomalias)
        }
    
    # ─────────────────────────────────────────────────────────
    # ANÁLISIS POR SECTORES ESPECÍFICOS
    # ─────────────────────────────────────────────────────────
    
    async def analyze_generation_sector(self) -> SectorStatus:
        """Análisis completo del sector de generación"""
        status = SectorStatus("generacion")
        
        try:
            hoy = date.today()
            ayer = hoy - timedelta(days=1)
            semana_atras = hoy - timedelta(days=7)
            
            # Obtener datos de generación
            df_hoy = await asyncio.to_thread(
                self.generation_service.get_daily_generation_system,
                ayer, ayer
            )
            
            df_semana = await asyncio.to_thread(
                self.generation_service.get_daily_generation_system,
                semana_atras, ayer
            )
            
            if not df_hoy.empty:
                gen_hoy = df_hoy['valor_gwh'].iloc[0]
                status.kpis['generacion_hoy_gwh'] = round(gen_hoy, 2)
                
                # Tendencia semanal
                if not df_semana.empty and len(df_semana) > 1:
                    gen_promedio_semana = df_semana['valor_gwh'].mean()
                    status.kpis['generacion_promedio_semana_gwh'] = round(gen_promedio_semana, 2)
                    
                    # Calcular variación
                    variacion_pct = ((gen_hoy - gen_promedio_semana) / gen_promedio_semana) * 100
                    status.kpis['variacion_vs_semana_pct'] = round(variacion_pct, 2)
                    
                    # Detectar anomalía
                    if abs(variacion_pct) > THRESHOLDS['generacion_variacion']['critical_change']:
                        status.anomalias.append(Anomalia(
                            sector="generacion",
                            metric_name="variacion_generacion",
                            severity=SeverityLevel.CRITICAL,
                            current_value=gen_hoy,
                            expected_value=gen_promedio_semana,
                            description=f"Generación {'aumentó' if variacion_pct > 0 else 'disminuyó'} {abs(variacion_pct):.1f}% respecto a promedio semanal"
                        ))
                    elif abs(variacion_pct) > THRESHOLDS['generacion_variacion']['warning_change']:
                        status.anomalias.append(Anomalia(
                            sector="generacion",
                            metric_name="variacion_generacion",
                            severity=SeverityLevel.WARNING,
                            current_value=gen_hoy,
                            expected_value=gen_promedio_semana,
                            description=f"Generación con variación de {variacion_pct:.1f}% vs promedio semanal"
                        ))
                    
                    # Tendencia
                    if variacion_pct > 5:
                        status.trends['generacion'] = TrendDirection.UP
                    elif variacion_pct < -5:
                        status.trends['generacion'] = TrendDirection.DOWN
                    else:
                        status.trends['generacion'] = TrendDirection.STABLE
            
            # Mix energético (importante para diversificación)
            df_mix = await asyncio.to_thread(
                self.generation_service.get_generation_mix,
                ayer
            )
            
            if not df_mix.empty:
                mix_dict = {}
                for _, row in df_mix.iterrows():
                    mix_dict[row['tipo']] = {
                        'gwh': round(row['generacion_gwh'], 2),
                        'porcentaje': round(row['porcentaje'], 2)
                    }
                status.kpis['mix_energetico'] = mix_dict
                
                # Analizar dependencia hidráulica
                if 'HIDRAULICA' in mix_dict:
                    hidro_pct = mix_dict['HIDRAULICA']['porcentaje']
                    if hidro_pct > 80:
                        status.anomalias.append(Anomalia(
                            sector="generacion",
                            metric_name="dependencia_hidraulica",
                            severity=SeverityLevel.WARNING,
                            current_value=hidro_pct,
                            expected_value=70.0,
                            description=f"Alta dependencia hidráulica: {hidro_pct:.1f}% del mix"
                        ))
            
            # Status general del sector
            status.overall_status = self._calculate_sector_status(status.anomalias)
            status.summary = self._generate_generation_summary(status)
            
        except Exception as e:
            logger.error(f"Error en análisis de generación: {e}", exc_info=True)
            status.summary = f"Error analizando generación: {str(e)}"
            status.overall_status = SeverityLevel.INFO
        
        return status
    
    async def analyze_hydrology_sector(self) -> SectorStatus:
        """Análisis completo del sector hidrológico"""
        status = SectorStatus("hidrologia")
        
        try:
            hoy_str = date.today().strftime('%Y-%m-%d')
            
            # Reservas hídricas
            reserva_pct, reserva_gwh, _ = self.hydrology_service.get_reservas_hidricas(hoy_str)
            
            if reserva_pct is not None:
                status.kpis['reservas_pct'] = round(reserva_pct, 2)
                status.kpis['energia_embalsada_gwh'] = round(reserva_gwh, 2)
                
                # Detectar anomalías en reservas
                thresholds = THRESHOLDS['reservas_hidricas']
                if reserva_pct < thresholds['critical_low']:
                    status.anomalias.append(Anomalia(
                        sector="hidrologia",
                        metric_name="reservas_hidricas",
                        severity=SeverityLevel.CRITICAL,
                        current_value=reserva_pct,
                        expected_value=thresholds['optimal_min'],
                        description=f"Reservas hídricas críticas: {reserva_pct:.1f}% (por debajo de {thresholds['critical_low']}%)"
                    ))
                elif reserva_pct < thresholds['warning_low']:
                    status.anomalias.append(Anomalia(
                        sector="hidrologia",
                        metric_name="reservas_hidricas",
                        severity=SeverityLevel.ALERT,
                        current_value=reserva_pct,
                        expected_value=thresholds['optimal_min'],
                        description=f"Reservas hídricas bajas: {reserva_pct:.1f}%"
                    ))
                elif reserva_pct > thresholds['critical_high']:
                    status.anomalias.append(Anomalia(
                        sector="hidrologia",
                        metric_name="reservas_hidricas",
                        severity=SeverityLevel.WARNING,
                        current_value=reserva_pct,
                        expected_value=thresholds['optimal_max'],
                        description=f"Reservas muy altas: {reserva_pct:.1f}% (riesgo de vertimientos)"
                    ))
                
                # Tendencia de reservas
                if reserva_pct < thresholds['warning_low']:
                    status.trends['reservas'] = TrendDirection.DOWN
                elif reserva_pct > thresholds['optimal_max']:
                    status.trends['reservas'] = TrendDirection.UP
                else:
                    status.trends['reservas'] = TrendDirection.STABLE
            
            # Aportes hídricos
            aporte_pct, aporte_gwh = self.hydrology_service.get_aportes_hidricos(hoy_str)
            
            if aporte_pct is not None:
                status.kpis['aportes_pct_vs_historico'] = round(aporte_pct, 2)
                
                # Detectar anomalías en aportes
                thresholds = THRESHOLDS['aportes_hidricos']
                if aporte_pct < thresholds['critical_low']:
                    status.anomalias.append(Anomalia(
                        sector="hidrologia",
                        metric_name="aportes_hidricos",
                        severity=SeverityLevel.CRITICAL,
                        current_value=aporte_pct,
                        expected_value=100.0,
                        description=f"Aportes hídricos muy bajos: {aporte_pct:.1f}% vs media histórica"
                    ))
                elif aporte_pct < thresholds['warning_low']:
                    status.anomalias.append(Anomalia(
                        sector="hidrologia",
                        metric_name="aportes_hidricos",
                        severity=SeverityLevel.WARNING,
                        current_value=aporte_pct,
                        expected_value=100.0,
                        description=f"Aportes por debajo de media histórica: {aporte_pct:.1f}%"
                    ))
                elif aporte_pct > thresholds['critical_high']:
                    status.anomalias.append(Anomalia(
                        sector="hidrologia",
                        metric_name="aportes_hidricos",
                        severity=SeverityLevel.WARNING,
                        current_value=aporte_pct,
                        expected_value=100.0,
                        description=f"Aportes muy altos: {aporte_pct:.1f}% vs media (posible período lluvioso)"
                    ))
            
            status.overall_status = self._calculate_sector_status(status.anomalias)
            status.summary = self._generate_hydrology_summary(status)
            
        except Exception as e:
            logger.error(f"Error en análisis hidrológico: {e}", exc_info=True)
            status.summary = f"Error analizando hidrología: {str(e)}"
            status.overall_status = SeverityLevel.INFO
        
        return status
    
    async def analyze_demand_sector(self) -> SectorStatus:
        """Análisis del sector de demanda y precios"""
        status = SectorStatus("demanda_precios")
        
        try:
            hoy = date.today()
            ayer = hoy - timedelta(days=1)
            semana_atras = hoy - timedelta(days=7)
            
            # Demanda desde metrics (DemaCome)
            df_demanda = await asyncio.to_thread(
                self.metrics_service.get_metric_series,
                'DemaCome',
                ayer.isoformat(),
                ayer.isoformat()
            )
            
            if not df_demanda.empty and 'Value' in df_demanda.columns:
                demanda_hoy = df_demanda['Value'].iloc[0]
                status.kpis['demanda_hoy_gwh'] = round(demanda_hoy, 2)
                
                # Comparar con semana anterior
                df_demanda_semana = await asyncio.to_thread(
                    self.metrics_service.get_metric_series,
                    'DemaCome',
                    semana_atras.isoformat(),
                    ayer.isoformat()
                )
                
                if not df_demanda_semana.empty and len(df_demanda_semana) > 1 and 'Value' in df_demanda_semana.columns:
                    demanda_promedio = df_demanda_semana['Value'].mean()
                    variacion_pct = ((demanda_hoy - demanda_promedio) / demanda_promedio) * 100
                    status.kpis['variacion_demanda_pct'] = round(variacion_pct, 2)
                    
                    if abs(variacion_pct) > THRESHOLDS['demanda_variacion']['critical_change']:
                        status.anomalias.append(Anomalia(
                            sector="demanda_precios",
                            metric_name="variacion_demanda",
                            severity=SeverityLevel.ALERT,
                            current_value=demanda_hoy,
                            expected_value=demanda_promedio,
                            description=f"Demanda con variación atípica: {variacion_pct:+.1f}% vs promedio"
                        ))
            
            # Precios de bolsa desde metrics (PrecBolsNaci)
            df_precios = await asyncio.to_thread(
                self.metrics_service.get_metric_series,
                'PrecBolsNaci',
                ayer.isoformat(),
                ayer.isoformat()
            )
            
            if not df_precios.empty and 'Value' in df_precios.columns:
                precio_hoy = df_precios['Value'].iloc[0]
                status.kpis['precio_bolsa_cop_kwh'] = round(precio_hoy, 2)
                
                # Analizar volatilidad de precios (últimos 30 días)
                hace_30_dias = hoy - timedelta(days=30)
                df_precios_mes = await asyncio.to_thread(
                    self.metrics_service.get_metric_series,
                    'PrecBolsNaci',
                    hace_30_dias.isoformat(),
                    ayer.isoformat()
                )
                
                if not df_precios_mes.empty and len(df_precios_mes) >= 7 and 'Value' in df_precios_mes.columns:
                    precio_promedio = df_precios_mes['Value'].mean()
                    precio_std = df_precios_mes['Value'].std()
                    
                    # Detectar anomalía si precio > μ + 2σ
                    if precio_hoy > (precio_promedio + 2 * precio_std):
                        status.anomalias.append(Anomalia(
                            sector="demanda_precios",
                            metric_name="precio_bolsa",
                            severity=SeverityLevel.WARNING,
                            current_value=precio_hoy,
                            expected_value=precio_promedio,
                            description=f"Precio de bolsa anormalmente alto: ${precio_hoy:.2f}/kWh (promedio: ${precio_promedio:.2f})"
                        ))
            
            status.overall_status = self._calculate_sector_status(status.anomalias)
            status.summary = self._generate_demand_summary(status)
            
        except Exception as e:
            logger.error(f"Error en análisis de demanda: {e}", exc_info=True)
            status.summary = f"Error analizando demanda: {str(e)}"
            status.overall_status = SeverityLevel.INFO
        
        return status
    
    async def analyze_losses_sector(self) -> SectorStatus:
        """Análisis del sector de pérdidas"""
        status = SectorStatus("perdidas")
        
        if not self.losses_service:
            status.summary = "Servicio de pérdidas no disponible"
            return status
        
        try:
            ayer = date.today() - timedelta(days=1)
            semana_atras = ayer - timedelta(days=7)
            
            ayer_str = ayer.strftime('%Y-%m-%d')
            semana_atras_str = semana_atras.strftime('%Y-%m-%d')
            
            # Obtener análisis de pérdidas
            analysis = await asyncio.to_thread(
                self.losses_service.get_losses_analysis,
                semana_atras_str, ayer_str
            )
            
            if analysis:
                # Extraer indicadores
                if 'indicators' in analysis and not analysis['indicators'].empty:
                    df_ind = analysis['indicators']
                    ultima_fila = df_ind.iloc[-1] if not df_ind.empty else None
                    
                    if ultima_fila is not None:
                        if 'perdidas_totales_pct' in df_ind.columns:
                            perdidas_pct = ultima_fila['perdidas_totales_pct']
                            status.kpis['perdidas_totales_pct'] = round(perdidas_pct, 2)
                            
                            # Detectar anomalías
                            thresholds = THRESHOLDS['perdidas']
                            if perdidas_pct > thresholds['critical_high']:
                                status.anomalias.append(Anomalia(
                                    sector="perdidas",
                                    metric_name="perdidas_totales",
                                    severity=SeverityLevel.CRITICAL,
                                    current_value=perdidas_pct,
                                    expected_value=thresholds['optimal_max'],
                                    description=f"Pérdidas críticas: {perdidas_pct:.2f}% (límite: {thresholds['critical_high']}%)"
                                ))
                            elif perdidas_pct > thresholds['warning_high']:
                                status.anomalias.append(Anomalia(
                                    sector="perdidas",
                                    metric_name="perdidas_totales",
                                    severity=SeverityLevel.WARNING,
                                    current_value=perdidas_pct,
                                    expected_value=thresholds['optimal_max'],
                                    description=f"Pérdidas elevadas: {perdidas_pct:.2f}%"
                                ))
            
            status.overall_status = self._calculate_sector_status(status.anomalias)
            status.summary = self._generate_losses_summary(status)
            
        except Exception as e:
            logger.error(f"Error en análisis de pérdidas: {e}", exc_info=True)
            status.summary = f"Error analizando pérdidas: {str(e)}"
            status.overall_status = SeverityLevel.INFO
        
        return status
    
    async def analyze_restrictions_sector(self) -> SectorStatus:
        """Análisis del sector de restricciones"""
        status = SectorStatus("restricciones")
        
        if not self.restrictions_service:
            status.summary = "Servicio de restricciones no disponible"
            return status
        
        try:
            hoy = date.today()
            ayer = hoy - timedelta(days=1)
            semana_actual = hoy - timedelta(days=7)
            semana_anterior = hoy - timedelta(days=14)
            
            ayer_str = ayer.strftime('%Y-%m-%d')
            semana_actual_str = semana_actual.strftime('%Y-%m-%d')
            semana_anterior_inicio = (hoy - timedelta(days=14)).strftime('%Y-%m-%d')
            semana_anterior_fin = (hoy - timedelta(days=8)).strftime('%Y-%m-%d')
            
            # Restricciones semana actual
            summary_actual = await asyncio.to_thread(
                self.restrictions_service.get_restrictions_summary,
                semana_actual_str, ayer_str
            )
            
            # Restricciones semana anterior
            summary_anterior = await asyncio.to_thread(
                self.restrictions_service.get_restrictions_summary,
                semana_anterior_inicio, semana_anterior_fin
            )
            
            if summary_actual is not None and not summary_actual.empty:
                total_actual = len(summary_actual)
                status.kpis['restricciones_semana_actual'] = total_actual
                
                if summary_anterior is not None and not summary_anterior.empty:
                    total_anterior = len(summary_anterior)
                    status.kpis['restricciones_semana_anterior'] = total_anterior
                    
                    if total_anterior > 0:
                        ratio = total_actual / total_anterior
                        thresholds = THRESHOLDS['restricciones_incremento']
                        
                        if ratio >= thresholds['critical_multiplier']:
                            status.anomalias.append(Anomalia(
                                sector="restricciones",
                                metric_name="incremento_restricciones",
                                severity=SeverityLevel.CRITICAL,
                                current_value=total_actual,
                                expected_value=total_anterior,
                                description=f"Restricciones se {ratio:.1f}x en la última semana ({total_actual} vs {total_anterior})"
                            ))
                        elif ratio >= thresholds['warning_multiplier']:
                            status.anomalias.append(Anomalia(
                                sector="restricciones",
                                metric_name="incremento_restricciones",
                                severity=SeverityLevel.WARNING,
                                current_value=total_actual,
                                expected_value=total_anterior,
                                description=f"Aumento significativo de restricciones: {total_actual} vs {total_anterior}"
                            ))
            
            status.overall_status = self._calculate_sector_status(status.anomalias)
            status.summary = self._generate_restrictions_summary(status)
            
        except Exception as e:
            logger.error(f"Error en análisis de restricciones: {e}", exc_info=True)
            status.summary = f"Error analizando restricciones: {str(e)}"
            status.overall_status = SeverityLevel.INFO
        
        return status
    
    # ─────────────────────────────────────────────────────────
    # UTILIDADES
    # ─────────────────────────────────────────────────────────
    
    def _calculate_sector_status(self, anomalias: List[Anomalia]) -> SeverityLevel:
        """Calcula el status general de un sector basado en sus anomalías"""
        if not anomalias:
            return SeverityLevel.NORMAL
        
        # Si hay al menos una crítica
        if any(a.severity == SeverityLevel.CRITICAL for a in anomalias):
            return SeverityLevel.CRITICAL
        
        # Si hay al menos una alerta
        if any(a.severity == SeverityLevel.ALERT for a in anomalias):
            return SeverityLevel.ALERT
        
        # Si hay warnings
        if any(a.severity == SeverityLevel.WARNING for a in anomalias):
            return SeverityLevel.WARNING
        
        return SeverityLevel.INFO
    
    def _calculate_overall_status(self, sectores: Dict[str, SectorStatus]) -> SeverityLevel:
        """Calcula el status general del sistema completo"""
        if not sectores:
            return SeverityLevel.UNKNOWN
        
        # Tomar el peor status de todos los sectores
        statuses = [s.overall_status for s in sectores.values()]
        
        if SeverityLevel.CRITICAL in statuses:
            return SeverityLevel.CRITICAL
        if SeverityLevel.ALERT in statuses:
            return SeverityLevel.ALERT
        if SeverityLevel.WARNING in statuses:
            return SeverityLevel.WARNING
        if SeverityLevel.INFO in statuses:
            return SeverityLevel.INFO
        
        return SeverityLevel.NORMAL
    
    def _count_by_severity(self, anomalias: List[Anomalia]) -> Dict[str, int]:
        """Cuenta anomalías por nivel de severidad"""
        counts = {level.value: 0 for level in SeverityLevel}
        for anomalia in anomalias:
            counts[anomalia.severity.value] += 1
        return counts
    
    def _generate_executive_summary(
        self, 
        sectores: Dict[str, SectorStatus],
        anomalias_criticas: List[Anomalia]
    ) -> str:
        """Genera resumen ejecutivo textual del estado del sector"""
        lines = []
        
        # Header según severidad
        estado_general = self._calculate_overall_status(sectores)
        
        if estado_general == SeverityLevel.CRITICAL:
            lines.append("🔴 ESTADO CRÍTICO DEL SECTOR ENERGÉTICO")
        elif estado_general == SeverityLevel.ALERT:
            lines.append("🟠 ALERTA EN EL SECTOR ENERGÉTICO")
        elif estado_general == SeverityLevel.WARNING:
            lines.append("🟡 ADVERTENCIAS EN EL SECTOR ENERGÉTICO")
        else:
            lines.append("🟢 SECTOR ENERGÉTICO OPERANDO NORMALMENTE")
        
        lines.append("")
        
        # Resumen por sector
        for sector_name, sector_status in sectores.items():
            icon = {
                SeverityLevel.CRITICAL: "🔴",
                SeverityLevel.ALERT: "🟠",
                SeverityLevel.WARNING: "🟡",
                SeverityLevel.INFO: "🔵",
                SeverityLevel.NORMAL: "🟢"
            }.get(sector_status.overall_status, "⚪")
            
            lines.append(f"{icon} {sector_name.upper()}: {sector_status.summary}")
        
        # Anomalías críticas
        if anomalias_criticas:
            lines.append("")
            lines.append(f"⚠️  {len(anomalias_criticas)} ANOMALÍAS REQUIEREN ATENCIÓN:")
            for anomalia in anomalias_criticas[:5]:  # Máximo 5
                lines.append(f"   • {anomalia.description}")
        
        return "\n".join(lines)
    
    def _generate_generation_summary(self, status: SectorStatus) -> str:
        """Genera resumen del sector generación"""
        parts = []
        if 'generacion_hoy_gwh' in status.kpis:
            parts.append(f"Generación: {status.kpis['generacion_hoy_gwh']:.1f} GWh")
        if 'variacion_vs_semana_pct' in status.kpis:
            var = status.kpis['variacion_vs_semana_pct']
            parts.append(f"({var:+.1f}% vs semana anterior)")
        if len(status.anomalias) > 0:
            parts.append(f"- {len(status.anomalias)} anomalías detectadas")
        return " ".join(parts) if parts else "Sin datos suficientes"
    
    def _generate_hydrology_summary(self, status: SectorStatus) -> str:
        """Genera resumen del sector hidrología"""
        parts = []
        if 'reservas_pct' in status.kpis:
            parts.append(f"Reservas: {status.kpis['reservas_pct']:.1f}%")
        if 'aportes_pct_vs_historico' in status.kpis:
            parts.append(f"Aportes: {status.kpis['aportes_pct_vs_historico']:.1f}% vs histórico")
        if len(status.anomalias) > 0:
            parts.append(f"- {len(status.anomalias)} anomalías")
        return " | ".join(parts) if parts else "Sin datos suficientes"
    
    def _generate_demand_summary(self, status: SectorStatus) -> str:
        """Genera resumen del sector demanda"""
        parts = []
        if 'demanda_hoy_gwh' in status.kpis:
            parts.append(f"Demanda: {status.kpis['demanda_hoy_gwh']:.1f} GWh")
        if 'precio_bolsa_cop_kwh' in status.kpis:
            parts.append(f"Precio bolsa: ${status.kpis['precio_bolsa_cop_kwh']:.2f}/kWh")
        return " | ".join(parts) if parts else "Sin datos suficientes"
    
    def _generate_losses_summary(self, status: SectorStatus) -> str:
        """Genera resumen del sector pérdidas"""
        if 'perdidas_totales_pct' in status.kpis:
            return f"Pérdidas totales: {status.kpis['perdidas_totales_pct']:.2f}%"
        return "Sin datos de pérdidas"
    
    def _generate_restrictions_summary(self, status: SectorStatus) -> str:
        """Genera resumen del sector restricciones"""
        if 'restricciones_semana_actual' in status.kpis:
            return f"{status.kpis['restricciones_semana_actual']} restricciones esta semana"
        return "Sin datos de restricciones"
