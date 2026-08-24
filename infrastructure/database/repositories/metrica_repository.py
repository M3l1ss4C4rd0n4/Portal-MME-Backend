"""
Repositorio para el catálogo de métricas/variables (esquema ontologia) — Fase 12.
Implementa IMetricaRepository.
"""

from typing import Any, Dict, List, Optional

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IMetricaRepository


class MetricaRepository(BaseRepository, IMetricaRepository):
    """Repositorio para ontologia.dim_metrica / metrica_relacion."""

    def listar_metricas(
        self, dominio: Optional[str] = None, estado: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        condiciones = []
        params: List[Any] = []
        if dominio:
            condiciones.append("dominio = %s")
            params.append(dominio)
        if estado:
            condiciones.append("estado = %s")
            params.append(estado)
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        query = f"""
            SELECT metrica_id, codigo_tecnico, nombre_display, dominio, esquema_origen,
                   tabla_origen, columna_origen, unidad, fuente, descripcion,
                   es_indice_regulatorio, referencia_normativa, estado, creado_en
            FROM ontologia.dim_metrica
            {where}
            ORDER BY dominio, es_indice_regulatorio DESC, nombre_display
        """
        return self.execute_query(query, tuple(params) if params else None)

    def obtener_por_id(self, metrica_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT metrica_id, codigo_tecnico, nombre_display, dominio, esquema_origen,
                   tabla_origen, columna_origen, unidad, fuente, descripcion,
                   es_indice_regulatorio, referencia_normativa, estado, creado_en
            FROM ontologia.dim_metrica
            WHERE metrica_id = %s
        """
        return self.execute_query_one(query, (metrica_id,))

    def obtener_por_codigo(self, dominio: str, codigo_tecnico: str) -> Optional[Dict[str, Any]]:
        query = """
            SELECT metrica_id, codigo_tecnico, nombre_display, dominio, esquema_origen,
                   tabla_origen, columna_origen, unidad, fuente, descripcion,
                   es_indice_regulatorio, referencia_normativa, estado, creado_en
            FROM ontologia.dim_metrica
            WHERE dominio = %s AND codigo_tecnico = %s
        """
        return self.execute_query_one(query, (dominio, codigo_tecnico))

    def buscar_por_nombre(self, texto: str) -> List[Dict[str, Any]]:
        query = """
            SELECT metrica_id, codigo_tecnico, nombre_display, dominio, unidad,
                   fuente, descripcion, es_indice_regulatorio, referencia_normativa
            FROM ontologia.dim_metrica
            WHERE nombre_display ILIKE %(patron)s OR codigo_tecnico ILIKE %(patron)s
            ORDER BY es_indice_regulatorio DESC, nombre_display
            LIMIT 20
        """
        return self.execute_query(query, {"patron": f"%{texto}%"})

    def relaciones_de_metrica(self, metrica_id: int) -> List[Dict[str, Any]]:
        query = """
            SELECT r.relacion_id, r.tipo_relacion, r.descripcion, r.referencia_normativa,
                   o.metrica_id AS origen_id, o.codigo_tecnico AS origen_codigo,
                   o.nombre_display AS origen_nombre,
                   d.metrica_id AS destino_id, d.codigo_tecnico AS destino_codigo,
                   d.nombre_display AS destino_nombre
            FROM ontologia.metrica_relacion r
            JOIN ontologia.dim_metrica o ON o.metrica_id = r.metrica_origen_id
            JOIN ontologia.dim_metrica d ON d.metrica_id = r.metrica_destino_id
            WHERE r.metrica_origen_id = %(id)s OR r.metrica_destino_id = %(id)s
            ORDER BY r.tipo_relacion
        """
        return self.execute_query(query, {"id": metrica_id})
