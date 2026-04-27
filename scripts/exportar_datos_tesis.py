"""
exportar_datos_tesis.py
=======================
Exporta los datos relevantes de la BD portal_energetico para el director de tesis.

Genera en data/tesis_director/:
  1. dataset_maestro_diario.csv     — Serie pivotada 2000-2026 con todas las variables clave
  2. embalses_individuales.csv      — Nivel % útil de cada embalse por separado (2000-2026)
  3. aportes_hidricos_rios.csv      — Aportes hídricos por río individual (2000-2026)
  4. generacion_por_planta.csv      — Generación real por planta (2000-2026, ~558 plantas)
  5. predictions_calidad.csv        — Historial de calidad ex-post de predicciones actuales
  6. predictions_actuales.csv       — Predicciones vigentes con intervalos de confianza
  7. costo_unitario_diario.csv      — CU desagregado G+T+D+C+P+R diario (2020-2026)
  8. perdidas_tecnicas_notecnicas.csv — Pérdidas técnicas vs no técnicas estimadas (2020-2026)
  9. catalogo_recursos.csv          — Catálogo de plantas, embalses, ríos con tipo/tecnología
 10. README_diccionario_datos.txt   — Descripción de cada archivo, campos, unidades y fuente

Uso:
    cd /home/admonctrlxm/server
    source venv/bin/activate
    python scripts/exportar_datos_tesis.py
"""

import os
import sys
import pandas as pd
import psycopg2
from datetime import datetime

# ── Configuración ─────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "portal_energetico",
    "user": "postgres",
}

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tesis_director")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def conectar():
    return psycopg2.connect(**DB_CONFIG)


def exportar(df: pd.DataFrame, nombre: str):
    path = os.path.join(OUTPUT_DIR, nombre)
    df.to_csv(path, index=False, encoding="utf-8-sig")  # utf-8-sig para Excel
    kb = os.path.getsize(path) / 1024
    print(f"  ✓ {nombre:50s} {len(df):>8,} filas  {kb:>8,.0f} KB")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# 1. DATASET MAESTRO DIARIO (pivotado)
# ══════════════════════════════════════════════════════════════════════════════
def generar_dataset_maestro(conn):
    print("\n[1/9] Dataset maestro diario (pivotado)...")

    # — Nivel de embalses sistema (% útil agregado XM)
    q_embalses = """
        SELECT fecha::date as fecha, AVG(valor_gwh) as embalses_pct_util_sistema
        FROM sector_energetico.metrics
        WHERE metrica = 'PorcVoluUtilDiar' AND recurso = '_SISTEMA_'
        GROUP BY fecha::date ORDER BY fecha::date
    """

    # — Aportes hídricos sistema total (GWh/día)
    q_aportes = """
        SELECT fecha::date as fecha, SUM(valor_gwh) as aportes_hidricos_gwh
        FROM sector_energetico.metrics
        WHERE metrica = 'AporEner' AND entidad = 'Sistema'
        GROUP BY fecha::date ORDER BY fecha::date
    """

    # — Generación real por categoría tecnológica (usando nombre del recurso)
    # Gene tiene ~558 plantas; las agrupamos por tecnología usando el catálogo
    q_gene_hidro = """
        SELECT m.fecha::date as fecha, SUM(m.valor_gwh) as generacion_hidraulica_gwh
        FROM sector_energetico.metrics m
        JOIN sector_energetico.catalogos c ON c.codigo = m.recurso AND c.catalogo = 'ListadoRecursos'
        WHERE m.metrica = 'Gene' AND m.entidad = 'Recurso' AND c.tipo = 'HIDRAULICA'
        GROUP BY m.fecha::date ORDER BY m.fecha::date
    """
    q_gene_termica = """
        SELECT m.fecha::date as fecha, SUM(m.valor_gwh) as generacion_termica_gwh
        FROM sector_energetico.metrics m
        JOIN sector_energetico.catalogos c ON c.codigo = m.recurso AND c.catalogo = 'ListadoRecursos'
        WHERE m.metrica = 'Gene' AND m.entidad = 'Recurso' AND c.tipo = 'TERMICA'
        GROUP BY m.fecha::date ORDER BY m.fecha::date
    """
    q_gene_solar = """
        SELECT m.fecha::date as fecha, SUM(m.valor_gwh) as generacion_solar_gwh
        FROM sector_energetico.metrics m
        JOIN sector_energetico.catalogos c ON c.codigo = m.recurso AND c.catalogo = 'ListadoRecursos'
        WHERE m.metrica = 'Gene' AND m.entidad = 'Recurso' AND c.tipo = 'SOLAR'
        GROUP BY m.fecha::date ORDER BY m.fecha::date
    """
    q_gene_eolica = """
        SELECT m.fecha::date as fecha, SUM(m.valor_gwh) as generacion_eolica_gwh
        FROM sector_energetico.metrics m
        JOIN sector_energetico.catalogos c ON c.codigo = m.recurso AND c.catalogo = 'ListadoRecursos'
        WHERE m.metrica = 'Gene' AND m.entidad = 'Recurso' AND c.tipo = 'EOLICA'
        GROUP BY m.fecha::date ORDER BY m.fecha::date
    """
    q_gene_total = """
        SELECT fecha::date as fecha, SUM(valor_gwh) as generacion_total_gwh
        FROM sector_energetico.metrics
        WHERE metrica = 'Gene' AND entidad = 'Sistema'
        GROUP BY fecha::date ORDER BY fecha::date
    """

    # — Demanda real sistema (GWh/día)
    q_demanda = """
        SELECT fecha::date as fecha, SUM(valor_gwh) as demanda_real_gwh
        FROM sector_energetico.metrics
        WHERE metrica = 'DemaReal' AND entidad = 'Sistema'
        GROUP BY fecha::date ORDER BY fecha::date
    """

    # — Precio bolsa nacional (COP/kWh) y precio de escasez
    q_precios = """
        SELECT fecha::date as fecha,
               MAX(CASE WHEN recurso='DOMÉSTICO' THEN valor_gwh END) as precio_bolsa_cop_kwh,
               MAX(CASE WHEN recurso='NO DOMÉSTICO' THEN valor_gwh END) as precio_bolsa_no_dom_cop_kwh
        FROM sector_energetico.metrics
        WHERE metrica = 'PrecBolsNaci'
        GROUP BY fecha::date ORDER BY fecha::date
    """
    q_escasez = """
        SELECT fecha::date as fecha, AVG(valor_gwh) as precio_escasez_cop_kwh
        FROM sector_energetico.metrics
        WHERE metrica = 'PrecEsca'
        GROUP BY fecha::date ORDER BY fecha::date
    """

    # — Variables climáticas NASA POWER (zona hidrológica)
    q_nasa = """
        SELECT fecha::date as fecha,
               AVG(CASE WHEN metrica='NASA_Precipitacion' THEN valor_gwh END) as precipitacion_nasa_mm,
               AVG(CASE WHEN metrica='NASA_Temp2M_Hidro' THEN valor_gwh END)  as temperatura_nasa_c,
               AVG(CASE WHEN metrica='NASA_RH2M_Hidro'   THEN valor_gwh END)  as humedad_relativa_pct,
               AVG(CASE WHEN metrica='NASA_IrrGlobal'    THEN valor_gwh END)  as irradiacion_mj_m2,
               AVG(CASE WHEN metrica='NASA_Viento10M'    THEN valor_gwh END)  as viento_10m_ms
        FROM sector_energetico.metrics
        WHERE metrica IN ('NASA_Precipitacion','NASA_Temp2M_Hidro','NASA_RH2M_Hidro',
                          'NASA_IrrGlobal','NASA_Viento10M')
        GROUP BY fecha::date ORDER BY fecha::date
    """

    # — Pérdidas sistema (GWh/día)
    q_perdidas = """
        SELECT fecha::date as fecha, SUM(valor_gwh) as perdidas_energia_gwh
        FROM sector_energetico.metrics
        WHERE metrica = 'PerdidasEner' AND entidad = 'Sistema'
        GROUP BY fecha::date ORDER BY fecha::date
    """

    print("   Cargando series individuales (puede tomar ~60 seg)...")
    dfs = {}
    queries = {
        "embalses": q_embalses,
        "aportes": q_aportes,
        "hidro": q_gene_hidro,
        "termica": q_gene_termica,
        "solar": q_gene_solar,
        "eolica": q_gene_eolica,
        "gene_total": q_gene_total,
        "demanda": q_demanda,
        "precios": q_precios,
        "escasez": q_escasez,
        "nasa": q_nasa,
        "perdidas": q_perdidas,
    }

    for nombre, query in queries.items():
        print(f"   → {nombre}...", end=" ", flush=True)
        dfs[nombre] = pd.read_sql(query, conn, parse_dates=["fecha"])
        print(f"{len(dfs[nombre]):,} filas")

    # Merge por fecha (outer join para conservar toda la historia)
    print("   Combinando en tabla pivotada...")
    maestro = dfs["embalses"]
    for key in ["aportes", "hidro", "termica", "solar", "eolica", "gene_total",
                "demanda", "precios", "escasez", "nasa", "perdidas"]:
        maestro = maestro.merge(dfs[key], on="fecha", how="outer")

    # Ordenar y agregar columnas derivadas
    maestro = maestro.sort_values("fecha").reset_index(drop=True)

    # Columna: participación hidráulica (%)
    maestro["participacion_hidraulica_pct"] = (
        maestro["generacion_hidraulica_gwh"] / maestro["generacion_total_gwh"] * 100
    ).round(2)

    # Columna: déficit (demanda - generación, GWh)
    maestro["balance_oferta_demanda_gwh"] = (
        maestro["generacion_total_gwh"] - maestro["demanda_real_gwh"]
    ).round(4)

    exportar(maestro, "dataset_maestro_diario.csv")
    return maestro


# ══════════════════════════════════════════════════════════════════════════════
# 2. EMBALSES INDIVIDUALES (serie larga 2000-2026)
# ══════════════════════════════════════════════════════════════════════════════
def generar_embalses_individuales(conn):
    print("\n[2/9] Embalses individuales (% volumen útil)...")
    q = """
        SELECT fecha::date as fecha, recurso as embalse, valor_gwh as pct_volumen_util
        FROM sector_energetico.metrics
        WHERE metrica = 'PorcVoluUtilDiar'
          AND recurso NOT IN ('_SISTEMA_', 'Sistema', 'AGREGADO BOGOTA')
        ORDER BY fecha::date, recurso
    """
    df = pd.read_sql(q, conn, parse_dates=["fecha"])
    exportar(df, "embalses_individuales.csv")


# ══════════════════════════════════════════════════════════════════════════════
# 3. APORTES HÍDRICOS POR RÍO (serie larga 2000-2026)
# ══════════════════════════════════════════════════════════════════════════════
def generar_aportes_rios(conn):
    print("\n[3/9] Aportes hídricos por río individual...")
    q = """
        SELECT fecha::date as fecha, recurso as rio, valor_gwh as aporte_gwh
        FROM sector_energetico.metrics
        WHERE metrica = 'AporEner' AND entidad = 'Rio'
        ORDER BY fecha::date, recurso
    """
    df = pd.read_sql(q, conn, parse_dates=["fecha"])
    exportar(df, "aportes_hidricos_rios.csv")


# ══════════════════════════════════════════════════════════════════════════════
# 4. GENERACIÓN POR PLANTA (2000-2026, ~558 plantas)
# ══════════════════════════════════════════════════════════════════════════════
def generar_gene_por_planta(conn):
    print("\n[4/9] Generación real por planta (con tipo tecnología)...")
    q = """
        SELECT m.fecha::date as fecha,
               m.recurso as planta,
               COALESCE(c.tipo, 'DESCONOCIDO') as tecnologia,
               COALESCE(c.region, '') as region,
               m.valor_gwh as generacion_gwh
        FROM sector_energetico.metrics m
        LEFT JOIN sector_energetico.catalogos c
               ON c.codigo = m.recurso AND c.catalogo = 'ListadoRecursos'
        WHERE m.metrica = 'Gene' AND m.entidad = 'Recurso'
        ORDER BY m.fecha::date, m.recurso
    """
    df = pd.read_sql(q, conn, parse_dates=["fecha"])
    exportar(df, "generacion_por_planta.csv")


# ══════════════════════════════════════════════════════════════════════════════
# 5. CALIDAD DE PREDICCIONES (MAPE ex-post histórico)
# ══════════════════════════════════════════════════════════════════════════════
def generar_calidad_predicciones(conn):
    print("\n[5/9] Historial calidad ex-post de predicciones...")
    q = """
        SELECT fuente, fecha_evaluacion::date, fecha_desde, fecha_hasta,
               dias_overlap, mape_expost, rmse_expost, mape_train, rmse_train,
               modelo, notas
        FROM sector_energetico.predictions_quality_history
        ORDER BY fuente, fecha_evaluacion
    """
    df = pd.read_sql(q, conn, parse_dates=["fecha_evaluacion", "fecha_desde", "fecha_hasta"])

    # Columna: razón drift (qué tanto empeoró vs entrenamiento)
    df["factor_drift"] = (df["mape_expost"] / df["mape_train"]).round(2)
    df["alerta_drift"] = df["factor_drift"] > 2.0
    exportar(df, "predictions_calidad.csv")


# ══════════════════════════════════════════════════════════════════════════════
# 6. PREDICCIONES ACTUALES CON INTERVALOS
# ══════════════════════════════════════════════════════════════════════════════
def generar_predicciones_actuales(conn):
    print("\n[6/9] Predicciones actuales vigentes...")
    q = """
        SELECT fuente, fecha_prediccion, horizonte_dias, modelo,
               valor_gwh_predicho, intervalo_inferior, intervalo_superior,
               confianza, mape, rmse, metodo_prediccion,
               fecha_generacion::date as fecha_generacion
        FROM sector_energetico.predictions
        ORDER BY fuente, fecha_prediccion
    """
    df = pd.read_sql(q, conn, parse_dates=["fecha_prediccion", "fecha_generacion"])
    exportar(df, "predictions_actuales.csv")


# ══════════════════════════════════════════════════════════════════════════════
# 7. COSTO UNITARIO DIARIO (componentes tarifarios)
# ══════════════════════════════════════════════════════════════════════════════
def generar_costo_unitario(conn):
    print("\n[7/9] Costo Unitario diario (G+T+D+C+P+R)...")
    q = """
        SELECT fecha, componente_g, componente_t, componente_d,
               componente_c, componente_p, componente_r, cu_total,
               demanda_gwh, generacion_gwh, perdidas_gwh, perdidas_pct,
               confianza, notas
        FROM sector_energetico.cu_daily
        ORDER BY fecha
    """
    df = pd.read_sql(q, conn, parse_dates=["fecha"])
    exportar(df, "costo_unitario_diario.csv")


# ══════════════════════════════════════════════════════════════════════════════
# 8. PÉRDIDAS TÉCNICAS VS NO TÉCNICAS
# ══════════════════════════════════════════════════════════════════════════════
def generar_perdidas(conn):
    print("\n[8/9] Pérdidas técnicas vs no técnicas (2020-2026)...")
    q = """
        SELECT fecha,
               perdidas_total_gwh, perdidas_tecnicas_gwh, perdidas_no_tecnicas_gwh,
               generacion_gwh,
               perdidas_total_pct, perdidas_tecnicas_pct, perdidas_no_tecnicas_pct,
               costo_perdidas_total_mcop, costo_perdidas_tecnicas_mcop, costo_no_tecnicas_mcop,
               precio_bolsa_cop_kwh, metodo_estimacion, confianza,
               anomalia_detectada, notas
        FROM sector_energetico.losses_detailed
        ORDER BY fecha
    """
    df = pd.read_sql(q, conn, parse_dates=["fecha"])
    exportar(df, "perdidas_tecnicas_notecnicas.csv")


# ══════════════════════════════════════════════════════════════════════════════
# 9. CATÁLOGO DE RECURSOS
# ══════════════════════════════════════════════════════════════════════════════
def generar_catalogo(conn):
    print("\n[9/9] Catálogo de recursos (plantas, embalses, ríos)...")
    q = """
        SELECT catalogo, codigo, nombre, tipo, region, capacidad, metadata
        FROM sector_energetico.catalogos
        ORDER BY catalogo, tipo, nombre
    """
    df = pd.read_sql(q, conn)
    exportar(df, "catalogo_recursos.csv")


# ══════════════════════════════════════════════════════════════════════════════
# README / DICCIONARIO DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
def generar_readme():
    print("\n[README] Generando diccionario de datos...")
    hoy = datetime.today().strftime("%d de %B de %Y")

    texto = f"""
================================================================================
  DATOS PORTAL ENERGÉTICO COLOMBIA — PAQUETE PARA DIRECTOR DE TESIS
  Generado: {hoy}
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
"""
    path = os.path.join(OUTPUT_DIR, "README_diccionario_datos.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(texto)
    kb = os.path.getsize(path) / 1024
    print(f"  ✓ {'README_diccionario_datos.txt':50s} {kb:>8,.0f} KB")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  EXPORTACIÓN DE DATOS — PAQUETE TESIS DIRECTOR")
    print(f"  Destino: {OUTPUT_DIR}")
    print("=" * 70)

    conn = conectar()
    try:
        generar_dataset_maestro(conn)
        generar_embalses_individuales(conn)
        generar_aportes_rios(conn)
        generar_gene_por_planta(conn)
        generar_calidad_predicciones(conn)
        generar_predicciones_actuales(conn)
        generar_costo_unitario(conn)
        generar_perdidas(conn)
        generar_catalogo(conn)
    finally:
        conn.close()

    generar_readme()

    # Resumen final
    print("\n" + "=" * 70)
    print("  RESUMEN FINAL")
    print("=" * 70)
    total_bytes = 0
    for archivo in sorted(os.listdir(OUTPUT_DIR)):
        path = os.path.join(OUTPUT_DIR, archivo)
        size = os.path.getsize(path)
        total_bytes += size
        print(f"  {archivo:50s} {size/1024/1024:6.1f} MB")
    print(f"\n  TOTAL: {total_bytes/1024/1024:.1f} MB")
    print(f"\n  ✅ Archivos listos en: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
