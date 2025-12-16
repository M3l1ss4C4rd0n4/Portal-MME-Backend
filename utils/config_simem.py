"""
Configuración de métricas SIMEM para integración en el Dashboard MME

Total de métricas configuradas: 214
Categorías: 11 (Generación, Demanda, Disponibilidad, Precios, Intercambios, 
             Hidrología, Combustibles, Meteorológicas, Contratos, Control, Transmisión)
"""

# =============================================================================
# MÉTRICAS SIMEM ORGANIZADAS POR CATEGORÍA
# =============================================================================

METRICAS_SIMEM_POR_CATEGORIA = {
    '⚡ Generación': {
        'icon': 'fa-bolt',
        'color': '#FFD700',
        'metricas': {
            'GIdeal': 'Generación ideal total',
            'GReal': 'Generación real',
            'GProg': 'Generación programada',
            'GProgDespacho': 'Generación programada despacho unidad',
            'GProgRedespacho': 'Generación programada redespacho unidad',
            'GIdealNal': 'Generación ideal nacional',
            'GIdealInt': 'Generación ideal internacional (Venezuela)',
            'GIdealTie': 'Generación ideal internacional (Ecuador)',
            'GeneracionSeg': 'Magnitud de generación de seguridad',
            'GeneracionRealEstimada': 'Generación real estimada',
            'ENFICCVerificada': 'ENFICC verificada',
            'CapEfectivaNeta': 'Capacidad efectiva neta'
        },
        'descripcion': 'Métricas de producción de energía del SIMEM'
    },
    
    '📊 Demanda': {
        'icon': 'fa-chart-line',
        'color': '#4169E1',
        'metricas': {
            'DdaReal': 'Demanda real',
            'DdaCom': 'Demanda comercial',
            'DdaRealRegulada': 'Demanda real regulada',
            'DdaRealNoRegulada': 'Demanda real NO regulada',
            'DdaRealOR': 'Demanda real operadores red',
            'DemandaComercialNacional': 'Demanda comercial nacional',
            'DemandaComercialInternacional': 'Demanda comercial internacional',
            'DemandaComercialTie': 'Demanda comercial TIE',
            'DemandaUPME': 'Demanda total proyectada por la UPME',
            'EnergiaNoAtendida': 'Demanda no atendida',
            'DdaDesconecVoluntariaVerif': 'Demanda desconectable voluntaria verificada'
        },
        'descripcion': 'Métricas de consumo eléctrico del SIMEM'
    },
    
    '⚡ Disponibilidad': {
        'icon': 'fa-tower-broadcast',
        'color': '#FF6347',
        'metricas': {
            'DispReal': 'Disponibilidad real',
            'DispCom': 'Disponibilidad comercial por cada recurso de generación',
            'DispDeclarada': 'Disponibilidad declarada',
            'DispProg': 'Disponibilidad programada',
            'DispComAnilloRespTotal': 'Disponibilidad comercial contratos respaldo'
        },
        'descripcion': 'Disponibilidad de recursos de generación'
    },
    
    '💰 Precios y Costos': {
        'icon': 'fa-dollar-sign',
        'color': '#32CD32',
        'metricas': {
            'CostoMarginalDespacho': 'Costo marginal del despacho',
            'CostoMarginalRedespacho': 'Costo marginal redespacho',
            'CEE': 'Costo equivalente de energia',
            'CERE': 'Costo equivalente real de energia',
            'COM_PE': 'Costo de operación y mantenimiento para el precio de escasez',
            'COM_PME': 'Costo de operación y mantenimiento para el precio marginal de escasez',
            'CUCargoConfi_USD': 'Costo unitario del cargo por confiabilidad',
            'MargenDePrecioSubastaRV': 'Margen de precio resultante de la SRCFV'
        },
        'descripcion': 'Precios y costos del mercado eléctrico'
    },
    
    '🌍 Intercambios Internacionales': {
        'icon': 'fa-globe',
        'color': '#1E90FF',
        'metricas': {
            'EnergiaImportadaRealEstimada': 'Energía importada real estimada',
            'EnergiaExportadaRealEstimada': 'Energía exportada real estimada',
            'EnergiaImportadaProgramadaRedespacho': 'Energía importada programada redespacho',
            'EnergiaExportadaProgramadaRedespacho': 'Energía exportada programada redespacho',
            'DdaRealInternacional': 'Demanda real internacional',
            'DeltaInt': 'Delta incremento internacional',
            'DeltaNal': 'Delta incremento nacional'
        },
        'descripcion': 'Importaciones y exportaciones de energía'
    },
    
    '💧 Hidrología': {
        'icon': 'fa-water',
        'color': '#4682B4',
        'metricas': {
            'AportesHidricosEnergia': 'Aportes hídricos de las series hidrológicas expresados en energía',
            'AportesHidricosMasa': 'Aportes hídricos de las series hidrológicas',
            'AportesHidricosMasaPSS95': 'Aportes hídricos para un 95% de Probabilidad de Ser Superado (PSS)',
            'CapacidadUtilMasa': 'Capacidad útil del embalse',
            'MediaHistoricaEnergia': 'Aporte promedio mensual multianual en energía',
            'MediaHistoricaMasa': 'Aporte promedio mensual multianual'
        },
        'descripcion': 'Aportes y capacidades de embalses'
    },
    
    '🔥 Combustibles': {
        'icon': 'fa-fire',
        'color': '#FF8C00',
        'metricas': {
            'ConsumoCombustible': 'Consumo de combustible',
            'ConsumoCombustibleFueraMerito': 'Consumo combustible proporcional a la reconciliación positiva',
            'CostoCombustibleReportado': 'Costo de suministro combustible',
            'CostoReferenciaCombustible': 'Costo referencia por tipo combustible'
        },
        'descripcion': 'Consumo y costos de combustibles'
    },
    
    '🌤️ Variables Meteorológicas': {
        'icon': 'fa-cloud-sun',
        'color': '#87CEEB',
        'metricas': {
            'HumedadRelativa': 'Humedad relativa',
            'DireccionViento': 'Dirección del viento',
            'VelocidadViento': 'Velocidad del viento'
        },
        'descripcion': 'Condiciones meteorológicas para generación renovable'
    },
    
    '💼 Contratos y Transacciones': {
        'icon': 'fa-handshake',
        'color': '#20B2AA',
        'metricas': {
            'DespachoTotalContratoLPCompra': 'Cantidad de compra despachada en contratos de largo plazo',
            'DespachoTotalContratoLPVenta': 'Cantidad de venta despachada en contratos de largo plazo',
            'CantidadVentasContratosSICEP': 'Cantidad ventas en contratos del SICEP',
            'MgCTB': 'Magnitud compras transacciones en bolsa',
            'Energia_Transada_Mecanismo': 'Representatividad de la energía transada'
        },
        'descripcion': 'Contratos y transacciones del mercado'
    },
    
    '⚙️ Control y Regulación': {
        'icon': 'fa-cogs',
        'color': '#708090',
        'metricas': {
            'MargenAGCAbajo': 'Banda AGC Abajo',
            'CU_ServAGC': 'Costo unitario por servicio regulación secundaria frecuencia',
            'CU_ResComAGC': 'Costo unitario responsabilidad comercial de AGC',
            'DeltaHOAbajo': 'Delta holgura abajo horaria',
            'DeltaHOArriba': 'Delta holgura arriba horaria'
        },
        'descripcion': 'Control automático de generación y regulación de frecuencia'
    },
    
    '⚡ Transmisión': {
        'icon': 'fa-tower-broadcast',
        'color': '#FF6347',
        'metricas': {
            # Infraestructura y Flujos de Red
            'EnergiaReferSTNnacional': 'Energías originales fronteras generación',
            'EnergiaReferSTNInternacional': 'Energía horaria contadores STN',
            'DdaRealOR': 'Demanda real operadores red',
            'EnergiaExportadaProgramadaRedespacho': 'Energía exportada programada redespacho',
            'EnergiaImportadaProgramadaRedespacho': 'Energía importada programada redespacho',
            'EnergiaExportadaRealEstimada': 'Energía exportada real estimada',
            'EnergiaImportadaRealEstimada': 'Energía importada real estimada',
            'CostoMarginalRedespacho': 'Costo marginal redespacho',
            'GProgRedespacho': 'Generación programada redespacho unidad',
            'GProgGrupoRedespacho': 'Generación programada grupo redespacho',
            'Vlr_Rest_conAlivio': 'Valor restricciones sistema con alivios',
            'PorcDistribucionSaldoNetoTIE_Merito': 'Porcentaje distribución saldo neto TIE mérito',
            'PorcDistribucionSaldoNetoTIE_FueraMerito': 'Porcentaje distribución saldo neto TIE fuera mérito',
            'PONE_ExpCol': 'Precio exportación nodo frontera',
            # Cargos por Uso de Redes
            'CargoMonomio': 'Cargos por uso',
            'CUCargoConfi_USD': 'Costo unitario cargo confiabilidad',
            'PMaximoCargoConfi': 'Precio máximo cargo confiabilidad',
            'PPromPonCargoConfi': 'Precio promedio cargo confiabilidad',
            'Vlr_Recaudar_OEFV_alMrgPSubastaReconfigur_TG_TRG': 'Valor cargo OEFV por PCC',
            'Vlr_Recaudar_OEFV_alPPromPonCargoConfi_TG_TRGC': 'Valor cargo OEFV por margen PCC',
            'Vlr_Recaudar_OEFV_Cargo': 'Valor cargo recurso OEFV'
        },
        'descripcion': 'Sistema de Transmisión Nacional (STN), flujos energéticos en redes, redespacho y cargos por uso'
    }
}

# =============================================================================
# MÉTRICAS SIMEM CRÍTICAS PARA EL MME
# =============================================================================

METRICAS_SIMEM_CRITICAS = {
    'GReal': {
        'nombre': 'Generación Real SIMEM',
        'descripcion': 'Energía efectivamente producida por todas las plantas generadoras registrada en el SIMEM',
        'unidad': 'MWh',
        'frecuencia': 'Horaria',
        'criticidad': 'Alta',
        'aplicaciones': ['Monitoreo operativo en tiempo real', 'Validación de datos de despacho', 'Auditoría de generación']
    },
    'DdaReal': {
        'nombre': 'Demanda Real SIMEM',
        'descripcion': 'Consumo total de energía del SIN registrado en el SIMEM',
        'unidad': 'MWh',
        'frecuencia': 'Horaria',
        'criticidad': 'Alta',
        'aplicaciones': ['Monitoreo de consumo', 'Detección de anomalías', 'Planificación operativa']
    },
    'CostoMarginalDespacho': {
        'nombre': 'Costo Marginal del Despacho',
        'descripcion': 'Costo marginal del sistema eléctrico determinado por el modelo de despacho',
        'unidad': '$/kWh',
        'frecuencia': 'Horaria',
        'criticidad': 'Alta',
        'aplicaciones': ['Formación de precios', 'Señales económicas', 'Evaluación de eficiencia del mercado']
    },
    'DispReal': {
        'nombre': 'Disponibilidad Real',
        'descripcion': 'Capacidad real de generación disponible considerando fallas y mantenimientos',
        'unidad': 'MW',
        'frecuencia': 'Horaria',
        'criticidad': 'Alta',
        'aplicaciones': ['Monitoreo de confiabilidad', 'Gestión de reservas', 'Planificación de mantenimientos']
    }
}

# =============================================================================
# MAPEO DE DIMENSIONES COMUNES EN SIMEM
# =============================================================================

DIMENSIONES_SIMEM = {
    'CodigoPlanta': 'Código de la planta de generación',
    'CodigoAgente': 'Código del agente del mercado',
    'Version': 'Versión del archivo SIMEM',
    'FechaHora': 'Fecha y hora del registro',
    'Fecha': 'Fecha del registro',
    'CodigoEmbalse': 'Código del embalse',
    'CodigoSerieHidrologica': 'Código de la serie hidrológica',
    'RegionHidrologica': 'Región hidrológica',
    'CodigoAreaOperativa': 'Área operativa del sistema',
    'CodigoSubAreaOperativa': 'Sub-área operativa del sistema'
}

# =============================================================================
# FUNCIÓN PARA OBTENER TODAS LAS VARIABLES SIMEM
# =============================================================================

def obtener_listado_simem():
    """
    Obtiene el listado completo de variables disponibles en SIMEM
    
    Returns:
        DataFrame con CodigoVariable, Nombre y Dimensiones
    """
    try:
        from pydataxm.pydatasimem import VariableSIMEM
        return VariableSIMEM.get_collection()
    except Exception as e:
        print(f"Error obteniendo listado SIMEM: {e}")
        return None

def obtener_metricas_simem_por_categoria(categoria):
    """
    Obtiene las métricas SIMEM de una categoría específica
    
    Args:
        categoria: Nombre de la categoría (ej: '⚡ Generación')
        
    Returns:
        Dict con las métricas de la categoría o None si no existe
    """
    return METRICAS_SIMEM_POR_CATEGORIA.get(categoria, {}).get('metricas', {})
