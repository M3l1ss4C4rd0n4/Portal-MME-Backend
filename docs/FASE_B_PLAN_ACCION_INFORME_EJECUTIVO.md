# FASE B — Plan de Acción para Mejora del Informe Ejecutivo MME

**Fecha:** 2026-03-01  
**Referencia:** FASE_A_DIAGNOSTICO_INFORME_EJECUTIVO.md

---

## RESUMEN DE ESTADO POST-RESTART

Con el restart de Celery workers (Mar 1, 08:41), varias mejoras ya activas:

| Issue | Estado | Nota |
|-------|--------|------|
| Charts no embebidos en PDF | ✅ RESUELTO | Nuevo `report_service.py` embebe PNG base64. Logs confirman "Gráficos generados: 3" |
| 8 páginas → 5 páginas | ✅ RESUELTO | Nuevo code tiene 5 page builders sin tablas crudas de predicción |
| Semáforo KPI + explicaciones | ✅ RESUELTO | `_build_page_mercado` incluye semáforo + contextual teal boxes |
| Análisis por fuente generación | ✅ RESUELTO | `_build_page_generacion` tiene bloques per-source analysis |
| Predicción compacta (cards) | ✅ RESUELTO | 3 pred cards en P1/P2/P3 reemplazan tablas day-by-day |
| Proyecciones 1 Mes tabla compact | ✅ RESUELTO | P3 Hidrología tiene tabla resumen 3 métricas |
| Telegram 400 Bad Request | ✅ MITIGADO | Fallback retry sin parse_mode + error logging |

---

## ACCIONES PENDIENTES POR FASE

### FASE B.1 — Postprocesamiento narrativa IA (URGENTE, 2-3h)

**Objetivo:** Eliminar fugas de campos JSON y frases genéricas del texto IA antes de renderizar el PDF.

**Implementación:**
1. Crear función `_postprocess_informe_ia(texto)` en `orchestrator_service.py`
2. Aplicar filtros:
   - Regex: detectar y eliminar nombres de campos JSON (`_pct_`, `cambio_pct_vs_`, `desviacion_pct_media_*`)
   - Detectar comillas invertidas (backticks) y eliminar
   - Verificar que tiene al menos 4 de las 5 secciones (## headers)
   - Verificar longitud mínima (>500 chars)
   - Si falla validación → retry con IA (1 intento) o usar texto limpio
3. Llamar ANTES de guardar en cache y retornar

**Archivos a modificar:**
- `domain/services/orchestrator_service.py` (añadir función post línea ~3180)

### FASE B.2 — Verificación end-to-end del informe actual (URGENTE, 30min)

**Objetivo:** Confirmar que el PDF generado hoy (con código nuevo) tiene charts, 5 páginas, y formato correcto.

**Implementación:**
1. Trigger manual de `send_daily_summary` 
2. Interceptar el PDF antes de cleanup
3. Verificar: 5 páginas, charts embebidos, semáforo, pred cards, no JSON leaks

### FASE B.3 — Variables de mercado adicionales (MEDIO, 3-4h)

**Objetivo:** Agregar Precio Escasez, Precio Máximo Diario y Demanda Regulada/No Regulada al PDF Página 1.

**Implementación:**
1. Obtener métricas `PrecEsc`, `PrecMaxDiar`, `DemaRegu`, `DemaNoRegu` desde MetricsService
2. Agregar al contexto enriquecido en orquestador
3. Renderizar en `_build_page_mercado` con formato similar al modelo PDF

**Archivos a modificar:**
- `domain/services/orchestrator_service.py` (enriquecer contexto)
- `domain/services/report_service.py` (render adicional en P1)

### FASE B.4 — Embalses regionales (MEDIO, 4-6h)

**Objetivo:** Mostrar nivel de embalses por las 6 regiones hidrológicas como el modelo PDF.

**Implementación:**
1. Ya existe mapeo embalse → región en `informe_charts.py` (EMBALSE_REGION)
2. Consultar VoluUtilDiarEner/CapaUtilDiarEner agrupado por embalse
3. Agregar tarjetas regionales (Antioquia, Caldas, Valle, Caribe, Oriente, Centro) en P3

**Archivos a modificar:**
- `domain/services/hydrology_service.py` (método `get_regional_reserves()`)
- `domain/services/orchestrator_service.py` (enriquecer embalses_detalle con regiones)
- `domain/services/report_service.py` (renderizar cards regionales en P3)

### FASE B.5 — Transacciones Internacionales (LARGO, 6-8h)

**Objetivo:** Agregar sección de Import/Export Colombia-Ecuador.

**Dependencia:** Datos de intercambio internacional deben ser ingestados vía ETL desde SIMEM/XM.

### FASE B.6 — Alertas regulatorias CNO/UPME (LARGO, 8-12h)

**Objetivo:** Agregar sección de alertas del Consejo Nacional de Operación y UPME Plan 6GW+.

**Dependencia:** Requiere scraping o API de fuentes externas (actas CNO, web UPME).

### FASE B.7 — Optimización del prompt IA (MEDIO, 2-3h)

**Objetivo:** Mejorar calidad de narrativa con few-shot examples y contexto comprimido.

**Implementación:**
1. Agregar 1-2 ejemplos (few-shot) de párrafos bien escritos en el system_prompt
2. Comprimir contexto_ia a ~8K chars máximo (eliminar campos redundantes)
3. Agregar instrucción explícita: "No uses backticks ni nombres técnicos de campos"
4. Probar con diferentes temperaturas (0.2-0.4)

---

## PRIORIDAD DE EJECUCIÓN

```
DÍA 1 (HOY):
  [B.1] Postprocesamiento narrativa IA ← CRÍTICO
  [B.2] Verificación end-to-end ← VALIDACIÓN

DÍA 2-3:
  [B.7] Optimización prompt IA
  [B.3] Variables de mercado adicionales

SEMANA 2:
  [B.4] Embalses regionales

SEMANA 3+:
  [B.5] Transacciones internacionales
  [B.6] Alertas CNO/UPME
```

---

*Plan generado como complemento de FASE_A_DIAGNOSTICO_INFORME_EJECUTIVO.md*
