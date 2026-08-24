#!/usr/bin/env python3
"""
Ontología — Fase 11 Ronda 5 (+ Fase 13 Bloque B): clasifica
ontologia.informes_documentos.tema por patrón determinístico de nombre de
archivo / carpeta de origen (nunca por heurística de IA) — permite que la
búsqueda RAG filtre por tipo de documento en vez de depender solo de
similitud vectorial. Cobertura inicial (Ronda 5) limitada al dominio
sector_energetico; esta ronda (Fase 13) extiende la clasificación a
comunidades energéticas y documentación interna PMO.

Uso:
    venv/bin/python3 scripts/ontologia/clasificar_tema_informes.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# (condición SQL, tema) — se evalúan en orden, la primera que matchee gana.
PATRONES = [
    # %% escapa el literal '%' de ILIKE frente al formateo de parámetros de psycopg2.
    ("nombre_archivo ILIKE '%%SeguimientoDespacho%%'", "despacho"),
    ("nombre_archivo ILIKE '%%VariablesHidrologicas%%'", "hidrologia"),
    ("nombre_archivo ILIKE '%%VariablesOperativas%%'", "operativas"),
    ("carpeta_origen = 'BOLETINES_XM'", "panorama_climatico"),
    (
        "(nombre_archivo ILIKE 'GUIA_ESTADOS_Y_ALERTAS%%' "
        "OR nombre_archivo ILIKE 'INFORME_DETALLADO DEL SISTEMA DE ALERTAS%%')",
        "metodologia_alertas",
    ),
    # Fase 13 Bloque B — extensión más allá de sector_energetico.
    ("carpeta_origen = 'ACTAS_ELECTROCAQUETA'", "comunidades"),
    ("nombre_archivo ILIKE '%%Comunidades Energ%%'", "comunidades"),
    (
        "(nombre_archivo ILIKE 'Diagnostico_Tableros%%' "
        "OR nombre_archivo ILIKE 'Propuesta Estructura Funcional%%')",
        "pmo_interno",
    ),
    # Ampliación RAG (2026-08-05) — Comunidades/Colombia Solar/Subsidios,
    # ver scripts/ontologia/build_informes_embeddings.py::CARPETAS_*.
    ("carpeta_origen ILIKE 'COMUNIDADES_%%'", "comunidades"),
    ("carpeta_origen ILIKE 'COLOMBIA_SOLAR_%%'", "colombia_solar"),
    ("carpeta_origen ILIKE 'SUBSIDIOS_%%'", "subsidios"),
    # Fase 23 Bloque 2 — COMUNIDADES_ESQUEMAS_COMERCIALIZACION ya matchea el
    # patrón COMUNIDADES_% de arriba, sin necesitar una regla nueva.
    ("carpeta_origen ILIKE 'PROYECTOS_ESTRATEGICOS_%%'", "proyectos_estrategicos"),
    # Fase 29 — Informe de Empalme (único documento con botón de descarga real
    # del portal que quedaba sin indexar; ver build_informes_embeddings.py::_indexar_informe_empalme).
    ("carpeta_origen = 'INFORME_EMPALME'", "informe_empalme"),
    # Fase 33 — estudios de planeación públicos de XM (corto/mediano/largo
    # plazo, flexibilidad del SIN, senda de referencia); ver
    # build_informes_embeddings.py::_indexar_planeacion_xm.
    ("carpeta_origen ILIKE 'PLANEACION_XM_%%'", "planeacion_xm"),
    # Fase 35 — Boletín Energético XM (356 PDFs reales, distinto de los
    # demás sub-temas de Planeación XM: es un panorama semanal general del
    # SIN, no un estudio técnico puntual). Se aplica DESPUÉS del patrón
    # genérico PLANEACION_XM_%% de arriba, para que gane sobre él (cada
    # UPDATE sobreescribe `tema` para las filas que matchea, en orden).
    ("carpeta_origen = 'PLANEACION_XM_BOLETIN'", "boletin_energetico_xm"),
    # Fase 36 — "Informe del Despacho" diario del repositorio público de XM
    # (build_informes_embeddings.py::_indexar_infodespacho_xm) — mismo dominio
    # que 'despacho' (novedades de consignaciones, indisponibilidades por
    # equipo), reutiliza el tema existente en vez de crear uno nuevo.
    ("carpeta_origen = 'INFODESPACHO_XM'", "despacho"),
    # Fase 37 — normativa CREG (resoluciones/circulares), indexada desde
    # gestornormativo.creg.gov.co — ver build_informes_embeddings.py::_indexar_creg_normativa.
    # Un solo tema para las 3 carpetas (corpus general + las 8 núcleo).
    ("carpeta_origen IN ('CREG_RESOLUCIONES', 'CREG_CIRCULARES', 'CREG_RESOLUCIONES_NUCLEO')", "creg_normativa"),
    # Fase 37 (continuación 2026-08-20) — normativa UPME + Ministerio de
    # Minas y Energía, misma plataforma Alejandría que la CREG — ver
    # build_informes_embeddings.py::_indexar_upme_mme_normativa. Tema propio
    # (no reutiliza 'creg_normativa') porque son entidades distintas de la CREG.
    ("carpeta_origen IN ('UPME_RESOLUCIONES', 'UPME_CIRCULARES', 'MME_RESOLUCIONES', 'MME_CIRCULARES')", "normativa_upme_mme"),
    # Fase 37 (continuación 2026-08-20) — informes/estudios técnicos de UPME
    # (Plan Energético Nacional, Boletín Estadístico, estudios sectoriales) —
    # ver build_informes_embeddings.py::_indexar_publicaciones_upme. Tema
    # propio, distinto de 'normativa_upme_mme' (contenido narrativo/analítico,
    # no legal).
    ("carpeta_origen = 'UPME_PUBLICACIONES'", "publicaciones_upme"),
    # Fase 37 (continuación 2026-08-20) — contenido misional propio del
    # sitio del Ministerio (ej. Plan de Expansión de Referencia
    # Generación-Transmisión) — ver build_informes_embeddings.py::_indexar_publicaciones_mme.
    ("carpeta_origen = 'MME_PLANES_EXPANSION'", "publicaciones_mme"),
    # Fase 37 (continuación 2026-08-21) — normativa EN TRÁMITE (no vigente
    # todavía) — temas propios y distintos de 'creg_normativa'/
    # 'normativa_upme_mme' a propósito, para que el Asistente pueda
    # distinguir "ley vigente" de "proyecto en consulta pública".
    ("carpeta_origen = 'CREG_PROYECTOS_RESOLUCION'", "creg_proyectos_resolucion"),
    ("carpeta_origen = 'MME_CONCEPTOS'", "mme_conceptos_juridicos"),
]


def main() -> None:
    total = 0
    for condicion, tema in PATRONES:
        filas = db_manager.execute_non_query(
            f"UPDATE ontologia.informes_documentos SET tema = %(tema)s WHERE {condicion}",
            {"tema": tema},
        )
        logger.info(f"tema='{tema}': {condicion}")
        total += 1

    resumen = db_manager.query_df(
        "SELECT tema, count(*) AS n FROM ontologia.informes_documentos GROUP BY 1 ORDER BY 1 NULLS LAST"
    )
    logger.info(f"Resumen de clasificación:\n{resumen.to_string()}")


if __name__ == "__main__":
    main()
