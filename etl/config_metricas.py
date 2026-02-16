"""
Configuración de Métricas para ETL
Portal Energético MME
"""

# Mapeo explícito de unidades por métrica (según documentación XM)
UNIDADES_POR_METRICA = {
    # Energía (GWh)
    'Gene': 'GWh',
    'DemaCome': 'GWh',
    'DemaReal': 'GWh',
    'DemaRealReg': 'GWh',
    'DemaRealNoReg': 'GWh',
    'AporEner': 'GWh',
    'AporEnerMediHist': 'GWh',
    'VoluUtilDiarEner': 'GWh',
    'CapaUtilDiarEner': 'GWh',
    'VertEner': 'GWh',
    'GeneIdea': 'GWh',
    'GeneProgDesp': 'GWh',
    'GeneFueraMerito': 'GWh',
    'ImpoEner': 'GWh',
    'ExpoEner': 'GWh',
    'PerdidasEner': 'GWh',
    'DemaNoAtenProg': 'GWh',
    'DemaNoAtenNoProg': 'GWh',
    'ENFICC': 'GWh',
    'ObligEnerFirme': 'GWh',
    'DDVContratada': 'GWh',
    
    # Potencia (MW)
    'DispoCome': 'MW',
    'DispoReal': 'MW',
    'DispoDeclarada': 'MW',
    'CapEfecNeta': 'MW',
    
    # Precios ($/kWh)
    'PrecBolsNaci': '$/kWh',
    'PrecBolsNaciTX1': '$/kWh',
    'PrecOferDesp': '$/kWh',
    'PrecOferIdeal': '$/kWh',
    'PrecEsca': '$/kWh',
    'PrecEscaAct': '$/kWh',
    'PrecEscaMarg': '$/kWh',
    'PrecEscaPon': '$/kWh',
    'CostMargDesp': '$/kWh',
    'PrecCargConf': '$/kWh',
    'PrecPromCont': '$/kWh',
    'MaxPrecOferNal': '$/kWh',
    
    # Caudales (m³/s)
    'AporCaudal': 'm³/s',
    'AporCaudalMediHist': 'm³/s',
    
    # Moneda (COP) - RESTRICCIONES, NO CONVERTIR A GWh
    'RestAliv': 'COP',
    'RestSinAliv': 'COP',
    'RentasCongestRestr': 'COP',
    
    # Masas (Hm³)
    'VolTurbMasa': 'Hm³',
    'VoluUtilDiarMasa': 'Hm³',
    'VertMasa': 'Hm³',
    'CapaUtilDiarMasa': 'Hm³',
    
    # Porcentajes (%)
    'PorcApor': '%',
    'PorcVoluUtilDiar': '%',
}

# Rangos de validación por métrica/entidad (min, max)
RANGOS_VALIDACION = {
    'DemaCome/Sistema': (150, 350),      # GWh/día
    'Gene/Sistema': (100, 400),          # GWh/día
    'AporEner/Sistema': (10, 800),       # GWh/día (muy variable)
    'DemaReal/Sistema': (150, 350),      # GWh/día
}

# Métricas a poblar en la base de datos
METRICAS_CONFIG = {
    # Indicadores principales página Generación
    'indicadores_generacion': [
        {
            'metric': 'VoluUtilDiarEner',
            'entity': 'Embalse',
            'conversion': 'kWh_a_GWh',  # API devuelve en kWh
            'dias_history': 1826,  # 5 años (2020-2025)
            'batch_size': 30  # 30 días por batch
        },
        {
            'metric': 'CapaUtilDiarEner',
            'entity': 'Embalse',
            'conversion': 'kWh_a_GWh',  # API devuelve en kWh
            'dias_history': 1826,  # 5 años (2020-2025)
            'batch_size': 30  # 30 días por batch
        },
        {
            'metric': 'AporEner',
            'entity': 'Sistema',
            'conversion': 'Wh_a_GWh',  # API devuelve en Wh
            'dias_history': 1826,  # 5 años (2020-2025)
            'batch_size': 30  # 30 días por batch
        },
        {
            'metric': 'AporEnerMediHist',
            'entity': 'Sistema',
            'conversion': 'Wh_a_GWh',  # API devuelve en Wh
            'dias_history': 1826,  # 5 años (2020-2025)
            'batch_size': 30  # 30 días por batch
        },
        {
            'metric': 'Gene',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Values_Hour* en kWh, sumar → GWh
            'dias_history': 1826,  # 5 años (2020-2025)
            'batch_size': 30  # 30 días por batch
        }
    ],
    
    # Generación por fuentes
    'generacion_fuentes': [
        {
            'metric': 'Gene',
            'entity': 'Recurso',
            'conversion': 'horas_a_diario',
            'dias_history': 1826,  # 5 años (2020-2025)
            'batch_size': 30  # 30 días por batch para 5 años
        }
    ],
    
    # Métricas de Hidrología
    'metricas_hidrologia': [
        {
            'metric': 'ListadoEmbalses',
            'entity': 'Sistema',
            'conversion': None,
            'dias_history': 2
        },
        {
            'metric': 'ListadoRios',
            'entity': 'Sistema',
            'conversion': None,
            'dias_history': 2
        },
        {
            'metric': 'AporEner',
            'entity': 'Rio',
            'conversion': 'Wh_a_GWh',
            'dias_history': 365,  # 1 año para análisis histórico
            'batch_size': 15  # 15 días por batch
        },
        {
            'metric': 'AporEnerMediHist',
            'entity': 'Rio',
            'conversion': 'Wh_a_GWh',
            'dias_history': 365,  # 1 año
            'batch_size': 15  # 15 días por batch
        },
        {
            'metric': 'AporCaudal',
            'entity': 'Rio',
            'conversion': None,  # Ya en m³/s
            'dias_history': 30,  # Aumentado de 7 a 30 días
            'batch_size': 10
        },
        {
            'metric': 'PorcApor',
            'entity': 'Rio',
            'conversion': None,  # Porcentajes
            'dias_history': 365,  # 1 año
            'batch_size': 15  # 15 días por batch
        }
    ],
    
    # Métricas de Distribución
    'metricas_distribucion': [
        {
            'metric': 'DemaCome',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',
            'dias_history': 1826,  # 5 años (igual que generación)
            'batch_size': 30
        },
        {
            'metric': 'DemaCome',
            'entity': 'Agente',
            'conversion': 'horas_a_diario',  # Values_Hour* en kWh, sumar → GWh
            'dias_history': 1826,  # 5 años (2020-2025) - ACTUALIZADO
            'batch_size': 7  # 7 días por batch (muchos agentes)
        },
        {
            'metric': 'DemaReal',
            'entity': 'Agente',
            'conversion': 'horas_a_diario',  # Values_Hour* en kWh, sumar → GWh
            'dias_history': 1826,  # 5 años (2020-2025) - ACTUALIZADO
            'batch_size': 7  # 7 días por batch (muchos agentes)
        },
        {
            'metric': 'DemaRealReg',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Values_Hour* en kWh, sumar → GWh
            'dias_history': 1826,  # 5 años
            'batch_size': 30
        },
        {
            'metric': 'DemaRealReg',
            'entity': 'Agente',
            'conversion': 'horas_a_diario',  # Values_Hour* en kWh, sumar → GWh
            'dias_history': 1826,  # 5 años
            'batch_size': 7
        },
        {
            'metric': 'DemaRealNoReg',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Values_Hour* en kWh, sumar → GWh
            'dias_history': 1826,  # 5 años
            'batch_size': 30
        },
        {
            'metric': 'DemaRealNoReg',
            'entity': 'Agente',
            'conversion': 'horas_a_diario',  # Values_Hour* en kWh, sumar → GWh
            'dias_history': 1826,  # 5 años
            'batch_size': 7
        },
        {
            'metric': 'DemaNoAtenProg',
            'entity': 'Area',
            'conversion': 'horas_a_diario',  # Suma 24 horas → GWh
            'dias_history': 30,
            'batch_size': 7
        },
        {
            'metric': 'DemaNoAtenNoProg',
            'entity': 'Area',
            'conversion': 'horas_a_diario',  # Suma 24 horas → GWh
            'dias_history': 30,
            'batch_size': 7
        }
    ],
    
    # Listados de sistema
    'listados_sistema': [
        {
            'metric': 'ListadoRecursos',
            'entity': 'Sistema',
            'conversion': None,
            'dias_history': 7
        },
        {
            'metric': 'ListadoAgentes',
            'entity': 'Sistema',
            'conversion': None,
            'dias_history': 7
        }
    ],

    # Métricas de Restricciones (NUEVO - Corregido 2026-01-30)
    'metricas_restricciones': [
        {
            'metric': 'RestAliv',
            'entity': 'Sistema',
            'conversion': 'sum_hours', # Suma horaria sin dividir
            'dias_history': 365,
            'batch_size': 30,
            'descripcion': 'Restricciones Aliviadas'
        },
        {
            'metric': 'RestSinAliv',
            'entity': 'Sistema',
            'conversion': 'sum_hours', # Suma horaria sin dividir
            'dias_history': 365,
            'batch_size': 30,
            'descripcion': 'Restricciones Sin Alivio'
        },
        {
            'metric': 'RespComerAGC',
            'entity': 'Sistema',
            'conversion': 'sum_hours', # Suma horaria sin dividir
            'dias_history': 365,
            'batch_size': 30,
            'descripcion': 'Responsabilidad Comercial AGC'
        }
    ],
    
    # Métricas de Pérdidas (NUEVO - Validado 2025-12-03)
    'metricas_perdidas': [
        {
            'metric': 'PerdidasEner',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Values_Hour* en MWh, sumar → GWh
            'dias_history': 1826,  # 5 años para análisis histórico
            'batch_size': 30,
            'descripcion': 'Pérdidas totales de energía del sistema'
        },
        {
            'metric': 'PerdidasEnerReg',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Values_Hour* en MWh, sumar → GWh
            'dias_history': 1826,  # 5 años
            'batch_size': 30,
            'descripcion': 'Pérdidas de energía regulada'
        },
        {
            'metric': 'PerdidasEnerNoReg',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Values_Hour* en MWh, sumar → GWh
            'dias_history': 1826,  # 5 años
            'batch_size': 30,
            'descripcion': 'Pérdidas de energía no regulada'
        }
    ],
    
    # Métricas de Disponibilidad - Transmisión (NUEVO - Validado 2025-12-03)
    'metricas_disponibilidad': [
        {
            'metric': 'DispoReal',
            'entity': 'Recurso',
            'conversion': 'horas_a_diario',  # Values_Hour01-24 en kW → Promedio diario MW
            'dias_history': 180,  # 6 meses (muchos recursos)
            'batch_size': 7,  # Batches pequeños (miles de registros)
            'descripcion': 'Disponibilidad real por recurso'
        },
        {
            'metric': 'DispoCome',
            'entity': 'Recurso',
            'conversion': 'horas_a_diario',  # Values_Hour01-24 en kW → Promedio diario MW
            'dias_history': 180,  # 6 meses
            'batch_size': 7,
            'descripcion': 'Disponibilidad comercial por recurso'
        },
        {
            'metric': 'DispoDeclarada',
            'entity': 'Recurso',
            'conversion': 'horas_a_diario',  # Values_Hour01-24 en kWh → Promedio diario MW
            'dias_history': 180,  # 6 meses
            'batch_size': 7,
            'descripcion': 'Disponibilidad declarada por recurso'
        }
    ],
    
    # Métricas de Restricciones (NUEVO - Validado 2025-12-03)
    'metricas_restricciones': [
        {
            'metric': 'RestAliv',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Suma horaria en $
            'dias_history': 365,  # 1 año para análisis costos
            'batch_size': 30,
            'descripcion': 'Restricciones aliviadas del sistema'
        },
        {
            'metric': 'RestSinAliv',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Suma horaria en $
            'dias_history': 365,  # 1 año
            'batch_size': 30,
            'descripcion': 'Restricciones sin alivios'
        },
        {
            'metric': 'GeneSeguridad',
            'entity': 'Recurso',
            'conversion': 'horas_a_diario',  # Suma horaria kWh → GWh
            'dias_history': 90,  # 3 meses (varios recursos)
            'batch_size': 15,
            'descripcion': 'Generación de seguridad por recurso'
        },
        {
            'metric': 'RespComerAGC',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Suma horaria en $
            'dias_history': 365,  # 1 año
            'batch_size': 30,
            'descripcion': 'Responsabilidad comercial AGC'
        }
    ],
    
    # Métricas de Mercado (NUEVO - Complementarias - Validado 2025-12-03)
    'metricas_mercado': [
        {
            'metric': 'PrecBolsNaci',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Promedio horario $/kWh
            'dias_history': 1826,  # 5 años para análisis histórico precios
            'batch_size': 30,
            'descripcion': 'Precio bolsa nacional'
        },
        {
            'metric': 'CostMargDesp',
            'entity': 'Sistema',
            'conversion': 'horas_a_diario',  # Promedio horario $/kWh
            'dias_history': 1826,  # 5 años
            'batch_size': 30,
            'descripcion': 'Costo marginal de despacho'
        },
        {
            'metric': 'PrecEscaAct',
            'entity': 'Sistema',
            'conversion': 'sin_conversion',  # Promedio diario en $/kWh
            'dias_history': 1826,  # 5 años (descontinuado desde marzo 2025)
            'batch_size': 30,
            'descripcion': 'Precio Escasez Activación (histórico hasta feb 2025)'
        },
        {
            'metric': 'PrecEscaSup',
            'entity': 'Sistema',
            'conversion': 'sin_conversion',  # Promedio diario en $/kWh
            'dias_history': 365,  # Desde marzo 2025
            'batch_size': 30,
            'descripcion': 'Precio Escasez Superior (desde marzo 2025)'
        },
        {
            'metric': 'PrecEscaInf',
            'entity': 'Sistema',
            'conversion': 'sin_conversion',  # Promedio diario en $/kWh
            'dias_history': 365,  # Desde marzo 2025
            'batch_size': 30,
            'descripcion': 'Precio Escasez Inferior (desde marzo 2025)'
        }
    ]
}
