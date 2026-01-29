"""
Modelo de dominio para predicciones
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class Prediction:
    """Representa una predicción"""
    
    fecha_prediccion: date
    fuente: str
    valor_gwh_predicho: float
    intervalo_inferior: float
    intervalo_superior: float
    fecha_generacion: Optional[date] = None
    horizonte_meses: Optional[int] = None
    modelo: Optional[str] = None
    confianza: Optional[float] = None
    fecha_creacion: Optional[str] = None
    
    @staticmethod
    def from_row(row: Dict[str, Any]) -> "Prediction":
        """Crea una Prediction desde un row de BD"""
        return Prediction(
            fecha_prediccion=row.get("fecha_prediccion"),
            fuente=row.get("fuente"),
            valor_gwh_predicho=row.get("valor_gwh_predicho"),
            intervalo_inferior=row.get("intervalo_inferior"),
            intervalo_superior=row.get("intervalo_superior"),
            fecha_generacion=row.get("fecha_generacion"),
            horizonte_meses=row.get("horizonte_meses"),
            modelo=row.get("modelo"),
            confianza=row.get("confianza"),
            fecha_creacion=row.get("fecha_creacion"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "fecha_prediccion": self.fecha_prediccion,
            "fuente": self.fuente,
            "valor_gwh_predicho": self.valor_gwh_predicho,
            "intervalo_inferior": self.intervalo_inferior,
            "intervalo_superior": self.intervalo_superior,
            "fecha_generacion": self.fecha_generacion,
            "horizonte_meses": self.horizonte_meses,
            "modelo": self.modelo,
            "confianza": self.confianza,
            "fecha_creacion": self.fecha_creacion,
        }
