"""
Mixin: Ontología unificada — geografía DANE + empresas/prestadores (Fase 1/2 del
roadmap "Palantir-IA"). Cruza comunidades, contratos OR, FENOGE, Colombia Solar,
subsidios y supervisión por departamento vía ontologia.mv_resumen_departamento.

Capa 100% analítica/de solo lectura — ninguna acción sobre contratos.
"""
import asyncio
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from domain.schemas.orchestrator import ErrorDetail
from domain.services.orchestrator.utils.decorators import handle_service_error
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_REGRESAR_MENU = {"id": "menu", "titulo": "🔙 Menú principal"}


def _normalizar(texto: str) -> str:
    """Quita tildes y pasa a mayúsculas — para comparar nombres de departamento en texto libre."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.upper().strip()


def resolver_departamento_en_texto(
    texto: str, departamentos: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Busca el nombre de un departamento DANE mencionado dentro de un texto libre.
    Compara los nombres más largos primero para que "Valle del Cauca" no pierda
    frente a una coincidencia parcial de "Valle".
    """
    texto_norm = _normalizar(texto)
    for depto in sorted(departamentos, key=lambda d: -len(d["nombre_departamento"])):
        if _normalizar(depto["nombre_departamento"]) in texto_norm:
            return depto
    return None


class OntologiaHandlerMixin:
    """
    Mixin que agrupa:
    - _handle_resumen_departamento (handler, intent explícito)
    - _handle_buscar_texto_rag, _handle_buscar_empresa, _handle_vecindario_empresa,
      _handle_riesgo_atraso_or, _handle_listar_proyectos (Fase 9 — tools del
      Asistente IA; envuelven capacidades de Fase 1/5/7/8 que antes solo se
      exponían como endpoints REST, nunca al orquestador/chatbot)
    """

    @handle_service_error
    async def _handle_resumen_departamento(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: vista 360 de un departamento — cruza comunidades energéticas,
        contratos OR, FENOGE, Colombia Solar, subsidios y supervisión.

        parameters:
            departamento: nombre en texto libre (ej. "Chocó"), o
            codigo_dane_departamento: código DANE de 2 dígitos (ej. "27")
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        codigo = parameters.get("codigo_dane_departamento")
        nombre = parameters.get("departamento")

        departamentos = await asyncio.to_thread(service.listar_departamentos)

        if not codigo and nombre:
            match = resolver_departamento_en_texto(nombre, departamentos)
            if match:
                codigo = match["codigo_dane_departamento"]

        if not codigo:
            errors.append(ErrorDetail(
                code="MISSING_DEPARTAMENTO",
                message="Debes indicar 'departamento' (nombre) o 'codigo_dane_departamento'",
            ))
            data["departamentos_disponibles"] = [d["nombre_departamento"] for d in departamentos]
            return data, errors

        resumen = await asyncio.to_thread(service.resumen_departamento, codigo)
        if resumen is None:
            errors.append(ErrorDetail(
                code="DEPARTAMENTO_NO_ENCONTRADO",
                message="No se encontró información DANE para el departamento indicado",
            ))
            return data, errors

        data["resumen_departamento"] = resumen
        data["nota"] = (
            "Cruce de comunidades energéticas, contratos OR, FENOGE, Colombia Solar, "
            "subsidios y supervisión para este departamento. Cobertura geográfica en "
            "curación progresiva — ver GET /v1/ontologia/alias/pendientes."
        )
        data["opcion_regresar"] = _REGRESAR_MENU
        return data, errors

    @handle_service_error
    async def _handle_buscar_texto_rag(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: búsqueda semántica (RAG) sobre observaciones/objeto de contratos
        de supervisión E informes PDF/PPTX/DOCX de SharePoint (PMO, actas
        ELECTROCAQUETA, boletín XM, informes diarios XM).

        parameters:
            consulta: texto de búsqueda en lenguaje natural (requerido)
            top_k: máximo de resultados (default 5)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        consulta = parameters.get("consulta", "").strip()
        if not consulta:
            errors.append(ErrorDetail(
                code="MISSING_CONSULTA",
                message="Debes indicar 'consulta'",
            ))
            return data, errors

        from core.container import get_ontologia_service
        service = get_ontologia_service()
        top_k = int(parameters.get("top_k", 5))

        resultados = await asyncio.to_thread(service.buscar_texto, consulta, top_k)
        data["resultados"] = resultados
        data["nota"] = (
            "Cada resultado indica 'fuente' ('contrato' u 'informe') y su 'similitud' "
            "(0-1) con la consulta. Cita el nombre_archivo cuando la fuente sea 'informe'."
        )
        return data, errors

    @handle_service_error
    async def _handle_buscar_empresa(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: busca una empresa/prestador/ejecutor por NIT o nombre/sigla.

        parameters:
            nombre: nombre o sigla en texto libre (ej. "GENSA"), o
            nit: NIT exacto
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        nombre = parameters.get("nombre")
        nit = parameters.get("nit")
        if not nombre and not nit:
            errors.append(ErrorDetail(
                code="MISSING_EMPRESA",
                message="Debes indicar 'nombre' o 'nit'",
            ))
            return data, errors

        from core.container import get_ontologia_service
        service = get_ontologia_service()

        empresas = await asyncio.to_thread(service.buscar_empresas, nit, nombre)
        data["empresas"] = empresas
        data["nota"] = (
            "Usa el 'empresa_id' de un resultado con este llamado para explorar su "
            "vecindario con la herramienta vecindario_empresa."
        )
        return data, errors

    @handle_service_error
    async def _handle_vecindario_empresa(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: grafo de relaciones de una empresa (solo lectura) — contratos
        verificados por NIT, proyectos por nombre difuso, geografía donde opera,
        y otras empresas con contratos en las mismas zonas.

        parameters:
            empresa_id: id numérico obtenido con buscar_empresa (requerido)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        empresa_id = parameters.get("empresa_id")
        if empresa_id is None:
            errors.append(ErrorDetail(
                code="MISSING_EMPRESA_ID",
                message="Debes indicar 'empresa_id' (usa buscar_empresa primero para obtenerlo)",
            ))
            return data, errors

        from core.container import get_graph_service
        service = get_graph_service()

        vecindario = await asyncio.to_thread(service.vecindario_empresa, int(empresa_id))
        if vecindario is None:
            errors.append(ErrorDetail(
                code="EMPRESA_NO_ENCONTRADA",
                message="No se encontró ninguna empresa con ese empresa_id",
            ))
            return data, errors

        data["vecindario"] = vecindario
        return data, errors

    @handle_service_error
    async def _handle_riesgo_atraso_or(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: ranking de contratos OR por riesgo de atraso (cronograma de obra),
        mayor riesgo primero. Puramente informativo — no cambia ningún estado.

        parameters:
            limit: máximo de contratos a devolver (default 10)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        from core.container import get_risk_service
        service = get_risk_service()
        limit = int(parameters.get("limit", 10))

        ranking = await asyncio.to_thread(service.riesgo_atraso_contratos_or)
        data["ranking"] = ranking[:limit]
        data["total_contratos_evaluados"] = len(ranking)
        data["nota"] = (
            "Score informativo de riesgo de atraso basado en el cronograma de obra. "
            "No modifica el estado de ningún contrato."
        )
        return data, errors

    @handle_service_error
    async def _handle_listar_proyectos(
        self, parameters: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[ErrorDetail]]:
        """
        Handler: lista proyectos de la ontología (objeto de primera clase),
        opcionalmente filtrados por programa.

        parameters:
            programa: 'contratos_or' | 'colombia_solar' | 'fenoge' (opcional)
        """
        data: Dict[str, Any] = {}
        errors: List[ErrorDetail] = []

        from core.container import get_ontologia_service
        service = get_ontologia_service()
        programa = parameters.get("programa")

        proyectos = await asyncio.to_thread(service.listar_proyectos, programa)
        data["proyectos"] = proyectos
        return data, errors
