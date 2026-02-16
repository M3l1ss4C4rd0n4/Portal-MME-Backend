"""
Configuración de pytest y fixtures compartidas

Este archivo define fixtures reutilizables para todos los tests.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from typing import Generator

# ==================== DATABASE FIXTURES ====================

@pytest.fixture
def mock_db_manager() -> Mock:
    """Mock del DatabaseManager para tests sin DB real"""
    manager = Mock()
    manager.get_connection = Mock()
    manager.execute_query = Mock()
    manager.execute_dataframe = Mock()
    return manager


@pytest.fixture
def sample_metrics_df() -> pd.DataFrame:
    """DataFrame de ejemplo con métricas para testing"""
    fechas = pd.date_range(start='2026-01-01', end='2026-01-31', freq='D')
    return pd.DataFrame({
        'fecha': fechas,
        'metrica': ['Gene'] * len(fechas),
        'entidad': ['Total'] * len(fechas),
        'recurso': ['SISTEMA'] * len(fechas),
        'valor_gwh': [10000 + i * 100 for i in range(len(fechas))],
        'unidad': ['GWh'] * len(fechas)
    })


@pytest.fixture
def sample_hourly_df() -> pd.DataFrame:
    """DataFrame de ejemplo con datos horarios"""
    data = []
    for dia in range(1, 8):  # 7 días
        for hora in range(1, 25):  # 24 horas
            data.append({
                'fecha': datetime(2026, 1, dia),
                'metrica': 'Gene',
                'entidad': 'Total',
                'recurso': 'SISTEMA',
                'hora': hora,
                'valor_mwh': 400 + (hora * 10)
            })
    return pd.DataFrame(data)


@pytest.fixture
def sample_transmission_df() -> pd.DataFrame:
    """DataFrame de ejemplo con líneas de transmisión"""
    return pd.DataFrame({
        'linea': ['L001', 'L002', 'L003'],
        'tension_kv': [500, 230, 115],
        'longitud_km': [150.5, 89.3, 45.2],
        'operador': ['ISA', 'CELSIA', 'EPM'],
        'sistema': ['STN', 'STN', 'STR'],
        'origen': ['Bogotá', 'Medellín', 'Cali'],
        'destino': ['Medellín', 'Cali', 'Pereira']
    })


# ==================== REPOSITORY FIXTURES ====================

@pytest.fixture
def mock_metrics_repository() -> Mock:
    """Mock del MetricsRepository"""
    repo = Mock()
    repo.get_metric_data = Mock(return_value=pd.DataFrame({
        'fecha': pd.date_range('2026-01-01', periods=30),
        'valor_gwh': [10000] * 30
    }))
    repo.list_available_metrics = Mock(return_value=['Gene', 'DemaReal', 'DemaCome'])
    return repo


@pytest.fixture
def mock_transmission_repository() -> Mock:
    """Mock del TransmissionRepository"""
    repo = Mock()
    repo.get_transmission_lines = Mock(return_value=pd.DataFrame({
        'linea': ['L001', 'L002'],
        'tension_kv': [500, 230],
        'longitud_km': [150.5, 89.3]
    }))
    repo.get_summary_stats = Mock(return_value={
        'total_lines': 857,
        'total_km': 30946,
        'operators': 34
    })
    return repo


# ==================== SERVICE FIXTURES ====================

@pytest.fixture
def generation_service_with_mock(mock_metrics_repository):
    """GenerationService con repositorio mockeado"""
    from domain.services.generation_service import GenerationService
    return GenerationService(repository=mock_metrics_repository)


@pytest.fixture
def transmission_service_with_mock(mock_transmission_repository):
    """TransmissionService con repositorio mockeado"""
    from domain.services.transmission_service import TransmissionService
    return TransmissionService(repository=mock_transmission_repository)


# ==================== DATE FIXTURES ====================

@pytest.fixture
def date_range_january_2026() -> tuple:
    """Rango de fechas típico para tests"""
    return ('2026-01-01', '2026-01-31')


@pytest.fixture
def single_date_2026() -> str:
    """Fecha única para tests"""
    return '2026-01-15'


# ==================== CATALOG FIXTURES ====================

@pytest.fixture
def sample_catalogs_df() -> pd.DataFrame:
    """DataFrame de ejemplo con catálogos"""
    return pd.DataFrame({
        'catalogo': ['ListadoRecursos', 'ListadoRecursos', 'ListadoEmbalses'],
        'codigo': ['GUAVIO', 'TEQUENDAMA', 'GUAVIO'],
        'nombre': ['GUAVIO', 'TEQUENDAMA', 'Embalse Guavio'],
        'tipo': ['HIDRAULICA', 'HIDRAULICA', 'EMBALSE']
    })


# ==================== MARKER: SLOW TESTS ====================

def pytest_configure(config):
    """Configure custom pytest markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


# ==================== AUTO-USE FIXTURES ====================

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons entre tests para evitar estado compartido"""
    yield
    # Aquí se pueden resetear singletons si es necesario
    # Por ejemplo: DatabaseManager._instance = None


# ==================== PARAMETRIZE COMMON VALUES ====================

# Métricas comunes para parametrizar tests
COMMON_METRICS = ['Gene', 'DemaReal', 'DemaCome', 'DispoReal']

# Rangos de fechas comunes
COMMON_DATE_RANGES = [
    ('2026-01-01', '2026-01-31'),  # 1 mes
    ('2025-12-01', '2026-01-31'),  # 2 meses
    ('2025-01-01', '2026-01-31'),  # 1 año
]
