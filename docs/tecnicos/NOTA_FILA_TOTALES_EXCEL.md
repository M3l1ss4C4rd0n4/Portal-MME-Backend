# Nota técnica: Fila de totales de tabla Excel leída como dato real

**Fecha:** 2026-05-18  
**Afectó:** `subsidios.subsidios_pagos` — hoja `Pagos` de `Base_Subsidios_DDE.xlsx`  
**Impacto:** Total de Valor Resolución aparecía como $63.8T en vez de $31.9T (el doble)

---

## Qué pasó

La hoja `Pagos` en `Base_Subsidios_DDE.xlsx` es una **tabla de Excel con la "Fila de totales" activada**.  
Excel añade una fila extra debajo de los datos con la fórmula `=SUBTOTALES(109;[Valor Resolución])` que suma solo las filas visibles.

`pandas.read_excel()` **no distingue esta fila de totales de los datos reales** — la lee como si fuera una fila más, con:
- Todas las columnas de texto/clave en `NaN`  
- `Valor Resolución` = $31,907,588,678,520 (el resultado de la fórmula)

El resultado: el `SUM(valor_resolucion)` en la BD era exactamente el doble del valor correcto.

---

## Cómo detectarlo

En cualquier Excel, verificar si la última fila cumple:
- ≥ 50% de las columnas son `NaN`  
- Al menos un campo numérico tiene un valor mayor a 1,000,000,000

Script de detección disponible en el ETL (ver commit `1703d40`).  
**Escaneo ejecutado el 2026-05-18 sobre todos los Excel del portal → solo afectó este archivo.**

---

## Cómo se corrigió

En `etl/etl_subsidios.py`, función `importar_pagos()`, se añadió antes de insertar:

```python
# Eliminar la fila de totales de la tabla Excel (=SUBTOTALES al final)
df = df[df['Nombre del Prestador'].notna() | df['No. de Resolución'].notna()]
```

Adicionalmente se cambió la estrategia de carga de upsert-por-hash a **full refresh** (DELETE + INSERT) para que la BD sea un espejo exacto del Excel sin ninguna manipulación.

---

## Regla para el futuro

> **Antes de usar `pd.read_excel()` en hojas que son tablas de Excel:**  
> Verificar si la persona que mantiene el archivo tiene la "Fila de totales" activada  
> (pestaña Diseño de tabla → Fila de totales ✓).  
> Si existe, descartar las filas donde las columnas clave son todas `NaN`.

---

## Quién debe saber esto

- **Diana G** (mantiene `Base_Subsidios_DDE.xlsx`): informar que la fila de totales es leída por el sistema y que si la desactiva en Excel se eliminaría el problema en la fuente.
- Cualquier desarrollador que agregue un nuevo ETL de Excel debe revisar si la hoja tiene fila de totales.
