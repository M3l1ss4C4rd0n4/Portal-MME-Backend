"""
Utilidades SQL para limpiar campos de supervision.contratos.

La Matriz General de Reparto mezcla números puros, pesos colombianos
($ 297.983.971,00) y marcadores de categoría (FINANCIERA, No aplica).
"""

from __future__ import annotations

from typing import Optional

# Marcadores textuales que no son montos ni conteos.
_COP_SKIP = ("FINANCIERA", "NO APLICA", "EN EJECUCIÓN", "N/A", "NA")
_INT_SKIP = _COP_SKIP


def sql_parse_cop(column: str) -> str:
    """Expresión SQL → numeric | NULL para valores en pesos.

    Castea la columna a text para soportar tanto columnas TEXT como NUMERIC
    (el ETL puede inferir NUMERIC cuando los valores del Excel son numéricos).
    """
    skip = ", ".join(f"'{s}'" for s in _COP_SKIP)
    col = f"({column.strip()})::text"
    return f"""
    CASE
      WHEN {col} IS NULL OR TRIM({col}) = '' THEN NULL
      WHEN UPPER(TRIM(REPLACE({col}, CHR(160), ''))) IN ({skip}) THEN NULL
      WHEN TRIM({col}) ~ '^[0-9]+(\\.[0-9]+)?$'
        THEN CAST(TRIM({col}) AS numeric)
      WHEN TRIM({col}) ~ '[0-9]'
        THEN CAST(
          NULLIF(
            REPLACE(
              REPLACE(
                REGEXP_REPLACE(TRIM(REPLACE({col}, CHR(160), '')), '[^0-9,.-]', '', 'g'),
                '.', ''
              ),
              ',', '.'
            ),
            ''
          ) AS numeric
        )
      ELSE NULL
    END
    """


def sql_parse_int(column: str) -> str:
    """Expresión SQL → entero | NULL para conteos de usuarios.

    Castea la columna a text para soportar tanto columnas TEXT como NUMERIC.
    """
    skip = ", ".join(f"'{s}'" for s in _INT_SKIP)
    col = f"({column.strip()})::text"
    return f"""
    CASE
      WHEN {col} IS NULL OR TRIM({col}) = '' THEN NULL
      WHEN UPPER(TRIM(REPLACE({col}, CHR(160), ''))) IN ({skip}) THEN NULL
      WHEN TRIM(REPLACE({col}, CHR(160), '')) ~ '^[0-9]+(\\.[0-9]+)?$'
        THEN CAST(TRIM(REPLACE({col}, CHR(160), '')) AS numeric)
      WHEN TRIM(REPLACE({col}, CHR(160), '')) ~ '[0-9]'
        THEN CAST(REGEXP_REPLACE(TRIM(REPLACE({col}, CHR(160), '')), '[^0-9]', '', 'g') AS numeric)
      ELSE NULL
    END
    """


def sql_parse_cop_guarded(column: str, max_valid: float = 1e11) -> str:
    """Como `sql_parse_cop()`, pero descarta valores con escala incorrecta
    (> `max_valid`) como anómalos → NULL.

    Mismo criterio de la corrección de datos de 2026-06-20 en
    `api/v1/routes/supervision_portal.py` (valores por desembolsar de ~49
    cuatrillones por errores de captura en Excel) — generalizado aquí para que
    también lo use `domain/services/orchestrator/handlers/supervision_handler.py`,
    que antes usaba `sql_parse_cop()` sin este guardrail.
    """
    parsed = sql_parse_cop(column)
    return f"""
    CASE
      WHEN ({parsed}) > {max_valid}
        THEN NULL
      ELSE ({parsed})
    END
    """


def sql_parse_pct(column: str) -> str:
    """Expresión SQL → numeric (0-1) | NULL para columnas de porcentaje en texto/numeric.

    Descarta valores > 1 (100%) como anómalos — mismo criterio ya aplicado a
    `porcentaje_de_desembolsos` desde la corrección de datos de 2026-06-20
    (generaliza el `_PARSE_FIN` que antes vivía duplicado en
    `api/v1/routes/supervision_portal.py`, parametrizado por columna).
    """
    col = f"({column.strip()})::text"
    return f"""
    CASE
      WHEN {col} ~ '[0-9]' AND {col} ~ '%%'
        THEN CASE
          WHEN CAST(REPLACE(REPLACE(TRIM({col}),'%%',''),',','.') AS numeric) / 100 <= 1
            THEN CAST(REPLACE(REPLACE(TRIM({col}),'%%',''),',','.') AS numeric) / 100
          ELSE NULL
        END
      WHEN {col} ~ '^[0-9.]'
           AND TRIM({col}) ~ '^[0-9. ]+$'
        THEN CASE
          WHEN CAST(TRIM({col}) AS numeric) <= 1
            THEN CAST(TRIM({col}) AS numeric)
          ELSE NULL
        END
    END
    """


# Tipos de solución considerados generación fotovoltaica centralizada.
FOTOVOLTAICO_TIPOS_SQL = (
    "UPPER(TRIM(tipo_de_solucion)) IN ('PARQUE SOLAR', 'PARQUE GENERADOR')"
)

# ─── Filtros compartidos de supervision.contratos ───────────────────────────
# Extraídos de api/v1/routes/supervision_portal.py (2026-09-08) — antes vivían
# duplicados ahí y en domain/services/orchestrator/handlers/supervision_handler.py,
# lo que causó que una corrección de datos (2026-06-20, _PARSE_FIN) nunca llegara
# al handler del orquestador. Un solo lugar de ahora en adelante.

FILTER_COLS = [
    ("fondo", "fondo"),
    ("estado_del_contrato", "estado"),
    ("etapa_del_contrato", "etapa"),
    ("departamento", "departamento"),
    ("municipio", "municipio"),
]

# Buckets de etapa ya usados por el dashboard real (/v1/supervision/dashboard) —
# agrupan las grafías fragmentadas de etapa_del_contrato. Los "%%" son literales
# de LIKE escapados para psycopg2 (se ejecutan siempre vía cur.execute(sql, params)).
ETAPA_BUCKETS = {
    "ejecucion": "etapa_del_contrato LIKE 'EJECUCI%%'",
    "aom": "etapa_del_contrato IN ('AOM','ATBF - AOM','ATEI - AOM')",
    "liquidacion": "etapa_del_contrato LIKE 'LIQUIDACI%%'",
    "liquidado": "etapa_del_contrato IN ('LIQUIDADO','LIQUIDADO - AOM')",
    "perdida_competencia": "etapa_del_contrato LIKE 'PERDIDA%%'",
}


def build_filter(filters: list[tuple[str, Optional[str]]]) -> tuple[str, list]:
    """Construye una cláusula `AND col = %s ...` a partir de pares (columna, valor).

    Los valores `None` se omiten (filtro no aplicado). Nunca concatena el valor
    del usuario directamente en el SQL — siempre vía placeholder `%s`.
    """
    params: list[str] = []
    clauses: list[str] = []
    for col, val in filters:
        if val is not None:
            params.append(val)
            clauses.append(f"{col} = %s")
    where = ("AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def base_year_where(ano_min: int, ano_max: int) -> str:
    return f"""
        FLOOR(ano)::integer BETWEEN {ano_min} AND {ano_max}
        AND estado_del_contrato IS NOT NULL AND TRIM(estado_del_contrato) != ''
    """


def kpi_filter_where(
    ano_min: int,
    ano_max: int,
    fondo: Optional[str] = None,
    estado: Optional[str] = None,
    etapa: Optional[str] = None,
    departamento: Optional[str] = None,
    municipio: Optional[str] = None,
) -> tuple[str, list[str]]:
    """WHERE parametrizado combinando el rango de año con los filtros opcionales.

    Usada tanto por `/v1/supervision/dashboard` y `/v1/supervision/detalle`
    (api/v1/routes/supervision_portal.py) como por el Asistente IA
    (domain/services/orchestrator/handlers/supervision_handler.py).
    """
    kpi_params: list[str] = []
    kpi_clauses: list[str] = [base_year_where(ano_min, ano_max)]
    for col, val in [
        ("fondo", fondo),
        ("estado_del_contrato", estado),
        ("etapa_del_contrato", etapa),
        ("departamento", departamento),
        ("municipio", municipio),
    ]:
        if val is not None:
            kpi_params.append(val)
            kpi_clauses.append(f"{col} = %s")
    return " AND ".join(kpi_clauses), kpi_params
