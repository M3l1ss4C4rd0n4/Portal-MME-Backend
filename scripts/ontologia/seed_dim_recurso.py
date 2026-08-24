#!/usr/bin/env python3
"""
Ontología — Fase 13 Bloque B: siembra ontologia.dim_recurso 1:1 desde
sector_energetico.catalogos (catalogo='ListadoRecursos') — copia
determinística, sin curación manual necesaria porque la fuente ya es un
catálogo limpio sincronizado desde la API de XM (código único por recurso).

Fase 23 (2026-08-06): `capacidad` viene NULL en el 100% de las filas de
ListadoRecursos (la fuente nunca la trae) — se cruza además con la métrica
`CapEfecNeta` de sector_energetico.metrics (292.976 filas, 2.099/2.266
recursos con match directo por código), tomando el valor más reciente por
recurso. Verificado contra el catálogo oficial de XM
(pydataxm.ReadDB().all_variables(), MetricId='CapEfecNeta') que la unidad
real es **kW**, no MW como aparece (mal etiquetado) en la columna `unidad`
de sector_energetico.metrics — confirmado además con valores reales
conocidos (CTG1/Cartagena 1: 52000 → 52 MW; GVIO/Guavio: 1.250.000 →
1.250 MW, ambos coinciden con la capacidad pública real de esas plantas).
Se divide entre 1000 al sembrar. `COALESCE` con `catalogo.capacidad` primero
por si XM alguna vez empieza a publicarla directamente en ListadoRecursos.

Uso:
    venv/bin/python3 scripts/ontologia/seed_dim_recurso.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def main() -> None:
    recursos = db_manager.query_df("""
        SELECT codigo, nombre, tipo, region, capacidad, fecha_actualizacion
        FROM sector_energetico.catalogos
        WHERE catalogo = 'ListadoRecursos'
    """)
    logger.info(f"{len(recursos)} recursos encontrados en sector_energetico.catalogos")

    cap_efec_neta = db_manager.query_df("""
        SELECT DISTINCT ON (recurso) recurso, valor_gwh AS cap_kw
        FROM sector_energetico.metrics
        WHERE metrica = 'CapEfecNeta'
        ORDER BY recurso, fecha DESC
    """)
    cap_por_codigo = {
        row["recurso"]: float(row["cap_kw"]) / 1000.0
        for _, row in cap_efec_neta.iterrows()
        if row["cap_kw"] == row["cap_kw"]  # NaN check
    }
    logger.info(f"{len(cap_por_codigo)} recursos con capacidad real (CapEfecNeta, convertida kW→MW)")

    n_desde_metrics = 0
    for _, r in recursos.iterrows():
        capacidad_catalogo = r["capacidad"] if r["capacidad"] == r["capacidad"] else None  # NaN check
        capacidad = capacidad_catalogo
        if capacidad is None and r["codigo"] in cap_por_codigo:
            capacidad = cap_por_codigo[r["codigo"]]
            n_desde_metrics += 1

        db_manager.execute_non_query(
            """
            INSERT INTO ontologia.dim_recurso
                (codigo_xm, nombre, tipo, region, capacidad, actualizado_en)
            VALUES (%(codigo)s, %(nombre)s, %(tipo)s, %(region)s, %(capacidad)s, %(actualizado)s)
            ON CONFLICT (codigo_xm) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                tipo = EXCLUDED.tipo,
                region = EXCLUDED.region,
                capacidad = EXCLUDED.capacidad,
                actualizado_en = EXCLUDED.actualizado_en
            """,
            {
                "codigo": r["codigo"],
                "nombre": r["nombre"],
                "tipo": r["tipo"],
                "region": r["region"],
                "capacidad": capacidad,
                "actualizado": r["fecha_actualizacion"],
            },
        )

    logger.info(f"{n_desde_metrics} recursos completados con capacidad real desde CapEfecNeta")
    total = db_manager.query_df("SELECT count(*) AS n FROM ontologia.dim_recurso")
    logger.info(f"ontologia.dim_recurso: {int(total['n'].iloc[0])} filas totales tras la siembra")


if __name__ == "__main__":
    main()
