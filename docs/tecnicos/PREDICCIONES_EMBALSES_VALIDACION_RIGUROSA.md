# Validación rigurosa del modelo de predicción de embalses (EMBALSES_PCT)

**Portal Energético — Ministerio de Minas y Energía (MME)**
**Fecha:** Agosto 2026
**Alcance:** `scripts/train_predictions_sector_energetico.py` (`PredictorMetricaSectorial`, ensemble Prophet + SARIMAX), `api/v1/routes/predictions.py`, `domain/services/portal_report_service.py`, frontend `energia/predicciones`.

---

## Resumen ejecutivo

El portal mostraba una única cifra de precisión ("MAPE 4.5%") para el modelo de predicción de nivel de embalses del SIN, proveniente de un holdout de entrenamiento de 180 días — nunca de una validación out-of-sample real. Esta ronda de trabajo:

1. Encontró y corrigió un `NameError` que impedía que la función de backtest riguroso (`main_backtest()`) se hubiera ejecutado exitosamente **ni una sola vez** desde que existía en el código.
2. Corrió el backtest real (entrenar hasta un año de corte, validar contra el año siguiente completo) para 5 años distintos (2022, 2023, 2024, 2009, 2014) — el error real out-of-sample resultó estar entre **7% y 32%**, no el 4.5% publicitado.
3. Descubrió que el propio backtest, en su primera versión, alimentaba el modelo con datos climáticos "de trampa" (perfect-foresight) — corrigió esto con una segunda variante fiel a las asunciones reales de producción.
4. Encontró y corrigió un **bug crítico y preexistente**: SARIMAX nunca usó ninguna variable climática real (ni ONI) porque la librería `pmdarima` renombró su parámetro de variables exógenas de `exogenous` a `X`, y el código viejo pasaba el nombre obsoleto sin que nadie lo notara — se absorbía en silencio.
5. Corrigió que el intervalo de confianza mostrado no se ensanchaba con el horizonte del pronóstico (Prophet, con `growth='flat'`, tiene una banda de ancho prácticamente constante).
6. Desglosó el error por horizonte (1-30, 31-90, 91-180, 181-365, 366-730 días) — reveló que el modelo es confiable a corto plazo (1-8%) pero tiene una debilidad sistemática en el rango de 1 a 6 meses (hasta 55% de error en algunos años).
7. Actualizó el portal para mostrar el **rango real de error observado**, no un número único optimista.

---

## 1. Contexto y motivación

El modelo de predicción de embalses (`EMBALSES_PCT`, métrica `PorcVoluUtilDiar` de XM) es un ensemble de dos componentes:

- **Prophet** (Meta): captura estacionalidad bimodal andina (dos temporadas de lluvia/año), usa 7 regresores climáticos/hidrológicos vía `add_regressor()`: `ideam_precipitacion_anomalia`, `oni_index`, `oni_index_lag90`, `gmst_anomalia`, `apor_ener_lag7`, `pdo_index`, `soi_index`.
- **SARIMAX** (`pmdarima.auto_arima`): modelo estadístico más simple, diseñado para usar ONI (y, desde esta ronda, también SOI) como variable exógena.

Los dos se combinan con pesos calculados por error inverso sobre un holdout de 180 días, y ese mismo holdout produce el "MAPE" que el portal mostraba como cifra de precisión (~4.5%).

**El problema**: ese número mide qué tan bien el modelo se ajusta a datos que ya vio durante el entrenamiento (con un pequeño margen de holdout), no cómo se comporta prediciendo un futuro genuinamente desconocido. Ya existía en el código una función `main_backtest(backtest_year)` diseñada exactamente para medir esto último (entrenar solo hasta el 31 de diciembre de un año, y validar contra los ~2 años siguientes) — pero nunca se había ejecutado con éxito.

---

## 2. Bug #1 — `main_backtest()` nunca había corrido (NameError)

La función instanciaba una clase `EnsemblePredictor` que **nunca existió** en el archivo (0 resultados de búsqueda en todo el historial de git). La clase real se llama `PredictorMetricaSectorial`. Esto significa que la función, documentada como el mecanismo de validación riguroso del sistema, llevaba tiempo indefinido fallando en la primera línea cada vez que alguien intentaba correrla — y nadie lo había notado porque el error solo aparece al ejecutarla manualmente, nunca en el flujo normal de producción.

**Corregido**: `predictor = PredictorMetricaSectorial(fuente, config)`.

Primera corrida exitosa real (corte 2024-12-31, validado contra 602 días reales hasta agosto 2026, incluyendo un episodio de El Niño activo): **MAPE out-of-sample real = 9.26%**, frente al 4.5% que mostraba el portal.

---

## 3. Backtest en 5 años distintos (2022, 2023, 2024, 2009, 2014)

Con la función ya funcional, se corrió para múltiples años de corte — incluyendo, a pedido explícito del usuario, las dos crisis hidrológicas históricas reales de Colombia (2010-2011 y 2015-2016, esta última con el episodio de El Niño más severo de la muestra), que ningún backtest anterior había tocado.

| Año de corte | Período validado | MAPE holdout (optimista) | **MAPE out-of-sample real** |
|---|---|---|---|
| 2022 | 2023-2024 | 3.62% | **22.56%** (sobreajuste detectado) |
| 2023 | 2024-2025 | 3.79% | **20.17%** (sobreajuste detectado) |
| 2024 | 2025-2026 | 16.96% | **9.26%** |
| 2009 (crisis 2010-11) | 2010-2011 | 5.04% | **16.61%** |
| 2014 (crisis 2015-16, El Niño severo) | 2015-2016 | 1.54% | **31.66%** (el peor de los 5) |

**Hallazgo central**: el error real varía entre 9% y 32% según el año — mucho más que el 4.5% publicitado, y con evidencia clara de sobreajuste (el modelo se ajusta muy bien a los datos que ya vio, pero generaliza mal) en 4 de los 5 años.

---

## 4. Bug #2 — el propio backtest hacía trampa ("perfect-foresight")

Al revisar el código de `main_backtest()`, se encontró que alimentaba el período de prueba con los valores climáticos **reales, ya conocidos hoy** (2026) — no con lo que producción realmente tiene disponible al momento de pronosticar. En producción real, más allá del corto plazo:

- `pdo_index`, `soi_index`, `gmst_anomalia` se mantienen en su último valor conocido por 90 días y luego decaen linealmente a un valor neutral (climatológico) en los siguientes 90 días.
- `ideam_precipitacion_anomalia`, `apor_ener_lag7` se asumen exactamente en cero (condición "normal") desde el primer día del pronóstico.
- Solo `oni_index`/`oni_index_lag90` tienen un pronóstico real hacia adelante (NOAA CPC).

Es decir: el número de la tabla anterior era, en realidad, un **techo optimista** — el mejor caso posible si el modelo hubiera conocido el clima futuro perfectamente.

**Corregido**: nueva función `main_backtest_produccion_fiel(backtest_year, fuente)` que reconstruye el período de prueba con la misma lógica que usa producción real. Requirió además corregir la propia función de reconstrucción de regresores (`construir_regresores_futuros()`), que usaba internamente `pd.Timestamp.today()` en vez de aceptar una fecha de referencia — sin este fix, un backtest histórico habría usado por error la fecha real de hoy (2026) en vez de la fecha de corte del backtest.

Resultado — comparación entre el techo optimista y la medición honesta:

| Año | Perfect-foresight | **Fiel a producción** |
|---|---|---|
| 2022 | 22.56% | **27.11%** |
| 2023 | 20.17% | **23.20%** |
| 2024 | 9.26% | **7.16%** (contraintuitivo: mejor sin trampa) |
| 2009 | — | **16.61%** |
| 2014 | — | **31.66%** |

El caso de 2024 es un hallazgo genuino, no un error: "conocer perfectamente" el clima real a veces introduce más ruido en el ajuste que asumir una condición neutral, si el histórico real de ese período específico tuvo valores atípicos.

---

## 5. Bug #3 (mayor) — SARIMAX nunca usó ninguna variable exógena

Al intentar agregar SOI como segunda variable exógena de SARIMAX (además de ONI), el resultado del backtest salió **exactamente idéntico** al de la corrida sin SOI — sospechoso. Investigado con un experimento controlado (comparar `auto_arima` entrenado sin exógeno / con ONI real / con **ruido aleatorio puro** como control negativo): los 3 casos dieron el mismo AIC exacto, y ningún coeficiente exógeno aparecía en el resumen del modelo ajustado.

**Causa raíz**: la librería `pmdarima` (versión instalada, 2.1.1) renombró el parámetro de variables exógenas de `exogenous` a `X` en `auto_arima()`, `ARIMA.fit()` y `ARIMA.predict()`. Como `auto_arima()` acepta cualquier argumento adicional sin error (`**fit_args`), las 6 llamadas de este archivo que usaban el nombre viejo `exogenous=...` se ignoraban silenciosamente — sin ningún error ni warning. **El componente SARIMAX ha sido, en la práctica, un SARIMA puro (sin ninguna señal climática) desde antes de esta sesión**, pese a que todo el código, comentarios y documentación asumían lo contrario.

**Corregido**: las 6 ocurrencias cambiadas de `exogenous=` a `X=`.

**Impacto real medido, tras corregir el bug y re-correr los 5 backtests**: el cambio fue pequeño (entre −0.71 y +1.57 puntos porcentuales, sin dirección consistente). Esto tiene una explicación: el ensemble está dominado por el peso de Prophet (típicamente 0.85-0.9), que ya recibía las 7 señales climáticas desde siempre vía `add_regressor()` — el componente SARIMAX, aunque roto, tenía una influencia minoritaria en el resultado final. Además, el coeficiente de ONI en el SARIMAX corregido resultó **no ser estadísticamente significativo** (p=0.815) sobre la serie diaria completa de 26 años — consistente con el hallazgo (ver §7) de que el clima correlaciona mucho más fuerte con los aportes hídricos (flujo) que con el nivel del embalse (stock) directamente.

**Aun así, el fix es correcto y se mantiene**: es la primera vez que SARIMAX funciona como fue diseñado, y beneficia a producción sin ningún riesgo adicional identificado.

---

## 6. Bug #4 — el intervalo de confianza no se ensanchaba con el horizonte

Verificado contra el código fuente instalado de Prophet 1.3.0: con `growth='flat'` (usado para EMBALSES_PCT) y `mcmc_samples=0`, la función `flat_trend()` de Prophet devuelve un valor **constante** en cada simulación de incertidumbre, sin importar cuán lejos en el futuro esté el día pronosticado. El único componente que sí crecía con el horizonte era la contribución de SARIMAX (minoritaria en el peso del ensemble), diluyendo casi por completo el efecto. Un factor de calibración adicional (`factor_cal`) se aplicaba de forma **plana** en todo el horizonte — explicaba por qué la cobertura empírica del intervalo salía ~100% en todos los backtests: la banda era ancha de forma pareja, no informativa sobre dónde había más incertidumbre real.

**Corregido**: el ancho del intervalo ahora usa la forma real de crecimiento del componente SARIMAX (cuya varianza de pronóstico sí crece genuinamente con el horizonte, por construcción estadística de un ARIMA), tomando el máximo entre esa señal y la pendiente de degradación de cobertura observada dentro del propio holdout. Verificado con una prueba aislada (datos sintéticos): el ancho del intervalo pasó de ser prácticamente constante a crecer **7 veces** entre el día 1 y el día 730 — sin afectar el valor central del pronóstico.

---

## 7. Desglose de error por horizonte — dónde falla realmente el modelo

Se añadió a `main_backtest()`/`main_backtest_produccion_fiel()` un desglose del MAPE por bucket de horizonte (columna `mape_por_horizonte`, persistida en `predictions_backtest_history`).

Ejemplo (2023, fiel a producción, con el fix de SARIMAX):

| Horizonte | MAPE |
|---|---|
| 1-30 días | 3.85% |
| 31-90 días | 33.17% |
| 91-180 días | **50.36%** |
| 181-365 días | 25.81% |
| 366-730 días | 15.27% |

**Patrón consistente en los 5 años corridos**: el corto plazo (1-30 días) es siempre el punto fuerte del modelo (2-8% de error), pero el rango de **31 a 180 días es sistemáticamente el más débil** — nunca el mejor, casi siempre de los peores (10% a 55%). El muy largo plazo (366-730 días) es más variable (5% a 48%), dependiendo de qué tan parecido resultó ser el futuro real a la extrapolación simple que el modelo asume para las señales sin pronóstico oficial.

**Causa probable** (evidencia de investigación externa, ver `docs/trabajo de grado/00_LEEME.md` — tesis de grado de Melissa Cardona, análisis de correlación/Granger 2000-2018): el nivel del embalse es una variable de **stock** (integral acumulada de aportes pasados), mientras que el clima correlaciona fuerte con las variables de **flujo** (aportes hídricos, r=0.72 con 13 días de rezago para `xm_PorcApor → HSIN`; SOI correlaciona más fuerte que ONI con los aportes: r=0.32-0.46 vs. r=0.15-0.23). Regresar el nivel del embalse directamente contra el clima de hoy (como hace SARIMAX) salta el paso donde la señal climática realmente es fuerte — un pipeline de dos etapas (predecir aportes primero, luego integrar al nivel) es la mejora arquitectónica de mayor potencial identificada, **aún no implementada**.

---

## 8. Cambios en la comunicación pública (portal)

- `GET /v1/predictions/dashboard`: el campo `mape` de embalses ahora prioriza el resultado de `predictions_backtest_history` (out-of-sample real) sobre el holdout optimista; nuevos campos `mape_rango_min`, `mape_rango_max`, `mape_anios_evaluados` exponen el rango observado entre todos los años ya corridos.
- Frontend (`energia/predicciones`): la tarjeta de precisión, la leyenda del gráfico y el texto narrativo muestran ahora **"MAPE X%-Y% (rango histórico validado)"** en vez de un número único, cuando hay más de un año de backtest disponible — con explicación en lenguaje simple de por qué el error varía según el año.
- `domain/services/portal_report_service.py` (generador del PDF descargable): mismo criterio aplicado, para que el documento exportado no contradiga lo que muestra la página web.

---

## 9. Estado actual y trabajo pendiente (backlog)

**Ya corregido y en producción**: bugs #1-#4 de arriba, más limpieza de configuración muerta (`n_jobs=-1` en `auto_arima`, ignorado silenciosamente por la librería cuando `stepwise=True`; documentación de que `changepoint_prior_scale` es inerte bajo `growth='flat'`) y eliminación de un mecanismo de pesos adaptativos que consultaba tablas en vivo sin filtro de fecha de corte (fuga temporal en principio, aunque verificado que nunca llegaba a afectar un pronóstico real).

**Backlog explícito, no implementado todavía**, por orden de potencial de impacto:

1. **Pipeline de dos etapas (aportes → nivel)**: el cambio de mayor potencial según la evidencia de correlación — requiere rediseño real, no un ajuste puntual.
2. **Reconsiderar `growth='flat'` vs. `'linear'` en Prophet**: hay evidencia de una tendencia secular real inducida por El Niño que `growth='flat'` no puede capturar en absoluto.
3. **`oni_index_lag90` como bandera de régimen** (crisis/normal, umbral binario) en vez de solo regresor continuo — su correlación continua es débil, pero su capacidad de distinguir crisis-vs-normal (test de Kolmogorov-Smirnov) es la más fuerte de cualquier variable climática disponible.
4. **Ventana de entrenamiento ponderada hacia lo reciente**, en vez de usar los 26 años completos por igual — ayudaría al modelo a adaptarse más rápido al régimen climático actual.
5. Reducir el ancho *base* del intervalo de confianza sin perder cobertura real — el fix de esta ronda corrige que el ancho crezca con el horizonte, pero el ancho de partida sigue siendo generoso (cobertura empírica ~100% en los 5 backtests).
6. Investigar si el ETL de IDEAM de producción usa un timeout corto — la tesis de grado encontró mejoras de cobertura de datos históricos de hasta 3x al ampliar el timeout de 35s a 45s.

**Nota de gobernanza**: todo el trabajo de esta ronda se hizo con `main_backtest_produccion_fiel()` como herramienta de diagnóstico — no toca el pipeline de entrenamiento real de producción (`main()`), salvo por los fixes #3 y #4 (SARIMAX exógeno, intervalo de confianza), que sí afectan al próximo reentrenamiento programado. Ya existe una tarea de Celery (`backtests-predicciones-mensual`, primer domingo del mes) que re-corre el backtest riguroso automáticamente — pero solo para el año más reciente, no el barrido de múltiples años/crisis hecho en esta ronda, que fue un ejercicio manual puntual.

---

## Referencias de código

- `scripts/train_predictions_sector_energetico.py`: `PredictorMetricaSectorial` (clase, línea ~1275), `main_backtest()`, `main_backtest_produccion_fiel()`, `construir_regresores_futuros()`.
- `sql/migrations/039_predictions_backtest_history.sql`, `040_predictions_backtest_mape_por_horizonte.sql`.
- `api/v1/routes/predictions.py` (endpoint `/v1/predictions/dashboard`).
- `docs/trabajo de grado/00_LEEME.md` — evidencia de correlación/Granger citada en §7.
