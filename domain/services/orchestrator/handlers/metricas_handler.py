"""
Mixin: Métricas handlers (Generación, Hidrología, Demanda, Precio, General).
"""
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error

logger = logging.getLogger(__name__)


class MetricasHandlerMixin:
    """Mixin para handlers de métricas sectoriales."""

    async def _handle_generacion_electrica(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de generación eléctrica"""
        data = {}
        errors = []

        # Extraer parámetros
        fecha_str = parameters.get('fecha')
        fecha_inicio_str = parameters.get('fecha_inicio')
        fecha_fin_str = parameters.get('fecha_fin')
        recurso = parameters.get('recurso')

        # Determinar fechas
        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            start_date = fecha
            end_date = fecha
        elif fecha_inicio_str and fecha_fin_str:
            start_date = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=7)

        try:
            df_system = await asyncio.wait_for(
                asyncio.to_thread(
                    self.generation_service.get_daily_generation_system,
                    start_date,
                    end_date
                ),
                timeout=self.SERVICE_TIMEOUT
            )

            if not df_system.empty:
                total = df_system['valor_gwh'].sum()
                promedio = df_system['valor_gwh'].mean()

                data['generacion_total_gwh'] = round(total, 2)
                data['generacion_promedio_gwh'] = round(promedio, 2)
                data['periodo'] = {
                    'inicio': start_date.isoformat(),
                    'fin': end_date.isoformat()
                }

                if fecha_str:
                    try:
                        df_resources = await asyncio.wait_for(
                            asyncio.to_thread(
                                self.generation_service.get_generation_by_source,
                                start_date,
                                end_date
                            ),
                            timeout=self.SERVICE_TIMEOUT
                        )

                        if not df_resources.empty:
                            por_recurso = {}
                            for fuente in df_resources['fuente'].unique():
                                df_fuente = df_resources[df_resources['fuente'] == fuente]
                                por_recurso[fuente.lower()] = round(df_fuente['valor_gwh'].sum(), 2)

                            data['por_recurso'] = por_recurso
                    except Exception as e:
                        logger.warning(f"Error obteniendo recursos: {e}")
                        errors.append(ErrorDetail(
                            code="PARTIAL_DATA",
                            message="No se pudo obtener el detalle por recurso"
                        ))
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No hay datos de generación para el periodo solicitado"
                ))

        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El servicio de generación tardó demasiado en responder"
            ))
        except Exception as e:
            logger.error(f"Error en handle_generacion_electrica: {e}")
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar datos de generación"
            ))

        return data, errors

    @handle_service_error
    async def _handle_hidrologia(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de hidrología/embalses"""
        data = {}
        errors = []

        fecha_str = parameters.get('fecha')
        embalse = parameters.get('embalse')

        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        else:
            fecha = date.today()

        try:
            nivel_pct, energia_gwh, fecha_dato_emb = await asyncio.wait_for(
                asyncio.to_thread(
                    self.hydrology_service.get_reservas_hidricas,
                    fecha.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )

            if nivel_pct is not None and energia_gwh is not None:
                data['nivel_promedio_sistema'] = round(nivel_pct, 2)
                data['energia_embalsada_gwh'] = round(energia_gwh, 2)
                data['fecha'] = fecha_dato_emb or fecha.isoformat()

                if embalse:
                    errors.append(ErrorDetail(
                        code="NOT_IMPLEMENTED",
                        message="Consulta por embalse específico no implementada en esta versión"
                    ))
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No hay datos de embalses para la fecha solicitada"
                ))

        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El servicio de hidrología tardó demasiado en responder"
            ))
        except Exception as e:
            logger.error(f"Error en handle_hidrologia: {e}")
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar datos de embalses"
            ))

        return data, errors

    @handle_service_error
    async def _handle_demanda_sistema(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de demanda del sistema"""
        data = {}
        errors = []

        fecha_str = parameters.get('fecha')
        fecha_inicio_str = parameters.get('fecha_inicio')
        fecha_fin_str = parameters.get('fecha_fin')

        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            start_date = fecha
            end_date = fecha
        elif fecha_inicio_str and fecha_fin_str:
            start_date = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=7)

        try:
            df_demand = await asyncio.wait_for(
                asyncio.to_thread(
                    self.metrics_service.get_metric_series,
                    'DemaCome',
                    start_date.isoformat(),
                    end_date.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )

            if not df_demand.empty and 'Value' in df_demand.columns:
                total = df_demand['Value'].sum()
                promedio = df_demand['Value'].mean()
                maximo = df_demand['Value'].max()

                data['demanda_total_gwh'] = round(total, 2)
                data['demanda_promedio_gwh'] = round(promedio, 2)
                data['demanda_maxima_gwh'] = round(maximo, 2)
                data['periodo'] = {
                    'inicio': start_date.isoformat(),
                    'fin': end_date.isoformat()
                }
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No hay datos de demanda para el periodo solicitado"
                ))

        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El servicio de demanda tardó demasiado en responder"
            ))
        except Exception as e:
            logger.error(f"Error en handle_demanda_sistema: {e}")
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar datos de demanda"
            ))

        return data, errors

    @handle_service_error
    async def _handle_precio_bolsa(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """Handler para intent de precios de bolsa"""
        data = {}
        errors = []

        fecha_str = parameters.get('fecha')
        fecha_inicio_str = parameters.get('fecha_inicio')
        fecha_fin_str = parameters.get('fecha_fin')

        if fecha_str:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            start_date = fecha
            end_date = fecha
        elif fecha_inicio_str and fecha_fin_str:
            start_date = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=7)

        try:
            df_prices = await asyncio.wait_for(
                asyncio.to_thread(
                    self.metrics_service.get_metric_series,
                    'PrecBolsNaci',
                    start_date.isoformat(),
                    end_date.isoformat()
                ),
                timeout=self.SERVICE_TIMEOUT
            )

            if not df_prices.empty and 'Value' in df_prices.columns:
                promedio = df_prices['Value'].mean()
                maximo = df_prices['Value'].max()
                minimo = df_prices['Value'].min()

                data['precio_promedio_cop_kwh'] = round(promedio, 2)
                data['precio_maximo_cop_kwh'] = round(maximo, 2)
                data['precio_minimo_cop_kwh'] = round(minimo, 2)
                data['periodo'] = {
                    'inicio': start_date.isoformat(),
                    'fin': end_date.isoformat()
                }
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No hay datos de precios para el periodo solicitado"
                ))

        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El servicio de precios tardó demasiado en responder"
            ))
        except Exception as e:
            logger.error(f"Error en handle_precio_bolsa: {e}")
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar datos de precios"
            ))

        return data, errors

    @handle_service_error
    async def _handle_metricas_generales(
        self,
        parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler para métricas generales/resumen del sistema.
        Usa el análisis inteligente completo.
        """
        data = {}
        errors = []

        try:
            from domain.services.intelligent_analysis_service import SeverityLevel
            result = await asyncio.wait_for(
                self.intelligent_analysis.analyze_complete_sector(),
                timeout=self.TOTAL_TIMEOUT - 5
            )

            if result:
                data['estado_general'] = result['estado_general']
                data['resumen'] = result['resumen_ejecutivo']

                data['sectores'] = {}
                for sector_name, sector_status in result['sectores'].items():
                    data['sectores'][sector_name] = {
                        'estado': sector_status.get('estado', 'normal'),
                        'kpis_principales': sector_status.get('kpis', {})
                    }

                critical_anomalies = []
                for a in result.get('anomalias_criticas', []):
                    sev = a.get('severidad', a.get('severity', 'INFO'))
                    if isinstance(sev, str):
                        sev_name = sev.upper()
                    elif isinstance(sev, SeverityLevel):
                        sev_name = sev.name
                    else:
                        continue

                    if sev_name in ['CRITICAL', 'ALERT']:
                        critical_anomalies.append(a)

                data['alertas'] = critical_anomalies[:5] if critical_anomalies else []
                data['fecha'] = datetime.utcnow().isoformat()

                logger.info(
                    f"[METRICAS_GENERALES] Estado={data['estado_general']} | "
                    f"Alertas={len(critical_anomalies)}"
                )
            else:
                errors.append(ErrorDetail(
                    code="NO_DATA",
                    message="No se pudieron obtener las métricas generales"
                ))

        except asyncio.TimeoutError:
            errors.append(ErrorDetail(
                code="TIMEOUT",
                message="El análisis de métricas tardó demasiado en ejecutarse"
            ))
        except Exception as e:
            logger.error(f"Error en _handle_metricas_generales: {e}", exc_info=True)
            errors.append(ErrorDetail(
                code="SERVICE_ERROR",
                message="Error al consultar métricas generales"
            ))

        return data, errors
