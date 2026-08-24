#!/usr/bin/env python3
"""
Ontología — Fase 12/17: siembra ontologia.dim_metrica y ontologia.metrica_relacion.

Fase 17 extiende la cobertura de sector_energetico (única dominio catalogado
hasta ahora) a los otros 7 dominios de negocio del portal (fenoge,
colombia_solar, contratos_or, subsidios, presupuesto, hidrocarburos,
supervision) — mismo principio de curación por relevancia que siempre: solo se
catalogan columnas numéricas que son KPIs reales (verificadas contra
information_schema.columns en vivo), nunca IDs/fechas/texto libre que el
cargador dinámico de Excel (etl_nuevos_dashboards.py) tipeó como numeric por
heurística. Las tablas `presupuesto.c_*`/`o_*` (solo columnas `unnamed_N`, sin
cabecera parseable) y `hidrocarburos.presupuesto_proyectos` (duplicaría
codigo_tecnico de `presupuesto_resumen` — detalle por proyecto, no un KPI de
portal) quedan deliberadamente fuera.

Cobertura de sector_energetico sigue deliberadamente parcial: la ampliación 3
solo cataloga variables climáticas/solares (NASA/IDEAM) de nomenclatura
estándar y no ambigua — los códigos de liquidación/mercado de mayor volumen
restantes (DDVContratada, RecoPosMoneda, RecoNegMoneda, VentContEnerSICEP,
CompContEnerSICEP, PrecCargConf, DescMasa, PrecOferDesp/Ideal, VentBolsaTIEEner,
CompBolsaTIEEner, CostRecPos/Neg, PrecEsca, ComContRespEner, VentContRespEner)
se dejan sin catalogar a propósito: son terminología interna de liquidación de
XM de la que no se tiene certeza suficiente para no inventar una descripción
— mismo principio de siempre, ver geografia_alias/empresa_alias.

Las relaciones de metrica_relacion son una transcripción manual de lógica ya
verificada (core/umbrales_oficiales.py para sector_energetico; relaciones
aritméticas obvias entre columnas de la misma tabla para los demás dominios)
— nunca inferidas automáticamente desde nombres de columnas.

Uso:
    venv/bin/python3 scripts/ontologia/seed_dim_metrica.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from infrastructure.database.manager import db_manager  # noqa: E402
from infrastructure.logging.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Métricas base de XM confirmadas en uso real (sector_snapshot.py y otros
# routes/services que consultan sector_energetico.metrics con estas metrica=).
# ═══════════════════════════════════════════════════════════════════════════
METRICAS_BASE = [
    # (codigo_tecnico, nombre_display, unidad, descripcion)
    ("Gene", "Generación real del SIN", "GWh",
     "Generación eléctrica real despachada, por recurso/entidad o agregada al Sistema."),
    ("DemaSIN", "Demanda del Sistema Interconectado Nacional", "GWh",
     "Demanda total de energía del SIN."),
    ("DemaCome", "Demanda comercial", "GWh",
     "Demanda de energía facturada a comercializadores."),
    ("DemaReal", "Demanda real", "GWh",
     "Demanda de energía efectivamente atendida por el sistema."),
    ("PorcVoluUtilDiar", "Nivel de embalse del SIN (% volumen útil)", "%",
     "Porcentaje del volumen útil de los embalses agregados del SIN respecto a su capacidad total. "
     "Insumo directo del Índice NE (Res. CREG 209/2020)."),
    ("VoluUtilDiarEner", "Volumen útil diario de embalses", "GWh",
     "Volumen útil de los embalses expresado en energía equivalente (GWh)."),
    ("AporEner", "Aportes hídricos diarios", "GWh/día",
     "Aportes hídricos diarios a los embalses del SIN, en energía equivalente."),
    ("AporEnerMediHist", "Media histórica de aportes hídricos", "GWh/día",
     "Media histórica de aportes hídricos para el mismo período del año — denominador del Índice HSIN."),
    ("AporCaudal", "Aportes hídricos en caudal", "m³/s",
     "Aportes hídricos diarios expresados en caudal."),
    ("PorcApor", "Aportes hídricos vs. media histórica", "%",
     "Aportes hídricos actuales como porcentaje de la media histórica del mismo período — base del Índice HSIN."),
    ("CapEfecNeta", "Capacidad efectiva neta instalada", "MW",
     "Capacidad de generación efectiva neta instalada en el SIN."),
    ("CapaUtilDiarEner", "Capacidad útil diaria de embalses", "GWh",
     "Capacidad útil total diaria de los embalses del SIN, en energía equivalente."),
    ("PPPrecBolsNaci", "Precio de bolsa ponderado", "COP/kWh",
     "Precio de Bolsa Nacional Ponderado (PBP) — insumo del Índice PBP del Estatuto CREG 026/2014."),
    ("PrecEscaInf", "Precio de Escasez Inferior (PEI)", "COP/kWh",
     "Precio de Escasez Inferior vigente — Resolución CREG 101 066/2024, art. 3."),
    ("PrecEscaSup", "Precio de Escasez Superior (PES)", "COP/kWh",
     "Precio de Escasez Superior vigente — Resolución CREG 101 066/2024, art. 4."),
    ("MaxPrecOferNal", "Precio máximo de oferta nacional", "COP/kWh",
     "Techo regulatorio de precio de oferta en el mercado de bolsa nacional."),
    ("PerdidasEner", "Pérdidas de energía", "GWh",
     "Pérdidas de energía en el Sistema Interconectado Nacional."),
    ("RestAliv", "Restricciones aliviadas", "GWh",
     "Energía de restricciones operativas que fue aliviada por el despacho."),
    ("RestSinAliv", "Restricciones sin aliviar", "GWh",
     "Energía de restricciones operativas que no pudo ser aliviada por el despacho."),
    ("CompContEnerReg", "Compras en contratos regulados", "GWh",
     "Energía comprada bajo contratos bilaterales del mercado regulado."),
    ("PrecPromContRegu", "Precio promedio de contratos regulados", "COP/kWh",
     "Precio promedio de la energía transada en contratos bilaterales regulados."),
]

# ═══════════════════════════════════════════════════════════════════════════
# Fase 13 Bloque B — ampliación de METRICAS_BASE. Fuente: etl/config_metricas.py
# (METRICAS_CONFIG + UNIDADES_POR_METRICA), la configuración real y ya
# documentada de los ETLs que pueblan sector_energetico.metrics — no son
# métricas inventadas ni adivinadas, son las que el propio pipeline ETL del
# portal ya declara y describe. Prioriza las que tienen 'descripcion' propia
# en METRICAS_CONFIG (curación ya hecha por quien construyó el ETL) más un
# grupo adicional de nombres estándar de XM con unidad confirmada.
# ═══════════════════════════════════════════════════════════════════════════
METRICAS_BASE_AMPLIACION = [
    # Con descripción propia en etl/config_metricas.py::METRICAS_CONFIG
    ("RespComerAGC", "Responsabilidad Comercial AGC", "COP",
     "Responsabilidad comercial por Control Automático de Generación (AGC) del sistema."),
    ("PerdidasEnerReg", "Pérdidas de energía — mercado regulado", "GWh",
     "Pérdidas de energía atribuibles al mercado regulado."),
    ("PerdidasEnerNoReg", "Pérdidas de energía — mercado no regulado", "GWh",
     "Pérdidas de energía atribuibles al mercado no regulado."),
    ("DispoReal", "Disponibilidad real por recurso", "MW",
     "Disponibilidad real de generación reportada por cada recurso/planta."),
    ("DispoCome", "Disponibilidad comercial por recurso", "MW",
     "Disponibilidad comercial declarada por cada recurso/planta para el mercado."),
    ("DispoDeclarada", "Disponibilidad declarada por recurso", "MW",
     "Disponibilidad que cada recurso/planta declara tener disponible para despacho."),
    ("GeneSeguridad", "Generación de seguridad por recurso", "GWh",
     "Generación despachada por razones de seguridad operativa del sistema, no por mérito económico."),
    ("CostMargDesp", "Costo marginal de despacho", "COP/kWh",
     "Costo marginal horario del despacho del sistema."),
    ("PrecEscaAct", "Precio de Escasez de Activación (histórico)", "COP/kWh",
     "Precio de Escasez de Activación — vigente hasta feb. 2025, reemplazado por PEI/PES (Res. CREG 101 066/2024)."),
    # Nombres estándar de XM con unidad confirmada (UNIDADES_POR_METRICA),
    # sin 'descripcion' propia en METRICAS_CONFIG pero de significado estándar
    # y no ambiguo dentro de la nomenclatura XM.
    ("DemaRealReg", "Demanda real — mercado regulado", "GWh",
     "Demanda real de energía del mercado regulado."),
    ("DemaRealNoReg", "Demanda real — mercado no regulado", "GWh",
     "Demanda real de energía del mercado no regulado."),
    ("VertEner", "Vertimientos de energía", "GWh",
     "Energía vertida (agua turbinada sin generar, por embalse lleno u otra restricción operativa)."),
    ("ImpoEner", "Importaciones de energía", "GWh",
     "Energía importada desde interconexiones internacionales."),
    ("ExpoEner", "Exportaciones de energía", "GWh",
     "Energía exportada por interconexiones internacionales."),
    ("ENFICC", "Energía Firme para el Cargo por Confiabilidad", "GWh",
     "Energía firme reconocida a cada recurso para efectos del Cargo por Confiabilidad."),
    ("ObligEnerFirme", "Obligación de Energía Firme (OEF)", "GWh",
     "Obligación de Energía Firme asignada — insumo del Cargo por Confiabilidad."),
]

# ═══════════════════════════════════════════════════════════════════════════
# Segunda ampliación (Fase 13, ronda de profundización de ontología):
# priorizadas por volumen real de filas en sector_energetico.metrics (no por
# orden alfabético ni cobertura ciega) — se catalogan las que tienen >50.000
# filas Y terminología XM estándar de la que se tiene certeza razonable. Los
# ~80 códigos restantes (muchos con <200 filas o nombres ambiguos como
# 'DemaOR', 'RemuRealIndiv', 'IndRecMargina') se dejan deliberadamente sin
# catalogar en esta ronda — no se inventa una descripción para un código del
# que no se tiene certeza real, mismo principio que en toda la ontología.
# ═══════════════════════════════════════════════════════════════════════════
METRICAS_BASE_AMPLIACION_2 = [
    ("DemaComeNoReg", "Demanda comercial no regulada", "GWh",
     "Demanda de energía facturada a comercializadores del mercado no regulado."),
    ("GeneIdea", "Generación ideal", "GWh",
     "Generación que se habría dado en un despacho ideal, sin restricciones de red."),
    ("GeneProgDesp", "Generación programada por despacho", "GWh",
     "Generación programada resultante del despacho económico (orden de mérito)."),
    ("GeneProgRedesp", "Generación programada por redespacho", "GWh",
     "Generación reprogramada tras el despacho inicial, por restricciones operativas."),
    ("GeneFueraMerito", "Generación fuera de mérito", "GWh",
     "Generación despachada fuera del orden económico, por restricciones de red o seguridad."),
    ("DemaNoAtenProg", "Demanda no atendida programada", "GWh",
     "Demanda no atendida por racionamiento programado."),
    ("DemaNoAtenNoProg", "Demanda no atendida no programada", "GWh",
     "Demanda no atendida por falla o evento no programado."),
    ("DemaComeReg", "Demanda comercial regulada", "GWh",
     "Demanda de energía facturada a comercializadores del mercado regulado."),
    ("CompContEner", "Compras totales en contratos", "GWh",
     "Energía comprada bajo contratos bilaterales (regulado + no regulado)."),
    ("CompContEnerNoReg", "Compras en contratos — mercado no regulado", "GWh",
     "Energía comprada bajo contratos bilaterales del mercado no regulado."),
    ("VentContEner", "Ventas totales en contratos", "GWh",
     "Energía vendida bajo contratos bilaterales."),
    ("CompBolsNaciEner", "Compras de energía en bolsa nacional", "GWh",
     "Energía comprada directamente en la bolsa de energía nacional."),
    ("VentBolsNaciEner", "Ventas de energía en bolsa nacional", "GWh",
     "Energía vendida directamente en la bolsa de energía nacional."),
    ("RecoPosEner", "Reconciliación positiva de energía", "GWh",
     "Ajuste positivo entre la generación programada y la real de un recurso."),
    ("RecoNegEner", "Reconciliación negativa de energía", "GWh",
     "Ajuste negativo entre la generación programada y la real de un recurso."),
    ("EmisionesCO2Eq", "Emisiones de CO2 equivalente", "ton",
     "Emisiones de gases de efecto invernadero asociadas a la generación, en CO2 equivalente."),
    ("ConsCombustibleMBTU", "Consumo de combustible", "MBTU",
     "Consumo de combustible reportado por las plantas térmicas, en unidades térmicas (MBTU)."),
    ("AporCaudalMediHist", "Media histórica de aportes en caudal", "m³/s",
     "Media histórica de aportes hídricos en caudal para el mismo período del año."),
    ("VertMasa", "Vertimientos en volumen de agua", "Hm³",
     "Volumen de agua vertida (no turbinada) de los embalses."),
    ("VoluUtilDiarMasa", "Volumen útil diario de embalses (masa)", "Hm³",
     "Volumen útil diario de los embalses del SIN, en volumen de agua."),
    ("CapaUtilDiarMasa", "Capacidad útil diaria de embalses (masa)", "Hm³",
     "Capacidad útil total diaria de los embalses del SIN, en volumen de agua."),
    ("VolTurbMasa", "Volumen turbinado", "Hm³",
     "Volumen de agua turbinada para generación hidráulica."),
    ("ONI_Index", "Índice ONI (El Niño / La Niña)", None,
     "Índice Oceánico El Niño (NOAA) — mide la anomalía de temperatura superficial del Pacífico "
     "ecuatorial, referencia estándar para clasificar fase El Niño/La Niña/Neutral."),
    ("PDO_Index", "Índice PDO (Oscilación Decadal del Pacífico)", None,
     "Índice de Oscilación Decadal del Pacífico (NOAA), patrón climático de baja frecuencia."),
    ("SOI_Index", "Índice SOI (Oscilación del Sur)", None,
     "Índice de Oscilación del Sur (NOAA), mide la diferencia de presión atmosférica asociada a El Niño/La Niña."),
    ("GMST_Anomalia", "Anomalía de temperatura media global", "°C",
     "Anomalía de la temperatura media global de superficie respecto al período de referencia histórico."),
    ("CondicionEstatutoRiesgo", "Condición del Estatuto de Riesgo (fuente XM)", None,
     "Condición del sistema (NORMAL/VIGILANCIA/RIESGO) publicada directamente por XM según el "
     "Estatuto de Desabastecimiento — fuente oficial, distinta del cálculo interno CONDICION_SISTEMA "
     "de este portal (ver metrica_relacion) que se deriva de NE+HSIN+PBP."),
]

# ═══════════════════════════════════════════════════════════════════════════
# Tercera ampliación (Fase 17): variables climáticas/solares de nomenclatura
# estándar (prefijo NASA_/IDEAM_, mismo origen que ONI/PDO/SOI/GMST ya
# catalogados) — se excluyen deliberadamente los códigos de liquidación/
# mercado de mayor volumen (DDVContratada, RecoPosMoneda, etc., ver docstring
# del módulo): son terminología interna de XM de la que no se tiene certeza
# suficiente para describir sin inventar.
# ═══════════════════════════════════════════════════════════════════════════
METRICAS_BASE_AMPLIACION_3 = [
    ("NASA_Precipitacion", "Precipitación (NASA POWER)", "mm/día",
     "Precipitación diaria estimada por satélite (NASA POWER), usada como insumo climático de hidrología."),
    ("NASA_Temp2M", "Temperatura a 2m (NASA POWER)", "°C",
     "Temperatura del aire a 2 metros de altura, estimada por satélite (NASA POWER)."),
    ("NASA_Temp2M_Hidro", "Temperatura a 2m — zonas hidrológicas (NASA POWER)", "°C",
     "Temperatura del aire a 2 metros, agregada para las zonas de aporte hídrico relevantes al SIN."),
    ("NASA_RH2M", "Humedad relativa a 2m (NASA POWER)", "%",
     "Humedad relativa del aire a 2 metros de altura, estimada por satélite (NASA POWER)."),
    ("NASA_RH2M_Hidro", "Humedad relativa a 2m — zonas hidrológicas (NASA POWER)", "%",
     "Humedad relativa a 2 metros, agregada para las zonas de aporte hídrico relevantes al SIN."),
    ("NASA_Viento10M", "Velocidad del viento a 10m (NASA POWER)", "m/s",
     "Velocidad del viento a 10 metros de altura, estimada por satélite (NASA POWER)."),
    ("NASA_IrrGlobal", "Irradiancia solar global (NASA POWER)", "kWh/m²/día",
     "Irradiancia solar global horizontal estimada por satélite (NASA POWER), insumo de generación solar."),
    ("NASA_IrrCielo", "Irradiancia de cielo despejado (NASA POWER)", "kWh/m²/día",
     "Irradiancia solar bajo condición de cielo despejado (clear-sky), estimada por satélite (NASA POWER)."),
    ("IDEAM_VelViento", "Velocidad del viento (IDEAM)", "m/s",
     "Velocidad del viento medida en estaciones terrestres del IDEAM."),
    ("TempPanel", "Temperatura de panel solar", "°C",
     "Temperatura medida directamente sobre la superficie de un panel fotovoltaico de referencia."),
    ("TempAmbSolar", "Temperatura ambiente en sitio solar", "°C",
     "Temperatura ambiente medida en el sitio de una planta/piloto solar."),
    ("IrrPanel", "Irradiancia en plano de panel", "W/m²",
     "Irradiancia solar medida directamente en el plano de un panel fotovoltaico de referencia."),
    ("IrrGlobal", "Irradiancia solar global (medición en tierra)", "W/m²",
     "Irradiancia solar global horizontal medida por sensor en tierra (distinta de NASA_IrrGlobal, satelital)."),
]


# ═══════════════════════════════════════════════════════════════════════════
# Cuarta ampliación (Fase 23, 2026-08-06): los 10 códigos de liquidación/mercado
# de alto volumen (650K+ filas combinadas en sector_energetico.metrics) que la
# Fase 17 excluyó deliberadamente por no tener certeza suficiente de su
# significado ("sin inventar", ver nota histórica arriba). Se catalogan ahora
# porque se encontró una fuente verificable real: pydataxm.ReadDB().all_variables()
# — el catálogo oficial que XM expone vía su propia API pública (MetricId/
# MetricName/MetricUnits/MetricDescription), la misma librería que ya usan los
# ETLs de este proyecto (etl_todas_metricas_xm.py y otros) para descargar los
# datos — no es una fuente nueva, es la fuente de verdad que ya se usaba para
# los valores, ahora también para los metadatos. RecoPosMoneda/RecoNegMoneda
# quedan con su descripción cortada a propósito en 200 caracteres — así la
# entrega la API de XM (truncamiento real del proveedor, no un error de
# transcripción); se preservan tal cual en vez de completarlas a mano.
METRICAS_BASE_AMPLIACION_4 = [
    ("DDVContratada", "DDV Contratada por Recurso", "kWh",
     "Valor total diario contratado por cada recurso de generación bajo el esquema de Demanda Desconectable Voluntaria."),
    ("RecoPosMoneda", "Reconciliación Positiva Moneda por Recurso", "COP",
     "Es el valor de la compensacion positiva que se debe aplicar a los generadores para cada uno de sus recursos "
     "ofertados debido a las diferencias entre el despacho ideal y la generacion real. Este concep…"),
    ("RecoNegMoneda", "Reconciliación Negativa Moneda por Recurso", "COP",
     "Costos asociados con generaciones desplazadas en el despacho real por Generaciones de Seguridad Fuera de "
     "Merito o por Redespachos (diferencia entre el despacho ideal y el real).Este concepto aplica de…"),
    ("VentContEnerSICEP", "Ventas en Contrato Energía del SICEP por Agente", "kWh",
     "Energia vendida mediante Contratos de largo plazo."),
    ("CompContEnerSICEP", "Compras en Contrato Energía en SICEP por Agente", "kWh",
     "Energía comprada mediante Contratos de largo plazo."),
    ("PrecCargConf", "Precio Cargo por Confiabilidad por Recurso", "USD/kWh",
     "Precio del Cargo por confiabilidad al que se remunera la Obligación de Energía Firme."),
    ("DescMasa", "Descargas por Embalse", "m3",
     "Agua descargada del embalse por compuertas de fondo o cualquier otro sistema, expresado en m3."),
    ("PrecOferDesp", "Precio de Oferta de Despacho por Recurso", "COP/kWh",
     "Es el precio de la energia de un recurso de generación despachados centralmente enviados por los agentes "
     "para el Despacho. Incluye el CEE."),
    ("PrecOferIdeal", "Precio de Oferta Ideal por Recurso", "COP/kWh",
     "Es el precio de la energia de una recurso de generación para cada una de las 24 horas de un dia. Difiere "
     "del precio de oferta de despacho en que incluye el CERE en lugar del CEE."),
    ("VentBolsaTIEEner", "Ventas Bolsa TIE Energía por Sistema", "kWh",
     "Energía comprada en la Bolsa de Energía para atender la demanda TIE."),
]


# Índices regulatorios calculados (dominio sector_energetico, fuente
# calculo_interno) — transcritos desde core/umbrales_oficiales.py.
# ═══════════════════════════════════════════════════════════════════════════
INDICES_REGULATORIOS = [
    # (codigo_tecnico, nombre_display, descripcion, referencia_normativa)
    ("NE", "Índice de Nivel de Embalse (NE)",
     "Compara el nivel real del embalse agregado del SIN contra la Senda de Referencia CREG. "
     "SUPERIOR si el embalse ≥ senda; ALERTA si está por debajo de la senda dentro de la tolerancia; "
     "INFERIOR si está por debajo persistentemente. La regla alternativa 'SUPERIOR si embalse > 70% "
     "del volumen útil' (introducida por la Res. CREG 210/2021) fue DEROGADA por la Resolución CREG "
     "101 112 de 2026 (vigente desde el 17-jun-2026) — desde entonces la clasificación depende "
     "exclusivamente de la senda de referencia. Calculado en clasificar_indice_ne() "
     "(core/umbrales_oficiales.py).",
     "Resolución CREG 209 de 2020, art. 2.8.2.1.3, modificada por Resolución CREG 101 112 de 2026"),
    ("HSIN", "Índice de Hidrología del SIN (HSIN)",
     "Aportes hídricos acumulados de las últimas 4 semanas sobre el promedio histórico del mismo "
     "período. ≥90% = NORMAL; <90% = VIGILANCIA; <70% = DÉFICIT SEVERO; ≤60% = CRÍTICO (nivel histórico "
     "de abril 2020). Calculado en clasificar_hsin() (core/umbrales_oficiales.py).",
     "Resolución CREG 026 de 2014, art. 2"),
    ("PBP", "Índice de Precio de Bolsa Promedio (PBP)",
     "Clasifica el Precio de Bolsa Promedio de los últimos 7 días contra el Precio de Escasez de "
     "Activación vigente. BAJO si el PBP estuvo por debajo del precio de escasez en 4 de los últimos "
     "7 días; ALTO en caso contrario. Calculado en clasificar_indice_pbp() (core/umbrales_oficiales.py).",
     "Resolución CREG 026 de 2014, art. 2"),
    ("CONDICION_SISTEMA", "Condición del Sistema (Normal / Vigilancia / Riesgo)",
     "Combina los índices NE, HSIN y PBP en una condición única del sistema eléctrico: NORMAL si los "
     "tres índices están en niveles óptimos; VIGILANCIA si algún índice está en alerta; RIESGO si NE "
     "está en nivel INFERIOR junto con una señal negativa de HSIN o PBP. "
     "Calculado en determinar_condicion_sistema() (core/umbrales_oficiales.py).",
     "Resolución CREG 026 de 2014, art. 3"),
]

# ═══════════════════════════════════════════════════════════════════════════
# Relaciones de derivación (transcritas manualmente de umbrales_oficiales.py).
# Cada tupla: (codigo_origen, codigo_destino, tipo_relacion, descripcion, ref_normativa)
# ═══════════════════════════════════════════════════════════════════════════
RELACIONES = [
    ("PorcVoluUtilDiar", "NE", "insumo_de",
     "El nivel diario de embalse (% volumen útil) se compara contra la Senda de Referencia CREG "
     "para clasificar el Índice NE.",
     "Resolución CREG 209 de 2020, art. 2.8.2.1.3"),
    ("AporEner", "HSIN", "insumo_de",
     "Los aportes hídricos diarios, acumulados 4 semanas, son el numerador del Índice HSIN.",
     "Resolución CREG 026 de 2014, art. 2"),
    ("AporEnerMediHist", "HSIN", "insumo_de",
     "La media histórica de aportes es el denominador del Índice HSIN.",
     "Resolución CREG 026 de 2014, art. 2"),
    ("PPPrecBolsNaci", "PBP", "insumo_de",
     "El precio de bolsa ponderado diario, en ventana de 7 días, es el insumo directo del Índice PBP.",
     "Resolución CREG 026 de 2014, art. 2"),
    ("PrecEscaInf", "PBP", "se_compara_con",
     "El PEI (Precio de Escasez Inferior) es uno de los umbrales de referencia contra los que se "
     "clasifica visualmente el PBP.",
     "Resolución CREG 101 066 de 2024, art. 3"),
    ("PrecEscaSup", "PBP", "se_compara_con",
     "El PES (Precio de Escasez Superior) es el techo de referencia contra el que se clasifica "
     "visualmente el PBP.",
     "Resolución CREG 101 066 de 2024, art. 4"),
    ("NE", "CONDICION_SISTEMA", "compone_indice",
     "El Índice NE es uno de los tres componentes de la Condición del Sistema.",
     "Resolución CREG 026 de 2014, art. 3"),
    ("HSIN", "CONDICION_SISTEMA", "compone_indice",
     "El Índice HSIN es uno de los tres componentes de la Condición del Sistema.",
     "Resolución CREG 026 de 2014, art. 3"),
    ("PBP", "CONDICION_SISTEMA", "compone_indice",
     "El Índice PBP es uno de los tres componentes de la Condición del Sistema.",
     "Resolución CREG 026 de 2014, art. 3"),
    ("CondicionEstatutoRiesgo", "CONDICION_SISTEMA", "se_compara_con",
     "XM publica su propia condición del Estatuto de Riesgo; se puede contrastar contra el cálculo "
     "interno CONDICION_SISTEMA (derivado de NE+HSIN+PBP) como verificación cruzada.",
     "Resolución CREG 026 de 2014, art. 3"),
]

DOMINIO = "sector_energetico"
ESQUEMA_ORIGEN = "sector_energetico"

# ═══════════════════════════════════════════════════════════════════════════
# Fase 17 — dominios nuevos. Cada tupla de 6 campos:
# (codigo_tecnico, nombre_display, unidad, descripcion, tabla_origen, columna_origen)
# codigo_tecnico es único solo dentro del dominio (UNIQUE(dominio, codigo_tecnico)
# en el esquema) — cuando 2 tablas del mismo dominio comparten un nombre de
# columna (ej. "avance" en seguimiento_avance_fisico Y seguimiento_avance_documental
# de contratos_or), se usa un codigo_tecnico distinto para cada uno (avance_fisico/
# avance_documental) en vez del nombre literal de columna.
# ═══════════════════════════════════════════════════════════════════════════

METRICAS_FENOGE = [
    ("kwp", "Capacidad instalada por comunidad energética", "kWp",
     "Capacidad de generación solar instalada para la comunidad energética.", "comunidades", "kwp"),
    ("beneficiarios", "Beneficiarios por comunidad energética", "personas",
     "Número de beneficiarios directos de la comunidad energética.", "comunidades", "beneficiarios"),
    ("valor_kwp", "Valor por kWp instalado", "COP",
     "Costo unitario del proyecto por kWp de capacidad instalada.", "comunidades", "valor_kwp"),
    ("valor_proyecto", "Valor total del proyecto FENOGE", "COP",
     "Valor total del proyecto de comunidad energética financiado por FENOGE.", "comunidades", "valor_proyecto"),
    ("real_financiero", "Ejecución financiera real", "COP",
     "Monto financiero realmente ejecutado del contrato FENOGE a la fecha de corte.", "seguimiento", "real_financiero"),
    ("programado_financiero", "Ejecución financiera programada", "COP",
     "Monto financiero programado del contrato FENOGE a la fecha de corte.", "seguimiento", "programado"),
    ("real_acumulado_pesos", "Ejecución financiera real acumulada", "COP",
     "Monto financiero real acumulado del contrato FENOGE desde su inicio.", "seguimiento", "real_acumulado_pesos"),
    ("programado_acumulado_pesos", "Ejecución financiera programada acumulada", "COP",
     "Monto financiero programado acumulado del contrato FENOGE desde su inicio.", "seguimiento", "programado_acumulado_pesos"),
    ("avance_real_pct", "Avance físico real", "%",
     "Porcentaje de avance físico real del contrato FENOGE a la fecha de corte.", "seguimiento", "avance_real_pct"),
    ("avance_programado_pct", "Avance físico programado", "%",
     "Porcentaje de avance físico programado del contrato FENOGE a la fecha de corte.", "seguimiento", "avance_programado_pct"),
    ("avance_real_acumulado_pct", "Avance físico real acumulado", "%",
     "Porcentaje de avance físico real acumulado del contrato FENOGE desde su inicio.", "seguimiento", "avance_real_acumulado_pct"),
    ("avance_programado_acumulado_pct", "Avance físico programado acumulado", "%",
     "Porcentaje de avance físico programado acumulado del contrato FENOGE desde su inicio.", "seguimiento", "avance_programado_acumulado_pct"),
]

METRICAS_COLOMBIA_SOLAR = [
    ("inversion", "Inversión del proyecto", "COP",
     "Monto de inversión del proyecto de energía solar.", "base", "inversion"),
    ("planeado_usuarios", "Usuarios planeados", "usuarios",
     "Número de usuarios/beneficiarios planeados para el proyecto.", "base", "planeado_usuarios"),
    ("ejecutado_usuarios", "Usuarios ejecutados", "usuarios",
     "Número de usuarios/beneficiarios efectivamente conectados.", "base", "ejecutado_usuarios"),
    ("capacidad_kwp_planeada", "Capacidad solar planeada", "kWp",
     "Capacidad de generación solar planeada del proyecto.", "base", "capacidad_kwp_planeada"),
    ("capacidad_kwp_ejecutada", "Capacidad solar ejecutada", "kWp",
     "Capacidad de generación solar efectivamente instalada.", "base", "capacidad_kwp_ejecutada"),
    ("eficiencia", "Eficiencia de ejecución", "%",
     "Relación entre lo ejecutado y lo planeado del proyecto solar.", "base", "eficiencia"),
]

METRICAS_CONTRATOS_OR = [
    ("avance_fisico", "Avance físico del proyecto OR", "%",
     "Porcentaje de avance físico de obra del proyecto de Obras de Restablecimiento.",
     "seguimiento_avance_fisico", "avance"),
    ("avance_documental", "Avance documental del proyecto OR", "%",
     "Porcentaje de avance documental (requisitos/entregables) del proyecto OR.",
     "seguimiento_avance_documental", "avance"),
    ("desembolso", "Desembolso por actividad documental", "COP",
     "Monto desembolsado asociado a una actividad del cronograma documental del proyecto OR.",
     "seguimiento_avance_documental", "desembolso"),
]

METRICAS_SUBSIDIOS = [
    ("subsidios", "Subsidios otorgados (histórico anual)", "COP",
     "Monto anual de subsidios otorgados a usuarios de estratos subsidiables.", "deficit_historico", "subsidios"),
    ("contribuciones", "Contribuciones recaudadas (histórico anual)", "COP",
     "Monto anual de contribuciones recaudadas de usuarios no subsidiables.", "deficit_historico", "contribuciones"),
    ("deficit_anual", "Déficit anual de subsidios", "COP",
     "Diferencia anual entre subsidios otorgados y contribuciones recaudadas.", "deficit_historico", "deficit_anual"),
    ("deficit_acumulado", "Déficit acumulado de subsidios", "COP",
     "Déficit de subsidios acumulado histórico.", "deficit_historico", "deficit_acumulado"),
    ("apropiacion_pgn", "Apropiación PGN para subsidios", "COP",
     "Recursos apropiados en el Presupuesto General de la Nación para cubrir el déficit de subsidios.",
     "deficit_historico", "apropiacion_pgn"),
    ("recursos_faltantes", "Recursos faltantes para subsidios", "COP",
     "Recursos que faltan para cubrir el déficit de subsidios tras la apropiación PGN.",
     "deficit_historico", "recursos_faltantes"),
    ("valor_asignado", "Valor asignado (resumen KPI)", "COP",
     "Valor total asignado por resolución en el resumen anual de KPIs de subsidios.", "kpis_resumen", "valor_asignado"),
    ("valor_pendiente", "Valor pendiente (resumen KPI)", "COP",
     "Valor pendiente de pago en el resumen anual de KPIs de subsidios.", "kpis_resumen", "valor_pendiente"),
    ("n_resoluciones", "Número de resoluciones (resumen KPI)", "resoluciones",
     "Cantidad de resoluciones de asignación de subsidios en el año.", "kpis_resumen", "n_resoluciones"),
    ("valor_resolucion", "Valor por resolución de pago", "COP",
     "Valor asignado en una resolución de pago de subsidios a un prestador.", "subsidios_pagos", "valor_resolucion"),
    ("valor_pagado", "Valor pagado por resolución", "COP",
     "Valor efectivamente pagado de una resolución de subsidios.", "subsidios_pagos", "valor_pagado"),
    ("pct_pagado", "Porcentaje pagado por resolución", "%",
     "Porcentaje del valor de la resolución que ya fue pagado.", "subsidios_pagos", "pct_pagado"),
    ("saldo_pendiente", "Saldo pendiente por resolución", "COP",
     "Saldo pendiente de pago de una resolución de subsidios.", "subsidios_pagos", "saldo_pendiente"),
    ("valor_disponible", "Valor disponible para pago", "COP",
     "Valor disponible en el fondo para atender el pago de una resolución.", "subsidios_pagos", "valor_disponible"),
]

METRICAS_PRESUPUESTO = [
    ("apropiacion", "Apropiación presupuestal", "COP",
     "Monto total apropiado en el presupuesto del proyecto/fondo.", "resumen", "apropiacion"),
    ("compromisos", "Compromisos presupuestales", "COP",
     "Monto comprometido del presupuesto apropiado.", "resumen", "compromisos"),
    ("comprometido", "Porcentaje comprometido", "%",
     "Porcentaje del presupuesto apropiado que ya está comprometido.", "resumen", "comprometido"),
    ("obligados", "Obligaciones presupuestales", "COP",
     "Monto obligado (causado) del presupuesto comprometido.", "resumen", "obligados"),
    ("obligado", "Porcentaje obligado", "%",
     "Porcentaje del presupuesto comprometido que ya está obligado.", "resumen", "obligado"),
    ("sin_comprometer_disponible", "Saldo disponible sin comprometer", "COP",
     "Saldo del presupuesto apropiado que aún no se ha comprometido.", "resumen", "sin_comprometer_disponible"),
]

METRICAS_HIDROCARBUROS = [
    ("valor_usd", "Precio de commodity de hidrocarburos", "USD",
     "Precio histórico de un commodity de hidrocarburos (ej. petróleo Brent/WTI).", "commodities_historico", "valor_usd"),
    ("variacion_abs", "Variación absoluta del precio", "USD",
     "Variación absoluta del precio del commodity respecto al período anterior.", "commodities_historico", "variacion_abs"),
    ("variacion_pct", "Variación porcentual del precio", "%",
     "Variación porcentual del precio del commodity respecto al período anterior.", "commodities_historico", "variacion_pct"),
    ("apropiacion_vigente", "Apropiación vigente (hidrocarburos)", "COP",
     "Monto de apropiación presupuestal vigente para proyectos de hidrocarburos.", "presupuesto_resumen", "apropiacion_vigente"),
    ("compromisos", "Compromisos presupuestales (hidrocarburos)", "COP",
     "Monto comprometido del presupuesto de hidrocarburos.", "presupuesto_resumen", "compromisos"),
    ("obligaciones", "Obligaciones presupuestales (hidrocarburos)", "COP",
     "Monto obligado (causado) del presupuesto de hidrocarburos.", "presupuesto_resumen", "obligaciones"),
    ("por_comprometer", "Saldo por comprometer (hidrocarburos)", "COP",
     "Saldo de la apropiación vigente que aún no se ha comprometido.", "presupuesto_resumen", "por_comprometer"),
    ("pct_compromisos", "Porcentaje comprometido (hidrocarburos)", "%",
     "Porcentaje de la apropiación vigente que ya está comprometido.", "presupuesto_resumen", "pct_compromisos"),
    ("pct_obligaciones", "Porcentaje obligado (hidrocarburos)", "%",
     "Porcentaje de la apropiación vigente que ya está obligada.", "presupuesto_resumen", "pct_obligaciones"),
    ("petroleo_bbl", "Producción diaria de petróleo", "bbl/día",
     "Producción fiscalizada diaria de petróleo, en barriles por día.", "produccion_diaria", "petroleo_bbl"),
    ("gas_fiscalizado_mpc", "Producción diaria de gas fiscalizado", "Mpc/día",
     "Producción fiscalizada diaria de gas natural, en millones de pies cúbicos por día.", "produccion_diaria", "gas_fiscalizado_mpc"),
    ("gas_comercializado_mpc", "Producción diaria de gas comercializado", "Mpc/día",
     "Producción comercializada diaria de gas natural, en millones de pies cúbicos por día.", "produccion_diaria", "gas_comercializado_mpc"),
]

METRICAS_SUPERVISION = [
    ("avance_contrato", "Avance general del contrato de supervisión", "%",
     "Porcentaje de avance general del contrato bajo supervisión del MME.", "contratos", "avance_contrato"),
    ("avance_de_obra", "Avance de obra", "%",
     "Porcentaje de avance físico de obra del contrato bajo supervisión.", "contratos", "avance_de_obra"),
    ("avance_documental_total", "Avance documental total", "%",
     "Porcentaje de avance de la matriz documental del contrato bajo supervisión.",
     "contratos", "avance_documental_total_matriz_documental"),
    ("valor_contrato_apoyos_financieros", "Valor del contrato — apoyos financieros", "COP",
     "Valor del contrato correspondiente a la información de apoyos financieros.",
     "contratos", "valor_del_contrato_informacion_apoyos_financieros"),
    ("valor_desembolsado_apoyos_financieros", "Valor desembolsado — apoyos financieros", "COP",
     "Valor efectivamente desembolsado del contrato en apoyos financieros.",
     "contratos", "valor_desembolsado_informacion_apoyos_financieros"),
    ("porcentaje_de_desembolsos", "Porcentaje de desembolsos", "%",
     "Porcentaje del valor del contrato que ya ha sido desembolsado.", "contratos", "porcentaje_de_desembolsos"),
    ("numero_usuarios_contratados", "Usuarios totales contratados", "usuarios",
     "Número de usuarios totales contratados a beneficiar por el proyecto.",
     "contratos", "numero_de_usuarios_totales_contratados"),
    ("numero_usuarios_finales", "Usuarios totales finales", "usuarios",
     "Número de usuarios totales efectivamente beneficiados al cierre del proyecto.",
     "contratos", "numero_de_usuarios_totales_finales"),
]

DOMINIOS_NUEVOS = [
    # (dominio, esquema_origen, lista_de_metricas_6_campos)
    ("fenoge", "fenoge", METRICAS_FENOGE),
    ("colombia_solar", "colombia_solar", METRICAS_COLOMBIA_SOLAR),
    ("contratos_or", "contratos_or", METRICAS_CONTRATOS_OR),
    ("subsidios", "subsidios", METRICAS_SUBSIDIOS),
    ("presupuesto", "presupuesto", METRICAS_PRESUPUESTO),
    ("hidrocarburos", "hidrocarburos", METRICAS_HIDROCARBUROS),
    ("supervision", "supervision", METRICAS_SUPERVISION),
]

# Relaciones de derivación genuinas para los dominios nuevos (misma tabla,
# nunca forzadas entre dominios sin vínculo real). Cada tupla:
# (codigo_origen, dominio_origen, codigo_destino, dominio_destino, tipo_relacion, descripcion)
RELACIONES_DOMINIOS_NUEVOS = [
    ("avance_fisico", "contratos_or", "avance_documental", "contratos_or", "se_compara_con",
     "El avance físico de obra y el avance documental del mismo proyecto OR se contrastan para "
     "detectar desfases entre lo construido y lo formalizado en el expediente."),
    ("real_financiero", "fenoge", "avance_real_pct", "fenoge", "insumo_de",
     "La ejecución financiera real acumulada es uno de los insumos del porcentaje de avance real del contrato."),
    ("programado_financiero", "fenoge", "avance_programado_pct", "fenoge", "insumo_de",
     "La ejecución financiera programada acumulada es uno de los insumos del porcentaje de avance programado."),
    ("ejecutado_usuarios", "colombia_solar", "eficiencia", "colombia_solar", "insumo_de",
     "Los usuarios efectivamente ejecutados, comparados contra los planeados, determinan la eficiencia del proyecto."),
    ("planeado_usuarios", "colombia_solar", "eficiencia", "colombia_solar", "insumo_de",
     "Los usuarios planeados son el denominador de referencia para calcular la eficiencia del proyecto."),
    ("valor_pagado", "subsidios", "pct_pagado", "subsidios", "insumo_de",
     "El valor pagado de una resolución es el numerador del porcentaje pagado."),
    ("valor_resolucion", "subsidios", "pct_pagado", "subsidios", "insumo_de",
     "El valor total de la resolución es el denominador del porcentaje pagado."),
    ("compromisos", "presupuesto", "comprometido", "presupuesto", "insumo_de",
     "El monto comprometido, sobre la apropiación, determina el porcentaje comprometido del presupuesto."),
    ("obligados", "presupuesto", "obligado", "presupuesto", "insumo_de",
     "El monto obligado, sobre lo comprometido, determina el porcentaje obligado del presupuesto."),
]


def _upsert_metrica_base(codigo: str, nombre: str, unidad: str, descripcion: str) -> int:
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.dim_metrica
            (codigo_tecnico, nombre_display, dominio, esquema_origen, tabla_origen,
             columna_origen, unidad, fuente, descripcion, estado)
        VALUES (%s, %s, %s, %s, 'metrics', 'metrica', %s, 'XM', %s, 'catalogado')
        ON CONFLICT (dominio, codigo_tecnico) DO UPDATE SET
            nombre_display = EXCLUDED.nombre_display,
            unidad = EXCLUDED.unidad,
            descripcion = EXCLUDED.descripcion,
            estado = 'catalogado'
        """,
        (codigo, nombre, DOMINIO, ESQUEMA_ORIGEN, unidad, descripcion),
    )
    row = db_manager.query_df(
        "SELECT metrica_id FROM ontologia.dim_metrica WHERE dominio = %(d)s AND codigo_tecnico = %(c)s",
        {"d": DOMINIO, "c": codigo},
    )
    return int(row["metrica_id"].iloc[0])


def _upsert_indice(codigo: str, nombre: str, descripcion: str, referencia: str) -> int:
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.dim_metrica
            (codigo_tecnico, nombre_display, dominio, fuente, descripcion,
             es_indice_regulatorio, referencia_normativa, estado)
        VALUES (%s, %s, %s, 'calculo_interno', %s, TRUE, %s, 'catalogado')
        ON CONFLICT (dominio, codigo_tecnico) DO UPDATE SET
            nombre_display = EXCLUDED.nombre_display,
            descripcion = EXCLUDED.descripcion,
            referencia_normativa = EXCLUDED.referencia_normativa,
            estado = 'catalogado'
        """,
        (codigo, nombre, DOMINIO, descripcion, referencia),
    )
    row = db_manager.query_df(
        "SELECT metrica_id FROM ontologia.dim_metrica WHERE dominio = %(d)s AND codigo_tecnico = %(c)s",
        {"d": DOMINIO, "c": codigo},
    )
    return int(row["metrica_id"].iloc[0])


def _upsert_relacion(origen_id: int, destino_id: int, tipo: str, descripcion: str, referencia: str = None) -> None:
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.metrica_relacion
            (metrica_origen_id, metrica_destino_id, tipo_relacion, descripcion, referencia_normativa)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (metrica_origen_id, metrica_destino_id, tipo_relacion) DO UPDATE SET
            descripcion = EXCLUDED.descripcion,
            referencia_normativa = EXCLUDED.referencia_normativa
        """,
        (origen_id, destino_id, tipo, descripcion, referencia),
    )


def _upsert_metrica_dominio(codigo: str, nombre: str, unidad: str, descripcion: str,
                             dominio: str, esquema_origen: str, tabla_origen: str, columna_origen: str) -> int:
    db_manager.execute_non_query(
        """
        INSERT INTO ontologia.dim_metrica
            (codigo_tecnico, nombre_display, dominio, esquema_origen, tabla_origen,
             columna_origen, unidad, fuente, descripcion, estado)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'XM', %s, 'catalogado')
        ON CONFLICT (dominio, codigo_tecnico) DO UPDATE SET
            nombre_display = EXCLUDED.nombre_display,
            unidad = EXCLUDED.unidad,
            descripcion = EXCLUDED.descripcion,
            tabla_origen = EXCLUDED.tabla_origen,
            columna_origen = EXCLUDED.columna_origen,
            estado = 'catalogado'
        """,
        (codigo, nombre, dominio, esquema_origen, tabla_origen, columna_origen, unidad, descripcion),
    )
    row = db_manager.query_df(
        "SELECT metrica_id FROM ontologia.dim_metrica WHERE dominio = %(d)s AND codigo_tecnico = %(c)s",
        {"d": dominio, "c": codigo},
    )
    return int(row["metrica_id"].iloc[0])


def main() -> None:
    ids: dict[str, int] = {}

    for codigo, nombre, unidad, descripcion in METRICAS_BASE:
        ids[codigo] = _upsert_metrica_base(codigo, nombre, unidad, descripcion)
    logger.info(f"{len(METRICAS_BASE)} métricas base sembradas/actualizadas")

    for codigo, nombre, unidad, descripcion in METRICAS_BASE_AMPLIACION:
        ids[codigo] = _upsert_metrica_base(codigo, nombre, unidad, descripcion)
    logger.info(f"{len(METRICAS_BASE_AMPLIACION)} métricas de ampliación (Fase 13) sembradas/actualizadas")

    for codigo, nombre, unidad, descripcion in METRICAS_BASE_AMPLIACION_2:
        ids[codigo] = _upsert_metrica_base(codigo, nombre, unidad, descripcion)
    logger.info(f"{len(METRICAS_BASE_AMPLIACION_2)} métricas de la 2da ampliación (Fase 13) sembradas/actualizadas")

    for codigo, nombre, unidad, descripcion in METRICAS_BASE_AMPLIACION_3:
        ids[codigo] = _upsert_metrica_base(codigo, nombre, unidad, descripcion)
    logger.info(f"{len(METRICAS_BASE_AMPLIACION_3)} métricas climáticas/solares (Fase 17) sembradas/actualizadas")

    for codigo, nombre, unidad, descripcion in METRICAS_BASE_AMPLIACION_4:
        ids[codigo] = _upsert_metrica_base(codigo, nombre, unidad, descripcion)
    logger.info(f"{len(METRICAS_BASE_AMPLIACION_4)} métricas de liquidación/mercado de alto volumen (Fase 23) sembradas/actualizadas")

    for codigo, nombre, descripcion, referencia in INDICES_REGULATORIOS:
        ids[codigo] = _upsert_indice(codigo, nombre, descripcion, referencia)
    logger.info(f"{len(INDICES_REGULATORIOS)} índices regulatorios sembrados/actualizados")

    for origen, destino, tipo, descripcion, referencia in RELACIONES:
        if origen not in ids or destino not in ids:
            logger.warning(f"Relación omitida (código no sembrado): {origen} -> {destino}")
            continue
        _upsert_relacion(ids[origen], ids[destino], tipo, descripcion, referencia)
    logger.info(f"{len(RELACIONES)} relaciones sembradas/actualizadas")

    # Fase 17 — dominios nuevos. ids_dominio guarda metrica_id por (dominio, codigo)
    # porque codigo_tecnico solo es único DENTRO de cada dominio.
    ids_dominio: dict[tuple[str, str], int] = {}
    total_nuevas = 0
    for dominio, esquema_origen, metricas in DOMINIOS_NUEVOS:
        for codigo, nombre, unidad, descripcion, tabla_origen, columna_origen in metricas:
            mid = _upsert_metrica_dominio(codigo, nombre, unidad, descripcion,
                                           dominio, esquema_origen, tabla_origen, columna_origen)
            ids_dominio[(dominio, codigo)] = mid
        logger.info(f"Dominio '{dominio}': {len(metricas)} métricas sembradas/actualizadas")
        total_nuevas += len(metricas)
    logger.info(f"Fase 17: {total_nuevas} métricas nuevas en {len(DOMINIOS_NUEVOS)} dominios")

    relaciones_nuevas = 0
    for cod_o, dom_o, cod_d, dom_d, tipo, descripcion in RELACIONES_DOMINIOS_NUEVOS:
        origen_id = ids_dominio.get((dom_o, cod_o))
        destino_id = ids_dominio.get((dom_d, cod_d))
        if origen_id is None or destino_id is None:
            logger.warning(f"Relación de dominio omitida (código no sembrado): {dom_o}.{cod_o} -> {dom_d}.{cod_d}")
            continue
        _upsert_relacion(origen_id, destino_id, tipo, descripcion)
        relaciones_nuevas += 1
    logger.info(f"Fase 17: {relaciones_nuevas} relaciones nuevas entre dominios")


if __name__ == "__main__":
    main()
