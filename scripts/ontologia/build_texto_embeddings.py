#!/usr/bin/env python3
"""
RAG — Fase 2 (profundización): indexa texto libre de supervision.contratos /
contratos_liquidacion (objeto del contrato + observaciones jurídicas/técnicas) en
ontologia.contratos_texto_embeddings, usando embeddings locales (sentence-transformers).

Idempotente: solo (re)calcula embeddings de contenido nuevo o modificado (compara
texto exacto vs. lo ya indexado); seguro de re-correr tras cada actualización de
supervision.contratos.

Uso:
    venv/bin/python3 scripts/ontologia/build_texto_embeddings.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.ml.embeddings import embed_batch, MODEL_NAME  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

LONGITUD_MINIMA = 15  # descarta observaciones triviales tipo "N/A", "-", "ok"

# (esquema, tabla, columna de texto) a indexar.
CAMPOS_A_INDEXAR = [
    ("supervision", "contratos", "objeto_del_contrato"),
    ("supervision", "contratos", "observacion_juridica_frente_al_ep"),
    ("supervision", "contratos", "observaciones_dificultades_y_gestion_por_parte_del_juridico"),
    ("supervision", "contratos", "observaciones_dificultades_y_gestion_por_parte_del_tecnico"),
    ("supervision", "contratos", "observaciones_estado_del_inventario"),
    ("supervision", "contratos_liquidacion", "objeto_del_contrato"),
    ("supervision", "contratos_liquidacion", "observaciones_dificultades_y_gestion_por_parte_del_juridico"),
    ("supervision", "contratos_liquidacion", "observaciones_dificultades_y_gestion_por_parte_del_tecnico"),
    ("supervision", "contratos_ejecucion", "observacion_alerta_de_incumplimiento"),
    ("supervision", "contratos_ejecucion", "observacion_estado_de_incumplimiento"),
]


def _vector_literal(v):
    return "[" + ",".join(f"{x:.8f}" for x in v) + "]"


def indexar_campo(esquema: str, tabla: str, columna: str) -> None:
    filas = db_manager.query_df(f"""
        SELECT id, {columna} AS contenido
        FROM {esquema}.{tabla}
        WHERE {columna} IS NOT NULL AND length(btrim({columna})) >= {LONGITUD_MINIMA}
    """)
    if filas.empty:
        logger.info(f"{esquema}.{tabla}.{columna}: sin contenido indexable")
        return

    ya_indexado = db_manager.query_df(
        """
        SELECT fila_id, contenido FROM ontologia.contratos_texto_embeddings
        WHERE esquema_origen = %s AND tabla_origen = %s AND campo = %s
        """,
        (esquema, tabla, columna),
    )
    indexado_map = dict(zip(ya_indexado["fila_id"], ya_indexado["contenido"])) if not ya_indexado.empty else {}

    pendientes = [
        (int(row["id"]), str(row["contenido"]))
        for _, row in filas.iterrows()
        if indexado_map.get(int(row["id"])) != str(row["contenido"])
    ]
    if not pendientes:
        logger.info(f"{esquema}.{tabla}.{columna}: {len(filas)} filas, todas ya indexadas")
        return

    textos = [c for _, c in pendientes]
    vectores = embed_batch(textos)

    for (fila_id, contenido), vector in zip(pendientes, vectores):
        db_manager.execute_non_query(
            f"""
            INSERT INTO ontologia.contratos_texto_embeddings
                (esquema_origen, tabla_origen, fila_id, campo, contenido, embedding, modelo)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
            ON CONFLICT (esquema_origen, tabla_origen, fila_id, campo)
            DO UPDATE SET contenido = EXCLUDED.contenido,
                          embedding = EXCLUDED.embedding,
                          modelo = EXCLUDED.modelo,
                          actualizado_en = NOW()
            """,
            (esquema, tabla, fila_id, columna, contenido, _vector_literal(vector), MODEL_NAME),
        )

    logger.info(
        f"{esquema}.{tabla}.{columna}: {len(pendientes)} embeddings nuevos/actualizados "
        f"de {len(filas)} filas con contenido"
    )


def main() -> None:
    for esquema, tabla, columna in CAMPOS_A_INDEXAR:
        indexar_campo(esquema, tabla, columna)

    total = db_manager.query_df("SELECT count(*) AS n FROM ontologia.contratos_texto_embeddings")
    logger.info(f"Total embeddings en ontologia.contratos_texto_embeddings: {int(total['n'].iloc[0])}")


if __name__ == "__main__":
    main()
