# Archivos Huérfanos (No Sincronizados)

**Fecha:** 14 de Mayo de 2026
**Descubierto durante:** Auditoría ETL - Mapeo Excel → BD

> **Actualizado 2026-09-30:** los 3 archivos de la fila "Archivos Válidos (pero huérfanos)" se
> confirmaron sin ningún handler ni referencia en el código (ver evidencia abajo) y se eliminaron
> de `data/onedrive/` en la limpieza de esa fecha. La narrativa de "archivo corrupto" de
> `Matriz_Subsidios_KPIs.xlsx` ya no es cierta: hoy es un Excel válido (4.4 MB, verificado con
> `file`) — pero sigue sin estar conectado a ningún handler activo del ETL de SharePoint
> (`etl_sharepoint_sync.py` solo lo menciona en un comentario, no en `SHAREPOINT_FILES`). Queda
> como pendiente de decisión real, sin relación con la corrupción original.

---

## 📂 Archivos Encontrados Pero NO Configurados en SHAREPOINT_FILES

| Archivo | Ubicación | Tamaño | Estado | Acción Recomendada |
|---|---|---|---|---|
| `Comunidades_Energeticas_Avance.xlsx` | `data/onedrive/` | 25 KB | ✅ Excel válido | Investigar si debe sincronizarse |
| `Comunidades_Energeticas_Avance.csv` | `data/onedrive/` | 14 KB | ✅ CSV válido | Investigar si debe sincronizarse |
| `Matriz_Implementacion_Base.xlsx` | `data/onedrive/` | 184 KB | ✅ Excel válido | Verificar si reemplaza a Matriz_General_Reparto.xlsx |
| `Matriz_Subsidios_KPIs.xlsx.corrupt.bak` | `data/onedrive/` | 57 KB | ❌ HTML (corrupto) | **REMOVIDO (renombrado a .corrupt.bak)** |

---

## 🔍 Hallazgos

### ✅ Archivos Válidos (pero huérfanos)

1. **Comunidades_Energeticas_Avance.xlsx / .csv**
   - No se encuentran referencias en handlers ETL
   - No se usan para alimentar ningún schema
   - **Posible causa:** Archivo intermedio o para análisis local
   - **Acción:** Contactar a equipo de datos para determinar si necesita sincronización

2. **Matriz_Implementacion_Base.xlsx**
   - Tamaño: 184 KB (más grande que Matriz_General_Reparto.xlsx)
   - No se encuentran referencias en handlers ETL
   - **Posible propósito:** ¿Reemplazar a Matriz_General_Reparto.xlsx para supervision.contratos?
   - **Acción:** Comparar contenido con Matriz_General_Reparto.xlsx; si es más reciente, considerar actualizar SHAREPOINT_FILES

### ❌ Archivo Corrupto (REMOVIDO)

**`Matriz_Subsidios_KPIs.xlsx`** → Renombrado a `Matriz_Subsidios_KPIs.xlsx.corrupt.bak`
- Era HTML (página de error), no Excel válido
- Tenía handler `etl_subsidios_kpis` que fue removido
- **Acción:** COMPLETADA ✅ — Handler y archivo removidos

---

## 🎯 Próximos Pasos (cerrados 2026-09-30)

- [x] **Comunidades_Energeticas_Avance.xlsx/.csv:** confirmado sin handler ni referencia en 4 meses
  — eliminados.
- [x] **Matriz_Implementacion_Base.xlsx:** confirmado sin handler ni referencia — eliminado.
- [ ] **Matriz_Subsidios_KPIs.xlsx:** sigue pendiente de decisión (ya no por corrupción, ver nota de
  arriba) — no se eliminó porque el archivo en sí es válido, solo falta decidir si se conecta.

---

## 📝 Referencias

- Documento de auditoría completo: `.knowledge/ETL_TABLE_MAPPING_AUDIT.md`
- Código modificado:
  - `etl/etl_sharepoint_sync.py` — Docstring actualizado, handler removido
  - `etl/etl_nuevos_dashboards.py` — Documentación de archivo local añadida

