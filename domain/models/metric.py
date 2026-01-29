"""
Modelo de dominio para métricas energéticas
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class Metric:
    """Representa una métrica energética"""
    
    fecha: date
    metrica: str
    entidad: str
    valor_gwh: float
    unidad: str = "GWh"
    recurso: Optional[str] = None
    fecha_actualizacion: Optional[str] = None
    
    @staticmethod
    def from_row(row: Dict[str, Any]) -> "Metric":
        """Crea un Metric desde un row de BD"""
        return Metric(
            fecha=row.get("fecha"),
            metrica=row.get("metrica"),
            entidad=row.get("entidad"),
            valor_gwh=row.get("valor_gwh"),
            unidad=row.get("unidad", "GWh"),
            recurso=row.get("recurso"),
            fecha_actualizacion=row.get("fecha_actualizacion"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "fecha": self.fecha,
            "metrica": self.metrica,
            "entidad": self.entidad,
            "valor_gwh": self.valor_gwh,
            "unidad": self.unidad,
            "recurso": self.recurso,
            "fecha_actualizacion": self.fecha_actualizacion,
        }
