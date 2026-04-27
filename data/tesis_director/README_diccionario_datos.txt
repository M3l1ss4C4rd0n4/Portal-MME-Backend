
================================================================================
  DATOS PORTAL ENERGÉTICO COLOMBIA — PAQUETE PARA DIRECTOR DE TESIS
  Generado: 14 de April de 2026
  Fuente primaria: XM (Operador del Sistema Interconectado Nacional, SIN)
  Fuente climática: NASA POWER (Power.larc.nasa.gov), IDEAM
  Sistema: Portal Dirección de Energía — MinMinas
================================================================================

DESCRIPCIÓN GENERAL
-------------------
Este paquete contiene datos históricos del Sistema Interconectado Nacional (SIN)
de Colombia, extraídos de la base de datos del Portal Energético del Ministerio
de Minas y Energía. Los datos son consumidos diariamente vía API oficial de XM
(operador del mercado mayorista de energía en Colombia).

Los archivos están en formato CSV (separador: coma, codificación: UTF-8 con BOM).
Unidades monetarias: COP (pesos colombianos). Energía: GWh salvo indicación.

ARCHIVOS
--------

1. dataset_maestro_diario.csv
   Serie diaria PIVOTADA desde año 2000 hasta hoy con las variables más relevantes
   del SIN agregadas al nivel sistema.
   Columnas:
     fecha                          : Fecha (YYYY-MM-DD)
     embalses_pct_util_sistema      : % volumen útil promedio del sistema de embalses (adim.)
     aportes_hidricos_gwh           : Aportes hídricos totales al sistema (GWh/día)
     generacion_hidraulica_gwh      : Generación hidráulica total (GWh/día)
     generacion_termica_gwh         : Generación térmica total (GWh/día) — gas, carbón, fuel oil
     generacion_solar_gwh           : Generación solar fotovoltaica total (GWh/día)
     generacion_eolica_gwh          : Generación eólica total (GWh/día)
     generacion_total_gwh           : Generación total SIN (GWh/día)
     demanda_real_gwh               : Demanda real atendida (GWh/día)
     precio_bolsa_cop_kwh           : Precio de bolsa nacional doméstico (COP/kWh)
     precio_bolsa_no_dom_cop_kwh    : Precio de bolsa nacional no doméstico (COP/kWh)
     precio_escasez_cop_kwh         : Precio de escasez regulatorio (COP/kWh)
     precipitacion_nasa_mm          : Precipitación NASA POWER promedio zonas hidrológicas (mm/día)
     temperatura_nasa_c             : Temperatura a 2m NASA POWER (°C)
     humedad_relativa_pct           : Humedad relativa a 2m NASA POWER (%)
     irradiacion_mj_m2              : Irradiación global horizontal NASA POWER (MJ/m²/día)
     viento_10m_ms                  : Velocidad del viento a 10m NASA POWER (m/s)
     perdidas_energia_gwh           : Pérdidas estimadas totales sistema (GWh/día)
     participacion_hidraulica_pct   : generacion_hidraulica / generacion_total × 100 (%)
     balance_oferta_demanda_gwh     : generacion_total - demanda_real (GWh/día)
   Fuente: XM (métricas), NASA POWER (clima)
   Período: 2000-01-01 a hoy (series largas: hidráulica, embalses, aportes desde 2000;
             clima NASA, demanda, precios desde 2020)

2. embalses_individuales.csv
   Nivel de cada uno de los 26 embalses principales del SIN por separado.
   Columnas: fecha | embalse | pct_volumen_util
   Embalses incluidos: Ituango, Guavio, El Quimbo, Betania, Calima, Peñol,
     Salvajina, Porce II, Porce III, Miel I, Chuza, Urra, Prado, Playas,
     Topocoro, Miraflores, Riogrande II, Troneras, entre otros.
   Fuente: XM — métrica PorcVoluUtilDiar
   Período: 2000-01-01 a hoy

3. aportes_hidricos_rios.csv
   Aportes hídricos energéticos diarios por río individual (48 ríos del SIN).
   Columnas: fecha | rio | aporte_gwh
   Ríos incluidos: Sogamoso, Ituango, Bogotá, Guavio, Guatapé, San Carlos,
     Betania, Cauca-Salvajina, Miel, Nare, Sinu, entre otros.
   Fuente: XM — métrica AporEner
   Período: 2000-01-01 a hoy

4. generacion_por_planta.csv
   Generación eléctrica real diaria de cada una de las ~558 plantas registradas.
   Columnas: fecha | planta | tecnologia | region | generacion_gwh
   Tecnologías: HIDRAULICA, TERMICA, SOLAR, EOLICA, COGENERADOR
   Fuente: XM — métrica Gene (real definitivo)
   Período: 2000-01-01 a hoy

5. predictions_calidad.csv
   Historial de evaluación ex-post de los 13 modelos predictivos actuales.
   Mide la precisión real (MAPE ex-post) comparando predicciones vs valores reales
   una vez publicados por XM.
   Columnas: fuente | fecha_evaluacion | mape_expost | rmse_expost | mape_train |
             rmse_train | modelo | factor_drift | alerta_drift | notas
   Fuentes evaluadas: DEMANDA, EMBALSES, EMBALSES_PCT, GENE_TOTAL, Hidráulica,
     Térmica, Solar, Eólica, Biomasa, APORTES_HIDRICOS, PRECIO_BOLSA,
     PRECIO_ESCASEZ, PERDIDAS
   Período de evaluación: Feb 2026 - hoy (sistema en producción desde esa fecha)
   Nota: factor_drift > 2 indica degradación significativa del modelo

6. predictions_actuales.csv
   Predicciones vigentes generadas por el sistema para los próximos 90 días.
   Columnas: fuente | fecha_prediccion | horizonte_dias | modelo |
             valor_gwh_predicho | intervalo_inferior | intervalo_superior |
             confianza | mape | rmse | metodo_prediccion | fecha_generacion
   Modelos usados: Prophet+SARIMA ensemble, LightGBM directo, TCN (horizonte largo)
   Período de predicción: horizonte de 1 a 90 días hacia adelante

7. costo_unitario_diario.csv
   Costo Unitario de Energía (CU) calculado diariamente según metodología CREG.
   Incluye desagregación por componentes tarifarios.
   Columnas: fecha | componente_g (generación) | componente_t (transmisión) |
             componente_d (distribución) | componente_c (comercialización) |
             componente_p (pérdidas) | componente_r (restricciones) | cu_total |
             demanda_gwh | generacion_gwh | perdidas_gwh | perdidas_pct | confianza | notas
   Unidades: COP/kWh para componentes de costo
   Fuente: Cálculo propio a partir de datos XM + CREG
   Período: 2020-02-06 a hoy

8. perdidas_tecnicas_notecnicas.csv
   Estimación diaria de pérdidas en el sistema de distribución, separadas entre:
   - Técnicas: físicamente inevitables (calor Joule: proporcionales a I²R, correlacionada con flujo)
   - No técnicas: pérdidas comerciales (hurto, fraude, errores de medición)
   Columnas: fecha | perdidas_total_gwh | perdidas_tecnicas_gwh | perdidas_no_tecnicas_gwh |
             generacion_gwh | perdidas_total_pct | perdidas_tecnicas_pct |
             perdidas_no_tecnicas_pct | costo_perdidas_total_mcop |
             costo_perdidas_tecnicas_mcop | costo_no_tecnicas_mcop |
             precio_bolsa_cop_kwh | metodo_estimacion | confianza |
             anomalia_detectada | notas
   Unidades: GWh para energía, MCOP (millones COP) para costos
   Nota: La separación técnica/no técnica es una ESTIMACIÓN (modelo estadístico),
         no medición directa. No existen medidores en cada punto de distribución.
   Período: 2020-02-06 a hoy

9. catalogo_recursos.csv
   Catálogo completo de recursos, plantas, embalses y ríos del SIN.
   Columnas: catalogo | codigo | nombre | tipo | region | capacidad | metadata
   Catálogos incluidos:
     ListadoRecursos  : 1,458 plantas generadoras (tipo: HIDRAULICA/TERMICA/SOLAR/EOLICA/COGENERADOR)
     ListadoAgentes   :   681 agentes del mercado mayorista
     ListadoEmbalses  :    38 embalses del SIN
     ListadoRios      :    87 ríos aportantes
   Fuente: XM
   Nota: columna 'capacidad' no está poblada actualmente (pendiente integración XM)

CONTEXTO TÉCNICO — LIMITACIONES CONOCIDAS
------------------------------------------
1. ENSO/ONI no disponible en BD: el índice oceánico del Niño (principal forzante
   climático de Colombia) NO está en este paquete. Debe obtenerse de NOAA:
   https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
   Este es el GAP más crítico para el modelo físico propuesto en la tesis.

2. Datos horarios no incluidos: la tabla metrics_hourly (32 GB) tiene resolución
   de 1 hora por planta desde 2020. Se omitió por tamaño. Puede generarse
   extracción agregada bajo solicitud.

3. Precipitación IDEAM solo desde 2025: la serie histórica larga de precipitación
   de estaciones IDEAM no está integrada. Las variables climáticas largas deben
   tomarse de ERA5 (ECMWF, https://cds.climate.copernicus.eu/) o NASA POWER.

4. Pérdidas no técnicas: estimación estadística, no medición directa.
   La columna anomalia_detectada = True indica outlier estadístico (z-score > 3σ).

5. Capacidades de embalses (V_max): no están en la BD. Fuente pública:
   XM Parámetros Técnicos — https://www.xm.com.co/

SISTEMA DE PREDICCIÓN ACTUAL — RESUMEN DE PRECISIÓN
----------------------------------------------------
Resultados MAPE ex-post (últimas evaluaciones, Feb-Abr 2026):
  EMBALSES          : ~0.02%  (excelente — nivel de agua poco volátil)
  EMBALSES_PCT      : ~3.4%   (muy bueno)
  PRECIO_ESCASEZ    : ~3.0%   (muy bueno — precio regulatorio predecible)
  Solar             : ~7.4%   (bueno)
  Biomasa           : ~10.9%  (aceptable)
  APORTES_HIDRICOS  : ~16.2%  (aceptable — fuerte estacionalidad ENSO)
  PERDIDAS          : ~21.5%  (regular)
  GENE_TOTAL        : ~24.4%  (regular)
  Térmica           : ~25.2%  (regular — depende de hidráulica)
  PRECIO_BOLSA      : ~39.9%  (deficiente — microestructura de mercado)
  Hidráulica        : ~39.9%  (deficiente — correlacionada con ENSO ausente)
  Eólica            : ~81.6%  (muy deficiente — datos < 3 años, poca historia)
  DEMANDA           : ~84.4%  (muy deficiente — anomalías frecuentes)

PROPUESTA DE MEJORA (TESIS)
---------------------------
El trabajo de grado propone incorporar:
  a) Modelo de balance hídrico EDO por cuenca (scipy.integrate.solve_ivp)
  b) Forzante climático ENSO (ONI) como variable exógena covariante
  c) Detección de ralentización crítica (Critical Slowing Down) como
     sistema de alerta temprana de crisis energéticas
  d) Entropía de transferencia para mapeo causal entre variables SIN
  e) Modelo de dos capas para precio de bolsa (equilibrio físico + prima mercado)
  f) Separación de pérdidas técnicas/no técnicas mediante regresión Joule
  g) Simulaciones contrafactuales Monte Carlo para análisis de riesgo

CONTACTO
--------
Portal: Dirección de Energía — Ministerio de Minas y Energía de Colombia
Datos primarios: XM S.A. E.S.P. (xm.com.co)
Generado con: Python 3.11, pandas, psycopg2, PostgreSQL 15
