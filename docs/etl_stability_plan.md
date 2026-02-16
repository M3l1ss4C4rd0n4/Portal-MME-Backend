# Plan de Estabilidad del ETL — Portal Energético MME

**Fecha:** 2025-07-09 (actualizado 2026-02-12)  
**Versión:** 1.1  
**Autor:** Arquitecto ETL  

---

## Resumen Ejecutivo

Este documento consolida el plan de estabilización del pipeline ETL que extrae datos de la API de XM, los transforma y los carga en PostgreSQL para alimentar el dashboard y la API del Portal Energético del MME.

**Problema central:** Las fallas recurrentes del ETL (métricas faltantes, conversiones incorrectas, unidades inconsistentes) se originan en la **dispersión de lógica de conversión** entre 4+ archivos sin una fuente única de verdad, combinada con la **ausencia de validación** antes de la inserción en base de datos.

**Solución implementada:** Centralización de reglas en `etl/etl_rules.py`, refactorización incremental del ETL principal, y creación de scripts de diagnóstico no destructivos.

---

## 1. Causas Raíz Identificadas

| # | Causa | Impacto | Estado |
|---|-------|---------|--------|
| F1 | API XM caída / timeout / formato cambiado | 0 registros cargados | ⚠️ Sin retry |
| F2 | `detectar_conversion()` usa pattern matching frágil | 170K+ registros con unidad errada | ✅ **RESUELTO** — ahora consulta `etl_rules.py` |
| F3 | Dict duplicado `metricas_restricciones` en `config_metricas.py` | Métricas perdidas silenciosamente | ❌ Pendiente |
| F4 | Doble conversión entre `asegurar_columna_valor()` y `convertir_unidades()` | Valores potencialmente incorrectos | ⚠️ Mitigado |
| F5 | Unidad asignada como `None` en BD | Dashboard muestra "None" | ✅ **RESUELTO** — `get_expected_unit()` |
| F6 | Sin validación antes de INSERT | Datos corruptos irreversibles | ✅ **RESUELTO** — `validate_metric_df()` |
| F7 | Servicios filtran por valores hardcoded | Queries vacíos | ✅ Resuelto (`_SISTEMA_` → `Sistema`) |
| F8 | `validar_etl.py` usa SQLite (obsoleto) | Sin validación post-ETL | ✅ **RESUELTO** — nuevo script |
| F9 | Dashboard con unidades mixtas | UX incorrecta | ⚠️ Se resuelve con F2+F5+F6 |
| F10 | `validaciones_rangos.py` con IDs incorrectos | Rangos no se aplican | ✅ **RESUELTO** — `etl_rules.py` |
| F11 | Cron sin retry ni alertas | 6h sin datos si falla | ❌ Pendiente |

Detalle completo: **[docs/etl_failure_root_causes.md](../docs/etl_failure_root_causes.md)**

---

## 2. Archivos Creados / Modificados

### Archivos Nuevos

| Archivo | Propósito | Líneas |
|---------|-----------|--------|
| `etl/etl_rules.py` | Fuente única de verdad: 69 reglas de métricas con unidad, conversión, rango, tipo de agregación | ~400 |
| `scripts/diagnostico_metricas_etl.py` | Diagnóstico no destructivo: verifica existencia, huecos, unidades, rangos contra BD | ~260 |
| `scripts/diagnostico_conversores_unidades.py` | Verifica conversiones con datos sintéticos + coherencia `detectar_conversion()` ↔ `etl_rules.py` | ~280 |
| `docs/etl_failure_root_causes.md` | Catálogo de 11 fallos con ubicación, causa raíz, impacto, estado, mitigación | ~250 |
| `docs/etl_stability_plan.md` | Este documento | — |

### Archivos Modificados

| Archivo | Cambios |
|---------|---------|
| `etl/etl_todas_metricas_xm.py` | 1. Import de `etl_rules` (get_expected_unit, validate_metric_df, etc.) |
| | 2. `detectar_conversion()`: consulta reglas centralizadas primero, fallback a pattern matching legacy |
| | 3. Unidad determinada por `get_expected_unit()` con fallback local |
| | 4. **Validación pre-insert**: `validate_metric_df()` entre conversión e inserción — bloquea inserción si hay error de unidad crítico |

### Archivos NO Modificados (seguridad §0)

- **Dashboard (Dash)**: Sin cambios — sigue respondiendo en :8050
- **API (FastAPI)**: Sin cambios — sigue respondiendo en :8000
- **Servicios de dominio**: Sin cambios
- **Base de datos**: Sin cambios en esquema ni datos existentes
- **Nginx, systemd, cron**: Sin cambios

---

## 3. Arquitectura de la Solución

```
╔═══════════════════════════════════════════════════════════════════╗
║                    etl/etl_rules.py                               ║
║               (FUENTE ÚNICA DE VERDAD)                            ║
║                                                                   ║
║  ┌──────────────────────────────────────────┐                     ║
║  │  69 MetricRule:                          │                     ║
║  │    metric_id, expected_unit, conversion, │                     ║
║  │    aggregation, valid_range, entities    │                     ║
║  └──────────────────────────────────────────┘                     ║
║                                                                   ║
║  API:                                                             ║
║    get_rule(id) → MetricRule                                      ║
║    get_expected_unit(id) → str                                    ║
║    get_conversion_type(id) → ConversionType                       ║
║    validate_metric_df(df, id) → [issues]                          ║
║    apply_conversion(df, id) → df                                  ║
╚═════════════════════════════════════════════════════════════════╝
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│ etl_todas_      │ │ diagnostico_    │ │ diagnostico_        │
│ metricas_xm.py  │ │ metricas_etl.py │ │ conversores_        │
│                 │ │                 │ │ unidades.py         │
│ detectar_conv() │ │ Lee BD vs reglas│ │ Tests sintéticos    │
│ → regla primero │ │ Reporta issues  │ │ Coherencia ETL↔rules│
│ unit = regla    │ │ CSV exportable  │ │                     │
│ validate pre-   │ │                 │ │                     │
│ insert          │ │                 │ │                     │
└────────┬────────┘ └────────┬────────┘ └──────────┬──────────┘
         │                    │                     │
         ▼                    ▼                     ▼
    (PostgreSQL)          (Reporte)            (14/14 tests ✅)
```

---

## 4. Cómo Usar los Scripts de Diagnóstico

### 4.1 Diagnóstico de métricas (datos en BD)

```bash
# Análisis completo — últimos 365 días
python3 scripts/diagnostico_metricas_etl.py

# Análisis de los últimos 30 días
python3 scripts/diagnostico_metricas_etl.py --dias 30

# Exportar a CSV para análisis en Excel
python3 scripts/diagnostico_metricas_etl.py --csv reporte_metricas.csv
```

**Salida:** Para cada una de las 69 métricas con regla, verifica:
- ✅/❌ Existencia de datos por entidad esperada
- Frescura (últimos datos vs hoy)
- Unidad correcta vs esperada
- Valores dentro de rango
- Huecos en la serie temporal

**Exit code:** 0 = todo OK, 1 = hay errores o métricas sin datos

### 4.2 Diagnóstico de conversores (funciones)

```bash
python3 scripts/diagnostico_conversores_unidades.py
```

**Salida:**
- 14 tests de conversión con datos sintéticos
- Coherencia `detectar_conversion()` ↔ `etl_rules.py` (69/69 coincidencias)
- Métricas en BD sin regla definida (58 pendientes)

### 4.3 Integración con cron (recomendado)

```bash
# Agregar al crontab después del ETL:
# 0 */6 * * * cd /home/admonctrlxm/server && python3 etl/etl_todas_metricas_xm.py --dias 7 >> logs/etl.log 2>&1
# 10 */6 * * * cd /home/admonctrlxm/server && python3 scripts/diagnostico_metricas_etl.py --dias 7 >> logs/diagnostico.log 2>&1
```

---

## 5. Resultados de la Validación

### Conversores: 14/14 tests pasaron ✅

| Test | Resultado |
|------|-----------|
| Wh → GWh (×2 métricas) | ✅ |
| Horas → GWh (×2 métricas) | ✅ |
| Horas → MW | ✅ |
| COP → MCOP | ✅ |
| Restricciones → MCOP | ✅ |
| Sin conversión (identidad) | ✅ |
| apply_conversion() (×6 métricas) | ✅ |

### Coherencia: 69/69 reglas sincronizadas ✅

`detectar_conversion()` ahora retorna el mismo tipo de conversión que `etl_rules.py` para las 69 métricas con regla definida.

### Cobertura: 61/119 métricas en BD cubiertas

- 61 métricas en BD tienen regla definida y serán validadas
- 58 métricas en BD aún sin regla (se procesan con lógica legacy, sin validación centralizada)
- 8 reglas definidas sin datos en BD (métricas históricas o poco frecuentes)

---

## 6. Trabajo Pendiente (Backlog)

### Prioridad Alta
1. **Limpiar datos históricos corruptos** — ~170K registros con unidad incorrecta (`CapEfecNeta`/GWh→MW, `AporCaudal*/GWh→m³/s`). Requiere un script de corrección one-shot con backup previo.
2. **Resolver dict duplicado** en `config_metricas.py` — Renombrar `metricas_restricciones` segundo bloque.
3. **Agregar reglas** para las 58 métricas sin cobertura.

### Prioridad Media
4. **Retry con backoff** en `descargar_metrica()` — 3 intentos con espera 5/15/30s.
5. **Alertas** — Enviar notificación (email/Slack/WhatsApp) si el diagnóstico post-ETL retorna exit code 1.
6. **Migrar** `convertir_unidades()` a usar `apply_conversion()` de `etl_rules.py` directamente (eliminar la función local).

### Prioridad Baja
7. **Deprecar** `validaciones_rangos.py` (rangos ya en `etl_rules.py`).
8. **Deprecar** `scripts/validar_etl.py` (reemplazado por `diagnostico_metricas_etl.py`).
9. **Tests unitarios** — Agregar tests formales con pytest para `etl_rules.py`.

---

## 7. Garantías de Seguridad (§0)

| Garantía | Cumplimiento |
|----------|-------------|
| No se borraron datos existentes en BD | ✅ |
| No se modificaron servicios de dashboard | ✅ |
| No se modificaron servicios de API | ✅ |
| No se tocaron archivos de nginx/systemd | ✅ |
| El ETL funciona igual que antes para métricas sin regla | ✅ (fallback a lógica legacy) |
| Los nuevos scripts son solo lectura (no escriben en BD) | ✅ |
| Las reglas centralizadas no rompen nada si se eliminan | ✅ (el fallback funciona sin ellas) |
| Todos los cambios son aditivos / incrementales | ✅ |

---

## 8. Checklist operativo diario/semanal

> **Última verificación completa:** 2026-02-12  
> **Resultado:** 69 reglas OK · 14/14 tests · 69/69 coherencia · 0 fallos  
> **Hallazgos pendientes:** 58 métricas en BD sin regla (no críticas); bug de clave duplicada `metricas_restricciones` en `config_metricas.py` (F3, sin impacto directo porque el ETL principal ya usa `etl_rules.py`); 95 IDs en `METRICAS_POR_SECCION` sin regla centralizada (fallback legacy funcional).

### A. Después de cada ejecución del ETL (cron cada 6h o manual)

1. **Revisar logs del ETL** buscando líneas con `🛑` (inserción bloqueada) o `ERROR`:
   ```bash
   grep -E '🛑|ERROR UNIDAD|Inserción BLOQUEADA' logs/etl.log | tail -20
   ```
2. **Ejecutar diagnóstico rápido** (últimos 7 días):
   ```bash
   python3 scripts/diagnostico_metricas_etl.py --dias 7
   ```
   - Exit code 0 → OK.
   - Exit code 1 → revisar las métricas con estado `SIN_DATOS` o `ERROR` en la salida.

### B. Semanalmente

3. **Ejecutar diagnóstico completo** y exportar CSV:
   ```bash
   python3 scripts/diagnostico_metricas_etl.py --dias 30 --csv reporte_semanal.csv
   ```
4. **Ejecutar diagnóstico de conversores**:
   ```bash
   python3 scripts/diagnostico_conversores_unidades.py
   ```
   - Confirmar **0 fallos** y **69/69 coherencia**.
   - Revisar la lista de métricas en BD sin regla; si alguna es crítica para el dashboard, crear su regla (ver sección C).

### C. Al añadir una métrica nueva

5. **Añadir regla** en `etl/etl_rules.py`: buscar la sección correspondiente y añadir una línea `_r(...)`:
   ```python
   _r("NuevaMetricaId",
       section=Section.SECCION_CORRECTA,
       expected_unit="UNIDAD",           # GWh, MW, $/kWh, Millones COP, m³/s, etc.
       conversion=ConversionType.TIPO,   # WH_TO_GWH, HOURS_TO_GWH, NONE, etc.
       aggregation=AggregationType.TIPO, # DAILY_VALUE, HOURLY_SUM, HOURLY_AVG
       valid_range=(MIN, MAX),
       entities=["Sistema"],             # o ["Recurso"], ["Rio"], etc.
       description="Descripción breve")
   ```
6. **Verificar** la nueva regla:
   ```bash
   python3 -c "from etl.etl_rules import get_rule; r = get_rule('NuevaMetricaId'); print(r)"
   python3 scripts/diagnostico_conversores_unidades.py
   ```
7. **Re-ejecutar el ETL** para esa métrica:
   ```bash
   python3 etl/etl_todas_metricas_xm.py --metrica NuevaMetricaId --dias 30
   ```
8. **Confirmar** que los datos llegaron bien:
   ```bash
   python3 scripts/diagnostico_metricas_etl.py --dias 30 | grep NuevaMetricaId
   ```

### D. Cuando el dashboard "no muestra datos"

9. **Identificar la métrica afectada** (qué gráfico del dashboard falla).
10. **Consultar BD** para ver si hay datos recientes:
    ```bash
    psql -U postgres -h localhost -d portal_energetico -c \
      "SELECT metrica, unidad, COUNT(*), MAX(fecha) FROM metrics WHERE metrica = 'METRICA_ID' GROUP BY metrica, unidad;"
    ```
11. **Si no hay datos recientes**: revisar logs del ETL para esa métrica → ¿la API de XM devolvió vacío? ¿se bloqueó por validación?
12. **Si hay datos pero unidad incorrecta**: la regla en `etl_rules.py` puede estar mal o faltar. Corregir y re-ejecutar.
13. **Si hay datos y unidad correcta**: el problema está en el servicio de dominio o en la página del dashboard. Verificar que el servicio no tenga métodos duplicados que sobrescriban la lógica funcional (como ocurrió con `get_distribution_data` — ver fix del 2026-02-12).

### E. Al modificar el ETL

14. **Antes de hacer push**: ejecutar los dos scripts de diagnóstico y confirmar 0 fallos.
15. **No cambiar** nombres de columnas en la tabla `metrics` (`valor_gwh`, `unidad`, `fecha`, `metrica`, `entidad`, `recurso`) — los dashboards dependen de ellos directamente.
16. **No cambiar** firmas de `descargar_metrica()`, `ejecutar_etl_completo()`, `detectar_conversion()` — otros scripts y el cron dependen de ellas.
17. **Recargar workers** después de cambios en código Python del API/dashboard:
    ```bash
    # Si systemd está configurado:
    sudo systemctl restart api-mme.service dashboard-mme.service
    # Si no, reinicio manual de gunicorn (con preload_app=True, HUP no basta):
    kill $(cat /tmp/gunicorn_dashboard_mme.pid) && sleep 2
    cd /home/admonctrlxm/server && nohup gunicorn -c gunicorn_config.py app:server &
    ```

### F. Verificación Express (copiar y pegar)

```bash
cd /home/admonctrlxm/server
python3 -c "import etl.etl_rules; print(f'Rules: {len(etl.etl_rules.get_all_rules())}')"
python3 -c "from etl.etl_todas_metricas_xm import detectar_conversion; print('ETL OK:', detectar_conversion('Gene','Sistema'))"
python3 scripts/diagnostico_conversores_unidades.py 2>&1 | tail -8
```
Resultado esperado: `Rules: 69`, `ETL OK: horas_a_GWh`, `✅ Pasaron: 14`, `❌ Fallaron: 0`, `Coincidencias: 69/69`.

