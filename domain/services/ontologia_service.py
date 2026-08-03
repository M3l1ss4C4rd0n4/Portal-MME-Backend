"""
Servicio de dominio para la ontología (geografía DANE + empresas/prestadores).
Lógica de negocio que usa IGeografiaRepository/IEmpresaRepository.
Implementa Inyección de Dependencias (Arquitectura Limpia).

Capa 100% de lectura/análisis — no expone ninguna operación de escritura sobre
tablas de negocio (aprobar/rechazar/cambiar estado). Ver ontologia.* en
sql/migrations/005-008.
"""

from typing import Any, Dict, List, Optional

from domain.interfaces.repositories import (
    IEmpresaRepository,
    IGeografiaRepository,
    IProyectoRepository,
    ISemanticSearchRepository,
)


def _get_default_geografia_repo():
    from core.container import container
    return container.get_geografia_repository()


def _get_default_empresa_repo():
    from core.container import container
    return container.get_empresa_repository()


def _get_default_semantic_search_repo():
    from core.container import container
    return container.get_semantic_search_repository()


def _get_default_proyecto_repo():
    from core.container import container
    return container.get_proyecto_repository()


class OntologiaService:
    """
    Servicio de ontología con inyección de dependencias.
    Depende de IGeografiaRepository/IEmpresaRepository (interfaces), no de
    implementaciones concretas.
    """

    def __init__(
        self,
        geografia_repository: Optional[IGeografiaRepository] = None,
        empresa_repository: Optional[IEmpresaRepository] = None,
        semantic_search_repository: Optional[ISemanticSearchRepository] = None,
        proyecto_repository: Optional[IProyectoRepository] = None,
    ):
        self.geografia_repo = geografia_repository or _get_default_geografia_repo()
        self.empresa_repo = empresa_repository or _get_default_empresa_repo()
        self.semantic_search_repo = semantic_search_repository or _get_default_semantic_search_repo()
        self.proyecto_repo = proyecto_repository or _get_default_proyecto_repo()

    def listar_departamentos(self) -> List[Dict[str, Any]]:
        return self.geografia_repo.listar_departamentos()

    def resumen_departamento(self, codigo_dane_departamento: str) -> Optional[Dict[str, Any]]:
        codigo = codigo_dane_departamento.zfill(2)
        return self.geografia_repo.resumen_departamento(codigo)

    def buscar_empresas(
        self, nit: Optional[str] = None, nombre: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.empresa_repo.buscar_empresas(nit=nit, nombre=nombre)

    def alias_pendientes(self, limit: int = 200) -> Dict[str, List[Dict[str, Any]]]:
        """Backlog de curación manual — geografía y empresas sin resolver."""
        return {
            "geografia": self.geografia_repo.alias_pendientes(limit=limit),
            "empresas": self.empresa_repo.alias_pendientes(limit=limit),
        }

    def salud_datos(self) -> Dict[str, Any]:
        """
        Fase 6 — gobierno de datos: deuda de ontología (backlog de alias sin
        resolver) + linaje reciente del pipeline (scripts/ontologia/*.py vía
        ontologia.etl_lineage). Superficie de esto es lo que permitió detectar
        que un ETL externo (DROP TABLE ... CASCADE) había tumbado 4 vistas
        materializadas sin ningún error visible hasta entonces.
        """
        lineage = self.geografia_repo.historial_lineage(limit=30)
        corridas_con_error = [row for row in lineage if row.get("estado") == "error"]
        return {
            "deuda_ontologia": {
                "geografia_sin_resolver": self.geografia_repo.contar_alias_pendientes(),
                "empresas_sin_resolver": self.empresa_repo.contar_alias_pendientes(),
            },
            "lineage_reciente": lineage,
            "corridas_con_error_recientes": len(corridas_con_error),
        }

    def listar_proyectos(self, programa: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.proyecto_repo.listar_proyectos(programa=programa)

    def obtener_proyecto(self, proyecto_id: int) -> Optional[Dict[str, Any]]:
        proyecto = self.proyecto_repo.obtener_por_id(proyecto_id)
        if proyecto is None:
            return None
        proyecto["alias"] = self.proyecto_repo.alias_de_proyecto(proyecto_id)
        return proyecto

    def buscar_texto(
        self, consulta: str, top_k: int = 5, umbral_similitud: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Búsqueda semántica (RAG) sobre objeto de contrato y observaciones
        jurídicas/técnicas de supervision.contratos — texto libre que no se puede
        resolver con SQL exacto. Embeddings locales, sin API externa.
        """
        from infrastructure.ml.embeddings import embed
        vector_consulta = embed(consulta)
        return self.semantic_search_repo.buscar_similar(
            vector_consulta, top_k=top_k, umbral_similitud=umbral_similitud
        )
