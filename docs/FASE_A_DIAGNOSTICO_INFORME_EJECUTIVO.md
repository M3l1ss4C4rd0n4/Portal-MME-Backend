# FASE A — Diagnóstico Completo del Informe Ejecutivo MME

**Autor:** Copilot (auditoría automatizada)  
**Fecha:** 2026-03-01  
**Versión analizada:** `report_service.py` (1716 líneas, Feb 28), `orchestrator_service.py` (3998 líneas), `anomaly_tasks.py` (792 líneas)  
**PDF modelo:** `downloadfile (2) (1).pdf` (5 págs, 1.1 MB — Feb 6, 2026)  
**PDF actual:** `Informe_Ejecutivo_MME_2026-02-19.pdf` (8 págs, 436 KB — Feb 19, 2026)

---

## 1. RESUMEN EJECUTIVO DEL DIAGNÓSTICO

El informe diario generado por el sistema tiene **deficiencias significativas** en 4 dimensiones respecto al PDF modelo del Viceministro:

| Dimensión | Estado | Gravedad |
|-----------|--------|----------|
| **Contenido narrativo (IA)** | Genérico, con fugas de campos JSON | 🔴 Crítico |
| **Estructura/Formato PDF** | 8 páginas vs 5 del modelo, 3 págs de tablas crudas | 🔴 Crítico |
| **Datos del pipeline** | Gráficos fallan silenciosamente, sin datos regionales | 🟠 Alto |
| **Alineación con modelo PDF** | Faltan 2 secciones completas (Transacciones, Alertas CNO) | 🟠 Alto |

---

## 2. ANÁLISIS DETALLADO — CONTENIDO NARRATIVO

### 2.1 Fuga de campos JSON en la narrativa

**Evidencia (PDF Feb 19, Página 1):**
> "Los embalses están por encima de la media histórica 2020-2025, con una desviación del 13.7% según el campo `desviacionpctmediahistorica2020_2025`"

**Causa raíz:** El prompt del sistema (línea ~3298 de `orchestrator_service.py`) incluye la regla:
```
REGLA 1: NUNCA menciones nombres de campos JSON
```
Pero el modelo de IA (Groq/OpenRouter) la viola. No hay post-procesamiento que detecte y elimine estas fugas.

**Impacto:** El Viceministro ve texto técnico incomprensible. Resta credibilidad institucional.

### 2.2 Narrativa genérica sin valor analítico

**Ejemplos del PDF Feb 19:**
- *"Es importante monitorear las tendencias para anticipar posibles señales de estrés"* — Frase vacía sin dato que la justifique.
- *"La dependencia de la generación de energía de los embalses [...] podrían llevar a riesgos estructurales"* — Verdad genérica, sin magnitud ni horizonte.
- *"Se recomienda monitorear de cerca la tendencia de los embalses"* — Recomendación sin acción concreta.

**Causa raíz:** El prompt IA es robusto (5 secciones, reglas de estilo, umbrales), pero:
1. No hay **validación de calidad post-generación** (longitud mínima por sección, detección de frases vacías, verificación de inclusión de anomalías).
2. El `contexto_json` que recibe la IA puede ser muy largo (~15K chars), lo que diluye la atención del modelo.
3. Se usa `temperature=0.3` que es bueno, pero no hay retry si la respuesta es pobre.

### 2.3 Anomalías no integradas en la narrativa

**Dato:** El PDF Feb 19 muestra anomalía "DATOS_CONGELADOS — CapaUtilDiarEner: datos idénticos 9 días consecutivos" en la tabla de la página 7, pero la sección 3.1 de la narrativa NO la menciona.

**Causa raíz:** El flujo de `send_daily_summary` obtiene anomalías de dos fuentes distintas:
1. El orquestador `informe_ejecutivo` (para la narrativa IA) — usa anomalías de `_handle_anomalias_detectadas`
2. Query directo a `alertas_historial` (para la tabla del PDF) — consulta última 24h desde BD

Si la anomalía fue detectada DESPUÉS de generar la narrativa IA (o si el orquestador no la encontró), aparece en la tabla pero no en el texto.

### 2.4 Noticias como títulos sueltos

Las noticias aparecen en la página 8 como títulos + fuente + fecha, sin integración al análisis. El modelo PDF, en contraste, integra noticias como análisis del sector (CNO 824, UPME 6GW+, EPM embalses).

---

## 3. ANÁLISIS DETALLADO — ESTRUCTURA PDF

### 3.1 Comparación de páginas: Modelo vs Actual

| Pág | PDF Modelo (downloadfile) | PDF Actual (Feb 19) |
|-----|--------------------------|---------------------|
| 1 | **Variables del Mercado:** Charts precio (escasez, max, PPP), demanda (regulada/no regulada), explicaciones regulatorias | **KPIs + Narrativa §1:** 3 cajas KPI, inicio de narrativa con fuga JSON |
| 2 | **Generación por fuente:** Análisis detallado por tipo (hidráulica, térmica, biomasa, eólica, solar) con tendencias e implicaciones | **Charts:** Solo placeholder "Ver en el Portal Energético" (gráficos fallaron) |
| 3 | **Hidrología:** Chart Volumen Útil con referencias 2024/2025, embalses regionales (6 regiones con reservas + aportes) | **Narrativa §2:** Proyecciones 1 mes, análisis señales |
| 4 | **Transacciones Internacionales:** Import/Export Ecuador en GWh y $/kWh, análisis mensual y anual | **Narrativa §3-4:** Riesgos genéricos, recomendaciones vagas |
| 5 | **Alertas del Sector:** CNO 824, Estado 6GW+, análisis solar ENFICC, eventos hidrológicos, posición EPM | **Narrativa §5 + Inicio tablas predicciones:** Cierre + tabla GENE_TOTAL |
| 6 | — | **Tablas predicciones:** GENE_TOTAL cont. + PRECIO_BOLSA |
| 7 | — | **Tablas predicciones:** EMBALSES + tabla anomalías |
| 8 | — | **Noticias + Canales:** 3 titulares + links chatbot/portal |

### 3.2 Hallazgos de estructura

| # | Hallazgo | Severidad |
|---|----------|-----------|
| E1 | **8 páginas vs 5 del modelo:** 3 páginas extras son tablas de predicciones día-a-día (93 filas de datos crudos) que NO aportan a un informe ejecutivo | 🔴 |
| E2 | **Gráficos fallaron silenciosamente:** Página 2 muestra "Ver en el Portal Energético" en lugar de chart real. Sin logging de error visible | 🔴 |
| E3 | **Sin datos regionales de embalses:** El modelo muestra 6 regiones (Antioquia, Caldas, Valle, Caribe, Oriente, Centro) con reservas % y aportes GWh/día. El actual solo tiene el agregado nacional | 🟠 |
| E4 | **Sin sección de Transacciones Internacionales:** Import/Export con Ecuador completamente ausente | 🟠 |
| E5 | **Sin Alertas CNO/UPME:** El modelo tiene alertas regulatorias (CNO 824, Plan 6GW+, solar ENFICC). El actual solo tiene anomalías estadísticas (DATOS_CONGELADOS) | 🟠 |
| E6 | **Predicción card solo para Precio:** Las prediction cards (resumen + tendencia) solo se generan para PageMercado (Precio). Generación y Embalses tienen cards pero dependen de `_find_metric_prediction` que busca keywords en nombres de métricas — poco robusto | 🟡 |

---

## 4. ANÁLISIS DETALLADO — PIPELINE DE DATOS

### 4.1 Flujo de generación del PDF (diagrama)

```
send_daily_summary (anomaly_tasks.py)
│
├─ 1. _api_call('informe_ejecutivo') → Orquestador
│   └─ _handle_informe_ejecutivo()
│       ├─ 6 task paralelas (estado, pred 1s/1m/6m/1a, anomalías)
│       ├─ Noticias enriched (best-effort, 15s timeout)
│       ├─ contexto_ia → _generar_informe_con_ia() → Groq/OpenRouter
│       └─ return {informe_texto, contexto_datos}
│
├─ 2. _api_call('estado_actual') → fichas (3 KPIs)
│
├─ 3. _api_call('predicciones') × 3 métricas → predicciones_lista
│
├─ 4. _api_call('noticias_sector') → noticias
│
├─ 5. DB query alertas_historial → anomalías (24h)
│
├─ 6. generate_all_informe_charts() → 3 PNGs (gen_pie, embalses_map, precios)
│
├─ 7. generar_pdf_informe() → PDF WeasyPrint
│   ├─ _build_page_mercado (KPIs + precio_chart + precio_pred_card)
│   ├─ _build_page_generacion (gen_pie + fuente_table + per-source analysis + gen_pred_card)
│   ├─ _build_page_hidrologia (embalses_chart + data_box + pred_table + emb_pred_card)
│   ├─ _build_page_analisis (narrativa IA → Markdown → HTML)
│   └─ _build_page_noticias (anomalías_table + noticias + canales)
│
├─ 8. broadcast (Telegram message + PDF, Email HTML + PDF attachment)
│
└─ 9. Cleanup temp files
```

### 4.2 Problemas del pipeline

| # | Problema | Archivo | Línea(s) |
|---|----------|---------|----------|
| P1 | **Charts silenciosamente vacíos:** Si `generate_all_informe_charts()` falla o retorna paths inválidos, `chart_paths` queda vacío. `generar_pdf_informe` recibe charts vacíos y usa fallback "Ver en el Portal". No hay logging explícito de QUÉ chart falló | `anomaly_tasks.py` | 560-568 |
| P2 | **Doble call a estado_actual:** Se llama primero en `informe_ejecutivo` (dentro del orquestador) y luego otra vez directamente (`_api_call('estado_actual')`). Son 2 HTTP calls al mismo endpoint → datos potencialmente distintos si hay actualización entre ambas | `anomaly_tasks.py` | 465-468 |
| P3 | **predicciones_lista vs contexto_datos.predicciones_mes:** El PDF recibe dos fuentes de predicciones: (a) `predicciones_lista` con 31 puntos por métrica del handler `predicciones`, (b) `contexto_datos.predicciones_mes` del orquestador. La tabla cruda usa (a), las cards usan (b). Pueden mostrar valores distintos | `anomaly_tasks.py` / `report_service.py` | Múltiples |
| P4 | **Sin fallback robusto para charts:** `informe_charts.py` usa Plotly+Kaleido para generar PNGs. Si Kaleido no está instalado o falla, el chart no se genera pero el error queda swallowed en un try/except genérico | `anomaly_tasks.py` | 553-568 |
| P5 | **Cache de narrativa IA por día:** `_informe_ia_cache` guarda el primer informe del día. Si se llama 2 veces (ej: manual + cron), la segunda usa el cache aunque los datos hayan cambiado | `orchestrator_service.py` | 3120-3130 |

### 4.3 Datos faltantes respecto al modelo PDF

| Dato del modelo PDF | Disponible en el sistema? | Dónde está? |
|---------------------|--------------------------|-------------|
| Precio escasez ($/kWh) | ✅ En SIMEM/BD | `metrics_service` puede obtener `PrecEsc  ` |
| Precio máximo diario | ✅ En SIMEM/BD | `metrics_service` → `PrecMaxDiar` |
| Demanda regulada/no-regulada | ✅ En SIMEM/BD | `metrics_service` → `DemaRegu`, `DemaNoRegu` |
| Generación por fuente con análisis | ✅ Parcial | `_build_generacion_por_fuente()` calcula % pero no genera análisis textual por fuente |
| Embalses regionales (6 regiones) | ❌ No implementado | Requiere query a `VoluUtilDiarEner` agrupado por departamento/región |
| Transacciones internacionales | ❌ No implementado | Requiere ingestión de datos de intercambio Colombia-Ecuador |
| Alertas CNO / UPME | ❌ No implementado | Requiere fuente externa (scraping CNO, API UPME) |
| Plan 6GW+ estado | ❌ No implementado | Requiere fuente UPME |

---

## 5. ANÁLISIS DETALLADO — CALIDAD DEL PROMPT IA

### 5.1 Fortalezas del prompt actual

- ✅ Estructura obligatoria de 5 secciones bien definida
- ✅ Reglas explícitas contra frases vacías y mención de campos JSON
- ✅ Umbrales de embalses documentados (30/40/50/85)
- ✅ Instrucciones específicas para Embalses (media histórica) y Generación por fuente
- ✅ Manejo de confianza: PRECIO_BOLSA marcado como EXPERIMENTAL
- ✅ Máximo 1200 palabras — evita respuestas excesivas

### 5.2 Debilidades del prompt actual

| # | Debilidad | Ejemplo |
|---|-----------|---------|
| D1 | **No hay post-validación:** El texto IA se acepta sin verificar que cumpla las reglas (no JSON leaks, no frases vacías, todas las secciones presentes) | La fuga `desviacionpctmediahistorica2020_2025` pasa sin filtro |
| D2 | **Sin ejemplos (few-shot):** El prompt describe reglas pero no da un ejemplo de sección bien escrita | Aumentaría adherencia a estilo |
| D3 | **Contexto IA demasiado grande:** `contexto_ia` puede tener >15K chars (~4K tokens), dejando poco espacio para razonamiento | Comprimir contexto a ~3K chars |
| D4 | **Sin instrucción sobre Transacciones ni Alertas regulatorias:** El prompt pide 5 secciones analíticas pero NO menciona intercambio internacional ni alertas CNO. Estos datos del modelo PDF no están en el prompt | Agregar secciones |
| D5 | **Sección 3.2 forzada a citar noticias:** "OBLIGATORIO referenciar al menos 2 titulares de noticias" — si solo hay 1 noticia relevante o ninguna, la IA inventa | Hacer condicional |

---

## 6. TABLA COMPARATIVA: MODELO PDF vs ACTUAL

| Aspecto | PDF Modelo (Viceministro) | PDF Actual (Sistema) | Gap |
|---------|--------------------------|---------------------|-----|
| **Páginas** | 5 (conciso) | 8 (inflado) | 🔴 -3 páginas tablas crudas |
| **Gráficos** | Charts reales con ejes, leyendas, colores institucionales | Placeholders "Ver en Portal" | 🔴 Charts no renderizan |
| **Estilo visual** | Título+subtítulo por página, banners de sección, tooltips explicativos | KPI boxes + texto corrido | 🟠 Falta diseño editorial |
| **Variables Mercado** | Precio escasez, PPP diario, max diario, demanda regulada/no | Solo precio bolsa | 🟠 Faltan 3 variables |
| **Generación** | Análisis por fuente (5 tipos) con tendencia e implicación por párrafo | Solo pie chart + tabla + card | 🟠 Sin análisis por fuente |
| **Hidrología** | Volumen útil + referencia 2024/2025 + 6 regiones con reservas + aportes | Nivel nacional + data box | 🟠 Sin regional |
| **Transacciones** | Import/export Ecuador en volumen y precio, análisis mensual/anual | Ausente | 🔴 Sección completa faltante |
| **Alertas** | CNO 824, UPME 6GW+, análisis solar ENFICC, eventos hidrológicos | Solo DATOS_CONGELADOS (estadístico) | 🟠 Sin alertas regulatorias |
| **Narrativa** | N/A (modelo es puramente datos/gráficos) | IA genera texto genérico con fugas JSON | 🔴 Calidad insuficiente |
| **Tablas predicción** | N/A | 3 páginas de datos día-a-día | 🔴 No ejecutivo |
| **Footer** | Fuente XM con actualización más reciente | Página X de Y | 🟡 Menor |

---

## 7. CAUSAS RAÍZ CONSOLIDADAS

### CR-1: Celery workers sin restart (RESUELTO ✅)
Los workers corrían desde Feb 19. Cambios a `report_service.py` del Feb 28 eran invisibles. **Resuelto Mar 1 con restart.**

### CR-2: Charts no se generan (ACTIVO 🔴)
`generate_all_informe_charts()` falla silenciosamente. Probable causa: Kaleido/Plotly no instala correctamente en el entorno de sistema (`/usr/bin/python3`). El venv tiene Plotly pero los workers usan sistema Python.

### CR-3: Narrativa IA sin post-validación (ACTIVO 🔴)
El texto generado por Groq/OpenRouter no pasa por ningún filtro de calidad. Fugas de JSON, frases vacías y secciones faltantes llegan al PDF tal cual.

### CR-4: Datos del modelo PDF no están en el pipeline (ACTIVO 🟠)
Transacciones internacionales, embalses regionales y alertas CNO/UPME no tienen flujo de datos ni endpoint. Requieren desarrollo de ETL + servicio.

### CR-5: Tablas de predicción cruda en el PDF (ACTIVO 🔴)
3 páginas de datos día-a-día (93 filas) inflan el PDF y no aportan a un ejecutivo. El modelo PDF NO tiene tablas crudas.

### CR-6: Telegram parse_mode Markdown (RESUELTO ✅ parcial)
Se agregó fallback retry sin parse_mode. Pero la raíz (contenido con chars especiales) persiste. **Mitigado con fallback.**

---

## 8. PRIORIZACIÓN DE ACCIONES (INPUT PARA FASE B)

| Prioridad | Acción | Esfuerzo | Impacto |
|-----------|--------|----------|---------|
| 🔴 P0 | Fix charts (verificar kaleido en sistema Python) | 1-2h | Alto — PDF sin gráficos es inaceptable |
| 🔴 P0 | Eliminar tablas predicción cruda del PDF (reemplazar por cards compactos) | 2-3h | Alto — reduce 8→5 páginas |
| 🔴 P1 | Post-validación narrativa IA (regex JSON fields, longitud mínima por sección, retry si falla) | 3-4h | Alto — elimina fugas JSON |
| 🟠 P1 | Agregar análisis por fuente de generación al PDF (ya calculado en orquestador, falta render) | 2-3h | Medio — acerca al modelo |
| 🟠 P2 | Agregar embalses regionales (ETL + render 6 regiones) | 4-6h | Medio — alinea con modelo |
| 🟠 P2 | Variables de mercado adicionales (escasez, max diario, demanda regulada) | 3-4h | Medio — completa Pág 1 |
| 🟡 P3 | Transacciones internacionales (ETL Colombia-Ecuador) | 6-8h | Medio — sección nueva |
| 🟡 P3 | Alertas regulatorias (scraping CNO, UPME) | 8-12h | Bajo-Medio — fuente externa |
| 🟡 P3 | Diseño editorial del PDF (banners, tooltips, colores institucionales) | 4-6h | Bajo — cosmético |

---

*Documento generado automáticamente como parte de la auditoría FASE A del Informe Ejecutivo MME.*
