#!/usr/bin/env python3
"""
Ontología — Fase 13 (profundización): resuelve menciones de plantas/recursos
específicos en los chunks del corpus RAG contra ontologia.dim_recurso, por
coincidencia de palabra completa (nunca subcadena — evita falsos positivos
de nombres cortos como "SUBA" o "ZEUS" que también son recursos reales).

Alcance: chunks con tema IN ('despacho', 'hidrologia', 'operativas',
'metodologia_alertas') — los temas donde los informes de XM efectivamente
nombran plantas específicas (SeguimientoDespacho lista plantas indisponibles;
Hidrologia y Operativas mencionan generación por planta; el documento de
metodología de alertas lista embalses reales por región, ej. "Centro: Agregado
Bogotá, El Quimbo, Muña..." — mismo tipo de contenido que hidrologia).

Fase 17 (Gap 5): 'panorama_climatico'/'comunidades'/'pmo_interno' se probaron
empíricamente (escaneando sus chunks reales con esta misma regex) y NO se
agregan — confirmado ruido, no solo nunca-considerados: 'comunidades' solo
producía falsos positivos por homónimos (ej. "SAN MIGUEL" como nombre de
municipio en una tabla de beneficiarios, no la planta hidráulica SMI1);
'pmo_interno' igual (ej. "SANTIAGO" como apellido de una persona en un
organigrama, no la planta STG1); 'panorama_climatico' tiene muy pocos chunks
indexados (3) para sacar una conclusión, se revisita si el corpus crece.

Uso:
    venv/bin/python3 scripts/ontologia/resolver_recurso_mencion.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

TEMAS_A_ESCANEAR = ("despacho", "hidrologia", "operativas", "metodologia_alertas")
LONGITUD_MINIMA_NOMBRE = 6  # evita falsos positivos de nombres cortos/genéricos


def main() -> None:
    recursos = db_manager.query_df(
        "SELECT recurso_id, nombre FROM ontologia.dim_recurso WHERE length(nombre) >= %(min)s",
        {"min": LONGITUD_MINIMA_NOMBRE},
    )
    logger.info(f"{len(recursos)} recursos candidatos (nombre >= {LONGITUD_MINIMA_NOMBRE} chars)")

    chunks = db_manager.query_df(
        """
        SELECT e.documento_id, e.chunk_index, e.contenido
        FROM ontologia.informes_texto_embeddings e
        JOIN ontologia.informes_documentos d ON d.documento_id = e.documento_id
        WHERE d.tema = ANY(%(temas)s)
        """,
        {"temas": list(TEMAS_A_ESCANEAR)},
    )
    logger.info(f"{len(chunks)} chunks a escanear (temas: {TEMAS_A_ESCANEAR})")

    # Precompilar un patrón de palabra completa por recurso (case-insensitive).
    patrones = [
        (row["recurso_id"], re.compile(r"\b" + re.escape(row["nombre"]) + r"\b", re.IGNORECASE))
        for _, row in recursos.iterrows()
    ]

    total_menciones = 0
    for _, chunk in chunks.iterrows():
        contenido = chunk["contenido"] or ""
        for recurso_id, patron in patrones:
            if patron.search(contenido):
                db_manager.execute_non_query(
                    """
                    INSERT INTO ontologia.recurso_mencion (documento_id, chunk_index, recurso_id)
                    VALUES (%(doc)s, %(chunk)s, %(recurso)s)
                    ON CONFLICT (documento_id, chunk_index, recurso_id) DO NOTHING
                    """,
                    {"doc": int(chunk["documento_id"]), "chunk": int(chunk["chunk_index"]), "recurso": int(recurso_id)},
                )
                total_menciones += 1

    logger.info(f"{total_menciones} menciones planta<->chunk resueltas/actualizadas")


if __name__ == "__main__":
    main()
