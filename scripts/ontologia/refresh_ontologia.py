#!/usr/bin/env python3
"""
Refresco diario de la capa de ontología — corre después del ETL SharePoint (4:02 AM):

1. Re-resuelve alias de geografía/empresa (nuevos valores de departamento/municipio/
   ejecutor que hayan llegado con la carga del día).
2. Actualiza embeddings de texto libre (contratos nuevos/modificados).
3. Re-siembra dim_metrica/dim_recurso (Fase 13), clasifica tema de informes nuevos
   y resuelve menciones de recurso en el texto (Fase 13/14).
4. REFRESH MATERIALIZED VIEW CONCURRENTLY de las 9 vistas de ontologia — sin esto,
   la ontología queda congelada en el estado del día que se sembró (Fase 1).

CONCURRENTLY no bloquea lecturas (requiere los índices únicos ya creados, ver
sql/ontologia_vistas_canonicas.sql), apropiado para correr en horario en que
el portal puede tener uso.

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
    "ontologia.mv_resumen_municipio",
]


VISTAS_CANONICAS_SQL = Path(__file__).resolve().parents[2] / "sql" / "ontologia_vistas_canonicas.sql"


def _recrear_vistas_faltantes() -> None:
    """
    Auto-reparación: algunos ETLs pre-existentes (ej. etl_sharepoint_sync.py sobre
    comunidades.base y supervision.*) recargan sus tablas con
    `DROP TABLE ... CASCADE` en vez de TRUNCATE — eso borra en cascada cualquier
    vista materializada construida sobre esa tabla (confirmado en vivo, repetidas
    veces). Fase 18: en vez de reaplicar la cadena histórica creciente de
    migraciones (008→...→029, cada corrida tardaba minutos — insostenible para
    un sanador que corre cada 5 min, y se encontró en vivo que una corrida
    interrumpida a medias podía dejar vistas sin su índice único), se aplica un
    único archivo canónico (`sql/ontologia_vistas_canonicas.sql`) con la
    definición *actual* de las 9 vistas, envuelto en una transacción — segundos,
    no minutos, y sin estado a medias posible (todo o nada). Ver el encabezado
    de ese archivo: toda migración futura que cambie una de estas 9 vistas debe
    actualizarlo también.
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
        f"ETL externo): {sorted(faltantes)} — recreando desde {VISTAS_CANONICAS_SQL.name}"
    )
    with registrar_paso("refresh_vistas", "recrear_vistas_faltantes") as paso:
        resultado = subprocess.run(
            ["psql", "-h", "localhost", "-U", "postgres", "-d", "portal_energetico",
             "-v", "ON_ERROR_STOP=1", "-f", str(VISTAS_CANONICAS_SQL)],
            capture_output=True, text=True,
        )
        if resultado.returncode != 0:
            raise RuntimeError(
                f"Recreación de vistas falló: {resultado.stderr[-500:]}"
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

    # Fase 17: dim_proyecto nunca estaba conectado al refresh diario (gap
    # operacional encontrado, no solo de cobertura) — 100% local a Postgres,
    # igual que geografia_alias/empresa_alias, no requiere aislarse en try/except.
    from scripts.ontologia.build_proyecto_alias import main as resolver_proyectos
    with registrar_paso("proyecto_alias", "build_proyecto_alias"):
        resolver_proyectos()

    from scripts.ontologia.build_texto_embeddings import main as indexar_embeddings
    with registrar_paso("texto_embeddings", "indexar_embeddings"):
        indexar_embeddings()

    # Catálogos de métricas/recursos (Fase 13/14) — 100% locales, idempotentes
    # (ON CONFLICT DO UPDATE), no dependen de red. Se re-siembran cada día para
    # que un cambio de código (ej. una métrica nueva agregada al script) se
    # aplique solo, sin depender de que alguien lo corra a mano.
    from scripts.ontologia.seed_dim_metrica import main as seed_metricas
    with registrar_paso("dim_metrica", "seed_dim_metrica"):
        seed_metricas()

    from scripts.ontologia.seed_dim_recurso import main as seed_recursos
    with registrar_paso("dim_recurso", "seed_dim_recurso"):
        seed_recursos()

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

    # Clasificación por tema + resolución de menciones de recursos (Fase 13
    # Ronda 5 / profundización) — dependen de que indexar_informes ya haya
    # corrido (documentos/chunks nuevos del día), por eso van después. Aislados
    # igual que el paso anterior: si fallan, no deben bloquear refrescar_vistas().
    try:
        from scripts.ontologia.clasificar_tema_informes import main as clasificar_temas
        with registrar_paso("informes_tema", "clasificar_tema_informes"):
            clasificar_temas()
    except Exception as e:
        logger.error(f"[ONTOLOGIA] Clasificación de tema de informes falló: {e}")

    try:
        from scripts.ontologia.resolver_recurso_mencion import main as resolver_menciones
        with registrar_paso("recurso_mencion", "resolver_recurso_mencion"):
            resolver_menciones()
    except Exception as e:
        logger.error(f"[ONTOLOGIA] Resolución de menciones de recursos falló: {e}")

    # Fase 37 Parte B — vigilancia de las 8 resoluciones CREG núcleo que
    # sustentan core/umbrales_oficiales.py: depende de que indexar_informes
    # ya haya corrido (resoluciones/circulares recientes indexadas ese día),
    # por eso va después. Aislado igual que los pasos anteriores — un fallo
    # aquí no debe bloquear refrescar_vistas().
    try:
        from scripts.ontologia.vigilancia_normativa_creg import main as vigilar_normativa_creg
        with registrar_paso("vigilancia_normativa_creg", "vigilancia_normativa_creg"):
            vigilar_normativa_creg()
    except Exception as e:
        logger.error(f"[ONTOLOGIA] Vigilancia normativa CREG falló: {e}")

    # Fase 39, ítem C.2 (automatizado a pedido del usuario 2026-08-25): chequeo
    # de sincronía Python↔TypeScript de los umbrales oficiales — antes era
    # manual, exactamente el motivo por el que la regla derogada del 70% (y
    # luego el bug del "ALERTA colapsado") persistieron sin que nadie lo
    # notara. Aislado en su propio try/except: invoca `npx ts-node` como
    # subproceso (portal-direccion-mme), con más superficie de falla que los
    # pasos 100% locales a Postgres de arriba — un fallo aquí no debe
    # bloquear el refresh de las vistas materializadas.
    try:
        from scripts.verificar_sincronia_umbrales import main as verificar_sincronia
        with registrar_paso("sincronia_umbrales", "verificar_sincronia_umbrales"):
            rc = verificar_sincronia()
            if rc != 0:
                logger.error(
                    f"[ONTOLOGIA] Sincronía Python↔TypeScript con discrepancias "
                    f"(rc={rc}) — ver detalle en logs con prefijo [SINCRONIA_UMBRALES]."
                )
    except Exception as e:
        logger.error(f"[ONTOLOGIA] Chequeo de sincronía Python↔TypeScript falló: {e}")

    refrescar_vistas()
    logger.info("[ONTOLOGIA] Refresco diario completo")


if __name__ == "__main__":
    main()
