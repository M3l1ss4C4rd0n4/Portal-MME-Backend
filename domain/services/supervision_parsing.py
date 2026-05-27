"""
Utilidades SQL para limpiar campos de supervision.contratos.

La Matriz General de Reparto mezcla números puros, pesos colombianos
($ 297.983.971,00) y marcadores de categoría (FINANCIERA, No aplica).
"""

from __future__ import annotations

# Marcadores textuales que no son montos ni conteos.
_COP_SKIP = ("FINANCIERA", "NO APLICA", "EN EJECUCIÓN", "N/A", "NA")
_INT_SKIP = _COP_SKIP


def sql_parse_cop(column: str) -> str:
    """Expresión SQL → numeric | NULL para valores en pesos."""
    skip = ", ".join(f"'{s}'" for s in _COP_SKIP)
    col = column.strip()
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
    """Expresión SQL → entero | NULL para conteos de usuarios."""
    skip = ", ".join(f"'{s}'" for s in _INT_SKIP)
    col = column.strip()
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


# Tipos de solución considerados generación fotovoltaica centralizada.
FOTOVOLTAICO_TIPOS_SQL = (
    "UPPER(TRIM(tipo_de_solucion)) IN ('PARQUE SOLAR', 'PARQUE GENERADOR')"
)
