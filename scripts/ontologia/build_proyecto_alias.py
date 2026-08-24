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
    en un solo string — no se descomponen aquí, solo se canonicalizan y se marcan
    es_compuesto=TRUE para que quede auditable, ver _es_valor_compuesto()).
  - fenoge.comunidades.numero_contrato (Fase 17 — 28 valores distintos, confirmado
    limpio: son números de contrato reales, sin filas de totales/basura, y es el
    grano correcto de "proyecto" en FENOGE — varias filas de `comunidad`
    /beneficiario comparten un mismo numero_contrato).

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
    ("fenoge", "comunidades", "numero_contrato", "fenoge"),
]


def _es_valor_compuesto(valor: str) -> bool:
    """Detecta strings multi-municipio en un solo campo (ej. colombia_solar.base.proyecto:
    "San Miguel, Valle del Guamuez,Villa Garzon,Puerto Guzman") — no se descompone, solo
    se marca como auditable (es_compuesto=TRUE), mismo criterio que geografia_alias."""
    return "," in valor


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


def _upsert_alias(esquema: str, tabla: str, columna: str, valor: str, proyecto_id: int, es_compuesto: bool) -> None:
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.proyecto_alias
            (esquema_origen, tabla_origen, columna_origen, valor_original, proyecto_id, es_compuesto, metodo)
        VALUES (%s, %s, %s, %s, %s, %s, 'exacto_normalizado')
        ON CONFLICT (esquema_origen, tabla_origen, columna_origen, valor_original, proyecto_id)
        DO UPDATE SET es_compuesto = EXCLUDED.es_compuesto
        """,
        (esquema, tabla, columna, valor, proyecto_id, es_compuesto),
    )


def resolver_fuente(esquema: str, tabla: str, columna: str, programa: str) -> None:
    valores = db_manager.query_df(f"""
        SELECT DISTINCT {columna} AS valor FROM {esquema}.{tabla}
        WHERE {columna} IS NOT NULL AND btrim({columna}) <> ''
    """)
    if valores.empty:
        logger.info(f"{esquema}.{tabla}.{columna}: sin proyectos")
        return

    resueltos, excluidos, compuestos = 0, 0, 0
    for _, row in valores.iterrows():
        valor = str(row["valor"]).strip()
        if valor.lower() in VALORES_NO_PROYECTO:
            excluidos += 1
            continue
        es_compuesto = _es_valor_compuesto(valor)
        proyecto_id = _upsert_dim_proyecto(valor, programa)
        _upsert_alias(esquema, tabla, columna, valor, proyecto_id, es_compuesto)
        resueltos += 1
        compuestos += int(es_compuesto)

    logger.info(
        f"{esquema}.{tabla}.{columna}: {resueltos} proyectos sembrados/resueltos "
        f"({excluidos} valores no-proyecto excluidos, {compuestos} multi-municipio marcados es_compuesto)"
    )


def resolver_geografia_fuente(esquema: str, tabla: str, columna: str) -> int:
    """Fase 23 Bloque 2: vincula cada proyecto con su(s) geografía(s) real(es),
    resolviendo departamento/municipio de la fila fuente vía la MISMA función
    ya usada por el resto de la ontología (f_resolver_geografia) — nunca
    intenta resolver valores es_compuesto (multi-municipio en un solo string),
    mismo principio que geografia_alias/empresa_alias."""
    filas = db_manager.query_df(f"""
        SELECT DISTINCT pa.proyecto_id, g.geografia_id
        FROM ontologia.proyecto_alias pa
        JOIN {esquema}.{tabla} t ON t.{columna} = pa.valor_original
        CROSS JOIN LATERAL ontologia.f_resolver_geografia(t.departamento, t.municipio) g
        WHERE pa.esquema_origen = %(esquema)s AND pa.tabla_origen = %(tabla)s
          AND pa.columna_origen = %(columna)s AND pa.es_compuesto = FALSE
    """, {"esquema": esquema, "tabla": tabla, "columna": columna})

    for _, row in filas.iterrows():
        db_manager.execute_non_query(
            """
            INSERT INTO ontologia.proyecto_geografia (proyecto_id, geografia_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (int(row["proyecto_id"]), int(row["geografia_id"])),
        )
    return len(filas)


def main() -> None:
    for esquema, tabla, columna, programa in FUENTES:
        resolver_fuente(esquema, tabla, columna, programa)

    total_vinculos = 0
    for esquema, tabla, columna, _programa in FUENTES:
        total_vinculos += resolver_geografia_fuente(esquema, tabla, columna)
    logger.info(f"ontologia.proyecto_geografia: {total_vinculos} vínculos proyecto↔geografía resueltos")

    total = db_manager.query_df("SELECT count(*) AS n FROM ontologia.dim_proyecto")
    logger.info(f"Total ontologia.dim_proyecto: {int(total['n'].iloc[0])}")


if __name__ == "__main__":
    main()
