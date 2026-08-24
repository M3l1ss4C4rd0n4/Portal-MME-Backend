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
    IContratoRepository,
    IEmpresaRepository,
    IGeografiaRepository,
    IMetricaRepository,
    IRecursoRepository,
    IProyectoRepository,
    ISemanticSearchRepository,
)


_RRF_K = 60  # constante estándar de la literatura de Reciprocal Rank Fusion

# Fase 29 — temas que corresponden a documentos con botón de descarga real en
# el portal (Boletín/Panorama Energético, informes diarios XM, actas de
# contratos OR vía ELECTROCAQUETA, informe de empalme) — reciben un bono de
# prioridad en el re-ranking (ver infrastructure/ml/reranking.py) frente a
# carpetas genéricas de SharePoint sin botón de descarga asociado.
TEMAS_PRIORITARIOS = {
    "despacho", "hidrologia", "operativas", "panorama_climatico",
    "comunidades", "informe_empalme",
}
# Nota (Fase 35): 'planeacion_xm'/'boletin_energetico_xm' NO se agregan aquí
# a propósito — ya reciben su propio bono de recencia (ver reranking.py), y
# apilar además el bono de prioridad de fuente sobre un corpus tan grande
# (cientos de documentos) no se probó combinado; se evita el riesgo de un
# bono compuesto sin calibrar en vez de extender esto sin evidencia.


def _fusionar_rrf(
    *listas: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Fase 25 (extendida en Fase 35 a N listas, ej. + buscar_recientes) —
    combina resultados de distintas estrategias de recuperación por
    Reciprocal Rank Fusion: score = Σ 1/(k + rank_i) sobre cada lista donde
    el candidato aparece. Usa solo la POSICIÓN en cada ranking, no el score
    crudo — evita tener que normalizar escalas incomparables (similitud
    coseno 0-1 vs. ts_rank_cd sin rango fijo vs. orden por fecha).
    Deduplica por `contenido` exacto (mismo criterio ya usado en las
    consultas SQL con DISTINCT ON)."""
    scores: Dict[str, float] = {}
    datos: Dict[str, Dict[str, Any]] = {}
    for lista in listas:
        for rank, item in enumerate(lista, start=1):
            clave = item["contenido"]
            scores[clave] = scores.get(clave, 0.0) + 1.0 / (_RRF_K + rank)
            datos.setdefault(clave, item)
    fusionados = sorted(datos.values(), key=lambda item: scores[item["contenido"]], reverse=True)
    return fusionados


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


def _get_default_metrica_repo():
    from core.container import container
    return container.get_metrica_repository()


def _get_default_recurso_repo():
    from core.container import container
    return container.get_recurso_repository()


def _get_default_contrato_repo():
    from core.container import container
    return container.get_contrato_repository()


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
        metrica_repository: Optional[IMetricaRepository] = None,
        recurso_repository: Optional[IRecursoRepository] = None,
        contrato_repository: Optional[IContratoRepository] = None,
    ):
        self.geografia_repo = geografia_repository or _get_default_geografia_repo()
        self.empresa_repo = empresa_repository or _get_default_empresa_repo()
        self.semantic_search_repo = semantic_search_repository or _get_default_semantic_search_repo()
        self.proyecto_repo = proyecto_repository or _get_default_proyecto_repo()
        self.metrica_repo = metrica_repository or _get_default_metrica_repo()
        self.recurso_repo = recurso_repository or _get_default_recurso_repo()
        self.contrato_repo = contrato_repository or _get_default_contrato_repo()

    def listar_departamentos(self) -> List[Dict[str, Any]]:
        return self.geografia_repo.listar_departamentos()

    def resumen_departamento(self, codigo_dane_departamento: str) -> Optional[Dict[str, Any]]:
        codigo = codigo_dane_departamento.zfill(2)
        return self.geografia_repo.resumen_departamento(codigo)

    def listar_municipios(self, codigo_dane_departamento: Optional[str] = None) -> List[Dict[str, Any]]:
        codigo = codigo_dane_departamento.zfill(2) if codigo_dane_departamento else None
        return self.geografia_repo.listar_municipios(codigo)

    def resumen_municipio(self, codigo_dane_municipio: str) -> Optional[Dict[str, Any]]:
        codigo = codigo_dane_municipio.zfill(5)
        return self.geografia_repo.resumen_municipio(codigo)

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

    def listar_proyectos(
        self, programa: Optional[str] = None, departamento: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.proyecto_repo.listar_proyectos(programa=programa, departamento=departamento)

    def obtener_proyecto(self, proyecto_id: int) -> Optional[Dict[str, Any]]:
        proyecto = self.proyecto_repo.obtener_por_id(proyecto_id)
        if proyecto is None:
            return None
        proyecto["alias"] = self.proyecto_repo.alias_de_proyecto(proyecto_id)
        proyecto["geografias"] = self.proyecto_repo.geografias_de_proyecto(proyecto_id)
        return proyecto

    def listar_metricas(
        self, dominio: Optional[str] = None, estado: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.metrica_repo.listar_metricas(dominio=dominio, estado=estado)

    def obtener_metrica(self, metrica_id: int) -> Optional[Dict[str, Any]]:
        metrica = self.metrica_repo.obtener_por_id(metrica_id)
        if metrica is None:
            return None
        metrica["relaciones"] = self.metrica_repo.relaciones_de_metrica(metrica_id)
        return metrica

    def buscar_metrica(self, texto: str) -> List[Dict[str, Any]]:
        """
        Búsqueda estructurada del catálogo de métricas por nombre o código técnico
        (Fase 12) — cada resultado incluye sus relaciones de derivación, para que
        el Asistente IA pueda responder "¿qué es X y de qué depende?" con datos
        reales y cita normativa, no con una respuesta genérica del LLM.
        """
        resultados = self.metrica_repo.buscar_por_nombre(texto)
        for metrica in resultados:
            metrica["relaciones"] = self.metrica_repo.relaciones_de_metrica(metrica["metrica_id"])
        return resultados

    def listar_recursos(
        self, tipo: Optional[str] = None, nombre: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.recurso_repo.listar_recursos(tipo=tipo, nombre=nombre)

    def obtener_recurso(self, codigo_xm: str) -> Optional[Dict[str, Any]]:
        recurso = self.recurso_repo.obtener_por_codigo(codigo_xm)
        if recurso is None:
            return None
        recurso["menciones_recientes"] = self.recurso_repo.menciones_recientes(recurso["recurso_id"])
        return recurso

    def obtener_contrato(self, contrato_id: int) -> Optional[Dict[str, Any]]:
        return self.contrato_repo.obtener_por_id(contrato_id)

    def buscar_texto(
        self,
        consulta: str,
        top_k: int = 5,
        umbral_similitud: float = 0.3,
        tema: Optional[str] = None,
        campo_contrato: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Búsqueda semántica (RAG) sobre objeto de contrato y observaciones
        jurídicas/técnicas de supervision.contratos — texto libre que no se puede
        resolver con SQL exacto. Embeddings locales, sin API externa.

        `tema`: filtro determinístico opcional (ej. 'despacho', 'panorama_climatico')
        sobre informes_documentos.tema — Fase 11 Ronda 5.
        `campo_contrato`: filtro determinístico equivalente sobre el corpus de
        contratos (ej. 'objeto_del_contrato') — Fase 13.

        Re-ranking (Fase 24): la similitud de embeddings por sí sola deja pasar
        contenido irrelevante con score engañosamente alto (reproducido: "cuál
        es el color favorito de un gato" obtenía 0.33-0.38 de similitud contra
        contratos sin relación). Se piden más candidatos de los pedidos
        (`top_k` ampliado) y se reordenan/filtran con un cross-encoder
        (infrastructure/ml/reranking.py) antes de recortar a `top_k` — la
        similitud de embeddings sigue siendo el primer filtro barato (umbral_similitud).

        Búsqueda híbrida (Fase 25): la búsqueda densa (embeddings) pierde
        coincidencias léxicas exactas — nombres de planta, códigos, términos
        poco frecuentes (reproducido: "plantas indisponibles CARTAGENA" no
        aparece en el pool vectorial ampliado, pero SÍ se encuentra por texto
        completo). Se combina con una búsqueda dispersa (Postgres full-text,
        buscar_texto_completo()) sobre el mismo pool, fusionadas por
        Reciprocal Rank Fusion (_fusionar_rrf) antes del re-ranking — cada
        técnica cubre lo que a la otra se le escapa.

        Recencia garantizada (Fase 35): en corpus con muchos documentos
        periódicos casi idénticos entre sí (ej. ~250 informes semanales de
        Planeación XM), el chunk correcto del informe MÁS RECIENTE puede
        quedar fuera del pool de candidatos de las dos búsquedas de arriba
        simplemente por volumen de competencia semántica — reproducido en
        vivo: similitud 0.345 (por encima del umbral) pero fuera del top-200
        de su tema. Cuando se pasa `tema`, se agrega una tercera búsqueda
        (buscar_recientes(), ordenada por fecha de publicación real, no por
        similitud) para garantizar que lo más reciente compita en el
        re-ranking — que ya trae su propio bono de recencia (Fase 35,
        infrastructure/ml/reranking.py) para romper empates de fraseo entre
        semanas distintas.
        """
        from infrastructure.ml.embeddings import embed
        from infrastructure.ml.reranking import rerank
        vector_consulta = embed(consulta)
        pool_ampliado = max(top_k * 3, 15)
        candidatos_vector = self.semantic_search_repo.buscar_similar(
            vector_consulta, top_k=pool_ampliado, umbral_similitud=umbral_similitud,
            tema=tema, campo_contrato=campo_contrato,
        )
        candidatos_fts = self.semantic_search_repo.buscar_texto_completo(
            consulta, top_k=pool_ampliado, tema=tema, campo_contrato=campo_contrato,
        )
        listas = [candidatos_vector, candidatos_fts]
        if tema:
            candidatos_recientes = self.semantic_search_repo.buscar_recientes(
                vector_consulta, tema=tema, top_k=pool_ampliado,
            )
            listas.append(candidatos_recientes)
        candidatos = _fusionar_rrf(*listas)
        return rerank(consulta, candidatos, top_k=top_k, temas_prioritarios=TEMAS_PRIORITARIOS)
