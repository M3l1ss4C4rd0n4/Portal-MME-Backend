"""
Servicio de dominio extendido para predicciones ML
Soporta Prophet, ARIMA y modelos ensemble
"""

from typing import Optional, Literal, Dict, Any
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from pathlib import Path

from infrastructure.database.repositories.predictions_repository import PredictionsRepository
from infrastructure.database.repositories.metrics_repository import MetricsRepository
from core.config import settings

# Importaciones de ML (manejo lazy para evitar errores si no están instalados)
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    Prophet = None

try:
    from pmdarima import auto_arima
    ARIMA_AVAILABLE = True
except ImportError:
    ARIMA_AVAILABLE = False
    auto_arima = None

logger = logging.getLogger(__name__)


class PredictionsService:
    """
    Servicio de predicciones con Machine Learning
    
    Funcionalidades:
    - Predicciones usando Prophet (Facebook)
    - Predicciones usando ARIMA (auto-tuning)
    - Modelos ensemble (combinación de múltiples modelos)
    - Gestión de intervalos de confianza
    - Almacenamiento de predicciones en BD
    """
    
    def __init__(
        self, 
        repo: Optional[PredictionsRepository] = None,
        metrics_repo: Optional[MetricsRepository] = None
    ):
        self.repo = repo or PredictionsRepository()
        self.metrics_repo = metrics_repo or MetricsRepository()
        self.models_dir = Path(settings.BASE_DIR) / "infrastructure" / "ml" / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
    
    # ═══════════════════════════════════════════════════════════
    # MÉTODOS LEGACY (compatibilidad con código existente)
    # ═══════════════════════════════════════════════════════════
    
    def get_latest_prediction_date(self) -> Optional[str]:
        """Fecha más reciente de predicciones"""
        return self.repo.get_latest_prediction_date()
    
    def count_predictions(self) -> int:
        """Total de predicciones"""
        return self.repo.count_predictions()
    
    def get_predictions(
        self,
        metric_id: str,
        start_date: str,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """Obtiene predicciones almacenadas para una métrica"""
        return self.repo.get_predictions(metric_id, start_date, end_date)
    
    # ═══════════════════════════════════════════════════════════
    # NUEVOS MÉTODOS DE PREDICCIÓN ML
    # ═══════════════════════════════════════════════════════════
    
    def forecast_metric(
        self,
        metric_id: str,
        entity: str,
        horizon_days: int = 30,
        model_type: Literal["prophet", "arima", "ensemble"] = "prophet",
        confidence_level: float = 0.95,
    ) -> pd.DataFrame:
        """
        Genera predicciones para una métrica específica.
        
        Args:
            metric_id: Código de métrica XM (ej: 'Gene', 'DemaReal')
            entity: Entidad (ej: 'Sistema', 'Recurso')
            horizon_days: Días a predecir hacia el futuro
            model_type: Tipo de modelo ('prophet', 'arima', 'ensemble')
            confidence_level: Nivel de confianza para intervalos (0.80, 0.90, 0.95)
        
        Returns:
            DataFrame con columnas: date, value, lower, upper, model
        
        Raises:
            ValueError: Si no hay suficientes datos históricos
            RuntimeError: Si el modelo no está disponible
        """
        logger.info(f"[PredictionsService] Iniciando predicción para {metric_id}/{entity} ({horizon_days} días, modelo={model_type})")
        
        # 1. Obtener datos históricos
        historical_df = self._get_historical_data(metric_id, entity)
        
        # 2. Validar datos suficientes
        if len(historical_df) < 30:
            raise ValueError(
                f"Datos insuficientes para predicción: {len(historical_df)} registros. "
                f"Se requieren al menos 30 días de histórico."
            )
        
        # 3. Ejecutar predicción según modelo
        if model_type == "prophet":
            if not PROPHET_AVAILABLE:
                raise RuntimeError("Prophet no está instalado. Ejecutar: pip install prophet")
            prediction_df = self._forecast_prophet(historical_df, horizon_days, confidence_level)
        
        elif model_type == "arima":
            if not ARIMA_AVAILABLE:
                raise RuntimeError("pmdarima no está instalado. Ejecutar: pip install pmdarima")
            prediction_df = self._forecast_arima(historical_df, horizon_days, confidence_level)
        
        elif model_type == "ensemble":
            prediction_df = self._forecast_ensemble(historical_df, horizon_days, confidence_level)
        
        else:
            raise ValueError(f"Tipo de modelo no soportado: {model_type}")
        
        # 4. Añadir metadata
        prediction_df['metric_id'] = metric_id
        prediction_df['entity'] = entity
        prediction_df['model'] = model_type
        
        logger.info(f"[PredictionsService] Predicción completada: {len(prediction_df)} días generados")
        
        return prediction_df
    
    def _get_historical_data(self, metric_id: str, entity: str, days_back: int = 365) -> pd.DataFrame:
        """
        Obtiene datos históricos de la métrica para entrenamiento.
        
        Args:
            metric_id: Código de métrica
            entity: Entidad
            days_back: Días hacia atrás a obtener
        
        Returns:
            DataFrame con columnas: date, value
        """
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        # Obtener desde repositorio
        df = self.metrics_repo.get_metric_data_by_entity(
            metric_id, 
            entity, 
            start_date, 
            end_date
        )
        
        if df is None or df.empty:
            raise ValueError(f"No se encontraron datos históricos para {metric_id}/{entity}")
        
        # Normalizar columnas
        df = df.rename(columns={
            'fecha': 'date',
            'Date': 'date',
            'valor_gwh': 'value',
            'valor': 'value',
            'Value': 'value'
        })
        
        # Asegurar tipos correctos
        df['date'] = pd.to_datetime(df['date'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        
        # Eliminar nulos y duplicados
        df = df.dropna(subset=['date', 'value'])
        df = df.drop_duplicates(subset=['date'], keep='last')
        df = df.sort_values('date')
        
        return df[['date', 'value']].reset_index(drop=True)
    
    def _forecast_prophet(
        self, 
        historical_df: pd.DataFrame, 
        horizon_days: int, 
        confidence_level: float
    ) -> pd.DataFrame:
        """
        Predicción usando Prophet (Facebook).
        
        Args:
            historical_df: DataFrame con 'date' y 'value'
            horizon_days: Días a predecir
            confidence_level: Nivel de confianza (0.80, 0.90, 0.95)
        
        Returns:
            DataFrame con: date, value, lower, upper
        """
        logger.info("[Prophet] Entrenando modelo...")
        
        # Preparar datos para Prophet (requiere columnas 'ds' y 'y')
        prophet_df = historical_df.rename(columns={'date': 'ds', 'value': 'y'})
        
        # Configurar modelo
        model = Prophet(
            interval_width=confidence_level,
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=True,
            changepoint_prior_scale=0.05,  # Regularización
        )
        
        # Entrenar
        model.fit(prophet_df)
        
        # Crear dataframe futuro
        future = model.make_future_dataframe(periods=horizon_days, freq='D')
        
        # Predecir
        forecast = model.predict(future)
        
        # Extraer solo predicciones futuras
        last_date = historical_df['date'].max()
        forecast_future = forecast[forecast['ds'] > last_date].copy()
        
        # Formato estándar
        result = pd.DataFrame({
            'date': forecast_future['ds'],
            'value': forecast_future['yhat'],
            'lower': forecast_future['yhat_lower'],
            'upper': forecast_future['yhat_upper'],
        })
        
        logger.info(f"[Prophet] Predicción completada: {len(result)} días")
        return result.reset_index(drop=True)
    
    def _forecast_arima(
        self, 
        historical_df: pd.DataFrame, 
        horizon_days: int, 
        confidence_level: float
    ) -> pd.DataFrame:
        """
        Predicción usando ARIMA con auto-tuning.
        
        Args:
            historical_df: DataFrame con 'date' y 'value'
            horizon_days: Días a predecir
            confidence_level: Nivel de confianza
        
        Returns:
            DataFrame con: date, value, lower, upper
        """
        logger.info("[ARIMA] Ajustando modelo (auto-tuning)...")
        
        # Extraer serie temporal
        y = historical_df['value'].values
        
        # Auto-ARIMA para encontrar mejor modelo
        model = auto_arima(
            y,
            start_p=1, start_q=1,
            max_p=5, max_q=5,
            seasonal=True,
            m=7,  # Estacionalidad semanal
            stepwise=True,
            suppress_warnings=True,
            error_action='ignore',
            trace=False
        )
        
        logger.info(f"[ARIMA] Modelo seleccionado: {model.order}")
        
        # Predecir
        forecast, conf_int = model.predict(
            n_periods=horizon_days, 
            return_conf_int=True,
            alpha=1 - confidence_level
        )
        
        # Generar fechas futuras
        last_date = historical_df['date'].max()
        future_dates = pd.date_range(
            start=last_date + timedelta(days=1),
            periods=horizon_days,
            freq='D'
        )
        
        # Formato estándar
        result = pd.DataFrame({
            'date': future_dates,
            'value': forecast,
            'lower': conf_int[:, 0],
            'upper': conf_int[:, 1],
        })
        
        logger.info(f"[ARIMA] Predicción completada: {len(result)} días")
        return result.reset_index(drop=True)
    
    def _forecast_ensemble(
        self, 
        historical_df: pd.DataFrame, 
        horizon_days: int, 
        confidence_level: float
    ) -> pd.DataFrame:
        """
        Predicción ensemble (promedio de Prophet + ARIMA).
        
        Args:
            historical_df: DataFrame con 'date' y 'value'
            horizon_days: Días a predecir
            confidence_level: Nivel de confianza
        
        Returns:
            DataFrame con: date, value, lower, upper
        """
        logger.info("[Ensemble] Ejecutando predicción con múltiples modelos...")
        
        predictions = []
        
        # Prophet
        if PROPHET_AVAILABLE:
            try:
                pred_prophet = self._forecast_prophet(historical_df, horizon_days, confidence_level)
                predictions.append(pred_prophet)
                logger.info("[Ensemble] Prophet ejecutado exitosamente")
            except Exception as e:
                logger.warning(f"[Ensemble] Prophet falló: {e}")
        
        # ARIMA
        if ARIMA_AVAILABLE:
            try:
                pred_arima = self._forecast_arima(historical_df, horizon_days, confidence_level)
                predictions.append(pred_arima)
                logger.info("[Ensemble] ARIMA ejecutado exitosamente")
            except Exception as e:
                logger.warning(f"[Ensemble] ARIMA falló: {e}")
        
        # Validar que al menos un modelo funcionó
        if len(predictions) == 0:
            raise RuntimeError("Todos los modelos fallaron. Verificar datos y librerías instaladas.")
        
        # Si solo hay un modelo, retornarlo directamente
        if len(predictions) == 1:
            logger.warning("[Ensemble] Solo un modelo disponible, retornando resultado directo")
            return predictions[0]
        
        # Promediar predicciones
        ensemble_result = predictions[0].copy()
        for col in ['value', 'lower', 'upper']:
            values = [pred[col].values for pred in predictions]
            ensemble_result[col] = np.mean(values, axis=0)
        
        logger.info(f"[Ensemble] Promedio de {len(predictions)} modelos completado")
        return ensemble_result
    
    # ═══════════════════════════════════════════════════════════
    # MÉTODOS DE CONVERSIÓN A FORMATO API
    # ═══════════════════════════════════════════════════════════
    
    def to_api_dict(
        self, 
        prediction_df: pd.DataFrame, 
        metric_id: str, 
        entity: str, 
        unit: str,
        model_type: str,
        horizon_days: int
    ) -> Dict[str, Any]:
        """
        Convierte predicciones a formato estándar de API.
        
        Args:
            prediction_df: DataFrame con predicciones
            metric_id: Código de métrica
            entity: Entidad
            unit: Unidad de medida
            model_type: Tipo de modelo usado
            horizon_days: Días de horizonte
        
        Returns:
            Dict con formato API estándar
        """
        if prediction_df is None or prediction_df.empty:
            return {
                "metric_id": metric_id,
                "entity": entity,
                "unit": unit,
                "model": model_type,
                "horizon_days": horizon_days,
                "generated_at": datetime.now().isoformat() + "Z",
                "count": 0,
                "data": []
            }
        
        # Construir lista de puntos de datos
        data_points = []
        for _, row in prediction_df.iterrows():
            point = {
                "date": row['date'].strftime('%Y-%m-%d'),
                "value": round(float(row['value']), 2)
            }
            
            # Añadir intervalos de confianza si existen
            if 'lower' in row and pd.notna(row['lower']):
                point['lower'] = round(float(row['lower']), 2)
            if 'upper' in row and pd.notna(row['upper']):
                point['upper'] = round(float(row['upper']), 2)
            if 'confidence' in row and pd.notna(row['confidence']):
                point['confidence'] = float(row['confidence'])
            
            data_points.append(point)
        
        return {
            "metric_id": metric_id,
            "entity": entity,
            "unit": unit,
            "model": model_type,
            "horizon_days": horizon_days,
            "generated_at": datetime.now().isoformat() + "Z",
            "count": len(data_points),
            "data": data_points
        }
