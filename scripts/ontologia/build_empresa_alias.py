#!/usr/bin/env python3
"""
Ontología — Fase 1: siembra ontologia.dim_empresa y resuelve ontologia.empresa_alias.

Semilla: subsidios.subsidios_empresas (única tabla con NIT/código SUI reales).

Resolución:
  - supervision.contratos.nit_ejecutor -> match determinístico por NIT (alta confianza).
  - Todo lo demás (contratos_or.ejecutor x5, fenoge.comunidades.contratista,
    colombia_solar.contratista_entidad/or_generador/contratista,
    supervision.contratos_liquidacion.ejecutor) -> texto libre SIN NIT, fuzzy matching
    de nombre vía pg_trgm. Nunca se auto-acepta en vistas de producción: todo queda
    metodo='match_nombre_fuzzy' con score de confianza, requiere revisión humana antes
    de usarse para atribuir un contrato a una empresa.

Uso:
    venv/bin/python3 scripts/ontologia/build_empresa_alias.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# Umbral mínimo de similitud (trigram) para siquiera proponer un candidato fuzzy.
# Por debajo de esto, se marca sin_resolver en vez de un match de baja calidad.
UMBRAL_SIMILITUD = 0.35

# (esquema, tabla, columna) de texto libre sin NIT -> resolución solo por fuzzy matching.
TABLAS_FUZZY = [
    ("contratos_or", "cronograma_contractual", "ejecutor"),
    ("contratos_or", "cronograma_obra", "ejecutor"),
    ("contratos_or", "seguimiento_avance_documental", "ejecutor"),
    ("contratos_or", "seguimiento_avance_fisico", "ejecutor"),
    ("contratos_or", "seguimiento_electrocqueta", "ejecutor"),
    ("supervision", "contratos_liquidacion", "ejecutor"),
    ("fenoge", "comunidades", "contratista"),
    ("colombia_solar", "base", "contratista_entidad"),
    ("colombia_solar", "base_general_or_inicial", "or_generador"),
    ("colombia_solar", "seguimiento_diario", "contratista"),
]


def seed_dim_empresa() -> int:
    """Siembra ontologia.dim_empresa desde subsidios.subsidios_empresas (idempotente)."""
    query = """
        INSERT INTO ontologia.dim_empresa (nit, codigo_sui, nombre_oficial, sigla)
        SELECT DISTINCT ON (codigo_sui)
               nit, codigo_sui, nombre_prestador, sigla
        FROM subsidios.subsidios_empresas
        WHERE codigo_sui IS NOT NULL AND btrim(codigo_sui) <> ''
        ORDER BY codigo_sui
        ON CONFLICT (codigo_sui) WHERE codigo_sui IS NOT NULL AND codigo_sui <> '' DO NOTHING
    """
    db_manager.execute_non_query(query)
    df = db_manager.query_df("SELECT count(*) AS n FROM ontologia.dim_empresa")
    total = int(df["n"].iloc[0])
    logger.info(f"ontologia.dim_empresa: {total} empresas sembradas")
    return total


def _upsert_alias(esquema, tabla, columna, valor, empresa_id, metodo, confianza=None) -> None:
    # DO UPDATE (no DO NOTHING): permite que una corrida posterior con mejor lógica
    # de resolución (ej. el fix de "también buscar por sigla") mejore una fila que
    # había quedado sin_resolver en una corrida anterior — DO NOTHING la habría
    # dejado congelada para siempre.
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.empresa_alias
            (esquema_origen, tabla_origen, columna_origen, valor_original,
             empresa_id, metodo, confianza)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (esquema_origen, tabla_origen, columna_origen, valor_original)
        DO UPDATE SET empresa_id = EXCLUDED.empresa_id, metodo = EXCLUDED.metodo,
                      confianza = EXCLUDED.confianza
        WHERE ontologia.empresa_alias.metodo IN ('sin_resolver', 'match_nombre_fuzzy')
        """,
        (esquema, tabla, columna, valor, empresa_id, metodo, confianza),
    )


def resolver_supervision_por_nit() -> None:
    """supervision.contratos.nit_ejecutor -> match determinístico por NIT."""
    filas = db_manager.query_df("""
        SELECT DISTINCT ejecutor, ROUND(nit_ejecutor)::text AS nit_txt
        FROM supervision.contratos
        WHERE nit_ejecutor IS NOT NULL AND ejecutor IS NOT NULL
    """)
    resueltos, pendientes = 0, 0
    for _, row in filas.iterrows():
        ejecutor, nit_txt = str(row["ejecutor"]), str(row["nit_txt"])
        match = db_manager.query_df(
            "SELECT empresa_id FROM ontologia.dim_empresa WHERE nit_normalizado = %s",
            (nit_txt,),
        )
        if len(match) == 1:
            _upsert_alias("supervision", "contratos", "ejecutor", ejecutor,
                          int(match["empresa_id"].iloc[0]), "match_nit")
            resueltos += 1
        else:
            _upsert_alias("supervision", "contratos", "ejecutor", ejecutor, None, "sin_resolver")
            pendientes += 1
    logger.info(f"supervision.contratos: {resueltos} resueltos por NIT, {pendientes} sin NIT coincidente")


def resolver_fuzzy() -> None:
    """Texto libre sin NIT -> mejor candidato por similitud de trigramas, sin auto-aceptar."""
    for esquema, tabla, columna in TABLAS_FUZZY:
        valores = db_manager.query_df(f"""
            SELECT DISTINCT {columna} AS valor FROM {esquema}.{tabla}
            WHERE {columna} IS NOT NULL AND btrim({columna}) <> ''
        """)
        if valores.empty:
            continue
        resueltos, pendientes = 0, 0
        for _, row in valores.iterrows():
            valor = str(row["valor"])
            # Busca también por sigla (ej. "GENSA") — no solo nombre_oficial (ej.
            # "GESTION ENERGETICA S.A. ESP"). Mismo fix ya aplicado a
            # EmpresaRepository.buscar_empresas() tras encontrar que la búsqueda
            # de "GENSA" no encontraba la empresa real de 315 contratos.
            candidato = db_manager.query_df(
                """
                SELECT empresa_id, nombre_oficial,
                       GREATEST(
                           similarity(nombre_oficial, %s),
                           similarity(coalesce(sigla, ''), %s)
                       ) AS score
                FROM ontologia.dim_empresa
                WHERE similarity(nombre_oficial, %s) > %s
                   OR similarity(coalesce(sigla, ''), %s) > %s
                ORDER BY score DESC
                LIMIT 1
                """,
                (valor, valor, valor, UMBRAL_SIMILITUD, valor, UMBRAL_SIMILITUD),
            )
            if not candidato.empty:
                _upsert_alias(esquema, tabla, columna, valor,
                              int(candidato["empresa_id"].iloc[0]),
                              "match_nombre_fuzzy",
                              round(float(candidato["score"].iloc[0]), 2))
                resueltos += 1
            else:
                _upsert_alias(esquema, tabla, columna, valor, None, "sin_resolver")
                pendientes += 1
        logger.info(
            f"{esquema}.{tabla}.{columna}: {resueltos} candidatos fuzzy propuestos "
            f"(requieren revisión), {pendientes} sin candidato razonable"
        )


def main() -> None:
    seed_dim_empresa()
    resolver_supervision_por_nit()
    resolver_fuzzy()


if __name__ == "__main__":
    main()
