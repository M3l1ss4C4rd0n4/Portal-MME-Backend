"""
Schemas Pydantic para el Motor de Simulación CREG

Define modelos de request/response para los endpoints de simulación:
- ParametrosSimulacion: Request body para POST /simulation/run
- SimulacionResponse: Response con resultado completo
- BaselineResponse: Información del baseline actual
- EscenarioResponse: Escenario predefinido

FASE 6 — Motor de Simulación CREG
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ParametrosSimulacion(BaseModel):
    """Request body para ejecutar una simulación."""

    precio_bolsa_factor: float = Field(
        1.0, ge=0.5, le=3.0,
        description="Multiplicador sobre PrecBolsNaci (1.0 = sin cambio)"
    )
    factor_perdidas: float = Field(
        0.085, ge=0.05, le=0.20,
        description="Factor pérdidas distribución SDL (CREG default 8.5%)"
    )
    cargo_restricciones_kw: Optional[float] = Field(
        None, ge=0, le=50,
        description="Cargo restricciones COP/kWh (None = usar valor actual)"
    )
    tasa_transmision: float = Field(
        1.0, ge=0.5, le=1.5,
        description="Multiplicador sobre componente transmisión"
    )
    tasa_comercializacion: float = Field(
        1.0, ge=0.5, le=1.5,
        description="Multiplicador sobre componente comercialización"
    )
    demanda_factor: float = Field(
        1.0, ge=0.7, le=1.3,
        description="Multiplicador sobre demanda"
    )
    nombre: str = Field(
        "Escenario personalizado",
        max_length=200,
        description="Nombre descriptivo del escenario"
    )
    tipo: str = Field(
        "PERSONALIZADO",
        description="Tipo de escenario"
    )
    guardar: bool = Field(
        False,
        description="Si True, persiste el resultado en simulation_results"
    )


class ImpactoEstrato3(BaseModel):
    """Impacto en factura hogar estrato 3."""
    consumo_kwh: int
    factura_base_cop: float
    factura_sim_cop: float
    diferencia_cop_mes: float
    diferencia_pct: float
    nota: str


class SimulacionResponse(BaseModel):
    """Response completa de una simulación."""
    cu_simulado: float
    cu_baseline: float
    delta_cop_kwh: float
    delta_pct: float
    componentes_simulados: Dict[str, float]
    componentes_baseline: Dict[str, float]
    impacto_estrato3: Dict[str, Any]
    serie_simulada: List[Dict[str, Any]]
    sensibilidad: Dict[str, Any]
    parametros_usados: Dict[str, Any]
    tipo_escenario: str
    advertencias: List[str]
    nota_legal: str


class BaselineResponse(BaseModel):
    """Información del baseline actual."""
    cu_base: float
    precio_bolsa_base: float
    desglose_componentes: Dict[str, float]
    desglose_porcentual: Dict[str, float]
    p_nt_validado: float
    parametros_creg_actuales: Dict[str, Any]


class EscenarioResponse(BaseModel):
    """Escenario predefinido."""
    id: str
    nombre: str
    descripcion: str
    tipo: str
    parametros: Dict[str, Any]
    contexto_historico: str


class HistorialItem(BaseModel):
    """Ítem del historial de simulaciones."""
    id: int
    nombre: str
    tipo: str
    impacto_pct: float
    fecha: str
    parametros: Dict[str, Any]
    cu_simulado: Optional[float] = None
    cu_baseline: Optional[float] = None
