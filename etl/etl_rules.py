#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║             REGLAS CENTRALIZADAS DE ETL — FUENTE ÚNICA DE VERDAD    ║
║                                                                      ║
║  Este módulo define, para cada métrica XM, la unidad final esperada, ║
║  la conversión a aplicar, el tipo de agregación horaria y los rangos ║
║  válidos de los valores.                                             ║
║                                                                      ║
║  OBJETIVO: Eliminar la dispersión de lógica de conversión que causa  ║
║  datos incorrectos (valores en Wh mostrados como GWh, COP mostrado  ║
║  sin dividir por 1 M, unidades=None, etc.).                          ║
║                                                                      ║
║  ── Cómo usar ──                                                     ║
║  1. Importe get_rule(metric_id) para obtener la regla de una métrica.║
║  2. Use validate_metric_df(df, metric_id) después de cualquier ETL   ║
║     para verificar que el DataFrame cumple las reglas antes de        ║
║     insertar en BD.                                                   ║
║  3. Use apply_conversion(df, metric_id) para aplicar la conversión   ║
║     definida de forma centralizada.                                   ║
║                                                                      ║
║  CAMBIO: Unifica reglas antes dispersas en etl_todas_metricas_xm.py, ║
║  config_metricas.py, validaciones.py y validaciones_rangos.py.        ║
║  No modifica firmas públicas de ningún módulo existente.              ║
║  Revertir: simplemente deje de importar este archivo; el ETL antiguo ║
║  seguirá funcionando con sus reglas locales.                          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# ENUMERACIONES
# ═══════════════════════════════════════════════════════════════

class ConversionType(str, Enum):
    """Tipos de conversión soportados por el ETL."""
    NONE           = "sin_conversion"
    WH_TO_GWH      = "Wh_a_GWh"           # ÷ 1 000 000
    KWH_TO_GWH     = "kWh_a_GWh"          # ÷ 1 000 000 (alias)
    HOURS_TO_GWH   = "horas_a_GWh"        # Σ Hours_01..24 ÷ 1 000 000
    HOURS_TO_MW    = "horas_a_MW"          # Avg Hours_01..24 ÷ 1 000
    COP_TO_MCOP    = "COP_a_MCOP"         # ÷ 1 000 000
    RESTR_TO_MCOP  = "restricciones_a_MCOP"  # Avg 24h ÷ 1 000 000


class AggregationType(str, Enum):
    """Cómo se agregan los datos horarios a diarios."""
    DAILY_VALUE  = "daily_value"     # Ya viene como valor diario
    HOURLY_SUM   = "hourly_sum"      # Σ de las 24 horas
    HOURLY_AVG   = "hourly_avg"      # Promedio de las 24 horas
    NONE         = "none"            # Sin agregación (catálogos, etc.)


class Section(str, Enum):
    """Secciones del dashboard / dominio."""
    GENERACION     = "Generación"
    DEMANDA        = "Demanda"
    HIDROLOGIA     = "Hidrología"
    RESTRICCIONES  = "Restricciones"
    PRECIOS        = "Precios"
    TRANSACCIONES  = "Transacciones"
    PERDIDAS       = "Pérdidas"
    INTERCAMBIOS   = "Intercambios"
    COMBUSTIBLES   = "Combustibles"
    RENOVABLES     = "Renovables"
    CARGOS         = "Cargos"
    TRANSMISION    = "Transmisión"
    CATALOGOS      = "Catálogos"


# ═══════════════════════════════════════════════════════════════
# DATA CLASS PARA REGLA
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class MetricRule:
    """Regla centralizada para una métrica XM."""
    metric_id: str
    section: Section
    expected_unit: str                          # Unidad final en BD
    conversion: ConversionType                  # Conversión a aplicar
    aggregation: AggregationType                # Tipo de agregación
    valid_range: Tuple[float, float] = (0, 1e12)  # (min, max) post-conversión
    allow_negative: bool = False                # ¿Se permiten valores < 0?
    description: str = ""
    entities: List[str] = field(default_factory=lambda: ["Sistema"])


# ═══════════════════════════════════════════════════════════════
# REGLAS POR MÉTRICA  — FUENTE ÚNICA DE VERDAD
# ═══════════════════════════════════════════════════════════════

_RULES: Dict[str, MetricRule] = {}


def _r(metric_id: str, **kw) -> None:
    """Macro interna para registrar reglas."""
    _RULES[metric_id] = MetricRule(metric_id=metric_id, **kw)


# ── Generación ──────────────────────────────────────────────
_r("Gene",              section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 500),  entities=["Sistema", "Recurso"], description="Generación real")
_r("GeneIdea",          section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 500),  description="Generación ideal")
_r("GeneProgDesp",      section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 500),  description="Gen. programada despacho")
_r("GeneProgRedesp",    section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 500),  description="Gen. programada redespacho")
_r("GeneFueraMerito",   section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 500),  description="Gen. fuera de mérito")
_r("GeneSeguridad",     section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 500),  entities=["Recurso"], description="Gen. de seguridad")
_r("CapEfecNeta",       section=Section.GENERACION,  expected_unit="MW",   conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 25000), entities=["Recurso"], description="Capacidad efectiva neta")
_r("ENFICC",            section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 500),  entities=["Recurso"], description="Energía firme")
_r("ObligEnerFirme",    section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 500),  entities=["Recurso"], description="Obligación energía firme")
_r("DDVContratada",     section=Section.GENERACION,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 500),  entities=["Recurso"], description="DDV contratada")

# ── Demanda ─────────────────────────────────────────────────
_r("DemaReal",          section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 350),  entities=["Sistema", "Agente"], description="Demanda real")
_r("DemaCome",          section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 350),  entities=["Sistema", "Agente", "MercadoComercializacion"], description="Demanda comercial")
_r("DemaRealReg",       section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 350),  entities=["Sistema", "Agente"], description="Demanda real regulada")
_r("DemaRealNoReg",     section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 350),  entities=["Sistema", "Agente"], description="Demanda real no regulada")
_r("DemaComeReg",       section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 350),  entities=["Sistema", "Agente"], description="Demanda comercial regulada")
_r("DemaComeNoReg",     section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 350),  entities=["Sistema", "Agente"], description="Demanda comercial no regulada")
_r("DemaSIN",           section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 350),  description="Demanda SIN")
_r("DemaMaxPot",        section=Section.DEMANDA,     expected_unit="MW",   conversion=ConversionType.HOURS_TO_MW,   aggregation=AggregationType.HOURLY_AVG,  valid_range=(0, 20000), description="Demanda máxima potencia")
_r("DemaNoAtenProg",    section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 50),   entities=["Area", "Subarea"], description="Demanda no atendida programada")
_r("DemaNoAtenNoProg",  section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 50),   entities=["Area", "Subarea"], description="Demanda no atendida no programada")
_r("DemaOR",            section=Section.DEMANDA,     expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM,  valid_range=(0, 350),  entities=["Agente"], description="Demanda OR")

# ── Hidrología ──────────────────────────────────────────────
_r("AporEner",          section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 800),  entities=["Rio", "Sistema"], description="Aportes energía")
_r("AporEnerMediHist",  section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 800),  entities=["Rio", "Sistema"], description="Aportes energía media histórica")
_r("VoluUtilDiarEner",  section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 20000), entities=["Embalse", "Sistema"], description="Volumen útil diario energía")
_r("CapaUtilDiarEner",  section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 20000), entities=["Embalse", "Sistema"], description="Capacidad útil diaria energía")
_r("VertEner",          section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000),  entities=["Embalse"], description="Vertimientos energía")
_r("AporValorEner",     section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 800),  entities=["Embalse"], description="Aportes valor energía")
_r("EneIndisp",         section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 500),  description="Energía indisponible")
_r("AportHidricoMens",  section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000),  description="Aportes hídricos mensuales")
_r("VolUtilesMens",     section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 20000), description="Volúmenes útiles mensuales")
_r("MediaHist",         section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 800),  description="Media histórica")
_r("PromediosAlDia",    section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 800),  description="Promedios al día")
_r("SeriesHistAport",   section=Section.HIDROLOGIA,  expected_unit="GWh",  conversion=ConversionType.WH_TO_GWH,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 800),  description="Series históricas aportes")
_r("AporCaudal",        section=Section.HIDROLOGIA,  expected_unit="m³/s", conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 50000), entities=["Rio"], description="Aportes caudal")
_r("AporCaudalMediHist",section=Section.HIDROLOGIA,  expected_unit="m³/s", conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 50000), entities=["Rio"], description="Aportes caudal media hist.")
_r("VoluUtilDiarMasa",  section=Section.HIDROLOGIA,  expected_unit="Hm³",  conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 50000), entities=["Embalse"], description="Volumen útil diario masa")
_r("CapaUtilDiarMasa",  section=Section.HIDROLOGIA,  expected_unit="Hm³",  conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 50000), entities=["Embalse"], description="Capacidad útil diaria masa")

# ── Restricciones ───────────────────────────────────────────
_r("RestAliv",          section=Section.RESTRICCIONES, expected_unit="Millones COP", conversion=ConversionType.RESTR_TO_MCOP,  aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 500), description="Restricciones aliviadas")
_r("RestSinAliv",       section=Section.RESTRICCIONES, expected_unit="Millones COP", conversion=ConversionType.RESTR_TO_MCOP,  aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 500), description="Restricciones sin alivio")
_r("RespComerAGC",      section=Section.RESTRICCIONES, expected_unit="Millones COP", conversion=ConversionType.COP_TO_MCOP,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), description="Responsabilidad comercial AGC")
_r("EjecGarantRestr",   section=Section.RESTRICCIONES, expected_unit="Millones COP", conversion=ConversionType.COP_TO_MCOP,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), description="Ejecución garantías restricciones")
_r("RentasCongestRestr",section=Section.RESTRICCIONES, expected_unit="Millones COP", conversion=ConversionType.COP_TO_MCOP,    aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), description="Rentas congestión restricciones")
_r("DesvGenVariableDesp",section=Section.RESTRICCIONES,expected_unit="GWh",           conversion=ConversionType.WH_TO_GWH,     aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 100), allow_negative=True, description="Desvío gen. variable despacho")
_r("DesvGenVariableRedesp",section=Section.RESTRICCIONES,expected_unit="GWh",         conversion=ConversionType.WH_TO_GWH,     aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 100), allow_negative=True, description="Desvío gen. variable redespacho")

# ── Precios ─────────────────────────────────────────────────
_r("PrecBolsNaci",      section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 5000), description="Precio bolsa nacional")
_r("PrecBolsNaciTX1",   section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 5000), description="Precio bolsa TX1")
_r("PrecOferDesp",      section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 5000), entities=["Recurso"], description="Precio oferta despacho")
_r("PrecOferIdeal",     section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 5000), entities=["Recurso"], description="Precio oferta ideal")
_r("PrecEsca",          section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), description="Precio escasez")
_r("PrecEscaAct",       section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), description="Precio escasez activación")
_r("PrecEscaMarg",      section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 5000), description="Precio escasez marginal")
_r("CostMargDesp",      section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 5000), description="Costo marginal despacho")
_r("PrecPromCont",      section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), description="Precio promedio contratos")
_r("MaxPrecOferNal",    section=Section.PRECIOS,     expected_unit="$/kWh", conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), description="Máx precio oferta nacional")

# ── Pérdidas ────────────────────────────────────────────────
_r("PerdidasEner",      section=Section.PERDIDAS,    expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 100),  description="Pérdidas energía total")
_r("PerdidasEnerReg",   section=Section.PERDIDAS,    expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 100),  description="Pérdidas energía regulada")
_r("PerdidasEnerNoReg", section=Section.PERDIDAS,    expected_unit="GWh",  conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 100),  description="Pérdidas energía no regulada")

# ── Transmisión / Disponibilidad ────────────────────────────
_r("DispoReal",         section=Section.TRANSMISION, expected_unit="MW",   conversion=ConversionType.HOURS_TO_MW,   aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 25000), entities=["Recurso"], description="Disponibilidad real")
_r("DispoCome",         section=Section.TRANSMISION, expected_unit="MW",   conversion=ConversionType.HOURS_TO_MW,   aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 25000), entities=["Recurso"], description="Disponibilidad comercial")
_r("DispoDeclarada",    section=Section.TRANSMISION, expected_unit="MW",   conversion=ConversionType.HOURS_TO_MW,   aggregation=AggregationType.HOURLY_AVG, valid_range=(0, 25000), entities=["Recurso"], description="Disponibilidad declarada")

# ── Intercambios ────────────────────────────────────────────
_r("ImpoEner",          section=Section.INTERCAMBIOS, expected_unit="GWh", conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 100),  description="Importación energía")
_r("ExpoEner",          section=Section.INTERCAMBIOS, expected_unit="GWh", conversion=ConversionType.HOURS_TO_GWH,  aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 100),  description="Exportación energía")

# ── Transacciones comerciales ───────────────────────────────
_r("CompBolsNaciEner",  section=Section.TRANSACCIONES, expected_unit="GWh", conversion=ConversionType.HOURS_TO_GWH, aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 500), entities=["Agente", "Sistema"], description="Compras bolsa nacional")
_r("VentBolsNaciEner",  section=Section.TRANSACCIONES, expected_unit="GWh", conversion=ConversionType.HOURS_TO_GWH, aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 500), entities=["Agente", "Sistema"], description="Ventas bolsa nacional")
_r("CompContEner",      section=Section.TRANSACCIONES, expected_unit="GWh", conversion=ConversionType.HOURS_TO_GWH, aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 500), entities=["Agente", "Sistema"], description="Compras contratos energía")
_r("VentContEner",      section=Section.TRANSACCIONES, expected_unit="GWh", conversion=ConversionType.HOURS_TO_GWH, aggregation=AggregationType.HOURLY_SUM, valid_range=(0, 500), entities=["Agente", "Sistema"], description="Ventas contratos energía")

# ── Cargos (COP → Millones COP) ───────────────────────────
_r("FAZNI",             section=Section.CARGOS,      expected_unit="Millones COP", conversion=ConversionType.COP_TO_MCOP, aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), description="Fondo FAZNI")
_r("ComContRespEner",   section=Section.CARGOS,      expected_unit="Millones COP", conversion=ConversionType.COP_TO_MCOP, aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 5000), entities=["Recurso", "Sistema"], description="Compensación contrato resp. energía")

# ── Combustibles ────────────────────────────────────────────
_r("ConsCombustibleMBTU",section=Section.COMBUSTIBLES,expected_unit="MBTU", conversion=ConversionType.NONE,          aggregation=AggregationType.DAILY_VALUE, valid_range=(0, 1e9), entities=["Combustible", "Recurso"], description="Consumo combustible MBTU")


# ═══════════════════════════════════════════════════════════════
# API PÚBLICA
# ═══════════════════════════════════════════════════════════════

def get_rule(metric_id: str) -> Optional[MetricRule]:
    """Retorna la regla para una métrica, o None si no está definida."""
    return _RULES.get(metric_id)


def get_all_rules() -> Dict[str, MetricRule]:
    """Retorna todas las reglas registradas (copia)."""
    return dict(_RULES)


def get_expected_unit(metric_id: str) -> Optional[str]:
    """Retorna la unidad esperada para una métrica, o None."""
    rule = _RULES.get(metric_id)
    return rule.expected_unit if rule else None


def get_conversion_type(metric_id: str) -> ConversionType:
    """Retorna el tipo de conversión para una métrica (NONE si no hay regla)."""
    rule = _RULES.get(metric_id)
    return rule.conversion if rule else ConversionType.NONE


def get_rules_by_section(section: Section) -> Dict[str, MetricRule]:
    """Retorna todas las reglas de una sección del dashboard."""
    return {k: v for k, v in _RULES.items() if v.section == section}


# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE VALIDACIÓN
# ═══════════════════════════════════════════════════════════════

def validate_metric_df(
    df: pd.DataFrame,
    metric_id: str,
    value_col: str = "valor_gwh",
    unit_col: str = "unidad",
) -> List[str]:
    """
    Valida un DataFrame contra las reglas centralizadas de la métrica.

    Retorna una lista de mensajes de error/advertencia.  Lista vacía = OK.

    NO modifica el DataFrame — es solo lectura.

    Parámetros
    ----------
    df : DataFrame ya convertido, listo para insertar en BD.
    metric_id : ID de la métrica XM.
    value_col : nombre de la columna con el valor numérico.
    unit_col : nombre de la columna con la unidad.
    """
    issues: List[str] = []
    rule = _RULES.get(metric_id)

    if rule is None:
        issues.append(f"WARN: No hay regla definida para '{metric_id}'. Se insertará sin validación centralizada.")
        return issues

    if df is None or df.empty:
        issues.append(f"ERROR: DataFrame vacío para '{metric_id}'.")
        return issues

    # 1. Verificar unidad
    if unit_col in df.columns:
        units_in_df = df[unit_col].dropna().unique()
        for u in units_in_df:
            if u != rule.expected_unit:
                issues.append(
                    f"ERROR UNIDAD: '{metric_id}' tiene unidad='{u}' en datos, "
                    f"pero se espera '{rule.expected_unit}'."
                )

    # 2. Verificar rango de valores
    if value_col in df.columns:
        vmin, vmax = rule.valid_range
        vals = df[value_col].dropna()

        if not rule.allow_negative:
            neg_count = (vals < 0).sum()
            if neg_count > 0:
                issues.append(
                    f"ERROR RANGO: '{metric_id}' tiene {neg_count} valores negativos "
                    f"(no permitido). Min={vals.min():.4f}"
                )

        out_of_range = ((vals < vmin) | (vals > vmax)).sum()
        if out_of_range > 0:
            issues.append(
                f"WARN RANGO: '{metric_id}' tiene {out_of_range}/{len(vals)} valores "
                f"fuera de [{vmin}, {vmax}]. Min={vals.min():.4f}, Max={vals.max():.4f}"
            )

    # 3. Verificar fechas
    fecha_col = None
    for c in ("fecha", "Date", "date"):
        if c in df.columns:
            fecha_col = c
            break
    if fecha_col:
        try:
            fechas = pd.to_datetime(df[fecha_col])
            futuras = (fechas > pd.Timestamp.now() + pd.Timedelta(days=2)).sum()
            if futuras > 0:
                issues.append(f"ERROR FECHA: '{metric_id}' tiene {futuras} registros con fecha futura.")
        except Exception:
            pass

    return issues


def apply_conversion(
    df: pd.DataFrame,
    metric_id: str,
    value_col: str = "Value",
) -> pd.DataFrame:
    """
    Aplica la conversión centralizada según las reglas de la métrica.

    Modifica el DataFrame in-place (pero retorna una copia por seguridad).
    Si no hay regla definida, retorna el DF sin cambios.

    NOTA: Esta función es un puente para que los ETL existentes puedan
    migrar gradualmente.  No reemplaza `convertir_unidades()` hasta que
    cada ETL la adopte explícitamente.
    """
    rule = _RULES.get(metric_id)
    if rule is None or df is None or df.empty:
        return df

    df = df.copy()

    # Normalizar nombre de columna
    if value_col not in df.columns and value_col.lower() in df.columns:
        df[value_col] = df[value_col.lower()]

    hour_cols = [f"Values_Hour{i:02d}" for i in range(1, 25)]
    existing_hours = [c for c in hour_cols if c in df.columns]

    conv = rule.conversion

    if conv == ConversionType.WH_TO_GWH or conv == ConversionType.KWH_TO_GWH:
        if value_col in df.columns:
            df[value_col] = df[value_col] / 1_000_000

    elif conv == ConversionType.HOURS_TO_GWH:
        if existing_hours:
            df[value_col] = df[existing_hours].sum(axis=1) / 1_000_000
        elif value_col in df.columns:
            df[value_col] = df[value_col] / 1_000_000

    elif conv == ConversionType.HOURS_TO_MW:
        if existing_hours:
            df[value_col] = df[existing_hours].mean(axis=1) / 1_000
        elif value_col in df.columns:
            df[value_col] = df[value_col] / 1_000

    elif conv == ConversionType.COP_TO_MCOP:
        if value_col in df.columns:
            df[value_col] = df[value_col] / 1_000_000
        elif existing_hours:
            df[value_col] = df[existing_hours].sum(axis=1) / 1_000_000

    elif conv == ConversionType.RESTR_TO_MCOP:
        if existing_hours:
            df[value_col] = df[existing_hours].mean(axis=1) / 1_000_000
        elif value_col in df.columns:
            df[value_col] = df[value_col] / 1_000_000

    return df


# ═══════════════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════════════

def summarize_rules() -> str:
    """Genera un resumen legible de todas las reglas (para logs / docs)."""
    lines = [
        f"{'Métrica':30s} | {'Sección':15s} | {'Unidad':15s} | {'Conversión':25s} | {'Rango':20s}",
        "-" * 115,
    ]
    for mid, rule in sorted(_RULES.items()):
        rng = f"[{rule.valid_range[0]}, {rule.valid_range[1]}]"
        lines.append(
            f"{mid:30s} | {rule.section.value:15s} | {rule.expected_unit:15s} "
            f"| {rule.conversion.value:25s} | {rng:20s}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(summarize_rules())
    print(f"\nTotal reglas definidas: {len(_RULES)}")
