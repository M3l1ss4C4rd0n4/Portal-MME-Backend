#!/usr/bin/env python3
"""
Ontología — Fase 7 Parte B: siembra ontologia.dim_proyecto y resuelve
ontologia.proyecto_alias.

"Proyecto" en contratos_or y "proyecto" en colombia_solar son entidades reales
distintas (contratos de normalización de redes vs. instalaciones solares) — no
hay una identidad "el mismo proyecto en ambos programas" que resolver por fuzzy
match, a diferencia de empresa (donde sí es la misma compañía apareciendo en
varios esquemas). Por eso dim_proyecto es único por (nombre_canonico, programa):
cada programa aporta sus propios proyectos, sin intentar cruzarlos entre sí.

Fuentes:
  - contratos_or.seguimiento_avance_fisico.nombre_proyecto_id (18 valores, 1 basura
    "Promedio Avance" excluida — fila de totales del Excel origen).
  - colombia_solar.base.proyecto (32 valores, texto libre; algunos multi-municipio
    en un solo string — no se descomponen aquí, solo se canonicalizan).

Uso:
    venv/bin/python3 scripts/ontologia/build_proyecto_alias.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# Valores que no son proyectos reales (filas de totales/resumen del Excel origen).
VALORES_NO_PROYECTO = {"promedio avance", ""}

FUENTES = [
    ("contratos_or", "seguimiento_avance_fisico", "nombre_proyecto_id", "contratos_or"),
    ("colombia_solar", "base", "proyecto", "colombia_solar"),
]


def _upsert_dim_proyecto(nombre: str, programa: str) -> int:
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.dim_proyecto (nombre_canonico, programa)
        VALUES (%s, %s)
        ON CONFLICT (nombre_canonico, programa) DO NOTHING
        """,
        (nombre, programa),
    )
    row = db_manager.query_df(
        "SELECT proyecto_id FROM ontologia.dim_proyecto WHERE nombre_canonico = %(n)s AND programa = %(p)s",
        {"n": nombre, "p": programa},
    )
    return int(row["proyecto_id"].iloc[0])


def _upsert_alias(esquema: str, tabla: str, columna: str, valor: str, proyecto_id: int) -> None:
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.proyecto_alias
            (esquema_origen, tabla_origen, columna_origen, valor_original, proyecto_id, metodo)
        VALUES (%s, %s, %s, %s, %s, 'exacto_normalizado')
        ON CONFLICT (esquema_origen, tabla_origen, columna_origen, valor_original, proyecto_id)
        DO NOTHING
        """,
        (esquema, tabla, columna, valor, proyecto_id),
    )


def resolver_fuente(esquema: str, tabla: str, columna: str, programa: str) -> None:
    valores = db_manager.query_df(f"""
        SELECT DISTINCT {columna} AS valor FROM {esquema}.{tabla}
        WHERE {columna} IS NOT NULL AND btrim({columna}) <> ''
    """)
    if valores.empty:
        logger.info(f"{esquema}.{tabla}.{columna}: sin proyectos")
        return

    resueltos, excluidos = 0, 0
    for _, row in valores.iterrows():
        valor = str(row["valor"]).strip()
        if valor.lower() in VALORES_NO_PROYECTO:
            excluidos += 1
            continue
        proyecto_id = _upsert_dim_proyecto(valor, programa)
        _upsert_alias(esquema, tabla, columna, valor, proyecto_id)
        resueltos += 1

    logger.info(
        f"{esquema}.{tabla}.{columna}: {resueltos} proyectos sembrados/resueltos "
        f"({excluidos} valores no-proyecto excluidos)"
    )


def main() -> None:
    for esquema, tabla, columna, programa in FUENTES:
        resolver_fuente(esquema, tabla, columna, programa)

    total = db_manager.query_df("SELECT count(*) AS n FROM ontologia.dim_proyecto")
    logger.info(f"Total ontologia.dim_proyecto: {int(total['n'].iloc[0])}")


if __name__ == "__main__":
    main()
