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

Fase 17 (Gap 3) agrega dos fuentes más de resolución:
  - seed_dim_empresa_desde_supervision(): dim_empresa solo se sembraba desde
    subsidios_empresas — 35 de 41 NITs reales de supervision.contratos no
    estaban catalogados, forzando fuzzy matching débil en vez de NIT
    determinístico. NITs con más de un nombre de ejecutor asociado se excluyen
    del seed automático (nunca se elige a ciegas cuál nombre es el correcto) —
    salvo el caso curado AMBIGUOS_CURADOS, verificado como la misma empresa con
    2 grafías. Un caso real verificado NO se cura (NIT 860063875: EMCALI y
    ENEL COLOMBIA son empresas genuinamente distintas, ninguna con NIT ya
    registrado en dim_empresa) — queda sin_resolver a propósito.
  - curar_empresas_sin_nit(): ~20 razones sociales de fenoge/colombia_solar
    confirmadas sin NIT en ninguna fuente (consorcios/uniones temporales/IPSE)
    se registran como nuevas dim_empresa, metodo='curado_manual'. "Total"
    (fila de totales de Excel) y "FENOGE" (nombre del programa, no un
    contratista real) quedan sin_resolver intencionalmente.

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
    # Fase 23 Bloque 2 — habilita la arista "interventor_de" en graph_service.py
    # (267 entidades reales, 81% de supervision.contratos con este campo poblado,
    # nunca antes resuelto contra dim_empresa).
    ("supervision", "contratos", "interventoria"),
]

# NITs con más de un nombre de ejecutor asociado en supervision.contratos,
# verificados a mano como la MISMA empresa con 2 grafías distintas — cualquier
# NIT ambiguo que NO esté aquí se excluye del seed automático (ver
# seed_dim_empresa_desde_supervision), nunca se elige un nombre a ciegas.
AMBIGUOS_CURADOS = {
    "846000553": "EMPRESA DE ENERGIA DEL PUTUMAYO S.A. E.S.P.",  # alias: "EEBP S.A. E.S.P."
}

# "EMCALI E.I.C.E. E.S.P." tenía 3 NITs distintos en supervision.contratos
# (843000057, 860063875, 890399003) — ejecutor con NIT ambiguo, nunca se
# resuelve automáticamente (ver _ejecutores_con_nit_ambiguo). Verificado
# externamente cuál es el NIT real de cada empresa involucrada (no adivinado):
# EMCALI = 890399003 (Concejo de Cali, concejodecali.gov.co/descargar.php?
# idFile=16164, "EMCALI EICE. ESP. NIT 890 399 003 4"); ENEL COLOMBIA =
# 860063875 (RUES vía empresas.larepublica.co/.../enel-colombia-s-a-e-s-p-
# 860063875, DataCrédito, documentación propia de fusión de Enel abril 2022).
# 843000057 pertenece de hecho a otra empresa real ya catalogada ("EMPRESA DE
# ENERGIA DEL GUAINIA..."), confirmado error de digitación en el dato origen
# — NUNCA se usa. Con esto, "EMCALI E.I.C.E. E.S.P." y "ENEL COLOMBIA S.A.
# E.S.P." como VALORES DE TEXTO se resuelven de forma segura a su NIT real,
# vía _upsert_alias directo (no vía el flujo de NIT-por-fila, que seguiría
# viendo 3 NITs asociados al mismo texto y los trataría como ambiguos).
EJECUTORES_NIT_VERIFICADO_EXTERNAMENTE = {
    "EMCALI E.I.C.E. E.S.P.": "890399003",
    "ENEL COLOMBIA S.A. E.S.P.": "860063875",
}

# Razones sociales confirmadas SIN NIT en ninguna fuente (fenoge.comunidades.
# contratista, colombia_solar.*contratista*) — consorcios/uniones temporales/
# IPSE reales, no catalogados porque dim_empresa solo se sembraba desde
# subsidios_empresas (prestadores de servicios públicos, universo distinto).
# valor_original -> nombre_oficial canónico (normaliza solo puntuación/espacios
# de variantes del mismo valor, ej. "ONE ENERGY SOLUTIONS." vs sin punto).
EMPRESAS_NUEVAS_CURADAS = {
    "COENERGIA": "COENERGIA",
    "CONSORCIO DESARROLLO SOLAR": "CONSORCIO DESARROLLO SOLAR",
    "CONSORCIO SOLAREEM": "CONSORCIO SOLAREEM",
    "CONSORCIO TRANSFORMACIÓN ENERGÉTICA.": "CONSORCIO TRANSFORMACIÓN ENERGÉTICA",
    "CRIC": "CRIC",
    "GRUPO PLANETA AMBIENTAL INVERSIONES S.A.S.": "GRUPO PLANETA AMBIENTAL INVERSIONES S.A.S.",
    "HERSIC INTERNATIONAL S.A.S BIC.": "HERSIC INTERNATIONAL S.A.S BIC",
    "IPSE": "IPSE (Instituto de Planificación y Promoción de Soluciones Energéticas)",
    "ONE ENERGY SOLUTIONS": "ONE ENERGY SOLUTIONS",
    "ONE ENERGY SOLUTIONS.": "ONE ENERGY SOLUTIONS",
    "PLANOS Y PLANAS CORPORACION": "PLANOS Y PLANAS CORPORACION",
    "SONENSOL": "SONENSOL",
    "SUNNY APP": "SUNNY APP",
    "Tecnología Solar Colombia S.A.S BIC – TESOCOL SAS ": "Tecnología Solar Colombia S.A.S BIC - TESOCOL SAS",
    "UNIÓN TEMPORAL ALIANZA SOLAR": "UNIÓN TEMPORAL ALIANZA SOLAR",
    "UNIÓN TEMPORAL ECOSOLAR": "UNIÓN TEMPORAL ECOSOLAR",
    "UNIÓN TEMPORAL ENERSOL": "UNIÓN TEMPORAL ENERSOL",
    "UNION TEMPORAL SSF SOINSOLAR-GVR": "UNION TEMPORAL SSF SOINSOLAR-GVR",
    "UT ENERGÍA SOLAR IA003-2025 LOTE 7.": "UT ENERGÍA SOLAR IA003-2025 LOTE 7",
    # supervision.contratos_liquidacion.ejecutor (Fase 17, continuación) —
    # razones sociales reales sin NIT en esa tabla, ninguna con indicio de
    # ambigüedad (a diferencia de EMCALI/ENEL, cada una tiene un solo nombre
    # asociado). "IPSE Amazonas" se mantiene como entidad propia, distinta de
    # "IPSE" (genérico, ya curado arriba) — es una oficina regional, sin
    # certeza de que comparta el mismo registro que la sede nacional.
    "ARDCO CONSTRUCCIONES S.A.S": "ARDCO CONSTRUCCIONES S.A.S",
    "CONSORCIO FAZNI INTERGRAL 2020": "CONSORCIO FAZNI INTERGRAL 2020",
    "CONSORCIO INTERVENTORES COLOMBIA": "CONSORCIO INTERVENTORES COLOMBIA",
    "DESARROLLADORA DE PROYECTOS DE INGENIERIA S.A.S": "DESARROLLADORA DE PROYECTOS DE INGENIERIA S.A.S",
    "FAZNI PMS": "FAZNI PMS",
    "GRUPO NUTRESA S.A.": "GRUPO NUTRESA S.A.",
    "HOCOL": "HOCOL",
    "INTERFAZNI EYP 2020": "INTERFAZNI EYP 2020",
    "IPSE Amazonas": "IPSE Amazonas",
    "NOVAVENTA": "NOVAVENTA",
    "PROINGES": "PROINGES",
    "SECOB LTDA": "SECOB LTDA",
    "UT INTERVENTORIA DE PUTUMAYO": "UT INTERVENTORIA DE PUTUMAYO",
}


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


def _ejecutores_con_nit_ambiguo() -> set:
    """Ejecutores (texto) de supervision.contratos con más de un NIT distinto
    asociado — ver docstring de resolver_supervision_por_nit(). Se calcula una
    sola vez y se usa tanto para excluir el seed automático de esos NITs como
    para dejar la resolución de ese ejecutor explícitamente sin_resolver."""
    d = db_manager.query_df("""
        SELECT ejecutor FROM (
            SELECT DISTINCT ejecutor, ROUND(nit_ejecutor)::text AS nit_txt
            FROM supervision.contratos
            WHERE nit_ejecutor IS NOT NULL AND ejecutor IS NOT NULL
        ) x
        GROUP BY ejecutor HAVING count(*) > 1
    """)
    return set(d["ejecutor"]) if not d.empty else set()


def seed_dim_empresa_desde_supervision() -> int:
    """Siembra dim_empresa también desde supervision.contratos.nit_ejecutor (Fase 17,
    Gap 3). Idempotente vía INSERT ... solo si el NIT no existe ya (no hay UNIQUE
    sobre nit_normalizado: se verificó en vivo que 8 NITs legítimamente tienen 2
    filas en dim_empresa, mismo NIT en más de una localidad/punto de servicio SUI —
    un UNIQUE rompería esa realidad de los datos). Excluye NITs con más de un
    nombre de ejecutor asociado, Y también NITs cuyo único nombre asociado es en
    sí mismo un ejecutor con NIT ambiguo en otra fila (ver
    _ejecutores_con_nit_ambiguo) — el filtro NUNCA se aplica antes de agrupar
    por NIT (bug real encontrado y corregido: filtrar antes le quitaba a un NIT
    compartido, ej. 860063875 de EMCALI/ENEL, la evidencia de que tenía más de
    un nombre, hacía que pareciera "limpio" para el nombre restante)."""
    ejecutores_ambiguos = _ejecutores_con_nit_ambiguo()
    pares = db_manager.query_df("""
        SELECT ROUND(nit_ejecutor)::text AS nit, ejecutor
        FROM supervision.contratos
        WHERE nit_ejecutor IS NOT NULL AND ejecutor IS NOT NULL
        GROUP BY 1, 2
    """)
    por_nit: dict[str, set] = {}
    for _, row in pares.iterrows():
        por_nit.setdefault(row["nit"], set()).add(str(row["ejecutor"]))

    sembrados, ambiguos_excluidos = 0, 0
    for nit, nombres in por_nit.items():
        ya_existe = db_manager.query_df(
            "SELECT 1 FROM ontologia.dim_empresa WHERE nit_normalizado = %s", (nit,)
        )
        if not ya_existe.empty:
            continue
        if len(nombres) > 1 or (nombres & ejecutores_ambiguos):
            if nit in AMBIGUOS_CURADOS:
                nombre = AMBIGUOS_CURADOS[nit]
            else:
                logger.warning(
                    f"NIT {nit} con nombres de ejecutor {sorted(nombres)} (ambiguo, directa o "
                    f"indirectamente) — excluido del seed automático, requiere revisión manual"
                )
                ambiguos_excluidos += 1
                continue
        else:
            nombre = next(iter(nombres))
        db_manager.execute_non_query(
            "INSERT INTO ontologia.dim_empresa (nit, nombre_oficial) VALUES (%s, %s)",
            (nit, nombre),
        )
        sembrados += 1
    logger.info(
        f"dim_empresa desde supervision.contratos: {sembrados} empresas nuevas, "
        f"{ambiguos_excluidos} NIT ambiguos excluidos (requieren revisión manual)"
    )
    return sembrados


def curar_empresas_sin_nit() -> None:
    """Registra como nuevas dim_empresa las razones sociales de EMPRESAS_NUEVAS_CURADAS
    (confirmadas sin NIT en ninguna fuente) y las alias a su valor_original real,
    buscando en qué tabla(s) de TABLAS_FUZZY aparece cada una."""
    curadas = 0
    for valor, nombre in EMPRESAS_NUEVAS_CURADAS.items():
        existente = db_manager.query_df(
            "SELECT empresa_id FROM ontologia.dim_empresa WHERE nombre_oficial = %s", (nombre,)
        )
        if existente.empty:
            db_manager.execute_non_query(
                "INSERT INTO ontologia.dim_empresa (nombre_oficial) VALUES (%s)", (nombre,)
            )
            existente = db_manager.query_df(
                "SELECT empresa_id FROM ontologia.dim_empresa WHERE nombre_oficial = %s", (nombre,)
            )
        empresa_id = int(existente["empresa_id"].iloc[0])
        for esquema, tabla, columna in TABLAS_FUZZY:
            existe_valor = db_manager.query_df(
                f"SELECT 1 FROM {esquema}.{tabla} WHERE {columna} = %s LIMIT 1", (valor,)
            )
            if not existe_valor.empty:
                _upsert_alias(esquema, tabla, columna, valor, empresa_id, "curado_manual")
                curadas += 1
    logger.info(f"{curadas} alias curados manualmente para razones sociales sin NIT")


def resolver_supervision_por_nit() -> None:
    """supervision.contratos.nit_ejecutor -> match determinístico por NIT.

    Un mismo ejecutor (texto) con más de un NIT distinto asociado se trata como
    ambiguo y queda sin_resolver — nunca se elige a ciegas cuál NIT es el
    correcto. Caso real verificado (Fase 17): "EMCALI E.I.C.E. E.S.P." aparece
    con 3 NITs distintos en supervision.contratos (843000057, 860063875,
    890399003); 843000057 pertenece de hecho a otra empresa real ya catalogada
    ("EMPRESA DE ENERGIA DEL GUAINIA..."), probable error de digitación en el
    dato origen — resolver por "el último NIT que se procese" habría
    atribuido contratos de Cali a una empresa de Guainía."""
    ejecutores_ambiguos = _ejecutores_con_nit_ambiguo()
    filas = db_manager.query_df("""
        SELECT DISTINCT ejecutor, ROUND(nit_ejecutor)::text AS nit_txt
        FROM supervision.contratos
        WHERE nit_ejecutor IS NOT NULL AND ejecutor IS NOT NULL
    """)
    nits_por_ejecutor: dict[str, set] = {}
    for _, row in filas.iterrows():
        nits_por_ejecutor.setdefault(str(row["ejecutor"]), set()).add(str(row["nit_txt"]))

    resueltos, pendientes, ambiguos = 0, 0, 0
    for ejecutor, nits in nits_por_ejecutor.items():
        if ejecutor in EJECUTORES_NIT_VERIFICADO_EXTERNAMENTE:
            # NIT ambiguo en el dato origen, pero verificado externamente
            # (Concejo de Cali / RUES / DataCrédito) cuál es el real — ver
            # docstring de EJECUTORES_NIT_VERIFICADO_EXTERNAMENTE.
            nit_txt = EJECUTORES_NIT_VERIFICADO_EXTERNAMENTE[ejecutor]
        elif ejecutor in ejecutores_ambiguos:
            logger.warning(
                f"Ejecutor '{ejecutor}' con {len(nits)} NITs distintos ({sorted(nits)}) — "
                f"ambiguo, queda sin_resolver, requiere revisión manual"
            )
            _upsert_alias("supervision", "contratos", "ejecutor", ejecutor, None, "sin_resolver")
            ambiguos += 1
            continue
        else:
            nit_txt = next(iter(nits))
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
    logger.info(
        f"supervision.contratos: {resueltos} resueltos por NIT, {pendientes} sin NIT coincidente, "
        f"{ambiguos} ejecutor con NIT ambiguo (sin_resolver a propósito)"
    )


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
    seed_dim_empresa_desde_supervision()
    resolver_supervision_por_nit()
    resolver_fuzzy()
    curar_empresas_sin_nit()


if __name__ == "__main__":
    main()
