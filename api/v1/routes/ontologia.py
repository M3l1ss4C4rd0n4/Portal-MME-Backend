"""
Endpoints de la ontología unificada (Fase 1 — geografía DANE + empresas/prestadores)

Capa semántica de solo lectura que cruza los 9 esquemas de negocio del portal
(comunidades, contratos_or, fenoge, subsidios, supervision, colombia_solar, ...) vía
ontologia.dim_geografia / dim_empresa. No expone ninguna operación de escritura sobre
contratos — es puramente analítico. Ver sql/migrations/005-008 y
scripts/ontologia/build_*_alias.py.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.dependencies import get_api_key, get_ontologia_service, get_graph_service
from domain.services.ontologia_service import OntologiaService
from domain.services.graph_service import GraphService

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/geografia", summary="Departamentos DANE disponibles en la ontología")
@limiter.limit("60/minute")
async def listar_geografia(
    request: Request,
    api_key: str = Depends(get_api_key),
    service: OntologiaService = Depends(get_ontologia_service),
):
    return {"departamentos": service.listar_departamentos()}


@router.get(
    "/geografia/{codigo_dane_departamento}/resumen",
    summary="Vista 360 de un departamento: comunidades + contratos OR + FENOGE + "
            "Colombia Solar + subsidios + supervisión",
)
@limiter.limit("60/minute")
async def resumen_departamento(
    request: Request,
    codigo_dane_departamento: str,
    api_key: str = Depends(get_api_key),
    service: OntologiaService = Depends(get_ontologia_service),
):
    resumen = service.resumen_departamento(codigo_dane_departamento)
    if resumen is None:
        raise HTTPException(
            status_code=404,
            detail=f"Departamento con código DANE '{codigo_dane_departamento}' no "
                   "encontrado en ontologia.dim_geografia",
        )
    return resumen


@router.get("/empresas", summary="Busca una empresa/prestador por NIT o nombre")
@limiter.limit("60/minute")
async def buscar_empresas(
    request: Request,
    nit: str = Query(None, description="NIT exacto (con o sin dígito de verificación)"),
    nombre: str = Query(None, description="Nombre o sigla, búsqueda difusa"),
    api_key: str = Depends(get_api_key),
    service: OntologiaService = Depends(get_ontologia_service),
):
    if not nit and not nombre:
        raise HTTPException(status_code=400, detail="Debe indicar 'nit' o 'nombre'")
    return {"empresas": service.buscar_empresas(nit=nit, nombre=nombre)}


@router.get(
    "/buscar-texto",
    summary="Búsqueda semántica (RAG) sobre objeto de contrato/observaciones de "
            "supervisión E informes PDF/PPTX de SharePoint (campo 'fuente' distingue)",
)
@limiter.limit("30/minute")
async def buscar_texto(
    request: Request,
    q: str = Query(..., min_length=3, description="Consulta en lenguaje natural"),
    top_k: int = Query(5, ge=1, le=20),
    api_key: str = Depends(get_api_key),
    service: OntologiaService = Depends(get_ontologia_service),
):
    resultados = service.buscar_texto(q, top_k=top_k)
    return {"consulta": q, "resultados": resultados}


@router.get(
    "/grafo/empresa/{empresa_id}",
    summary="Vecindario de 1 salto: empresa → contratos ejecutados → geografía "
            "(grafo de relaciones de solo lectura)",
)
@limiter.limit("30/minute")
async def grafo_empresa(
    request: Request,
    empresa_id: int,
    limit: int = Query(50, ge=1, le=200, description="Máximo de contratos a incluir en el vecindario"),
    api_key: str = Depends(get_api_key),
    service: GraphService = Depends(get_graph_service),
):
    vecindario = service.vecindario_empresa(empresa_id, limit_contratos=limit)
    if vecindario is None:
        raise HTTPException(status_code=404, detail=f"Empresa {empresa_id} no encontrada")
    return vecindario


@router.get(
    "/proyectos",
    summary="Lista proyectos (objeto de primera clase) — Fase 7, opcional filtrar por programa",
)
@limiter.limit("30/minute")
async def listar_proyectos(
    request: Request,
    programa: str = Query(None, description="'contratos_or' | 'colombia_solar' | 'fenoge'"),
    api_key: str = Depends(get_api_key),
    service: OntologiaService = Depends(get_ontologia_service),
):
    return {"proyectos": service.listar_proyectos(programa=programa)}


@router.get(
    "/proyectos/{proyecto_id}",
    summary="Detalle de un proyecto: dónde aparece (esquema/tabla) y con qué texto original",
)
@limiter.limit("30/minute")
async def obtener_proyecto(
    request: Request,
    proyecto_id: int,
    api_key: str = Depends(get_api_key),
    service: OntologiaService = Depends(get_ontologia_service),
):
    proyecto = service.obtener_proyecto(proyecto_id)
    if proyecto is None:
        raise HTTPException(status_code=404, detail=f"Proyecto {proyecto_id} no encontrado")
    return proyecto


@router.get(
    "/salud",
    summary="Salud de la ontología: deuda de curación + linaje reciente del pipeline "
            "(Fase 6 — gobierno de datos)",
)
@limiter.limit("30/minute")
async def salud_datos(
    request: Request,
    api_key: str = Depends(get_api_key),
    service: OntologiaService = Depends(get_ontologia_service),
):
    return service.salud_datos()


@router.get(
    "/alias/pendientes",
    summary="Backlog interno de curación: valores de geografía/empresa aún sin resolver",
)
@limiter.limit("30/minute")
async def alias_pendientes(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    api_key: str = Depends(get_api_key),
    service: OntologiaService = Depends(get_ontologia_service),
):
    return service.alias_pendientes(limit=limit)
