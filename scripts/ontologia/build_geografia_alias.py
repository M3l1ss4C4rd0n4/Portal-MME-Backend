#!/usr/bin/env python3
"""
Ontología — Fase 1: siembra ontologia.dim_geografia y resuelve ontologia.geografia_alias.

Semilla: supervision.contratos (única tabla con codigo_dane_departamento/
codigo_dane_municipio confiables). Luego resuelve, para cada (esquema, tabla, columna)
de negocio que usa texto libre de departamento/municipio, el geografia_id correspondiente:

  1. Tablas con departamento+municipio en la misma fila -> match exacto normalizado
     de la pareja (alta precisión, grano municipio).
  2. Tablas con solo municipio -> match por nombre de municipio único; ambiguo -> sin_resolver.
  3. subsidios.subsidios_empresas.departamento -> territorio compuesto (curado a mano,
     ver DEPARTAMENTOS_COMPUESTOS_CURADOS abajo), resuelve a todos los municipios de
     cada departamento listado (es_compuesto=TRUE).

Nunca escribe geografia_id dentro de las tablas de negocio — todo vive en
ontologia.geografia_alias, aditivo, ningún ETL existente cambia.

Uso:
    venv/bin/python3 scripts/ontologia/build_geografia_alias.py
    venv/bin/python3 scripts/ontologia/build_geografia_alias.py --reporte-pendientes
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# Tablas con departamento Y municipio en la misma fila -> resolución por pareja exacta.
TABLAS_PAR_DEPTO_MUNI = [
    ("comunidades", "base"),
    ("contratos_or", "seguimiento_avance_documental"),
    ("contratos_or", "seguimiento_avance_fisico"),
    ("fenoge", "comunidades"),
    ("colombia_solar", "base"),
    ("colombia_solar", "base_general_or_inicial"),
    ("colombia_solar", "proyectado_internas"),
    ("colombia_solar", "proyectado_obras_civiles"),
    ("colombia_solar", "proyectado_potencia"),
    ("colombia_solar", "proyectado_usuarios"),
    ("colombia_solar", "reportado_internas"),
    ("colombia_solar", "reportado_obras_civiles"),
    ("colombia_solar", "reportado_potencia"),
    ("colombia_solar", "reportado_usuarios"),
    ("subsidios", "subsidios_mapa"),
]

# Tablas que solo tienen municipio (sin columna departamento) -> resolución por nombre único.
TABLAS_SOLO_MUNICIPIO = [
    ("contratos_or", "cronograma_contractual"),
    ("contratos_or", "cronograma_obra"),
    ("contratos_or", "seguimiento_electrocqueta"),
]

# subsidios.subsidios_empresas.departamento: 43 valores distintos verificados en vivo,
# muchos compuestos con separadores inconsistentes ("/", ", ", " y ") y casos que no son
# geografía real ("No incumbente", "No presta servicio"). Curado a mano (no hay forma
# segura de parsear automáticamente "Archipiélago de San Andrés y Providencia y Santa
# Catalina." sin partirlo mal por el " y "). Mapea a la lista de departamentos DANE reales.
DEPARTAMENTOS_COMPUESTOS_CURADOS = {
    "Amazonas": ["AMAZONAS"],
    "Antioquia": ["ANTIOQUIA"],
    "Antioquia y Choco": ["ANTIOQUIA", "CHOCO"],
    "Arauca": ["ARAUCA"],
    "Archipiélago de San Andrés y Providencia y Santa Catalina.": ["ARCHIPIELAGO DE SAN ANDRES"],
    "Atlántico": ["ATLANTICO"],
    "Atlántico/Guajira/Magdalena": ["ATLANTICO", "LA GUAJIRA", "MAGDALENA"],
    "Bogotá D.C": ["BOGOTA"],
    "Bolivar": ["BOLIVAR"],
    "Bolivar/Cesar/Cordoba/Sucre": ["BOLIVAR", "CESAR", "CORDOBA", "SUCRE"],
    "Boyaca": ["BOYACA"],
    "Caldas": ["CALDAS"],
    "Caldas/Risaralda (Sin Pereira)": ["CALDAS", "RISARALDA"],
    "Caqueta": ["CAQUETA"],
    "Caquetá": ["CAQUETA"],
    "Casanare": ["CASANARE"],
    "Cauca": ["CAUCA"],
    "Chocó": ["CHOCO"],
    "Córdoba": ["CORDOBA"],
    "Cundinamarca": ["CUNDINAMARCA"],
    "Guainía": ["GUAINIA"],
    "Guaviare": ["GUAVIARE"],
    "Huila": ["HUILA"],
    "Magdalena": ["MAGDALENA"],
    "Magdalena y Cesar": ["MAGDALENA", "CESAR"],
    "Meta": ["META"],
    "Nariño": ["NARINO"],
    "Nariño y Cauca": ["NARINO", "CAUCA"],
    "Norte de Santander": ["NORTE DE SANTANDER"],
    "Putumayo": ["PUTUMAYO"],
    "Quindio": ["QUINDIO"],
    "Risaralda/Valle del Cauca": ["RISARALDA", "VALLE DEL CAUCA"],
    "Santander": ["SANTANDER"],
    "Sucre": ["SUCRE"],
    "Tolima/Valle del Cauca": ["TOLIMA", "VALLE DEL CAUCA"],
    "Valle del Cauca": ["VALLE DEL CAUCA"],
    "Valle del Cauca, Bolivar y Chocó": ["VALLE DEL CAUCA", "BOLIVAR", "CHOCO"],
    "Vaupés": ["VAUPES"],
    "Vichada": ["VICHADA"],
    "Vichada, Guajira, Bolivar, Casanare, Chocó": ["VICHADA", "LA GUAJIRA", "BOLIVAR", "CASANARE", "CHOCO"],
    # No son territorio geográfico real -> quedan explícitamente sin_resolver.
    "No incumbente": None,
    "No presta servicio": None,
}


def seed_dim_geografia() -> int:
    """Siembra ontologia.dim_geografia desde supervision.contratos (idempotente)."""
    query = """
        INSERT INTO ontologia.dim_geografia
            (codigo_dane_departamento, codigo_dane_municipio, nombre_departamento, nombre_municipio)
        SELECT DISTINCT ON (muni_cod)
               depto_cod, muni_cod, departamento, municipio
        FROM (
            SELECT
                LPAD(ROUND(codigo_dane_departamento)::text, 2, '0') AS depto_cod,
                LPAD(ROUND(codigo_dane_municipio)::text, 5, '0')    AS muni_cod,
                initcap(departamento) AS departamento,
                initcap(municipio)    AS municipio
            FROM supervision.contratos
            WHERE codigo_dane_departamento IS NOT NULL
              AND codigo_dane_municipio IS NOT NULL
              -- "VARIOS" es un placeholder de contratos multi-ubicación, no un
              -- departamento real (confirmado: 1 fila con codigo 99/99001 que colisiona
              -- con el código real de Vichada/Puerto Carreño).
              AND upper(departamento) <> 'VARIOS'
        ) t
        ORDER BY muni_cod, departamento
        ON CONFLICT (codigo_dane_municipio) DO NOTHING
    """
    db_manager.execute_non_query(query)
    df = db_manager.query_df("SELECT count(*) AS n FROM ontologia.dim_geografia")
    total = int(df["n"].iloc[0])
    logger.info(f"ontologia.dim_geografia: {total} municipios sembrados")
    return total


DIVIPOLA_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "referencia", "divipola_dane.csv",
)


def seed_dim_geografia_desde_divipola(csv_path: str = DIVIPOLA_CSV) -> int:
    """
    Completa ontologia.dim_geografia con el catálogo DIVIPOLA oficial del DANE
    (datos.gov.co, dataset gdxc-w37w, 1.122 municipios verificados) — sube la
    cobertura de los 527 municipios sembrados en Fase 1 (solo los que aparecían en
    contratos de supervision.contratos) al catálogo completo de Colombia.

    ON CONFLICT DO NOTHING: nunca sobreescribe un municipio ya sembrado, para no
    invalidar los geografia_id que ontologia.geografia_alias ya referencia — solo
    agrega los que faltan.
    """
    import pandas as pd

    if not os.path.exists(csv_path):
        logger.warning(f"[DIVIPOLA] Archivo no encontrado: {csv_path} — omitiendo")
        return 0

    df = pd.read_csv(csv_path, dtype=str)
    df = df.rename(columns={
        "cod_dpto": "codigo_dane_departamento",
        "cod_mpio": "codigo_dane_municipio",
        "dpto": "nombre_departamento",
        "nom_mpio": "nombre_municipio",
    })
    df["nombre_departamento"] = df["nombre_departamento"].str.title()
    df["nombre_municipio"] = df["nombre_municipio"].str.title()

    antes = db_manager.query_df("SELECT count(*) AS n FROM ontologia.dim_geografia")
    total_antes = int(antes["n"].iloc[0])

    registros = list(df[[
        "codigo_dane_departamento", "codigo_dane_municipio",
        "nombre_departamento", "nombre_municipio",
    ]].itertuples(index=False, name=None))

    for depto_cod, muni_cod, depto, muni in registros:
        db_manager.execute_non_query(
            """
            INSERT INTO ontologia.dim_geografia
                (codigo_dane_departamento, codigo_dane_municipio, nombre_departamento,
                 nombre_municipio, fuente)
            VALUES (%s, %s, %s, %s, 'DANE-DIVIPOLA')
            ON CONFLICT (codigo_dane_municipio) DO NOTHING
            """,
            (depto_cod, muni_cod, depto, muni),
        )

    despues = db_manager.query_df("SELECT count(*) AS n FROM ontologia.dim_geografia")
    total_despues = int(despues["n"].iloc[0])
    agregados = total_despues - total_antes
    logger.info(
        f"[DIVIPOLA] {agregados} municipios nuevos agregados "
        f"({total_antes} -> {total_despues} total)"
    )
    return agregados


def _upsert_alias(esquema: str, tabla: str, columna: str, valor: str,
                   geografia_id: int, metodo: str, es_compuesto: bool = False) -> None:
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.geografia_alias
            (esquema_origen, tabla_origen, columna_origen, valor_original,
             geografia_id, es_compuesto, metodo)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (esquema_origen, tabla_origen, columna_origen, valor_original, geografia_id)
        DO NOTHING
        """,
        (esquema, tabla, columna, valor, geografia_id, es_compuesto, metodo),
    )


def _upsert_sin_resolver(esquema: str, tabla: str, columna: str, valor: str) -> None:
    # ON CONFLICT apunta al índice único parcial (migración 012) — geografia_id es
    # siempre NULL aquí, y NULL <> NULL rompería el ON CONFLICT sobre el constraint
    # original (que incluye geografia_id), duplicando la fila en cada corrida.
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.geografia_alias
            (esquema_origen, tabla_origen, columna_origen, valor_original,
             geografia_id, es_compuesto, metodo)
        VALUES (%s, %s, %s, %s, NULL, FALSE, 'sin_resolver')
        ON CONFLICT (esquema_origen, tabla_origen, columna_origen, valor_original)
        WHERE metodo = 'sin_resolver'
        DO NOTHING
        """,
        (esquema, tabla, columna, valor),
    )


def resolver_pares_depto_municipio() -> None:
    """Resuelve tablas que tienen departamento+municipio en la misma fila."""
    for esquema, tabla in TABLAS_PAR_DEPTO_MUNI:
        pares = db_manager.query_df(f"""
            SELECT DISTINCT departamento, municipio
            FROM {esquema}.{tabla}
            WHERE departamento IS NOT NULL AND municipio IS NOT NULL
        """)
        if pares.empty:
            continue
        resueltos, pendientes = 0, 0
        for _, row in pares.iterrows():
            depto, muni = str(row["departamento"]), str(row["municipio"])
            # comunidades.base guarda el departamento con guion bajo en vez de
            # espacio (ej. "La_Guajira") — normalizar solo para el match, nunca
            # para valor_original (debe seguir siendo idéntico al dato de origen
            # para que el JOIN de las vistas materializadas siga funcionando).
            depto_match = depto.replace("_", " ")
            muni_match = muni.replace("_", " ")
            match = db_manager.query_df(
                """
                SELECT geografia_id FROM ontologia.dim_geografia
                WHERE nombre_departamento_normalizado = upper(ontologia.f_unaccent(%s))
                  AND nombre_municipio_normalizado = upper(ontologia.f_unaccent(%s))
                """,
                (depto_match, muni_match),
            )
            if len(match) == 1:
                geografia_id = int(match["geografia_id"].iloc[0])
                _upsert_alias(esquema, tabla, "departamento", depto, geografia_id, "exacto_normalizado")
                _upsert_alias(esquema, tabla, "municipio", muni, geografia_id, "exacto_normalizado")
                resueltos += 1
            else:
                _upsert_sin_resolver(esquema, tabla, "departamento", depto)
                _upsert_sin_resolver(esquema, tabla, "municipio", muni)
                pendientes += 1
        logger.info(f"{esquema}.{tabla}: {resueltos} pares resueltos, {pendientes} pendientes")


def resolver_solo_municipio() -> None:
    """Resuelve tablas que solo tienen municipio (sin departamento) por nombre único."""
    for esquema, tabla in TABLAS_SOLO_MUNICIPIO:
        valores = db_manager.query_df(f"""
            SELECT DISTINCT municipio FROM {esquema}.{tabla} WHERE municipio IS NOT NULL
        """)
        if valores.empty:
            continue
        resueltos, pendientes = 0, 0
        for _, row in valores.iterrows():
            muni = str(row["municipio"])
            match = db_manager.query_df(
                """
                SELECT geografia_id FROM ontologia.dim_geografia
                WHERE nombre_municipio_normalizado = upper(ontologia.f_unaccent(%s))
                """,
                (muni,),
            )
            if len(match) == 1:
                _upsert_alias(esquema, tabla, "municipio", muni,
                              int(match["geografia_id"].iloc[0]), "exacto_normalizado")
                resueltos += 1
            else:
                # 0 matches o nombre de municipio ambiguo (existe en >1 departamento)
                _upsert_sin_resolver(esquema, tabla, "municipio", muni)
                pendientes += 1
        logger.info(f"{esquema}.{tabla}: {resueltos} municipios resueltos, {pendientes} pendientes/ambiguos")


def resolver_subsidios_empresas() -> None:
    """Resuelve subsidios.subsidios_empresas.departamento (territorio, curado a mano)."""
    valores = db_manager.query_df("""
        SELECT DISTINCT departamento FROM subsidios.subsidios_empresas
        WHERE departamento IS NOT NULL AND btrim(departamento) <> ''
    """)
    resueltos, sin_mapeo, pendientes = 0, 0, 0
    for _, row in valores.iterrows():
        valor = str(row["departamento"])
        deptos = DEPARTAMENTOS_COMPUESTOS_CURADOS.get(valor, "__NO_CURADO__")
        if deptos is None:
            # Curado explícitamente como "no es territorio geográfico" (ej. "No incumbente")
            _upsert_sin_resolver("subsidios", "subsidios_empresas", "departamento", valor)
            sin_mapeo += 1
            continue
        if deptos == "__NO_CURADO__":
            _upsert_sin_resolver("subsidios", "subsidios_empresas", "departamento", valor)
            pendientes += 1
            logger.warning(f"subsidios_empresas.departamento sin curar: {valor!r}")
            continue
        es_compuesto = len(deptos) > 1
        municipios = db_manager.query_df(
            "SELECT geografia_id FROM ontologia.dim_geografia "
            "WHERE nombre_departamento_normalizado = ANY(%s)",
            (deptos,),
        )
        if municipios.empty:
            logger.warning(
                f"subsidios_empresas.departamento={valor!r} curado a {deptos}, "
                "pero ningún municipio en dim_geografia coincide con esos nombres"
            )
            _upsert_sin_resolver("subsidios", "subsidios_empresas", "departamento", valor)
            pendientes += 1
            continue
        for gid in municipios["geografia_id"].tolist():
            _upsert_alias("subsidios", "subsidios_empresas", "departamento", valor,
                          int(gid), "curado_manual", es_compuesto=es_compuesto)
        resueltos += 1
    logger.info(
        f"subsidios.subsidios_empresas: {resueltos} valores curados resueltos "
        f"({sin_mapeo} marcados no-geográficos, {pendientes} sin curar)"
    )


def reporte_pendientes(path: str) -> None:
    df = db_manager.query_df("""
        SELECT esquema_origen, tabla_origen, columna_origen, valor_original
        FROM ontologia.geografia_alias
        WHERE metodo = 'sin_resolver'
        ORDER BY 1, 2, 3, 4
    """)
    df.to_csv(path, index=False)
    logger.info(f"Reporte de {len(df)} valores sin_resolver escrito en {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reporte-pendientes", action="store_true",
                         help="Solo exporta CSV de valores sin_resolver, no vuelve a resolver")
    args = parser.parse_args()

    if args.reporte_pendientes:
        reporte_pendientes(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "geografia_pendientes.csv")
        )
        return

    seed_dim_geografia()
    seed_dim_geografia_desde_divipola()
    resolver_pares_depto_municipio()
    resolver_solo_municipio()
    resolver_subsidios_empresas()
    reporte_pendientes(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "geografia_pendientes.csv")
    )


if __name__ == "__main__":
    main()
