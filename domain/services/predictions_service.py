"""
Servicio de dominio para predicciones.
Re-exporta PredictionsService desde predictions_service_extended para unificar
la implementación. El stub original está consolidado en el módulo extendido.
"""

# Re-export: un único PredictionsService canónico en todo el codebase
from domain.services.predictions_service_extended import PredictionsService  # noqa: F401

__all__ = ["PredictionsService"]
