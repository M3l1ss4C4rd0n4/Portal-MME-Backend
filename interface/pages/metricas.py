
"""
MÓDULO DE INTERFAZ: METRICAS
============================
Este archivo contiene exclusivamente la lógica de presentación (UI) y callbacks de Dash.
Toda la lógica de negocio y acceso a datos ha sido migrada a:
- domain.services.metrics_service.MetricsService

NO importar directamente infraestructura o bases de datos aquí.
"""

def get_plotly_modules():
    """Importar plotly solo cuando se necesite"""
    import plotly.express as px
    import plotly.graph_objects as go
    return px, go

import dash
from dash import dcc, html, Input, Output, State, callback, register_page
import dash_table
import datetime as dt
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import date, timedelta, datetime
import sys
import os
from io import BytesIO
import base64
import warnings
import zipfile
import numpy as np
import pandas.api.types

# Imports de Dominio (Refactorización)
from domain.services.metrics_service import MetricsService

# Imports locales para componentes uniformes
from interface.components.layout import crear_navbar_horizontal, crear_boton_regresar
from core.constants import UIColors as COLORS
from infrastructure.logging.logger import setup_logger
from core.validators import validate_date_range, validate_string
from core.exceptions import DateRangeError, InvalidParameterError, DataNotFoundError
from core.config_simem import METRICAS_SIMEM_POR_CATEGORIA, METRICAS_SIMEM_CRITICAS, obtener_listado_simem

# Inicializar servicio (Singleton-like para uso en módulo)
metrics_service = MetricsService()

try:
    from pydataxm.pydatasimem import VariableSIMEM
    PYDATASIMEM_AVAILABLE = True
except ImportError:
    PYDATASIMEM_AVAILABLE = False

warnings.filterwarnings("ignore")

# Configurar logger para este módulo
logger = setup_logger(__name__)

# Ruta de la base de datos
DB_PATH = '/home/admonctrlxm/server/portal_energetico.db'

# =============================================================================
# SISTEMA AUTOMÁTICO DE GENERACIÓN DE INFORMACIÓN DE MÉTRICAS
# =============================================================================

# =============================================================================
# CLASIFICACIÓN DE MÉTRICAS POR SECCIÓN DEL PORTAL
# =============================================================================

METRICAS_POR_SECCION = {
    '⚡ Generación': {
        'icon': 'fa-bolt',
        'color': '#FFD700',
        'metricas': ['Gene', 'GeneIdea', 'GeneProgDesp', 'GeneProgRedesp', 'GeneFueraMerito', 
                     'GeneSeguridad', 'CapEfecNeta', 'ENFICC', 'ObligEnerFirme', 'DDVContratada'],
        'descripcion': 'Métricas relacionadas con la producción de energía eléctrica por plantas generadoras'
    },
    '📊 Demanda': {
        'icon': 'fa-chart-line',
        'color': '#4169E1',
        'metricas': ['DemaReal', 'DemaCome', 'DemaRealReg', 'DemaRealNoReg', 'DemaComeReg', 
                     'DemaComeNoReg', 'DemaSIN', 'DemaMaxPot', 'DemaNoAtenProg', 'DemaNoAtenNoProg', 'DemaOR'],
        'descripcion': 'Métricas de consumo eléctrico por sistema, agentes y sectores'
    },
    '⚡ Transmisión': {
        'icon': 'fa-tower-broadcast',
        'color': '#FF6347',
        'metricas': ['DispoReal', 'DispoCome', 'DispoDeclarada', 'CargoUsoSTN', 'CargoUsoSTR'],
        'descripcion': 'Disponibilidad de recursos de transmisión y cargos por uso de redes'
    },
    '🚫 Restricciones': {
        'icon': 'fa-ban',
        'color': '#DC143C',
        'metricas': ['RestAliv', 'RestSinAliv', 'RentasCongestRestr', 'EjecGarantRestr', 
                     'DesvGenVariableDesp', 'DesvGenVariableRedesp'],
        'descripcion': 'Restricciones operativas del sistema y costos asociados'
    },
    '💰 Precios': {
        'icon': 'fa-dollar-sign',
        'color': '#32CD32',
        'metricas': ['PrecBolsNaci', 'PrecBolsNaciTX1', 'PPPrecBolsNaci', 'PrecTransBolsa',
                     'PrecPromCont', 'PrecPromContRegu', 'PrecPromContNoRegu',
                     'PrecEsca', 'PrecEscaAct', 'PrecEscaMarg', 'PrecEscaPon',
                     'PrecOferDesp', 'PrecOferIdeal', 'MaxPrecOferNal',
                     'CostMargDesp', 'CostRecPos', 'CostRecNeg', 'PrecCargConf'],
        'descripcion': 'Precios de bolsa, contratos, escasez y ofertas de despacho'
    },
    '💼 Transacciones': {
        'icon': 'fa-exchange-alt',
        'color': '#20B2AA',
        'metricas': ['CompBolsNaciEner', 'VentBolsNaciEner', 'CompContEner', 'VentContEner',
                     'CompBolsaTIEEner', 'VentBolsaTIEEner', 'CompBolsaIntEner', 'VentBolsaIntEner'],
        'descripcion': 'Compras y ventas de energía en bolsa, contratos e intercambios'
    },
    '📉 Pérdidas': {
        'icon': 'fa-chart-line-down',
        'color': '#FF4500',
        'metricas': ['PerdidasEner', 'PerdidasEnerReg', 'PerdidasEnerNoReg'],
        'descripcion': 'Pérdidas de energía del sistema por mercado regulado y no regulado'
    },
    '🌍 Intercambios Internacionales': {
        'icon': 'fa-globe',
        'color': '#1E90FF',
        'metricas': ['ImpoEner', 'ExpoEner', 'ImpoMoneda', 'ExpoMoneda', 
                     'SnTIEMerito', 'SnTIEFueraMerito', 'DeltaInt', 'DeltaNal'],
        'descripcion': 'Importaciones, exportaciones y saldos de intercambios energéticos'
    },
    '💧 Hidrología': {
        'icon': 'fa-water',
        'color': '#4682B4',
        'metricas': ['AporEner', 'AporCaudal', 'AporEnerMediHist', 'AporCaudalMediHist',
                     'VoluUtilDiarEner', 'VoluUtilDiarMasa', 'CapaUtilDiarEner', 'CapaUtilDiarMasa',
                     'VertEner', 'VertMasa', 'VolTurbMasa', 'DescMasa', 'PorcApor', 'PorcVoluUtilDiar'],
        'descripcion': 'Aportes, volúmenes y capacidades útiles de embalses y ríos'
    },
    '🔥 Combustibles y Emisiones': {
        'icon': 'fa-fire',
        'color': '#FF8C00',
        'metricas': ['ConsCombustibleMBTU', 'ConsCombAprox', 'EmisionesCO2', 'EmisionesCH4', 
                     'EmisionesN2O', 'EmisionesCO2Eq', 'factorEmisionCO2e'],
        'descripcion': 'Consumo de combustibles y emisiones de gases de efecto invernadero'
    },
    '☀️ Energías Renovables': {
        'icon': 'fa-sun',
        'color': '#FFD700',
        'metricas': ['IrrPanel', 'IrrGlobal', 'TempPanel', 'TempAmbSolar'],
        'descripcion': 'Irradiación solar y temperatura para generación fotovoltaica'
    },
    '💵 Cargos y Tarifas': {
        'icon': 'fa-file-invoice-dollar',
        'color': '#228B22',
        'metricas': ['FAZNI', 'FAER', 'PRONE', 'MC', 'CERE', 'CEE', 
                     'CargoUsoSTN', 'CargoUsoSTR', 'CargMaxTPrima', 'CargMinTPrima', 'CargMedTPrima'],
        'descripcion': 'Componentes tarifarios y cargos del sistema eléctrico'
    }
}

# Diccionario global de métricas importantes con información detallada
METRICAS_IMPORTANTES = {
    'DemaEner': {
        'nombre': 'Demanda de Energía',
        'descripcion': 'Consumo total de energía eléctrica del Sistema Interconectado Nacional (SIN) medido en MWh. Representa la energía que requieren todos los usuarios del país: residenciales, comerciales, industriales y oficiales. Es el indicador principal para evaluar el crecimiento del sector energético.',
        'descripcion_practica': 'Consumo total de energía eléctrica del Sistema Interconectado Nacional (SIN) medido en MWh. Representa la energía que requieren todos los usuarios del país: residenciales, comerciales, industriales y oficiales. Es el indicador principal para evaluar el crecimiento del sector energético.',
        'unidad': 'MWh',
        'frecuencia': 'Horaria',
        'criticidad': 'Alta',
        'uso_directo': 'El MME utiliza esta métrica para: 1) Proyectar el crecimiento energético del país y planificar nueva capacidad de generación, 2) Dimensionar las redes de transmisión necesarias, 3) Establecer políticas de eficiencia energética, 4) Calcular subsidios y contribuciones del FSSRI',
        'valor_critico': 'Demanda máxima histórica Colombia: ~11,800 MWh/h. Picos >12,000 MWh/h requieren activación de reservas de emergencia.',
        'aplicaciones': ['Proyección de crecimiento energético', 'Planificación de nueva capacidad', 'Políticas de eficiencia energética', 'Cálculo de subsidios FSSRI'],
        'categoria': 'demanda'
    },
    'GeneReal': {
        'nombre': 'Generación Real',
        'descripcion': 'Energía efectivamente producida por todas las plantas generadoras del SIN en tiempo real. Incluye plantas hidráulicas, térmicas, eólicas, solares y menores. Muestra la capacidad real del sistema vs. la capacidad instalada, considerando mantenimientos, fallas y restricciones operativas.',
        'descripcion_practica': 'Energía efectivamente producida por todas las plantas generadoras del SIN en tiempo real. Incluye plantas hidráulicas, térmicas, eólicas, solares y menores. Muestra la capacidad real del sistema vs. la capacidad instalada, considerando mantenimientos, fallas y restricciones operativas.',
        'unidad': 'MWh',
        'frecuencia': 'Horaria',
        'criticidad': 'Alta',
        'uso_directo': 'El MME la usa para: 1) Monitorear la confiabilidad del parque generador nacional, 2) Evaluar la necesidad de nuevas licitaciones de generación, 3) Detectar problemas operativos en tiempo real, 4) Coordinar con el ONS medidas de emergencia',
        'valor_critico': 'Margen mínimo 200-300 MW sobre demanda. Déficit vs demanda activa Plan de Emergencia del ONS.',
        'aplicaciones': ['Monitoreo de confiabilidad', 'Evaluación de licitaciones', 'Detección de problemas operativos', 'Coordinación con ONS'],
        'categoria': 'generacion'
    },
    'PrecBols': {
        'nombre': 'Precio de Bolsa Nacional',
        'descripcion': 'Costo marginal del sistema eléctrico colombiano expresado en pesos por kWh. Se determina por el costo de la planta más costosa que debe operar para atender la demanda. Refleja la escasez o abundancia energética del país y es clave para las señales económicas del mercado.',
        'descripcion_practica': 'Costo marginal del sistema eléctrico colombiano expresado en pesos por kWh. Se determina por el costo de la planta más costosa que debe operar para atender la demanda. Refleja la escasez o abundancia energética del país y es clave para las señales económicas del mercado.',
        'unidad': 'COP$/kWh',
        'frecuencia': 'Horaria',
        'criticidad': 'Alta',
        'uso_directo': 'El MME lo utiliza para: 1) Diseñar esquemas tarifarios y políticas de subsidios, 2) Evaluar la necesidad de declarar emergencias energéticas, 3) Establecer señales para nuevas inversiones en generación, 4) Monitorear la competitividad del mercado',
        'valor_critico': 'Precio de escasez: 446.26 $/kWh (2025). Valores >300 $/kWh indican tensión del sistema.',
        'aplicaciones': ['Diseño tarifario', 'Políticas de subsidios', 'Evaluación de emergencias', 'Señales de inversión'],
        'categoria': 'precio'
    },
    'ReseAmb': {
        'nombre': 'Reservas Ambientales',
        'descripcion': 'Volumen de agua almacenado en los embalses del SIN disponible para generación hidroeléctrica. Medido como porcentaje de la capacidad útil total. Es el indicador clave para prevenir crisis energéticas y gestionar restricciones ambientales.',
        'descripcion_practica': 'Volumen de agua almacenado en los embalses del SIN disponible para generación hidroeléctrica. Medido como porcentaje de la capacidad útil total. Es el indicador clave para prevenir crisis energéticas y gestionar restricciones ambientales.',
        'unidad': '%',
        'frecuencia': 'Diaria',
        'criticidad': 'Alta',
        'uso_directo': 'El MME lo utiliza para: 1) Activar alertas y planes de emergencia energética, 2) Coordinar con autoridades ambientales restricciones de uso del agua, 3) Declarar fenómenos El Niño/La Niña, 4) Planificar estrategias de ahorro y uso eficiente',
        'valor_critico': 'Alerta Amarilla: <30%, Alerta Naranja: <20%, Emergencia: <15%. Nivel crítico histórico: 28% (Fenómeno El Niño 2016).',
        'aplicaciones': ['Alertas de emergencia', 'Coordinación con autoridades ambientales', 'Declaración de fenómenos climáticos', 'Estrategias de ahorro'],
        'categoria': 'reserva'
    }
}

def generar_info_automatica_metrica(metric_id, metric_name, metric_description, metric_units):
    """
    Genera automáticamente información detallada de una métrica basada en:
    - MetricId: Código de la métrica
    - MetricName: Nombre descriptivo 
    - MetricDescription: Descripción técnica de XM
    - MetricUnits: Unidades de medida
    """
    
    # Mapas de patrones para categorización automática
    PATRONES_CATEGORIA = {
        'demanda': {
            'keywords': ['dema', 'demand', 'consumo', 'cons'],
            'descripcion_base': 'consumo eléctrico del sistema',
            'uso_mme': 'planificación energética, proyección de crecimiento de demanda, dimensionamiento de infraestructura, políticas de eficiencia energética',
            'valores_criticos': 'Monitorear picos >11,000 MW y crecimiento >4% anual'
        },
        'generacion': {
            'keywords': ['gene', 'gener', 'generation'],
            'descripcion_base': 'producción de energía eléctrica',
            'uso_mme': 'evaluación de confiabilidad del parque generador, planificación de nueva capacidad, monitoreo operativo, cálculo de márgenes de reserva',
            'valores_criticos': 'Mantener margen >200 MW sobre demanda máxima'
        },
        'precio': {
            'keywords': ['prec', 'price', 'costo', 'cost'],
            'descripcion_base': 'formación de precios del mercado eléctrico',
            'uso_mme': 'diseño de políticas tarifarias, evaluación de subsidios FSSRI, análisis de competitividad del mercado, señales de inversión',
            'valores_criticos': 'Precio escasez 446.26 $/kWh - Monitorear >300 $/kWh'
        },
        'reserva': {
            'keywords': ['rese', 'reser', 'almac', 'embal'],
            'descripcion_base': 'disponibilidad energética del sistema',
            'uso_mme': 'gestión de alertas energéticas, coordinación intersectorial agua-energía, planificación ante fenómenos climáticos, declaración de emergencias',
            'valores_criticos': '<30% activa alerta amarilla, <20% emergencia energética'
        },
        'transacciones': {
            'keywords': ['trans', 'expo', 'impo', 'intercam'],
            'descripcion_base': 'intercambios energéticos',
            'uso_mme': 'política de integración energética regional, aprovechamiento de complementariedad, generación de divisas, evaluación de nuevas interconexiones',
            'valores_criticos': 'Capacidad máxima 500 MW con Ecuador'
        },
        'transmision': {
            'keywords': ['transm', 'restric', 'restrict', 'congestion'],
            'descripcion_base': 'operación del sistema de transmisión',
            'uso_mme': 'planificación de expansión de transmisión, identificación de cuellos de botella, evaluación de proyectos de infraestructura, análisis de confiabilidad',
            'valores_criticos': 'Restricciones frecuentes indican necesidad de refuerzo'
        },
        'combustible': {
            'keywords': ['combu', 'fuel', 'gas', 'carbon'],
            'descripcion_base': 'consumo de combustibles para generación térmica',
            'uso_mme': 'política de combustibles, evaluación de seguridad energética, análisis de dependencia de importaciones, cálculo de emisiones GEI',
            'valores_criticos': 'Alto consumo indica operación térmica intensiva'
        },
        'perdidas': {
            'keywords': ['perd', 'loss', 'reconcil'],
            'descripcion_base': 'eficiencia del sistema eléctrico',
            'uso_mme': 'evaluación de eficiencia operativa, políticas anti-hurto, priorización de inversiones en reducción de pérdidas, benchmarking de operadores',
            'valores_criticos': 'Meta nacional <8% pérdidas totales'
        },
        'capacidad': {
            'keywords': ['capa', 'capacity', 'disp', 'available'],
            'descripcion_base': 'disponibilidad de capacidad de generación',
            'uso_mme': 'cálculo de margen de reserva, evaluación de confiabilidad, planificación de mantenimientos, licitaciones de cargo por confiabilidad',
            'valores_criticos': 'Margen mínimo 12% según regulación CREG'
        }
    }
    
    # Determinar categoría basada en palabras clave
    categoria_detectada = 'general'
    info_categoria = {
        'descripcion_base': 'variable del sistema eléctrico colombiano',
        'uso_mme': 'análisis del sector energético, toma de decisiones técnicas, supervisión del mercado eléctrico, planificación energética nacional',
        'valores_criticos': 'Evaluar según contexto operativo y histórico'
    }
    
    metric_lower = (metric_id + ' ' + metric_name + ' ' + metric_description).lower()
    
    for categoria, datos in PATRONES_CATEGORIA.items():
        if any(keyword in metric_lower for keyword in datos['keywords']):
            categoria_detectada = categoria
            info_categoria = datos
            break
    
    # Generar descripción práctica inteligente
    descripcion_completa = f"{metric_description} Esta métrica representa {info_categoria['descripcion_base']} y es fundamental para el monitoreo y operación del Sistema Interconectado Nacional (SIN)."
    
    # Generar nombre amigable si no existe
    nombre_amigable = metric_name if metric_name and metric_name.strip() else f"Métrica {metric_id}"
    
    # Unidades con fallback
    unidad_final = metric_units if metric_units and metric_units != 'N/A' else 'Ver especificación XM'
    
    return {
        'nombre': nombre_amigable,
        'descripcion_practica': descripcion_completa,
        'unidad': unidad_final,
        'uso_directo': f"El MME utiliza esta métrica para: {info_categoria['uso_mme']}",
        'valor_critico': info_categoria['valores_criticos'],
        'categoria': categoria_detectada,
        'descripcion_tecnica_xm': metric_description
    }

# Función expandida para obtener información detallada
def obtener_info_metrica_completa(metric_id):
    """Obtener información específica y práctica de una métrica"""
    
    # Si es una métrica importante, usar información manual del diccionario global
    if metric_id in METRICAS_IMPORTANTES:
        return METRICAS_IMPORTANTES[metric_id]
    
    # Para otras métricas, generar automáticamente
    try:
        if not todas_las_metricas.empty:
            metric_info = todas_las_metricas[todas_las_metricas['MetricId'] == metric_id]
            if not metric_info.empty:
                first_record = metric_info.iloc[0]
                return generar_info_automatica_metrica(
                    metric_id=metric_id,
                    metric_name=first_record.get('MetricName', ''),
                    metric_description=first_record.get('MetricDescription', ''),
                    metric_units=first_record.get('MetricUnits', 'N/A')
                )
    except Exception:
        pass
    
    # Fallback para casos excepcionales
    return {
        'nombre': f'Métrica {metric_id}',
        'descripcion_practica': f'Variable del sistema eléctrico colombiano monitoreada por XM. Forma parte del conjunto de {len(todas_las_metricas)} métricas disponibles para análisis del sector energético.',
        'unidad': 'Ver especificación técnica XM',
        'uso_directo': 'Análisis técnico especializado del comportamiento del sistema eléctrico nacional para toma de decisiones del MME',
        'valor_critico': 'Los umbrales críticos deben definirse según análisis histórico y contexto operativo específico',
        'categoria': 'general'
    }

register_page(
    __name__,
    path="/metricas",
    name="Metricas",
    title="Dashboard Energético XM - Colombia",
    order=2
)

# Inicializar API XM de forma perezosa y cargar colecciones si están disponibles
todas_las_metricas = pd.DataFrame()

try:
    # Usar servicio de dominio para obtener metadatos
    todas_las_metricas = metrics_service.get_metrics_metadata()
    if not todas_las_metricas.empty:
        logger.info("Métricas disponibles cargadas desde servicio")
        logger.info(f"Métricas disponibles: {len(todas_las_metricas)}")
    else:
        logger.warning("No se pudieron cargar metadatos de métricas")
except Exception as e:
    logger.error(f"Error al inicializar métricas: {e}", exc_info=True)
    todas_las_metricas = pd.DataFrame()

# Función para obtener opciones únicas de MetricId y Entity
def get_metric_options():
    
    if todas_las_metricas.empty:
        logger.warning("Retornando opciones vacías porque todas_las_metricas está vacío")
        return [], []
    
    # Crear opciones de métricas y ordenarlas alfabéticamente por MetricName
    metric_options = [
        {"label": f"{row['MetricId']} - {row['MetricName']}", "value": row['MetricId']}
        for _, row in todas_las_metricas.iterrows()
    ]
    
    # Ordenar alfabéticamente por el label (que incluye MetricName)
    metric_options = sorted(metric_options, key=lambda x: x['label'])
    
    entity_options = [
        {"label": entity, "value": entity}
        for entity in todas_las_metricas['Entity'].unique()
        if pd.notna(entity)
    ]
    
    # También ordenar las entidades alfabéticamente
    entity_options = sorted(entity_options, key=lambda x: x['label'])
    
    logger.debug(f"Opciones de entidades disponibles: {len(entity_options)}")
    
    return metric_options, entity_options

metric_options, entity_options = get_metric_options()

def crear_selector_fuente_datos():
    """Crea un selector para elegir entre datos XM y SIMEM"""
    return dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label([
                        html.I(className="fas fa-database me-2"),
                        html.Strong("Fuente de Datos:")
                    ], className="mb-2"),
                    dbc.RadioItems(
                        id="selector-fuente-datos",
                        options=[
                            {"label": [
                                html.I(className="fas fa-bolt me-2", style={"color": "#FFD700"}),
                                "Métricas XM (Portal Energético)"
                            ], "value": "xm"},
                            {"label": [
                                html.I(className="fas fa-server me-2", style={"color": "#4169E1"}),
                                "Métricas SIMEM (Sistema de Información)"
                            ], "value": "simem", "disabled": not PYDATASIMEM_AVAILABLE}
                        ],
                        value="xm",
                        inline=True,
                        className="mb-0"
                    )
                ], md=8),
                dbc.Col([
                    dbc.Badge([
                        html.I(className="fas fa-info-circle me-1"),
                        f"XM: {len(metric_options)} métricas" if metric_options else "XM: Cargando..."
                    ], color="primary", className="me-2"),
                    dbc.Badge([
                        html.I(className="fas fa-info-circle me-1"),
                        "SIMEM: 193 variables" if PYDATASIMEM_AVAILABLE else "SIMEM: No disponible"
                    ], color="info")
                ], md=4, className="text-end")
            ], align="center")
        ])
    ], className="shadow-sm mb-3")

layout = html.Div([
    # Navbar horizontal
    # crear_navbar_horizontal(),
    
    # Container principal
    dbc.Container([
        
        dbc.Row([
            # Contenido principal (ahora ocupa todo el ancho)
            dbc.Col([
                # Panel de controles en tabs
                dbc.Tabs([
                    dbc.Tab(label="📊 Consulta de Métricas", tab_id="tab-consulta"),
                    dbc.Tab(label="🗂️ Análisis por Sección", tab_id="tab-secciones"),
                    dbc.Tab(label="📈 Análisis Energético", tab_id="tab-analisis"),
                    dbc.Tab(label="🔍 Exploración Avanzada", tab_id="tab-exploracion"),
                    dbc.Tab(label="📚 Guía para Ingenieros", tab_id="tab-guia"),
                ], id="metricas-tabs", active_tab="tab-consulta", className="mb-4"),
                
                # Contenido dinámico
                html.Div(id="metricas-tab-content")
            ], width=12)  # Ahora ocupa todo el ancho
        ])
    ], fluid=True)
], style={'backgroundColor': COLORS['bg_main'], 'minHeight': '100vh'})

# Layout del panel de controles energéticos
def crear_panel_controles_metricas():
    # Mostrar alerta si la API XM no está disponible (validado si tenemos metadatos)
    if todas_las_metricas.empty:
        return dbc.Card([
            dbc.CardBody([
                html.Div([
                    html.I(className="fas fa-exclamation-triangle me-2", style={"color": "#DC2626"}),
                    html.Strong("Servicio XM No Disponible", style={"fontSize": "1.1rem", "color": "#DC2626"})
                ], className="mb-3 d-flex align-items-center"),
                
                dbc.Alert([
                    html.H6([
                        html.I(className="fas fa-plug me-2"),
                        "Conexión con XM Interrumpida"
                    ], className="alert-heading"),
                    html.P([
                        "No se pudo establecer conexión con los datos de XM. Esto puede deberse a:"
                    ], className="mb-2"),
                    html.Ul([
                        html.Li("Problemas de conectividad a internet"),
                        html.Li("La librería pydataxm no está instalada correctamente"),
                        html.Li("Los servidores de XM están temporalmente no disponibles")
                    ]),
                    html.Hr(),
                    html.P([
                        html.Strong("Solución: "),
                        "Verifica tu conexión a internet y recarga la página. ",
                        "Si el problema persiste, contacta al administrador del sistema."
                    ], className="mb-0")
                ], color="danger")
            ])
        ], className="shadow-sm")
    
    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.I(className="fas fa-cogs me-2", style={"color": COLORS['primary']}),
                html.Strong("Panel de Consulta Energética", style={"fontSize": "1.1rem", "color": COLORS['text_primary']})
            ], className="mb-3 d-flex align-items-center"),
            
            dbc.Row([
                dbc.Col([
                    html.Label([
                        html.I(className="fas fa-chart-bar me-2"),
                        "Métrica Energética"
                    ], className="fw-bold mb-2 d-flex align-items-center"),
                    dcc.Dropdown(
                        id="metric-dropdown",
                        options=metric_options,
                        value=metric_options[0]["value"] if metric_options else None,
                        placeholder="Selecciona una métrica energética...",
                        className="form-control-modern mb-0",
                        style={"fontSize": "0.95rem"}
                    )
                ], lg=4, md=6, sm=12),
                
                dbc.Col([
                    html.Label([
                        html.I(className="fas fa-building me-2"),
                        "Entidad del Sistema"
                    ], className="fw-bold mb-2 d-flex align-items-center"),
                    dcc.Dropdown(
                        id="entity-dropdown",
                        options=entity_options,
                        placeholder="Selecciona una entidad...",
                        className="form-control-modern mb-0",
                        style={"fontSize": "0.95rem"}
                    )
                ], lg=4, md=6, sm=12),
                
                dbc.Col([
                    html.Label([
                        html.I(className="fas fa-calendar-range me-2"),
                        "Período de Análisis"
                    ], className="fw-bold mb-2 d-flex align-items-center"),
                    dcc.DatePickerRange(
                        id="date-picker-range",
                        start_date=date.today() - timedelta(days=7),  # Solo 7 días para consulta más rápida
                        end_date=date.today(),
                        display_format="DD/MM/YYYY",
                        className="form-control-modern",
                        style={"width": "100%"}
                    )
                ], lg=4, md=12, sm=12)
            ], className="g-3 align-items-end mb-3"),
            
            dbc.Row([
                dbc.Col([
                    dbc.Button([
                        html.I(className="fas fa-search me-2"),
                        "Consultar Datos Energéticos"
                    ],
                    id="query-button",
                    color="primary",
                    className="w-100 btn-modern",
                    style={"background": f"linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['accent']} 100%)", "border": "none"}
                    )
                ], lg=6, md=12),
                dbc.Col([
                    dbc.DropdownMenu([
                        dbc.DropdownMenuItem([
                            html.I(className="fas fa-file-excel me-2", style={'color': '#107C41'}),
                            "Descargar Excel (.xlsx)"
                        ], id="download-excel-btn"),
                        dbc.DropdownMenuItem([
                            html.I(className="fas fa-file-csv me-2", style={'color': '#FF6B35'}),
                            "Descargar CSV (.csv)"
                        ], id="download-csv-btn"),
                        dbc.DropdownMenuItem([
                            html.I(className="fas fa-file-pdf me-2", style={'color': '#DC3545'}),
                            "Descargar PDF (.pdf)"
                        ], id="download-pdf-btn"),
                        dbc.DropdownMenuItem(divider=True),
                        dbc.DropdownMenuItem([
                            html.I(className="fas fa-download me-2", style={'color': COLORS['primary']}),
                            "Descargar Todo (.zip)"
                        ], id="download-all-btn"),
                    ],
                    label=[
                        html.I(className="fas fa-download me-2"),
                        "Descargar Reporte"
                    ],
                    id="download-dropdown",
                    color="secondary",
                    className="w-100",
                    style={'width': '100%'}
                    ),
                    # Componentes de descarga
                    dcc.Download(id="download-metricas-excel"),
                    dcc.Download(id="download-metricas-csv"),
                    dcc.Download(id="download-metricas-pd"),
                    dcc.Download(id="download-metricas-zip")
                ], lg=6, md=12)
            ], className="g-3")
        ], className="p-4")
    ], className="shadow-sm")

# Aquí NO se incluye metricas-results-content porque debe estar dentro del tab

# Callback para manejar tabs
@callback(
    Output("metricas-tab-content", "children"),
    Input("metricas-tabs", "active_tab")
)
def render_metricas_tab_content(active_tab):
    if active_tab == "tab-consulta":
        return html.Div([
            crear_selector_fuente_datos(),
            html.Div(id="contenedor-consulta-dinamico", className="mt-3")
        ])
    elif active_tab == "tab-secciones":
        return html.Div([
            crear_selector_fuente_datos(),
            html.Div(id="contenedor-seccion-dinamico", className="mt-3")
        ])
    elif active_tab == "tab-analisis":
        return html.Div([
            dbc.Card([
                dbc.CardBody([
                    html.H4([
                        html.I(className="fas fa-chart-line me-2", style={"color": COLORS['primary']}),
                        "Análisis Energético del Sistema"
                    ], className="mb-4"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("⚡ Generación vs Demanda", className="mb-3"),
                                    html.P("Análisis comparativo entre generación eléctrica y demanda nacional.", className="text-muted")
                                ])
                            ], className="h-100")
                        ], md=6),
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H6("🔋 Mix Energético", className="mb-3"),
                                    html.P("Composición de fuentes de energía en el sistema eléctrico colombiano.", className="text-muted")
                                ])
                            ], className="h-100")
                        ], md=6)
                    ])
                ])
            ], className="shadow-sm"),
            html.Div(id="metricas-results-content-analisis", className="mt-4")
        ])
    elif active_tab == "tab-exploracion":
        return html.Div([
            crear_selector_fuente_datos(),
            html.Div(id="contenedor-exploracion-dinamico", className="mt-3")
        ])
    elif active_tab == "tab-guia":
        return crear_guia_ingenieros()
    
    return html.Div()

def crear_analisis_por_seccion():
    """Crear panel de análisis de métricas organizadas por sección del portal"""
    return html.Div([
        # Header
        dbc.Card([
            dbc.CardBody([
                html.H3([
                    html.I(className="fas fa-sitemap me-3", style={"color": COLORS['primary']}),
                    "Análisis de Métricas por Sección del Portal"
                ], className="mb-3", style={'color': COLORS['text_primary'], 'fontWeight': '600'}),
                
                dbc.Alert([
                    html.I(className="fas fa-info-circle me-2", style={'color': COLORS['info']}),
                    html.Strong("Explora las métricas organizadas según las secciones del Portal Energético. "),
                    "Cada sección agrupa métricas relacionadas para facilitar el análisis multivariado y correlacional."
                ], color="light", className="mb-0", style={'border': f'1px solid {COLORS["border"]}'})
            ])
        ], className="mb-4", style={'border': f'1px solid {COLORS["border"]}', 'boxShadow': f'0 2px 4px {COLORS["shadow_md"]}'}),
        
        # Grid de secciones
        dbc.Row([
            dbc.Col([
                crear_card_seccion(seccion, info)
            ], md=4, className="mb-4")
            for seccion, info in METRICAS_POR_SECCION.items()
        ]),
        
        # Contenedor para análisis multivariado
        html.Div(id="analisis-seccion-container", className="mt-4")
    ])

def crear_card_seccion(seccion, info):
    """Crear card para una sección específica"""
    return dbc.Card([
        dbc.CardHeader([
            html.H5([
                html.I(className=f"fas {info['icon']} me-2", style={'color': info['color']}),
                seccion
            ], className="mb-0", style={'fontSize': '1.1em', 'fontWeight': '600'})
        ], style={'backgroundColor': f"{info['color']}15", 'border': 'none'}),
        dbc.CardBody([
            html.P(info['descripcion'], className="mb-3", style={'fontSize': '0.9em', 'color': COLORS['text_secondary']}),
            
            dbc.Badge(f"{len(info['metricas'])} métricas disponibles", 
                     color="primary", className="mb-3", style={'fontSize': '0.85em'}),
            
            html.Div([
                html.H6("Métricas principales:", className="mb-2", style={'fontSize': '0.95em', 'fontWeight': '600'}),
                html.Ul([
                    html.Li(metrica, style={'fontSize': '0.85em', 'color': COLORS['text_secondary']})
                    for metrica in info['metricas'][:5]
                ], className="mb-2"),
                html.Small([
                    html.I(className="fas fa-ellipsis-h me-1"),
                    f"y {len(info['metricas']) - 5} más..." if len(info['metricas']) > 5 else ""
                ], style={'color': COLORS['text_muted'], 'fontSize': '0.8em'}) if len(info['metricas']) > 5 else None
            ]),
            
            dbc.Button([
                html.I(className="fas fa-chart-line me-2"),
                "Analizar Sección"
            ], color="primary", size="sm", outline=True, className="w-100 mt-3", 
               id={"type": "btn-analizar-seccion", "index": seccion},
               style={'fontSize': '0.85em'})
        ])
    ], style={'height': '100%', 'border': f'2px solid {info["color"]}30', 
              'boxShadow': f'0 2px 4px {COLORS["shadow_sm"]}', 
              'transition': 'all 0.3s ease',
              'cursor': 'pointer'},
       className="h-100")

def crear_guia_ingenieros():
    """Crear guía detallada para ingenieros del MME"""
    return html.Div([
        # Header de la guía
        dbc.Card([
            dbc.CardBody([
                html.H3([
                    html.I(className="fas fa-user-tie me-3", style={"color": COLORS['primary']}),
                    "Guía de Métricas para Ingenieros del MME"
                ], className="mb-3", style={'color': COLORS['text_primary'], 'fontWeight': '600'}),
                
                dbc.Alert([
                    html.I(className="fas fa-info-circle me-2", style={'color': COLORS['info']}),
                    html.Strong("Objetivo: "),
                    "Esta guía ayuda a identificar las métricas XM más adecuadas para generar tableros específicos según las necesidades del Ministerio de Minas y Energía."
                ], color="light", className="mb-3", style={'border': f'1px solid {COLORS["border"]}'})
            ])
        ], className="mb-4", style={'border': f'1px solid {COLORS["border"]}', 'boxShadow': f'0 2px 4px {COLORS["shadow_md"]}'}),
        
        # Métricas críticas
        dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className="fas fa-star me-2", style={'color': '#FFD700'}),
                    "Métricas Críticas para Tableros MME"
                ], className="mb-0", style={'color': COLORS['text_primary'], 'fontWeight': '600'})
            ], style={'backgroundColor': '#FFFDF0', 'border': 'none'}),
            dbc.CardBody([
                dbc.Row([
                    crear_card_metrica_detallada("DemaEner", METRICAS_IMPORTANTES["DemaEner"]),
                    crear_card_metrica_detallada("GeneReal", METRICAS_IMPORTANTES["GeneReal"]),
                ], className="mb-3"),
                dbc.Row([
                    crear_card_metrica_detallada("PrecBols", METRICAS_IMPORTANTES["PrecBols"]),
                    crear_card_metrica_detallada("ReseAmb", METRICAS_IMPORTANTES["ReseAmb"]),
                ])
            ])
        ], className="mb-4", style={'border': f'1px solid #FEF3C7'}),
        
        # Categorización de métricas
        dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className="fas fa-layer-group me-2", style={'color': COLORS['primary']}),
                    "Clasificación por Categorías"
                ], className="mb-0", style={'color': COLORS['text_primary'], 'fontWeight': '600'})
            ], style={'backgroundColor': '#F0F9FF', 'border': 'none'}),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.H6([
                            html.I(className="fas fa-bolt me-2", style={'color': COLORS['warning']}),
                            "Demanda y Consumo"
                        ], style={'color': COLORS['text_primary']}),
                        html.Ul([
                            html.Li("DemaEner - Demanda Nacional"),
                            html.Li("DemaComeSISTEMA - Demanda Comercial"),
                            html.Li("ConsEner - Consumo Total")
                        ], style={'fontSize': '0.9em', 'color': COLORS['text_secondary']})
                    ], md=6),
                    dbc.Col([
                        html.H6([
                            html.I(className="fas fa-industry me-2", style={'color': COLORS['success']}),
                            "Generación"
                        ], style={'color': COLORS['text_primary']}),
                        html.Ul([
                            html.Li("GeneReal - Generación Real"),
                            html.Li("GeneIdea - Generación Ideal"),
                            html.Li("CapaEfec - Capacidad Efectiva")
                        ], style={'fontSize': '0.9em', 'color': COLORS['text_secondary']})
                    ], md=6)
                ], className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.H6([
                            html.I(className="fas fa-dollar-sign me-2", style={'color': COLORS['info']}),
                            "Económicas"
                        ], style={'color': COLORS['text_primary']}),
                        html.Ul([
                            html.Li("PrecBols - Precio Bolsa"),
                            html.Li("CostoMarginal - Costo Marginal"),
                            html.Li("ValorTransacciones - Transacciones")
                        ], style={'fontSize': '0.9em', 'color': COLORS['text_secondary']})
                    ], md=6),
                    dbc.Col([
                        html.H6([
                            html.I(className="fas fa-tint me-2", style={'color': '#0EA5E9'}),
                            "Hidrológicas"
                        ], style={'color': COLORS['text_primary']}),
                        html.Ul([
                            html.Li("ReseAmb - Reserva Ambiental"),
                            html.Li("VolUte - Volumen Útil"),
                            html.Li("AporEner - Aportes Energéticos")
                        ], style={'fontSize': '0.9em', 'color': COLORS['text_secondary']})
                    ], md=6)
                ])
            ])
        ], className="mb-4", style={'border': f'1px solid #DBEAFE'}),
        
        # Recomendaciones para tableros
        dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className="fas fa-lightbulb me-2", style={'color': '#F59E0B'}),
                    "Recomendaciones para Tableros Específicos"
                ], className="mb-0", style={'color': COLORS['text_primary'], 'fontWeight': '600'})
            ], style={'backgroundColor': '#FFFBEB', 'border': 'none'}),
            dbc.CardBody([
                dbc.Accordion([
                    dbc.AccordionItem([
                        html.P("🎯 Métricas recomendadas: DemaEner, ConsEner, PrecBols", className="mb-2"),
                        html.P("📊 Frecuencia: Datos horarios para análisis detallado", className="mb-2"),
                        html.P("💡 Casos de uso: Proyecciones de demanda, análisis de picos de consumo, correlación precio-demanda", className="mb-0")
                    ], title="📈 Tablero de Demanda Energética Nacional"),
                    
                    dbc.AccordionItem([
                        html.P("🎯 Métricas recomendadas: GeneReal, CapaEfec, ReseAmb", className="mb-2"),
                        html.P("📊 Frecuencia: Datos diarios y horarios", className="mb-2"),
                        html.P("💡 Casos de uso: Monitoreo de disponibilidad, planificación operativa, gestión de embalses", className="mb-0")
                    ], title="⚡ Tablero de Generación y Capacidad"),
                    
                    dbc.AccordionItem([
                        html.P("🎯 Métricas recomendadas: PrecBols, CostoMarginal, ValorTransacciones", className="mb-2"),
                        html.P("📊 Frecuencia: Datos horarios para volatilidad", className="mb-2"),
                        html.P("💡 Casos de uso: Análisis de mercado, seguimiento financiero, alertas de precios", className="mb-0")
                    ], title="💰 Tablero Económico del Sector"),
                    
                    dbc.AccordionItem([
                        html.P("🎯 Métricas recomendadas: ReseAmb, AporEner, VolUte", className="mb-2"),
                        html.P("📊 Frecuencia: Datos diarios y semanales", className="mb-2"),
                        html.P("💡 Casos de uso: Gestión de sequías, planificación hídrica, alertas hidrológicas", className="mb-0")
                    ], title="🌊 Tablero Hidrológico Nacional")
                ])
            ])
        ], className="mb-4", style={'border': f'1px solid #FED7AA'})
    ])

def crear_card_metrica_detallada(metric_id, info):
    """Crear card detallada para una métrica específica"""
    return dbc.Col([
        dbc.Card([
            dbc.CardBody([
                html.H6([
                    html.I(className="fas fa-chart-bar me-2", style={'color': COLORS['primary']}),
                    f"{metric_id} - {info['nombre']}"
                ], className="mb-2", style={'color': COLORS['text_primary'], 'fontWeight': '600'}),
                
                html.P(info['descripcion'], className="mb-2", style={'color': COLORS['text_secondary'], 'fontSize': '0.9em'}),
                
                dbc.Row([
                    dbc.Col([
                        html.Small([
                            html.Strong("Unidad: ", style={'color': COLORS['text_primary']}),
                            info['unidad']
                        ], style={'color': COLORS['text_secondary']})
                    ], width=6),
                    dbc.Col([
                        html.Small([
                            html.Strong("Frecuencia: ", style={'color': COLORS['text_primary']}),
                            info['frecuencia']
                        ], style={'color': COLORS['text_secondary']})
                    ], width=6)
                ], className="mb-2"),
                
                html.Small([
                    html.Strong("Criticidad: "),
                    dbc.Badge(info['criticidad'], 
                             color="danger" if info['criticidad'] == "Alta" else "warning" if info['criticidad'] == "Media" else "secondary",
                             className="me-2")
                ], className="mb-2", style={'display': 'block'}),
                
                html.P([
                    html.Strong("💼 Aplicaciones: ", style={'color': COLORS['primary'], 'fontSize': '0.9em'}),
                    html.Br(),
                    ", ".join(info['aplicaciones'])
                ], className="mb-0", style={'color': COLORS['text_secondary'], 'fontSize': '0.8em'})
            ])
        ], style={'height': '100%', 'border': f'1px solid {COLORS["border"]}', 'boxShadow': f'0 1px 3px {COLORS["shadow_sm"]}'})
    ], md=6, className="mb-3")

# =============================================================================
# CALLBACKS PARA SELECTOR DE FUENTE DE DATOS (XM vs SIMEM)
# =============================================================================

@callback(
    Output("contenedor-consulta-dinamico", "children"),
    Input("selector-fuente-datos", "value")
)
def actualizar_panel_consulta(fuente):
    """Actualiza el panel de consulta según la fuente seleccionada"""
    if fuente == "simem":
        return crear_panel_consulta_simem()
    else:
        return html.Div([
            crear_panel_controles_metricas(),
            html.Div(id="metricas-results-content", className="mt-4")
        ])

@callback(
    Output("contenedor-seccion-dinamico", "children"),
    Input("selector-fuente-datos", "value")
)
def actualizar_panel_seccion(fuente):
    """Actualiza el panel de análisis por sección según la fuente"""
    if fuente == "simem":
        return crear_analisis_por_seccion_simem()
    else:
        return crear_analisis_por_seccion()

@callback(
    Output("contenedor-exploracion-dinamico", "children"),
    Input("selector-fuente-datos", "value")
)
def actualizar_panel_exploracion(fuente):
    """Actualiza el panel de exploración avanzada según la fuente"""
    if fuente == "simem":
        return crear_exploracion_simem()
    else:
        return crear_exploracion_xm()

def crear_panel_consulta_simem():
    """Crea el panel de consulta para métricas SIMEM"""
    if not PYDATASIMEM_AVAILABLE:
        return dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            "El módulo pydatasimem no está disponible. Por favor, instale pydataxm correctamente."
        ], color="warning")
    
    # Obtener listado de variables SIMEM
    try:
        listado_simem = obtener_listado_simem()
        if listado_simem is None or listado_simem.empty:
            raise Exception("No se pudo cargar el listado SIMEM")
        
        opciones_simem = [
            {"label": f"{row['CodigoVariable']} - {row['Nombre']}", "value": row['CodigoVariable']}
            for _, row in listado_simem.iterrows()
        ]
        opciones_simem = sorted(opciones_simem, key=lambda x: x['label'])
    except Exception as e:
        logger.error(f"Error cargando variables SIMEM: {e}")
        return dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            f"Error al cargar variables SIMEM: {str(e)}"
        ], color="danger")
    
    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.I(className="fas fa-server me-2", style={"color": COLORS['primary']}),
                html.Strong("Consulta de Variables SIMEM", style={"fontSize": "1.1rem"})
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    html.Label([
                        html.I(className="fas fa-chart-bar me-2"),
                        "Variable SIMEM"
                    ], className="fw-bold mb-2"),
                    dcc.Dropdown(
                        id="simem-variable-dropdown",
                        options=opciones_simem,
                        value=opciones_simem[0]["value"] if opciones_simem else None,
                        placeholder="Selecciona una variable SIMEM...",
                        className="form-control-modern"
                    )
                ], md=6),
                
                dbc.Col([
                    html.Label([
                        html.I(className="fas fa-calendar-range me-2"),
                        "Período"
                    ], className="fw-bold mb-2"),
                    dcc.DatePickerRange(
                        id="simem-date-picker",
                        start_date=date.today() - timedelta(days=7),
                        end_date=date.today(),
                        display_format="DD/MM/YYYY",
                        className="form-control-modern"
                    )
                ], md=6)
            ], className="mb-3"),
            
            dbc.Button([
                html.I(className="fas fa-search me-2"),
                "Consultar SIMEM"
            ], id="btn-consultar-simem", color="primary", size="lg", className="w-100")
        ])
    ], className="shadow-sm"),
    
    # Contenedor de resultados
    html.Div(id="simem-results", className="mt-4")

def crear_analisis_por_seccion_simem():
    """Crea el panel de análisis por sección para métricas SIMEM con análisis multivariable"""
    return html.Div([
        # Header principal
        dbc.Card([
            dbc.CardBody([
                html.H3([
                    html.I(className="fas fa-server me-3", style={"color": COLORS['primary']}),
                    "Análisis de Métricas SIMEM por Categoría"
                ], className="mb-3", style={'color': COLORS['text_primary'], 'fontWeight': '600'}),
                
                dbc.Alert([
                    html.I(className="fas fa-info-circle me-2", style={'color': COLORS['info']}),
                    html.Strong("Sistema de Información del Mercado Eléctrico (SIMEM). "),
                    "193 variables organizadas en 10 categorías para análisis detallado del sector energético colombiano."
                ], color="light", className="mb-0", style={'border': f'1px solid {COLORS["border"]}'})
            ])
        ], className="mb-4 shadow-sm"),
        
        # Grid de categorías SIMEM
        dbc.Row([
            crear_card_seccion_simem(seccion, info)
            for seccion, info in METRICAS_SIMEM_POR_CATEGORIA.items()
        ], className="g-3"),
        
        # Panel de análisis multivariable SIMEM
        html.Div([
            html.Hr(className="my-5"),
            
            dbc.Card([
                dbc.CardBody([
                    html.H4([
                        html.I(className="fas fa-project-diagram me-3", style={"color": COLORS['primary']}),
                        "Análisis Multivariable SIMEM"
                    ], className="mb-4", style={'fontWeight': '600'}),
                    
                    dbc.Alert([
                        html.I(className="fas fa-lightbulb me-2"),
                        html.Strong("Análisis de correlaciones: "),
                        "Explora las relaciones entre múltiples variables SIMEM para identificar patrones y dependencias del sistema eléctrico."
                    ], color="info", className="mb-4"),
                    
                    # Selector de variables para análisis
                    dbc.Row([
                        dbc.Col([
                            html.Label([
                                html.I(className="fas fa-list me-2"),
                                html.Strong("Variables para Análisis:")
                            ], className="mb-2"),
                            dcc.Dropdown(
                                id="simem-multivariable-dropdown",
                                options=[
                                    {"label": f"{codigo} - {nombre}", "value": codigo}
                                    for categoria in METRICAS_SIMEM_POR_CATEGORIA.values()
                                    for codigo, nombre in categoria['metricas'].items()
                                ],
                                value=['GReal', 'DdaReal', 'CostoMarginalDespacho'],
                                multi=True,
                                placeholder="Selecciona variables SIMEM para análisis...",
                                className="mb-3"
                            )
                        ], md=8),
                        
                        dbc.Col([
                            html.Label([
                                html.I(className="fas fa-calendar me-2"),
                                html.Strong("Período:")
                            ], className="mb-2"),
                            dcc.DatePickerRange(
                                id="simem-multivariable-dates",
                                start_date=date.today() - timedelta(days=7),
                                end_date=date.today(),
                                display_format="DD/MM/YYYY"
                            )
                        ], md=4)
                    ], className="mb-3"),
                    
                    dbc.Button([
                        html.I(className="fas fa-chart-line me-2"),
                        "Generar Análisis Multivariable"
                    ], id="btn-analisis-multivariable-simem", color="primary", size="lg", className="w-100 mb-3"),
                    
                    html.Div(id="simem-multivariable-results", className="mt-4")
                ])
            ], className="shadow-sm")
        ])
    ])

def crear_card_seccion_simem(seccion, info):
    """Crea una tarjeta para una sección de métricas SIMEM con listado completo"""
    metricas_dict = info['metricas']
    
    return dbc.Col([
        dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className=f"fas {info['icon']} me-2", style={'color': info['color']}),
                    seccion
                ], className="mb-0", style={'fontSize': '1.1em', 'fontWeight': '600'})
            ], style={'backgroundColor': f"{info['color']}15", 'border': 'none'}),
            dbc.CardBody([
                html.P(info['descripcion'], className="mb-3", style={'fontSize': '0.9em', 'color': COLORS['text_secondary']}),
                
                dbc.Badge(f"{len(metricas_dict)} métricas disponibles", 
                         color="info", className="mb-3", style={'fontSize': '0.85em'}),
                
                html.Div([
                    html.H6("📊 Variables SIMEM:", className="mb-2", style={'fontSize': '0.95em', 'fontWeight': '600'}),
                    html.Div([
                        html.Div([
                            html.I(className="fas fa-chevron-right me-2", style={'fontSize': '0.6em', 'color': info['color']}),
                            html.Strong(f"{codigo}: ", style={'fontSize': '0.8em', 'color': COLORS['primary']}),
                            html.Span(nombre, style={'fontSize': '0.8em', 'color': COLORS['text_secondary']})
                        ], className="mb-1")
                        for codigo, nombre in metricas_dict.items()
                    ], style={'maxHeight': '400px', 'overflowY': 'auto', 'paddingRight': '10px'})
                ]),
                
                html.Hr(className="my-3"),
                
                html.Small([
                    html.I(className="fas fa-info-circle me-1", style={'color': info['color']}),
                    "Usa el panel de consulta para visualizar estas variables"
                ], className="text-muted", style={'fontSize': '0.75em'})
            ])
        ], className="h-100 shadow-sm", style={'border': f'1px solid {COLORS["border"]}'})
    ], md=6, lg=4, className="mb-3")

def crear_exploracion_xm():
    """Crea el panel de exploración avanzada para métricas XM"""
    return html.Div([
        dbc.Card([
            dbc.CardBody([
                html.H4([
                    html.I(className="fas fa-search-plus me-2", style={"color": COLORS['primary']}),
                    "Exploración Avanzada de Datos XM"
                ], className="mb-4"),
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6("🔍 Análisis Multivariable", className="mb-3"),
                                html.P("Exploración de correlaciones entre múltiples métricas energéticas del Portal XM.", className="text-muted"),
                                html.Hr(),
                                dbc.Button("Próximamente", color="secondary", disabled=True, className="w-100")
                            ])
                        ], className="h-100")
                    ], md=6),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6("📊 Métricas Personalizadas", className="mb-3"),
                                html.P("Creación de indicadores energéticos específicos para análisis personalizado.", className="text-muted"),
                                html.Hr(),
                                dbc.Button("Próximamente", color="secondary", disabled=True, className="w-100")
                            ])
                        ], className="h-100")
                    ], md=6)
                ])
            ])
        ], className="shadow-sm"),
        html.Div(id="metricas-results-content-exploracion", className="mt-4")
    ])

def crear_exploracion_simem():
    """Crea el panel de exploración avanzada para métricas SIMEM"""
    return html.Div([
        dbc.Card([
            dbc.CardBody([
                html.H4([
                    html.I(className="fas fa-search-plus me-2", style={"color": COLORS['primary']}),
                    "Exploración Avanzada SIMEM"
                ], className="mb-4"),
                
                dbc.Alert([
                    html.I(className="fas fa-flask me-2"),
                    html.Strong("Análisis avanzado de variables SIMEM. "),
                    "Herramientas para exploración profunda del Sistema de Información del Mercado Eléctrico."
                ], color="info", className="mb-4"),
                
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6([
                                    html.I(className="fas fa-project-diagram me-2"),
                                    "Correlaciones SIMEM"
                                ], className="mb-3"),
                                html.P("Matriz de correlaciones entre variables del SIMEM para identificar relaciones.", 
                                      className="text-muted mb-3"),
                                dbc.Button([
                                    html.I(className="fas fa-chart-scatter me-2"),
                                    "Analizar Correlaciones"
                                ], color="primary", className="w-100", disabled=True)
                            ])
                        ], className="h-100 shadow-sm")
                    ], md=4),
                    
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6([
                                    html.I(className="fas fa-cube me-2"),
                                    "Análisis por Dimensiones"
                                ], className="mb-3"),
                                html.P("Exploración de variables SIMEM filtradas por planta, agente, región.", 
                                      className="text-muted mb-3"),
                                dbc.Button([
                                    html.I(className="fas fa-filter me-2"),
                                    "Filtrar por Dimensión"
                                ], color="primary", className="w-100", disabled=True)
                            ])
                        ], className="h-100 shadow-sm")
                    ], md=4),
                    
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6([
                                    html.I(className="fas fa-code-branch me-2"),
                                    "Comparación de Versiones"
                                ], className="mb-3"),
                                html.P("Compara diferentes versiones SIMEM para detectar variaciones en los datos.", 
                                      className="text-muted mb-3"),
                                dbc.Button([
                                    html.I(className="fas fa-exchange-alt me-2"),
                                    "Comparar Versiones"
                                ], color="primary", className="w-100", disabled=True)
                            ])
                        ], className="h-100 shadow-sm")
                    ], md=4)
                ])
            ])
        ], className="shadow-sm")
    ])

# Callbacks originales para funcionalidad (actualizando IDs)

# Callback para actualizar las opciones de entidad según la métrica seleccionada
@callback(
    [Output("entity-dropdown", "options"),
     Output("entity-dropdown", "value")],
    [Input("metric-dropdown", "value")]
)
def update_entity_options(selected_metric):
    if not selected_metric or todas_las_metricas.empty:
        return [], None
    
    # Filtrar las entidades disponibles para la métrica seleccionada
    metric_data = todas_las_metricas[todas_las_metricas['MetricId'] == selected_metric]
    
    if metric_data.empty:
        return [], None
    
    # Obtener las entidades únicas para esta métrica
    available_entities = metric_data['Entity'].dropna().unique()
    
    entity_options = [
        {"label": entity, "value": entity}
        for entity in available_entities
    ]
    
    # Ordenar las entidades alfabéticamente
    entity_options = sorted(entity_options, key=lambda x: x['label'])
    
    # Seleccionar automáticamente la primera entidad disponible (después del ordenamiento)
    default_value = entity_options[0]["value"] if len(entity_options) > 0 else None
    
    return entity_options, default_value

# Callback para mostrar información de la métrica seleccionada (actualizado para nuevo layout)
@callback(
    Output("metricas-results-content", "children"),
    [Input("query-button", "n_clicks")],
    [dash.dependencies.State("metric-dropdown", "value"),
     dash.dependencies.State("entity-dropdown", "value"),
     dash.dependencies.State("date-picker-range", "start_date"),
     dash.dependencies.State("date-picker-range", "end_date")]
)
def display_metric_results(n_clicks, selected_metric, selected_entity, start_date, end_date):
    """
    Callback principal para consultar y mostrar métricas XM.
    
    Incluye validación de parámetros y manejo robusto de errores.
    """
    # Validaciones iniciales
    if not n_clicks or not selected_metric:
        logger.debug("Callback terminado - falta métrica o no hay clicks")
        return dbc.Alert(
            "👆 Selecciona una métrica y haz clic en 'Consultar Datos Energéticos'", 
            color="info", 
            className="text-center"
        )
    
    if todas_las_metricas.empty:
        logger.warning("API XM no disponible o métricas no cargadas")
        return dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            html.Strong("Servicio XM no disponible: "),
            "No se pudieron cargar las métricas de XM. Verifica la conexión a internet y que la librería pydataxm esté correctamente instalada."
        ], color="warning")
    
    # Validar métrica seleccionada
    try:
        selected_metric = validate_string(
            selected_metric, 
            min_length=3, 
            max_length=50,
            name="métrica"
        )
    except InvalidParameterError as e:
        logger.error(f"Métrica inválida: {e}")
        return dbc.Alert([
            html.I(className="fas fa-times-circle me-2"),
            html.Strong("Métrica inválida: "),
            str(e)
        ], color="danger")
    
    metric_data = todas_las_metricas[todas_las_metricas['MetricId'] == selected_metric]
    
    if metric_data.empty:
        logger.warning(f"Métrica no encontrada: {selected_metric}")
        return dbc.Alert(
            f"Métrica '{selected_metric}' no encontrada en el sistema.", 
            color="warning"
        )
    
    # Información básica de la métrica
    metric_name = metric_data.iloc[0]['MetricName']
    available_entities = metric_data['Entity'].dropna().unique()
    metric_type = metric_data.iloc[0].get('Type', 'N/A')
    max_days = metric_data.iloc[0].get('MaxDays', 'N/A')
    units = metric_data.iloc[0].get('MetricUnits', 'N/A')
    description = metric_data.iloc[0].get('MetricDescription', 'Sin descripción disponible')
    
    # Obtener información detallada y educativa completa
    info_detallada = obtener_info_metrica_completa(selected_metric)
    
    # Card simplificado con información específica y práctica
    info_card = dbc.Card([
        dbc.CardHeader([
            html.H5([
                html.I(className="fas fa-chart-line me-2", style={'color': COLORS['primary']}),
                f"{selected_metric} - {info_detallada['nombre']}"
            ], className="mb-0", style={'color': COLORS['text_primary'], 'fontWeight': '600'})
        ], style={'backgroundColor': '#F0F9FF', 'border': 'none'}),
        dbc.CardBody([
            # Información práctica esencial
            dbc.Row([
                dbc.Col([
                    html.H6("¿Qué es y para qué sirve?", style={'color': COLORS['text_primary'], 'fontWeight': '600'}),
                    html.P(info_detallada['descripcion_practica'], 
                          style={'color': COLORS['text_secondary'], 'fontSize': '1rem', 'lineHeight': '1.5'})
                ], md=12)
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    html.H6("Uso directo en el MME:", style={'color': COLORS['text_primary'], 'fontWeight': '600'}),
                    html.P(info_detallada['uso_directo'], 
                          style={'color': COLORS['text_secondary'], 'fontSize': '0.95rem'})
                ], md=8),
                dbc.Col([
                    html.H6("Unidad:", style={'color': COLORS['text_primary'], 'fontWeight': '600'}),
                    html.P(f"{info_detallada['unidad']} ({units})" if units != 'N/A' and units != info_detallada['unidad'] else info_detallada['unidad'], 
                          style={'color': COLORS['text_secondary'], 'fontSize': '0.95rem', 'fontWeight': '500'})
                ], md=4)
            ], className="mb-3"),
            
            dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2", style={'color': '#DC2626'}),
                html.Strong("Valores críticos: "),
                info_detallada['valor_critico']
            ], color="warning", className="mb-3"),
            
            # Información técnica XM y entidades disponibles
            html.Hr(),
            dbc.Row([
                dbc.Col([
                    html.H6("Descripción técnica XM:", style={'color': COLORS['text_primary'], 'fontSize': '0.9rem'}),
                    html.P(
                        info_detallada.get('descripcion_tecnica_xm', description), 
                        style={'color': COLORS['text_secondary'], 'fontSize': '0.85rem', 'fontStyle': 'italic'}
                    )
                ], md=8),
                dbc.Col([
                    html.H6(f"Entidades disponibles: {len(available_entities)}", 
                           style={'color': COLORS['text_primary'], 'fontSize': '0.9rem'}),
                    html.P(", ".join(available_entities[:5]) + ("..." if len(available_entities) > 5 else ""), 
                          style={'color': COLORS['text_secondary'], 'fontSize': '0.8rem'})
                ], md=4)
            ]),
            
            # Información adicional de categorización automática
            html.Hr(),
            dbc.Row([
                dbc.Col([
                    dbc.Badge(
                        f"📂 Categoría: {info_detallada.get('categoria', 'general').title()}", 
                        color="info", 
                        className="me-2"
                    ),
                    dbc.Badge(
                        f"🔧 Tipo: {metric_type}", 
                        color="secondary", 
                        className="me-2"
                    ),
                    dbc.Badge(
                        f"📅 Días máximos: {max_days}", 
                        color="light", 
                        text_color="dark"
                    )
                ], md=12)
            ])
        ])
    ], className="mb-4", style={'border': f'1px solid #DBEAFE', 'boxShadow': f'0 2px 4px {COLORS["shadow_md"]}'})
    
    
    # Si hay entidad y fechas seleccionadas, intentar consultar datos
    if selected_entity and start_date and end_date:
        try:
            # Validar entidad
            try:
                selected_entity = validate_string(
                    selected_entity, 
                    min_length=1, 
                    max_length=100,
                    name="entidad"
                )
            except InvalidParameterError as e:
                logger.error(f"Entidad inválida: {e}")
                return html.Div([
                    info_card,
                    dbc.Alert([
                        html.I(className="fas fa-times-circle me-2"),
                        html.Strong("Entidad inválida: "),
                        str(e)
                    ], color="danger", className="mt-3")
                ])
            
            # Validar rango de fechas
            try:
                # Obtener max_days de la métrica
                max_days_allowed = metric_data.iloc[0].get('MaxDays', 365)
                if max_days_allowed == 'N/A':
                    max_days_allowed = 365
                
                start_validated, end_validated = validate_date_range(
                    start_date, 
                    end_date, 
                    max_days=int(max_days_allowed)
                )
                logger.info(f"Fechas validadas", extra={
                    'inicio': start_validated,
                    'fin': end_validated,
                    'metrica': selected_metric,
                    'entidad': selected_entity
                })
            except DateRangeError as e:
                logger.error(f"Error en rango de fechas: {e}", extra=e.details if hasattr(e, 'details') else {})
                return html.Div([
                    info_card,
                    dbc.Alert([
                        html.I(className="fas fa-calendar-times me-2"),
                        html.Strong("Error en fechas: "),
                        str(e),
                        html.Hr(),
                        html.Small(f"💡 Consejo: Esta métrica permite un máximo de {max_days_allowed} días. Reduce el rango de fechas.")
                    ], color="danger", className="mt-3")
                ])
            
            # Realizar consulta a la API (via Servicio de Dominio)
            logger.info(f"Iniciando consulta de métrica", extra={
                'metrica': selected_metric,
                'entidad': selected_entity,
                'fecha_inicio': start_dt,
                'fecha_fin': end_dt
            })
            
            try:
                # Usar servicio de dominio que maneja la lógica de obtención (Híbrido: DB + API)
                data = metrics_service.get_metric_series_hybrid(selected_metric, selected_entity, start_dt, end_dt)
            except Exception as api_error:
                logger.error(f"Error en consulta de datos", extra={
                    'error': str(api_error),
                    'metrica': selected_metric,
                    'entidad': selected_entity
                })
                return html.Div([
                    info_card,
                    dbc.Alert([
                        html.I(className="fas fa-exclamation-triangle me-2"),
                        html.Strong("Error consultando datos: "),
                        str(api_error),
                        html.Hr(),
                        html.Small("💡 Verifica la conexión a internet y que los parámetros sean correctos.")
                    ], color="danger", className="mt-3")
                ])
            
            # Validación robusta de tipos para asegurar DataFrame (Evita: 'list' object has no attribute 'empty')
            if data is None:
                data = pd.DataFrame()
            elif isinstance(data, list):
                data = pd.DataFrame(data)
            elif not isinstance(data, pd.DataFrame):
                logger.warning(f"Tipo de datos inesperado en metricas: {type(data)}")
                data = pd.DataFrame()

            if not data.empty:
                logger.info(f"Datos obtenidos exitosamente", extra={
                    'registros': len(data),
                    'columnas': list(data.columns),
                    'metrica': selected_metric
                })
# REMOVED DEBUG:                 print(f"✅ Datos obtenidos: {len(data)} registros")
                
                # Crear explicación de las columnas de la tabla
                columnas_info = dbc.Card([
                    dbc.CardHeader([
                        html.H6([
                            html.I(className="fas fa-info-circle me-2"),
                            "Explicación de la Tabla de Datos"
                        ], className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.P([
                            html.Strong("Estructura de la tabla:"), 
                            " Cada fila representa un registro temporal de la métrica seleccionada."
                        ], className="mb-2"),
                        html.Ul([
                            html.Li([
                                html.Strong("Date: "), 
                                "Fecha y hora del registro en formato YYYY-MM-DD HH:MM:SS (UTC-5 Colombia)"
                            ]),
                            html.Li([
                                html.Strong("Values: "), 
                                f"Valor numérico de la métrica en {units if units != 'N/A' else 'unidades correspondientes'}"
                            ]),
                            html.Li([
                                html.Strong("Entity: "), 
                                f"Entidad o agente del mercado al que corresponde el dato ({selected_entity})"
                            ]),
                            html.Li([
                                html.Strong("MetricId: "), 
                                f"Código único de la métrica en el sistema XM ({selected_metric})"
                            ])
                        ], style={'fontSize': '0.9rem'}),
                        html.Hr(),
                        html.P([
                            html.Strong("Interpretación:"), 
                            f" Los valores mostrados representan {info_detallada['descripcion_practica'][:100]}... ",
                            html.Br(),
                            html.Strong("Frecuencia de datos:"), 
                            " La mayoría de métricas se reportan con frecuencia horaria o diaria según la naturaleza del dato."
                        ], style={'fontSize': '0.85rem', 'color': '#6B7280'})
                    ])
                ], className="mb-3")
                
                # Crear tabla de datos
                data_table = dbc.Card([
                    dbc.CardHeader([
                        html.H6([
                            html.I(className="fas fa-table me-2"),
                            f"Datos Consultados ({len(data)} registros)"
                        ], className="mb-0")
                    ]),
                    dbc.CardBody([
                        dash_table.DataTable(
                            data=data.head(100).to_dict('records'),  # Limitar para rendimiento
                            columns=[{"name": i, "id": i} for i in data.columns],
                            style_cell={
                                'textAlign': 'left',
                                'padding': '10px',
                                'fontFamily': 'Inter, Arial',
                                'fontSize': '12px',
                                'border': '1px solid #e5e7eb',
                                'color': '#1f2937'
                            },
                            style_header={
                                'backgroundColor': '#1e40af',
                                'color': 'white',
                                'fontWeight': 'bold',
                                'border': '1px solid #d3d3d3'
                            },
                            style_data={
                                'backgroundColor': 'rgba(248, 248, 248, 0.8)',
                                'color': '#1f2937',
                                'border': '1px solid #e5e7eb'
                            },
                            sort_action="native",
                            filter_action="native",
                            page_action="native",
                            page_current=0,
                            page_size=10,
                            export_format="xlsx",
                            export_headers="display"
                        )
                    ])
                ])
                
                return html.Div([info_card, columnas_info, data_table])
            else:
                logger.warning("No se encontraron datos en la consulta", extra={
                    'metrica': selected_metric,
                    'entidad': selected_entity,
                    'fecha_inicio': start_dt,
                    'fecha_fin': end_dt
                })
                no_data_alert = dbc.Alert([
                    html.I(className="fas fa-inbox me-2"),
                    html.Strong("No se encontraron datos"),
                    html.Hr(),
                    html.P([
                        "No hay registros disponibles para los parámetros seleccionados:",
                        html.Ul([
                            html.Li(f"Métrica: {selected_metric}"),
                            html.Li(f"Entidad: {selected_entity}"),
                            html.Li(f"Período: {start_dt} - {end_dt}")
                        ])
                    ]),
                    html.Small([
                        html.Strong("💡 Sugerencias:"),
                        html.Br(),
                        "• Intenta con un rango de fechas más amplio",
                        html.Br(),
                        "• Verifica que la entidad tenga datos para esta métrica",
                        html.Br(),
                        "• Consulta fechas más recientes (algunos datos históricos pueden no estar disponibles)"
                    ])
                ], color="warning", className="mt-3")
                return html.Div([info_card, no_data_alert])
                
        except (DateRangeError, InvalidParameterError) as validation_error:
            # Errores de validación ya fueron manejados arriba
            logger.error(f"Error de validación: {validation_error}")
            raise
        except Exception as e:
            logger.error(f"Error inesperado en consulta de datos", extra={
                'error': str(e),
                'tipo_error': type(e).__name__,
                'metrica': selected_metric,
                'entidad': selected_entity
            }, exc_info=True)
            
            error_alert = dbc.Alert([
                html.I(className="fas fa-bug me-2"),
                html.Strong("Error inesperado: "),
                str(e),
                html.Hr(),
                html.Small([
                    html.Strong("ℹ️ Información técnica:"),
                    html.Br(),
                    f"Tipo de error: {type(e).__name__}",
                    html.Br(),
                    "Este error ha sido registrado en los logs del sistema."
                ])
            ], color="danger", className="mt-3")
            return html.Div([info_card, error_alert])
    
    return info_card

# =============================================================================
# CALLBACKS PARA CONSULTAS SIMEM
# =============================================================================

@callback(
    Output("simem-results", "children"),
    Input("btn-consultar-simem", "n_clicks"),
    State("simem-variable-dropdown", "value"),
    State("simem-date-picker", "start_date"),
    State("simem-date-picker", "end_date"),
    prevent_initial_call=True
)
def consultar_variable_simem(n_clicks, variable, start_date, end_date):
    """
    Consulta datos de una variable SIMEM y genera visualizaciones
    """
    if not n_clicks or not variable:
        return dbc.Alert("Selecciona una variable y fecha para consultar", color="info")
    
    if not PYDATASIMEM_AVAILABLE:
        return dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            "El módulo pydatasimem no está disponible"
        ], color="danger")
    
    try:
        # Consultar datos SIMEM
        from pydataxm.pydatasimem import VariableSIMEM
        
        # Mostrar indicador de carga
        with logger.contextualize(variable=variable):
            logger.info(f"Consultando variable SIMEM: {variable}")
        
        # Realizar consulta
        datos = VariableSIMEM(
            variable=variable,
            start_date=start_date,
            end_date=end_date
        ).request_data()
        
        if datos is None or datos.empty:
            return dbc.Alert([
                html.I(className="fas fa-info-circle me-2"),
                f"No hay datos disponibles para {variable} en el período seleccionado"
            ], color="warning")
        
        logger.info(f"Datos SIMEM obtenidos: {len(datos)} registros")
        
        # Generar visualizaciones
        px, go = get_plotly_modules()
        
        # Card de información
        info_card = dbc.Card([
            dbc.CardHeader([
                html.H5([
                    html.I(className="fas fa-chart-line me-2", style={'color': COLORS['primary']}),
                    f"Variable SIMEM: {variable}"
                ], className="mb-0")
            ]),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-database me-2", style={'color': COLORS['info']}),
                            html.Strong("Registros: "),
                            html.Span(f"{len(datos):,}")
                        ], className="mb-2")
                    ], md=3),
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-columns me-2", style={'color': COLORS['success']}),
                            html.Strong("Columnas: "),
                            html.Span(f"{len(datos.columns)}")
                        ], className="mb-2")
                    ], md=3),
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-calendar me-2", style={'color': COLORS['warning']}),
                            html.Strong("Período: "),
                            html.Span(f"{start_date} - {end_date}")
                        ], className="mb-2")
                    ], md=6)
                ])
            ])
        ], className="mb-3 shadow-sm")
        
        # Identificar columna de valor principal
        valor_col = None
        for col in datos.columns:
            if variable.lower() in col.lower() and col not in ['Fecha', 'FechaHora', 'Version']:
                valor_col = col
                break
        
        if valor_col is None:
            # Intentar con columnas numéricas
            numeric_cols = datos.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                valor_col = numeric_cols[0]
        
        graficos = []
        
        if valor_col:
            # Preparar datos para gráfico
            df_plot = datos.copy()
            
            # Identificar columna de fecha
            fecha_col = None
            for col in ['FechaHora', 'Fecha', 'fecha', 'fechahora']:
                if col in df_plot.columns:
                    fecha_col = col
                    break
            
            if fecha_col:
                # Convertir a datetime si es necesario
                if not pd.api.types.is_datetime64_any_dtype(df_plot[fecha_col]):
                    df_plot[fecha_col] = pd.to_datetime(df_plot[fecha_col])
                
                # Gráfico de serie temporal
                fig_temporal = px.line(
                    df_plot,
                    x=fecha_col,
                    y=valor_col,
                    title=f"Serie Temporal - {variable}",
                    labels={fecha_col: 'Fecha', valor_col: variable}
                )
                fig_temporal.update_layout(
                    hovermode='x unified',
                    plot_bgcolor='white',
                    paper_bgcolor='white'
                )
                fig_temporal.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
                fig_temporal.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
                
                graficos.append(
                    dbc.Card([
                        dbc.CardBody([
                            dcc.Graph(figure=fig_temporal, config={'displayModeBar': True})
                        ])
                    ], className="mb-3 shadow-sm")
                )
                
                # Estadísticas
                stats_card = dbc.Card([
                    dbc.CardHeader([
                        html.H6([
                            html.I(className="fas fa-chart-bar me-2"),
                            "Estadísticas Descriptivas"
                        ], className="mb-0")
                    ]),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Strong("Media: "),
                                html.Span(f"{df_plot[valor_col].mean():.2f}")
                            ], md=3),
                            dbc.Col([
                                html.Strong("Mediana: "),
                                html.Span(f"{df_plot[valor_col].median():.2f}")
                            ], md=3),
                            dbc.Col([
                                html.Strong("Mín: "),
                                html.Span(f"{df_plot[valor_col].min():.2f}")
                            ], md=3),
                            dbc.Col([
                                html.Strong("Máx: "),
                                html.Span(f"{df_plot[valor_col].max():.2f}")
                            ], md=3)
                        ])
                    ])
                ], className="mb-3 shadow-sm")
                
                graficos.append(stats_card)
        
        # Tabla de datos
        tabla = dbc.Card([
            dbc.CardHeader([
                html.H6([
                    html.I(className="fas fa-table me-2"),
                    "Datos SIMEM (últimos 100 registros)"
                ], className="mb-0")
            ]),
            dbc.CardBody([
                dash_table.DataTable(
                    data=datos.tail(100).to_dict('records'),
                    columns=[{"name": col, "id": col} for col in datos.columns],
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'left', 'padding': '10px'},
                    style_header={'backgroundColor': COLORS['primary'], 'color': 'white', 'fontWeight': 'bold'},
                    page_size=20
                )
            ])
        ], className="mb-3 shadow-sm")
        
        return html.Div([info_card] + graficos + [tabla])
        
    except Exception as e:
        logger.error(f"Error consultando SIMEM: {e}", exc_info=True)
        return dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            html.Strong("Error al consultar SIMEM: "),
            html.Br(),
            str(e)
        ], color="danger")

@callback(
    Output("simem-multivariable-results", "children"),
    Input("btn-analisis-multivariable-simem", "n_clicks"),
    State("simem-multivariable-dropdown", "value"),
    State("simem-multivariable-dates", "start_date"),
    State("simem-multivariable-dates", "end_date"),
    prevent_initial_call=True
)
def analisis_multivariable_simem(n_clicks, variables, start_date, end_date):
    """
    Análisis multivariable de variables SIMEM con correlaciones
    """
    if not n_clicks or not variables or len(variables) < 2:
        return dbc.Alert([
            html.I(className="fas fa-info-circle me-2"),
            "Selecciona al menos 2 variables para análisis multivariable"
        ], color="info")
    
    if not PYDATASIMEM_AVAILABLE:
        return dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            "El módulo pydatasimem no está disponible"
        ], color="danger")
    
    try:
        from pydataxm.pydatasimem import VariableSIMEM
        
        logger.info(f"Análisis multivariable SIMEM: {len(variables)} variables")
        
        # Consultar cada variable
        datos_dict = {}
        for var in variables:
            try:
                datos = VariableSIMEM(
                    variable=var,
                    start_date=start_date,
                    end_date=end_date
                ).request_data()
                
                if datos is not None and not datos.empty:
                    datos_dict[var] = datos
                    logger.info(f"Variable {var}: {len(datos)} registros")
            except Exception as e:
                logger.warning(f"Error consultando {var}: {e}")
        
        if len(datos_dict) < 2:
            return dbc.Alert([
                html.I(className="fas fa-exclamation-circle me-2"),
                f"Solo se pudieron cargar {len(datos_dict)} variables. Se necesitan al menos 2."
            ], color="warning")
        
        # Combinar datos por fecha
        df_combined = None
        for var, datos in datos_dict.items():
            # Identificar columnas
            fecha_col = None
            for col in ['FechaHora', 'Fecha', 'fecha']:
                if col in datos.columns:
                    fecha_col = col
                    break
            
            if not fecha_col:
                continue
            
            # Buscar columna de valor
            valor_col = None
            for col in datos.columns:
                if var.lower() in col.lower() and col not in ['Fecha', 'FechaHora', 'Version']:
                    valor_col = col
                    break
            
            if not valor_col:
                numeric_cols = datos.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) > 0:
                    valor_col = numeric_cols[0]
            
            if valor_col:
                df_temp = datos[[fecha_col, valor_col]].copy()
                df_temp.columns = ['Fecha', var]
                df_temp['Fecha'] = pd.to_datetime(df_temp['Fecha'])
                
                if df_combined is None:
                    df_combined = df_temp
                else:
                    df_combined = pd.merge(df_combined, df_temp, on='Fecha', how='outer')
        
        if df_combined is None or len(df_combined.columns) < 3:
            return dbc.Alert("No se pudieron combinar los datos", color="danger")
        
        # Calcular correlaciones
        df_numeric = df_combined.drop('Fecha', axis=1)
        correlacion = df_numeric.corr()
        
        px, go = get_plotly_modules()
        
        # Matriz de correlación
        fig_corr = px.imshow(
            correlacion,
            labels=dict(x="Variable", y="Variable", color="Correlación"),
            x=correlacion.columns,
            y=correlacion.columns,
            color_continuous_scale='RdBu_r',
            zmin=-1, zmax=1,
            title="Matriz de Correlación - Variables SIMEM"
        )
        fig_corr.update_layout(height=500)
        
        # Series temporales
        fig_series = go.Figure()
        for col in df_numeric.columns:
            fig_series.add_trace(go.Scatter(
                x=df_combined['Fecha'],
                y=df_combined[col],
                mode='lines',
                name=col
            ))
        fig_series.update_layout(
            title="Series Temporales - Comparación",
            xaxis_title="Fecha",
            yaxis_title="Valor",
            hovermode='x unified',
            height=400
        )
        
        # Tabla de correlaciones
        corr_table = correlacion.round(3).reset_index()
        
        return html.Div([
            dbc.Alert([
                html.I(className="fas fa-check-circle me-2"),
                f"Análisis completado: {len(datos_dict)} variables, {len(df_combined)} registros"
            ], color="success", className="mb-3"),
            
            dbc.Card([
                dbc.CardHeader([
                    html.H6([
                        html.I(className="fas fa-project-diagram me-2"),
                        "Matriz de Correlación"
                    ], className="mb-0")
                ]),
                dbc.CardBody([
                    dcc.Graph(figure=fig_corr, config={'displayModeBar': True})
                ])
            ], className="mb-3 shadow-sm"),
            
            dbc.Card([
                dbc.CardHeader([
                    html.H6([
                        html.I(className="fas fa-chart-line me-2"),
                        "Series Temporales Comparadas"
                    ], className="mb-0")
                ]),
                dbc.CardBody([
                    dcc.Graph(figure=fig_series, config={'displayModeBar': True})
                ])
            ], className="mb-3 shadow-sm"),
            
            dbc.Card([
                dbc.CardHeader([
                    html.H6([
                        html.I(className="fas fa-table me-2"),
                        "Tabla de Correlaciones"
                    ], className="mb-0")
                ]),
                dbc.CardBody([
                    dash_table.DataTable(
                        data=corr_table.to_dict('records'),
                        columns=[{"name": col, "id": col} for col in corr_table.columns],
                        style_cell={'textAlign': 'center', 'padding': '10px'},
                        style_header={'backgroundColor': COLORS['primary'], 'color': 'white', 'fontWeight': 'bold'},
                        style_data_conditional=[
                            {
                                'if': {
                                    'filter_query': '{{{col}}} > 0.7 && {{{col}}} < 1'.format(col=col),
                                    'column_id': col
                                },
                                'backgroundColor': '#d4edda',
                                'color': '#155724'
                            } for col in corr_table.columns if col != 'index'
                        ]
                    )
                ])
            ], className="shadow-sm")
        ])
        
    except Exception as e:
        logger.error(f"Error en análisis multivariable SIMEM: {e}", exc_info=True)
        return dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            html.Strong("Error en análisis: "),
            html.Br(),
            str(e)
        ], color="danger")

# =============================================================================
# CALLBACKS PARA DESCARGAS DE REPORTES
# =============================================================================

# Función auxiliar para generar datos de muestra o usar datos reales
def obtener_datos_reporte():
    """Obtener datos para el reporte"""
    try:
        # Obtener metadatos desde servicio de dominio
        df_metadata = metrics_service.get_metrics_metadata()
        
        # Crear DataFrame con información de métricas
        if not df_metadata.empty:
            df_metricas = pd.DataFrame({
                'Métrica': df_metadata['MetricId'].head(50),  # Primeras 50 métricas
                'Nombre': df_metadata['MetricName'].head(50),
                'Entidad': df_metadata['Entity'].head(50),
                'Tipo': ['Energética'] * 50,
                'Estado': ['Disponible'] * 50,
                'Última_Actualización': [dt.datetime.now().strftime('%Y-%m-%d')] * 50
            })
        else:
            df_metricas = pd.DataFrame()
        
        return df_metricas if not df_metricas.empty else None
    except Exception as e:
        logger.error(f"Error creando tabla de métricas: {e}", exc_info=True)
        return None
    
    # Si no hay datos reales, retornar None
    return None

# Callback para descarga Excel
@callback(
    Output("download-metricas-excel", "data"),
    Input("download-excel-btn", "n_clicks"),
    prevent_initial_call=True
)
def download_excel_report(n_clicks):
    if n_clicks:
        df = obtener_datos_reporte()
        
        # Crear buffer para Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Métricas_Disponibles', index=False)
            
            # Agregar hoja de resumen
            resumen_df = pd.DataFrame({
                'Estadística': ['Total Métricas', 'Métricas Disponibles', 'Fecha Reporte'],
                'Valor': [len(df), len(df[df['Estado'] == 'Disponible']), dt.datetime.now().strftime('%Y-%m-%d %H:%M')]
            })
            resumen_df.to_excel(writer, sheet_name='Resumen', index=False)
        
        excel_data = output.getvalue()
        
        return dcc.send_bytes(
            excel_data,
            filename=f"reporte_metricas_energeticas_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        )
    return dash.no_update

# Callback para descarga CSV
@callback(
    Output("download-metricas-csv", "data"),
    Input("download-csv-btn", "n_clicks"),
    prevent_initial_call=True
)
def download_csv_report(n_clicks):
    if n_clicks:
        df = obtener_datos_reporte()
        
        return dcc.send_data_frame(
            df.to_csv,
            filename=f"reporte_metricas_energeticas_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            index=False
        )
    return dash.no_update

# Callback para descarga PDF (simulado como texto)
@callback(
    Output("download-metricas-pdf", "data"),
    Input("download-pdf-btn", "n_clicks"),
    prevent_initial_call=True
)
def download_pdf_report(n_clicks):
    if n_clicks:
        df = obtener_datos_reporte()
        
        # Crear contenido del reporte en texto
        reporte_texto = f"""
REPORTE DE MÉTRICAS ENERGÉTICAS XM
==========================================

Fecha de Generación: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total de Métricas: {len(df)}

MÉTRICAS DISPONIBLES:
"""
        
        for idx, row in df.iterrows():
            reporte_texto += "\n{idx+1}. {row.get('Métrica', 'N/A')} - {row.get('Tipo', 'N/A')} - {row.get('Estado', 'N/A')}"
        
        reporte_texto += f"""

RESUMEN ESTADÍSTICO:
- Métricas Disponibles: {len(df[df['Estado'] == 'Disponible']) if 'Estado' in df.columns else len(df)}
- Última Actualización: {dt.datetime.now().strftime('%Y-%m-%d')}

---
Generado por Dashboard MME - Sistema de Métricas Energéticas
"""
        
        return dict(
            content=reporte_texto,
            filename=f"reporte_metricas_energeticas_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        )
    return dash.no_update

# Callback para descarga completa (ZIP)
@callback(
    Output("download-metricas-zip", "data"),
    Input("download-all-btn", "n_clicks"),
    prevent_initial_call=True
)
def download_complete_report(n_clicks):
    if n_clicks:
        import zipfile
        
        df = obtener_datos_reporte()
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Agregar CSV
            csv_data = df.to_csv(index=False)
            zip_file.writestr("metricas_energeticas.csv", csv_data)
            
            # Agregar Excel
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Métricas', index=False)
            zip_file.writestr("metricas_energeticas.xlsx", excel_buffer.getvalue())
            
            # Agregar reporte de texto
            reporte_texto = f"""
REPORTE COMPLETO DE MÉTRICAS ENERGÉTICAS XM
==========================================

Fecha de Generación: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total de Métricas Analizadas: {len(df)}

Este paquete contiene:
1. metricas_energeticas.csv - Datos en formato CSV
2. metricas_energeticas.xlsx - Datos en formato Excel
3. reporte_completo.txt - Este reporte descriptivo

ANÁLISIS DETALLADO:
{df.to_string(index=False)}

---
Dashboard MME - Ministerio de Minas y Energía
Sistema de Análisis de Métricas Energéticas
"""
            zip_file.writestr("reporte_completo.txt", reporte_texto)
        
        zip_data = zip_buffer.getvalue()
        
        return dcc.send_bytes(
            zip_data,
            filename=f"reporte_completo_metricas_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.zip"
        )

# ============================================
# CALLBACK: Análisis Multivariado por Sección
# ============================================
@callback(
    Output("analisis-seccion-container", "children"),
    Input({"type": "btn-analizar-seccion", "index": dash.ALL}, "n_clicks"),
    State({"type": "btn-analizar-seccion", "index": dash.ALL}, "id"),
    prevent_initial_call=True
)
def analizar_seccion_multivariado(n_clicks, ids):
    """Realizar análisis multivariado de métricas de una sección"""
    if not any(n_clicks):
        return html.Div()
    
    # Identificar qué botón fue clickeado
    ctx = dash.callback_context
    if not ctx.triggered:
        return html.Div()
    
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    import json
    button_id = json.loads(triggered_id)
    seccion = button_id["index"]
    
    if seccion not in METRICAS_POR_SECCION:
        return dbc.Alert("Sección no encontrada", color="danger")
    
    info_seccion = METRICAS_POR_SECCION[seccion]
    metricas = info_seccion['metricas']
    
    # Consultar datos de la base de datos (Refactorizado con MetricsService)
    try:
        # Inicializar servicio de métricas
        metrics_service = MetricsService()
        
        # Obtener últimos 90 días de datos
        fecha_fin = datetime.now()
        fecha_inicio = fecha_fin - timedelta(days=90)
        
        # Limitar a 10 métricas para rendimiento
        metrics_to_query = metricas[:10]
        
        # Usar el servicio optimizado en lugar del loop SQL
        logger.info(f"Consultando métricas: {metrics_to_query}")
        df_combined = metrics_service.get_multiple_metrics_history(
            metrics_list=metrics_to_query,
            start_date=fecha_inicio.strftime('%Y-%m-%d'),
            end_date=fecha_fin.strftime('%Y-%m-%d')
        )

        if df_combined is None or df_combined.empty:
            return dbc.Alert([
                html.I(className="fas fa-exclamation-triangle me-2"),
                f"No hay datos disponibles en la base de datos para las métricas de '{seccion}'. ",
                "Estas métricas están disponibles en la API de XM pero aún no han sido cargadas al sistema."
            ], color="warning")
        
        metricas_disponibles = df_combined['metrica'].unique().tolist()
        
        # Pivotar para análisis multivariado
        df_pivot = df_combined.pivot_table(
            index='fecha',
            columns='metrica',
            values='valor',
            aggfunc='mean'
        ).reset_index()
        
        # Eliminar columnas con muchos NaN
        df_pivot = df_pivot.dropna(thresh=len(df_pivot)*0.5, axis=1)
        df_pivot = df_pivot.fillna(method='ffill').fillna(method='bfill')
        
        # Crear visualizaciones
        return crear_visualizaciones_multivariadas(df_pivot, seccion, info_seccion, metricas_disponibles)
        
    except Exception as e:
        logger.error(f"Error en análisis multivariado: {e}")
        return dbc.Alert(f"Error al procesar datos: {str(e)}", color="danger")

def crear_visualizaciones_multivariadas(df, seccion, info_seccion, metricas_disponibles):
    """Crear visualizaciones de análisis multivariado"""
    px, go = get_plotly_modules()
    
    # Preparar datos para correlación
    df_numeric = df.select_dtypes(include=[float, int])
    
    if df_numeric.shape[1] < 2:
        return dbc.Alert("Se necesitan al menos 2 métricas con datos para análisis multivariado", color="warning")
    
    # 1. Matriz de correlación
    corr_matrix = df_numeric.corr()
    
    fig_corr = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns,
        y=corr_matrix.columns,
        colorscale='RdBu',
        zmid=0,
        text=corr_matrix.values,
        texttemplate='%{text:.2f}',
        textfont={"size": 10},
        colorbar=dict(title="Correlación")
    ))
    
    fig_corr.update_layout(
        title=f"Matriz de Correlación - {seccion}",
        height=500,
        xaxis={'side': 'bottom'},
        yaxis={'side': 'left'}
    )
    
    # 2. Scatter matrix (pairplot style)
    fig_scatter = px.scatter_matrix(
        df_numeric,
        dimensions=df_numeric.columns[:min(5, len(df_numeric.columns))],
        title=f"Análisis Multivariado - {seccion}",
        height=700
    )
    
    fig_scatter.update_traces(diagonal_visible=False, showupperhalf=False)
    
    # 3. Series temporales superpuestas (normalizadas)
    df_normalized = df.copy()
    for col in df_numeric.columns:
        if col in df_normalized.columns:
            min_val = df_normalized[col].min()
            max_val = df_normalized[col].max()
            if max_val > min_val:
                df_normalized[col] = (df_normalized[col] - min_val) / (max_val - min_val)
    
    fig_series = go.Figure()
    for col in df_numeric.columns:
        if col in df_normalized.columns:
            fig_series.add_trace(go.Scatter(
                x=df['fecha'] if 'fecha' in df.columns else df.index,
                y=df_normalized[col],
                mode='lines',
                name=col,
                line=dict(width=2)
            ))
    
    fig_series.update_layout(
        title=f"Series Temporales Normalizadas - {seccion}",
        xaxis_title="Fecha",
        yaxis_title="Valor Normalizado (0-1)",
        height=400,
        hovermode='x unified'
    )
    
    # Layout del análisis
    return html.Div([
        dbc.Card([
            dbc.CardHeader([
                html.H4([
                    html.I(className=f"fas {info_seccion['icon']} me-2", style={'color': info_seccion['color']}),
                    f"Análisis Multivariado: {seccion}"
                ], className="mb-0")
            ], style={'backgroundColor': f"{info_seccion['color']}15"}),
            dbc.CardBody([
                dbc.Alert([
                    html.I(className="fas fa-chart-line me-2"),
                    html.Strong(f"Métricas analizadas: "),
                    f"{', '.join(metricas_disponibles)}"
                ], color="info", className="mb-3"),
                
                # Estadísticas básicas
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6("Métricas Disponibles", className="text-muted"),
                                html.H3(len(metricas_disponibles), className="mb-0", style={'color': info_seccion['color']})
                            ])
                        ], className="text-center mb-3")
                    ], md=3),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6("Registros Analizados", className="text-muted"),
                                html.H3(len(df), className="mb-0", style={'color': info_seccion['color']})
                            ])
                        ], className="text-center mb-3")
                    ], md=3),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6("Correlación Promedio", className="text-muted"),
                                html.H3(f"{corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean():.2f}",
                                       className="mb-0", style={'color': info_seccion['color']})
                            ])
                        ], className="text-center mb-3")
                    ], md=3),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H6("Período de Datos", className="text-muted"),
                                html.H3("90 días", className="mb-0", style={'color': info_seccion['color']})
                            ])
                        ], className="text-center mb-3")
                    ], md=3)
                ], className="mb-4"),
                
                # Tabs para diferentes visualizaciones
                dbc.Tabs([
                    dbc.Tab([
                        dcc.Graph(figure=fig_corr, config={'displayModeBar': True})
                    ], label="🔥 Matriz de Correlación"),
                    
                    dbc.Tab([
                        dcc.Graph(figure=fig_scatter, config={'displayModeBar': True})
                    ], label="📊 Análisis Bivariado"),
                    
                    dbc.Tab([
                        dcc.Graph(figure=fig_series, config={'displayModeBar': True})
                    ], label="📈 Series Temporales"),
                    
                    dbc.Tab([
                        crear_tabla_correlaciones(corr_matrix, metricas_disponibles)
                    ], label="📋 Tabla de Correlaciones")
                ])
            ])
        ], className="mb-4", style={'border': f'2px solid {info_seccion["color"]}'}),
        
        dbc.Button([
            html.I(className="fas fa-arrow-left me-2"),
            "Volver a Secciones"
        ], id="btn-volver-secciones", color="secondary", outline=True, className="mb-4")
    ])

def crear_tabla_correlaciones(corr_matrix, metricas):
    """Crear tabla con las correlaciones más fuertes"""
    # Extraer correlaciones (sin diagonal)
    correlaciones = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i+1, len(corr_matrix.columns)):
            correlaciones.append({
                'Métrica 1': corr_matrix.columns[i],
                'Métrica 2': corr_matrix.columns[j],
                'Correlación': corr_matrix.iloc[i, j],
                'Abs': abs(corr_matrix.iloc[i, j])
            })
    
    df_corr = pd.DataFrame(correlaciones).sort_values('Abs', ascending=False)
    
    return html.Div([
        html.H5("Correlaciones más Fuertes", className="mb-3"),
        dbc.Table.from_dataframe(
            df_corr[['Métrica 1', 'Métrica 2', 'Correlación']].head(20),
            striped=True,
            bordered=True,
            hover=True,
            responsive=True,
            style={'fontSize': '0.9em'}
        )
    ])

@callback(
    Output("analisis-seccion-container", "children", allow_duplicate=True),
    Input("btn-volver-secciones", "n_clicks"),
    prevent_initial_call=True
)
def volver_secciones(n_clicks):
    """Limpiar análisis y volver a vista de secciones"""
    if n_clicks:
        return html.Div()
    return dash.no_update
    return dash.no_update
