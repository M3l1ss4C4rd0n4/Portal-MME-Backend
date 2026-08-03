"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                   REPOSITORY INTERFACES (PORTS)                               ║
║                                                                               ║
║  Interfaces para acceso a datos - Arquitectura Hexagonal                     ║
║  Domain no depende de Infrastructure, sino de estas abstracciones            ║
║                                                                               ║
║  Implementaciones concretas: infrastructure/database/repositories/           ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import date
import pandas as pd


class IMetricsRepository(ABC):
    """
    Interface para acceso a métricas energéticas.
    Define el contrato que debe cumplir cualquier implementación.
    """
    
    @abstractmethod
    def get_total_records(self) -> int:
        """Obtiene el total de registros en la tabla de métricas"""
    
    @abstractmethod
    def get_latest_date(self) -> Optional[str]:
        """Obtiene la fecha más reciente disponible"""
    
    @abstractmethod
    def get_metric_data(
        self,
        metric_id: str,
        start_date: str,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        unit: Optional[str] = None,
        entity: Optional[str] = None
    ) -> pd.DataFrame:
        """Obtiene serie temporal de una métrica específica"""
    
    @abstractmethod
    def get_metrics_history_by_list(
        self,
        metrics_list: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """Obtiene histórico para una lista de métricas"""
    
    @abstractmethod
    def list_metrics(self) -> List[Dict[str, Any]]:
        """Lista todas las métricas disponibles"""
    
    @abstractmethod
    def get_metrics_summary(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Obtiene resumen de métricas en un rango de fechas"""


class ICommercialRepository(ABC):
    """Interface para acceso a datos de comercialización eléctrica"""
    
    @abstractmethod
    def fetch_date_range(self, metric_code: str) -> Optional[tuple]:
        """Obtiene rango min/max de fechas disponible para una métrica"""
    
    @abstractmethod
    def fetch_commercial_metrics(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente_comprador: Optional[str] = None
    ) -> pd.DataFrame:
        """Consulta métricas de comercialización"""
    
    @abstractmethod
    def get_agents(self) -> List[str]:
        """Obtiene lista de agentes comerciales"""
    
    @abstractmethod
    def get_available_metrics(self) -> List[str]:
        """Obtiene lista de métricas de comercialización disponibles"""

    @abstractmethod
    def get_available_buyers(self) -> List[Dict[str, str]]:
        """Obtiene lista de compradores disponibles"""


class IDistributionRepository(ABC):
    """Interface para acceso a datos de distribución eléctrica"""
    
    @abstractmethod
    def fetch_date_range(self, metric_code: str) -> Optional[tuple]:
        """Obtiene rango min/max de fechas disponible"""
    
    @abstractmethod
    def fetch_distribution_metrics(
        self,
        metric_code: str,
        start_date: date,
        end_date: date,
        agente: Optional[str] = None,
        entities: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Consulta métricas de distribución"""
    
    @abstractmethod
    def fetch_agent_statistics(self) -> pd.DataFrame:
        """Obtiene estadísticas de agentes de distribución"""

    @abstractmethod
    def fetch_available_agents(self) -> List[Dict[str, str]]:
        """Obtiene lista de agentes distribuidores disponibles"""

    # db_manager is provided by concrete implementations via __init__
    db_manager: Any
    
    @abstractmethod
    def get_distributors(self) -> List[str]:
        """Obtiene lista de distribuidores"""
    
    @abstractmethod
    def get_available_metrics(self) -> List[str]:
        """Obtiene lista de métricas de distribución disponibles"""


class ITransmissionRepository(ABC):
    """Interface para acceso a datos de líneas de transmisión"""
    
    @abstractmethod
    def get_all_lines(self) -> pd.DataFrame:
        """Obtiene todas las líneas de transmisión"""
    
    @abstractmethod
    def get_lines_by_region(self, region: str) -> pd.DataFrame:
        """Obtiene líneas de transmisión por región"""
    
    @abstractmethod
    def get_lines_by_voltage(self, voltage: str) -> pd.DataFrame:
        """Obtiene líneas de transmisión por nivel de tensión"""
    
    @abstractmethod
    def get_total_count(self) -> int:
        """Obtiene el número total de líneas"""
    
    @abstractmethod
    def get_latest_update(self) -> Optional[str]:
        """Obtiene la fecha de última actualización"""


class IPredictionsRepository(ABC):
    """Interface para acceso a predicciones de machine learning"""
    
    @abstractmethod
    def save_predictions(
        self,
        metric: str,
        model_name: str,
        predictions_df: pd.DataFrame
    ) -> int:
        """Guarda predicciones generadas por un modelo"""
    
    @abstractmethod
    def get_predictions(
        self,
        metric: str,
        model_name: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """Obtiene predicciones almacenadas"""
    
    @abstractmethod
    def get_available_metrics(self) -> List[str]:
        """Lista métricas con predicciones disponibles"""
    
    @abstractmethod
    def get_available_models(self, metric: str) -> List[str]:
        """Lista modelos disponibles para una métrica"""
    
    @abstractmethod
    def delete_predictions(
        self,
        metric: str,
        model_name: Optional[str] = None
    ) -> int:
        """Elimina predicciones (útil para reentrenamiento)"""


class IGeografiaRepository(ABC):
    """
    Interface para la dimensión de geografía DANE (esquema ontologia).
    Capa semántica de solo lectura — no escribe en tablas de negocio.
    """

    @abstractmethod
    def listar_departamentos(self) -> List[Dict[str, Any]]:
        """Lista departamentos DANE presentes en ontologia.dim_geografia"""

    @abstractmethod
    def resumen_departamento(self, codigo_dane_departamento: str) -> Optional[Dict[str, Any]]:
        """Cruce multi-dominio para un departamento (ontologia.mv_resumen_departamento)"""

    @abstractmethod
    def resolver_alias(
        self, esquema: str, tabla: str, columna: str, valor: str
    ) -> List[Dict[str, Any]]:
        """Resuelve un valor de texto libre de un esquema de negocio a geografia_id(s)"""

    @abstractmethod
    def alias_pendientes(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Lista valores de geografia_alias aún sin resolver (backlog de curación)"""

    @abstractmethod
    def contar_alias_pendientes(self) -> int:
        """Total de valores de geografia_alias sin resolver (sin límite)"""

    @abstractmethod
    def historial_lineage(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Corridas recientes del pipeline de ontología (ontologia.etl_lineage)"""


class IProyectoRepository(ABC):
    """
    Interface para la dimensión de proyectos (esquema ontologia) — Fase 7.
    Proyecto como objeto de primera clase, independiente por programa
    (contratos_or, colombia_solar, fenoge no comparten identidad de proyecto).
    """

    @abstractmethod
    def listar_proyectos(self, programa: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista proyectos, opcionalmente filtrados por programa"""

    @abstractmethod
    def obtener_por_id(self, proyecto_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene un proyecto por su proyecto_id, o None si no existe"""

    @abstractmethod
    def alias_de_proyecto(self, proyecto_id: int) -> List[Dict[str, Any]]:
        """Filas de proyecto_alias resueltas para este proyecto (en qué esquema/tabla aparece)"""


class IEmpresaRepository(ABC):
    """
    Interface para la dimensión de empresas/prestadores/ejecutores (esquema ontologia).
    """

    @abstractmethod
    def buscar_empresas(
        self, nit: Optional[str] = None, nombre: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Busca empresas por NIT exacto o nombre (ILIKE)"""

    @abstractmethod
    def alias_pendientes(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Lista valores de empresa_alias sin resolver o con match fuzzy sin revisar"""

    @abstractmethod
    def contar_alias_pendientes(self) -> int:
        """Total de valores de empresa_alias sin resolver o con match fuzzy sin revisar (sin límite)"""

    @abstractmethod
    def obtener_por_id(self, empresa_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene una empresa por su empresa_id, o None si no existe"""

    @abstractmethod
    def contratos_supervision_por_nit(
        self, nit_normalizado: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Contratos de supervision.contratos donde esta empresa es ejecutor (match por NIT, alta confianza)"""

    @abstractmethod
    def contar_contratos_supervision_por_nit(self, nit_normalizado: str) -> int:
        """Total de contratos de esta empresa (sin límite) — para mostrar 'mostrando N de TOTAL'"""

    @abstractmethod
    def alias_resueltos_de_empresa(self, empresa_id: int) -> List[Dict[str, Any]]:
        """Todas las filas de empresa_alias resueltas (no sin_resolver) para esta empresa, con su método/confianza"""

    @abstractmethod
    def proyectos_de_empresa(self, empresa_id: int) -> List[Dict[str, Any]]:
        """Proyectos de contratos_or donde esta empresa es ejecutor (2do salto del grafo)"""

    @abstractmethod
    def empresas_relacionadas_por_geografia(
        self, codigos_dane_departamento: List[str], excluir_empresa_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Otras empresas con contratos en los mismos departamentos (patrón de concentración de contratistas)"""


class ISemanticSearchRepository(ABC):
    """
    Interface para búsqueda semántica (RAG) sobre texto libre de contratos
    (objeto del contrato, observaciones jurídicas/técnicas) — ontologia.contratos_texto_embeddings.
    """

    @abstractmethod
    def buscar_similar(
        self, embedding: List[float], top_k: int = 5, umbral_similitud: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Busca los textos más semánticamente similares a un embedding de consulta"""
