#!/usr/bin/env python3
"""
Refresco diario de la capa de ontología — corre después del ETL SharePoint (4:02 AM):

1. Re-resuelve alias de geografía/empresa (nuevos valores de departamento/municipio/
   ejecutor que hayan llegado con la carga del día).
2. Actualiza embeddings de texto libre (contratos nuevos/modificados).
3. REFRESH MATERIALIZED VIEW CONCURRENTLY de las 8 vistas de ontologia — sin esto,
   la ontología queda congelada en el estado del día que se sembró (Fase 1).

CONCURRENTLY no bloquea lecturas (requiere los índices únicos ya creados en la
migración 008), apropiado para correr en horario en que el portal puede tener uso.

Uso:
    venv/bin/python3 scripts/ontologia/refresh_ontologia.py
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402
from infrastructure.observability.lineage import registrar_paso  # noqa: E402

logger = get_logger(__name__)

VISTAS_MATERIALIZADAS = [
    "ontologia.mv_comunidades_geo",
    "ontologia.mv_contratos_or_fisico_geo",
    "ontologia.mv_contratos_or_documental_geo",
    "ontologia.mv_fenoge_geo",
    "ontologia.mv_colombia_solar_geo",
    "ontologia.mv_subsidios_mapa_geo",
    "ontologia.mv_supervision_geo",
    "ontologia.mv_resumen_departamento",
]


def _recrear_vistas_faltantes() -> None:
    """
    Auto-reparación: algunos ETLs pre-existentes (ej. etl_sharepoint_sync.py sobre
    comunidades.base y supervision.*) recargan sus tablas con
    `DROP TABLE ... CASCADE` en vez de TRUNCATE — eso borra en cascada cualquier
    vista materializada construida sobre esa tabla (confirmado en vivo: 3 de las
    8 vistas + mv_resumen_departamento desaparecieron así el 2026-08-02, sin
    ningún error visible hasta que el linaje lo expuso). Como la migración 008 usa
    CREATE MATERIALIZED VIEW IF NOT EXISTS en todas partes, re-aplicarla es
    siempre seguro/idempotente y recrea solo lo que falte.
    """
    existentes = db_manager.query_df(
        "SELECT matviewname FROM pg_matviews WHERE schemaname = 'ontologia'"
    )
    nombres_existentes = set(existentes["matviewname"]) if not existentes.empty else set()
    esperadas = {v.split(".")[1] for v in VISTAS_MATERIALIZADAS}
    faltantes = esperadas - nombres_existentes

    if not faltantes:
        return

    logger.warning(
        f"[REFRESH] Vistas materializadas faltantes (probable DROP CASCADE de un "
        f"ETL externo): {sorted(faltantes)} — recreando desde las migraciones"
    )
    # Reaplicar 008 (definición original) seguida de cada migración que desde
    # entonces redefinió alguna de estas vistas (014, 015, ...) — nunca solo
    # 008: si solo se reaplicara esa, un DROP CASCADE revertiría en silencio
    # los fixes posteriores (ej. 014 corrigió un nombre duplicado, 015 corrigió
    # un guion bajo en comunidades.departamento) la próxima vez que un ETL
    # externo tumbe estas vistas. Todas usan DROP/CREATE IF (NOT) EXISTS, así
    # que reaplicar la secuencia completa siempre converge al estado correcto.
    migraciones_dir = Path(__file__).resolve().parents[2] / "sql" / "migrations"
    migraciones = [
        migraciones_dir / "008_ontologia_vistas_materializadas.sql",
        migraciones_dir / "014_ontologia_fix_nombre_departamento_duplicado.sql",
        migraciones_dir / "015_ontologia_fix_guion_bajo_departamento.sql",
    ]
    with registrar_paso("refresh_vistas", "recrear_vistas_faltantes") as paso:
        for migracion in migraciones:
            resultado = subprocess.run(
                ["psql", "-h", "localhost", "-U", "postgres", "-d", "portal_energetico",
                 "-v", "ON_ERROR_STOP=1", "-f", str(migracion)],
                capture_output=True, text=True,
            )
            if resultado.returncode != 0:
                raise RuntimeError(
                    f"Recreación de vistas falló en {migracion.name}: {resultado.stderr[-500:]}"
                )
        paso.filas(len(faltantes))
    logger.info(f"[REFRESH] Vistas recreadas: {sorted(faltantes)}")


def refrescar_vistas() -> None:
    try:
        _recrear_vistas_faltantes()
    except Exception as e:
        logger.error(f"[REFRESH] No se pudieron recrear vistas faltantes: {e}")

    for vista in VISTAS_MATERIALIZADAS:
        try:
            with registrar_paso("refresh_vistas", vista) as paso:
                db_manager.execute_non_query(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {vista}")
                paso.filas(1)
            logger.info(f"[REFRESH] {vista} OK")
        except Exception as e:
            # Nunca dejar que una vista fallida tumbe el refresh de las demás.
            logger.error(f"[REFRESH] {vista} FALLÓ: {e}")


def main() -> None:
    logger.info("[ONTOLOGIA] Iniciando refresco diario")

    from scripts.ontologia.build_geografia_alias import (
        seed_dim_geografia, resolver_pares_depto_municipio,
        resolver_solo_municipio, resolver_subsidios_empresas,
    )
    with registrar_paso("geografia_alias", "seed_dim_geografia") as paso:
        paso.filas(seed_dim_geografia())
    with registrar_paso("geografia_alias", "resolver_pares_depto_municipio"):
        resolver_pares_depto_municipio()
    with registrar_paso("geografia_alias", "resolver_solo_municipio"):
        resolver_solo_municipio()
    with registrar_paso("geografia_alias", "resolver_subsidios_empresas"):
        resolver_subsidios_empresas()

    from scripts.ontologia.build_empresa_alias import (
        seed_dim_empresa, resolver_supervision_por_nit, resolver_fuzzy,
    )
    with registrar_paso("empresa_alias", "seed_dim_empresa") as paso:
        paso.filas(seed_dim_empresa())
    with registrar_paso("empresa_alias", "resolver_supervision_por_nit"):
        resolver_supervision_por_nit()
    with registrar_paso("empresa_alias", "resolver_fuzzy"):
        resolver_fuzzy()

    from scripts.ontologia.build_texto_embeddings import main as indexar_embeddings
    with registrar_paso("texto_embeddings", "indexar_embeddings"):
        indexar_embeddings()

    # Aislado en su propio try/except (a diferencia de los pasos anteriores):
    # depende de una llamada de red externa (Microsoft Graph/SharePoint), con más
    # superficie de falla que los pasos anteriores (100% locales a Postgres) — un
    # timeout o token vencido no debe bloquear el refresh de las vistas materializadas,
    # que sí son críticas para /vista-departamental y /salud-datos.
    try:
        from scripts.ontologia.build_informes_embeddings import main as indexar_informes
        with registrar_paso("informes_embeddings", "indexar_informes_sharepoint"):
            indexar_informes()
    except Exception as e:
        logger.error(f"[ONTOLOGIA] Indexación de informes SharePoint falló: {e}")

    refrescar_vistas()
    logger.info("[ONTOLOGIA] Refresco diario completo")


if __name__ == "__main__":
    main()
