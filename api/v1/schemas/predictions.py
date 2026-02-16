"""
Esquemas Pydantic para endpoints de predicciones ML

Define modelos de datos para:
- Respuestas de predicciones con intervalos de confianza
- Métricas de evaluación de modelos

Sigue las convenciones de docs/api_data_conventions.md

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

from typing import List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import pandas as pd

from api.v1.schemas.common import PredictionPoint


class PredictionResponse(BaseModel):
    """
    Respuesta de predicción ML
    
    Sigue el formato definido en docs/api_data_conventions.md
    
    Attributes:
        metric_id: Código de métrica XM
        entity: Entidad o agrupación
        unit: Unidad de medida
        model: Modelo ML utilizado (prophet, arima, ensemble)
        horizon_days: Días de proyección
        generated_at: Timestamp de generación (ISO 8601)
        data: Array de puntos de predicción con intervalos de confianza
    """
    metric_id: str = Field(..., description="Código de métrica XM")
    entity: str = Field(..., description="Entidad o agrupación")
    unit: str = Field(..., description="Unidad de medida")
    model: Literal["prophet", "arima", "ensemble"] = Field(
        ...,
        description="Modelo ML utilizado"
    )
    horizon_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Días de proyección (1-365)"
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp de generación en ISO 8601"
    )
    data: List[PredictionPoint] = Field(
        ...,
        description="Array de predicciones con intervalos de confianza"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "metric_id": "Gene",
                "entity": "Sistema",
                "unit": "GWh",
                "model": "prophet",
                "horizon_days": 30,
                "generated_at": "2026-02-03T14:30:00Z",
                "data": [
                    {
                        "date": "2026-03-01",
                        "value": 245.78,
                        "lower": 230.12,
                        "upper": 261.44,
                        "confidence": 0.95
                    }
                ]
            }
        }
    
    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        metric_id: str,
        entity: str,
        model_type: Literal["prophet", "arima", "ensemble"],
        horizon_days: int,
        unit: str = "GWh",
        confidence_level: float = 0.95
    ) -> "PredictionResponse":
        """
        Crea una respuesta desde un DataFrame de predicciones
        
        Args:
            df: DataFrame con columnas Date, yhat, yhat_lower, yhat_upper (Prophet)
                o Date, Value, Lower, Upper (formato genérico)
            metric_id: Código de métrica XM
            entity: Entidad o agrupación
            model_type: Tipo de modelo ML usado
            horizon_days: Días de proyección
            unit: Unidad de medida
            confidence_level: Nivel de confianza (default: 0.95)
            
        Returns:
            PredictionResponse con datos del DataFrame
        """
        # Normalizar nombres de columnas según el modelo
        df_normalized = df.copy()
        
        # Prophet usa 'ds', 'yhat', 'yhat_lower', 'yhat_upper'
        if 'ds' in df_normalized.columns:
            df_normalized = df_normalized.rename(columns={
                'ds': 'Date',
                'yhat': 'Value',
                'yhat_lower': 'Lower',
                'yhat_upper': 'Upper'
            })
        
        # Convertir DataFrame a lista de puntos de predicción
        prediction_points = []
        
        for _, row in df_normalized.iterrows():
            point = PredictionPoint(
                date=row["Date"] if isinstance(row["Date"], pd.Timestamp) else pd.to_datetime(row["Date"]),
                value=float(row["Value"]) if pd.notna(row["Value"]) else 0.0,
                lower=float(row.get("Lower", row["Value"] * 0.9)) if pd.notna(row.get("Lower")) else row["Value"] * 0.9,
                upper=float(row.get("Upper", row["Value"] * 1.1)) if pd.notna(row.get("Upper")) else row["Value"] * 1.1,
                confidence=confidence_level
            )
            prediction_points.append(point)
        
        return cls(
            metric_id=metric_id,
            entity=entity,
            unit=unit,
            model=model_type,
            horizon_days=horizon_days,
            generated_at=datetime.now(),
            data=prediction_points
        )


class ModelMetrics(BaseModel):
    """
    Métricas de evaluación de un modelo ML
    
    Attributes:
        mae: Error absoluto medio
        rmse: Raíz del error cuadrático medio
        mape: Error porcentual absoluto medio
        r2: Coeficiente de determinación R²
    """
    mae: Optional[float] = Field(None, description="Error Absoluto Medio (MAE)")
    rmse: Optional[float] = Field(None, description="Raíz del Error Cuadrático Medio (RMSE)")
    mape: Optional[float] = Field(None, description="Error Porcentual Absoluto Medio (MAPE)")
    r2: Optional[float] = Field(None, description="Coeficiente de determinación R²")
    
    class Config:
        json_schema_extra = {
            "example": {
                "mae": 12.34,
                "rmse": 15.67,
                "mape": 5.2,
                "r2": 0.92
            }
        }
