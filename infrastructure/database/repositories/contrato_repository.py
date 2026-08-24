"""
Repositorio para el detalle de un contrato individual de supervisión — Fase
28. Implementa IContratoRepository. Consulta en vivo contra
supervision.contratos, sin tabla propia en ontologia.
"""

from typing import Any, Dict, Optional

from infrastructure.database.repositories.base_repository import BaseRepository
from domain.interfaces.repositories import IContratoRepository


class ContratoRepository(BaseRepository, IContratoRepository):
    """Repositorio para supervision.contratos (detalle por id)."""

    def obtener_por_id(self, contrato_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, codcontrato, ejecutor, nit_ejecutor, interventoria,
                   departamento, municipio, codigo_dane_departamento, codigo_dane_municipio,
                   fondo, numero_bpin, estado_del_contrato, etapa_del_contrato,
                   avance_contrato, avance_de_obra, link_secop,
                   valor_del_contrato_informacion_apoyos_financieros AS valor_contrato,
                   valor_desembolsado_informacion_apoyos_financieros AS valor_desembolsado,
                   porcentaje_de_desembolsos, numero_de_usuarios_totales_contratados,
                   nombre_del_proyecto, tipo_de_solucion
            FROM supervision.contratos
            WHERE id = %(id)s
        """
        return self.execute_query_one(query, {"id": contrato_id})
