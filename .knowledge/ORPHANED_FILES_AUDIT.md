# Archivos Huérfanos (No Sincronizados)

**Fecha:** 14 de Mayo de 2026  
**Descubierto durante:** Auditoría ETL - Mapeo Excel → BD

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

## 🎯 Próximos Pasos

- [ ] **Verificar Comunidades_Energeticas_Avance:** ¿Es alternativa a Resumen_Implementación.xlsx?
- [ ] **Verificar Matriz_Implementacion_Base:** ¿Reemplaza a Matriz_General_Reparto?
- [ ] **Si se confirman como activas:** Agregar a SHAREPOINT_FILES con URLs de SharePoint
- [ ] **Si son obsoletas:** Archivar o eliminar para limpiar data/onedrive/

---

## 📝 Referencias

- Documento de auditoría completo: `.knowledge/ETL_TABLE_MAPPING_AUDIT.md`
- Código modificado:
  - `etl/etl_sharepoint_sync.py` — Docstring actualizado, handler removido
  - `etl/etl_nuevos_dashboards.py` — Documentación de archivo local añadida

