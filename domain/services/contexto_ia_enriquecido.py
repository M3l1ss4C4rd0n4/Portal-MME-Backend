"""
Helpers compartidos para enriquecer prompts de IA con RAG (Fase 8, con filtro
por `tema` de la Fase 11 Ronda 5) y con los índices regulatorios de
`ontologia.dim_metrica` (Fase 12) — reutilizados por `AgentIA` (ai_service.py)
y por el Informe Ejecutivo (`informe_handler.py`), mismo patrón ya probado en
`tasks/homeslider_diagnosticos_tasks.py`.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def contexto_rag_texto(consulta: str, tema: Optional[str] = None, top_k: int = 3) -> str:
    """
    Busca en el RAG (opcionalmente filtrado por `tema`) y devuelve un bloque de
    texto listo para insertar en un prompt. Cadena vacía si no hay resultados o
    si la búsqueda falla — nunca lanza, para no tumbar el flujo de generación.
    """
    try:
        from core.container import get_ontologia_service
        service = get_ontologia_service()
        resultados = service.buscar_texto(consulta, top_k=top_k, tema=tema)
    except Exception as e:
        logger.warning(f"[CONTEXTO_IA] Búsqueda RAG falló para '{consulta}' (tema={tema}): {e}")
        return ""

    if not resultados:
        return ""

    lineas = ["CONTEXTO NARRATIVO REAL (informes XM / guía de alertas / SharePoint):"]
    for r in resultados:
        fuente = r.get("nombre_archivo") or r.get("fuente", "informe")
        lineas.append(f"- ({fuente}): {r.get('contenido', '')[:500]}")
    return "\n".join(lineas)


def contexto_indices_regulatorios_texto() -> str:
    """
    Devuelve los 4 índices regulatorios de `ontologia.dim_metrica` (NE, HSIN,
    PBP, Condición del Sistema) con su descripción y relaciones, listos para
    insertar en un prompt — mismo contenido que ya usa la Fase 11, para que
    todos los generadores de texto expliquen los umbrales con la misma cita
    normativa consistente en vez de que cada uno redacte la suya.
    """
    try:
        from core.container import get_ontologia_service
        service = get_ontologia_service()
        metricas = service.listar_metricas(dominio="sector_energetico", estado="catalogado")
        indices = [m for m in metricas if m.get("es_indice_regulatorio")]
    except Exception as e:
        logger.warning(f"[CONTEXTO_IA] No se pudieron obtener índices regulatorios: {e}")
        return ""

    if not indices:
        return ""

    lineas = ["ÍNDICES REGULATORIOS (para que entiendas cómo se relacionan y clasifican las métricas):"]
    for ix in indices:
        lineas.append(
            f"- {ix['codigo_tecnico']} ({ix['nombre_display']}): {ix['descripcion']} "
            f"[{ix.get('referencia_normativa', '')}]"
        )
    return "\n".join(lineas)
