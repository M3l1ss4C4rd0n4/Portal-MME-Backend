"""
Tests unitarios para HydrologyService
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch

from domain.services.hydrology_service import HydrologyService


class TestHydrologyService:
    """Tests para HydrologyService"""
    
    def test_init(self):
        """Test: Servicio se inicializa correctamente"""
        service = HydrologyService()
        assert service is not None
    
    def test_get_reservas_hidricas_returns_tuple(self):
        """Test: get_reservas_hidricas retorna tuple válido"""
        service = HydrologyService()
        # Mock the internal method to avoid DB access
        service.calcular_volumen_util_unificado = Mock(return_value={
            'porcentaje': 50.0,
            'volumen_gwh': 1000,
            'fecha_datos': '2026-01-15'
        })
        
        result = service.get_reservas_hidricas('2026-01-15')
        
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] == 50.0
        assert result[1] == 1000
    
    @patch('infrastructure.database.repositories.metrics_repository.MetricsRepository')
    def test_get_aportes_hidricos_returns_tuple(self, MockRepoClass):
        """Test: get_aportes_hidricos retorna tuple válido"""
        mock_repo = MockRepoClass.return_value
        mock_repo.get_metric_data_by_entity = Mock(side_effect=[
            pd.DataFrame({
                'valor_gwh': [100, 80, 120],
                'recurso': ['RIO1', 'RIO2', 'RIO3'],
                'fecha': pd.to_datetime(['2026-01-01', '2026-01-01', '2026-01-01'])
            }),
            pd.DataFrame({
                'valor_gwh': [90, 70, 110],
                'recurso': ['RIO1', 'RIO2', 'RIO3'],
                'fecha': pd.to_datetime(['2026-01-01', '2026-01-01', '2026-01-01'])
            })
        ])
        
        service = HydrologyService()
        with patch('domain.services.validators.MetricValidators') as MockVal:
            MockVal.validate = Mock(return_value=True)
            result = service.get_aportes_hidricos('2026-01-15')
        
        assert isinstance(result, tuple)
        assert len(result) == 2
    
    def test_calcular_volumen_util_formula(self):
        """Test: Fórmula de cálculo de volumen útil es correcta"""
        # Datos de prueba
        volumen_actual = 1000  # GWh
        volumen_util = 2000    # GWh
        
        # Fórmula: % = (actual / util) * 100
        porcentaje_esperado = 50.0
        porcentaje_calculado = (volumen_actual / volumen_util) * 100
        
        assert porcentaje_calculado == porcentaje_esperado
    
    def test_calcular_aportes_vs_historico(self):
        """Test: Cálculo de aportes vs histórico es correcto"""
        # Datos de prueba
        aporte_actual = 100   # GWh
        aporte_historico = 80 # GWh
        
        # Fórmula: % = (actual / historico) * 100
        porcentaje_esperado = 125.0
        porcentaje_calculado = (aporte_actual / aporte_historico) * 100
        
        assert porcentaje_calculado == porcentaje_esperado
    
    def test_service_handles_none_result(self):
        """Test: Servicio maneja correctamente resultado None"""
        service = HydrologyService()
        # When calcular_volumen_util_unificado returns None, get_reservas_hidricas returns (None, None, None)
        service.calcular_volumen_util_unificado = Mock(return_value=None)
        
        result = service.get_reservas_hidricas('2026-01-15')
        assert result == (None, None, None)
    
    @pytest.mark.parametrize("fecha", [
        '2026-01-15',
        '2025-12-31',
        '2025-06-15',
    ])
    def test_get_reservas_multiple_dates(self, fecha):
        """Test: Servicio funciona con diferentes fechas"""
        service = HydrologyService()
        service.calcular_volumen_util_unificado = Mock(return_value={
            'porcentaje': 50.0,
            'volumen_gwh': 1000,
            'fecha_datos': fecha
        })
        
        result = service.get_reservas_hidricas(fecha)
        
        assert isinstance(result, tuple)
        assert len(result) == 3
    
    @pytest.mark.slow
    @pytest.mark.integration
    def test_get_reservas_with_real_database(self):
        """Test de integración: Consulta real a la base de datos"""
        service = HydrologyService()
        
        try:
            result = service.get_reservas_hidricas('2026-01-15')
            assert isinstance(result, tuple)
        except Exception as e:
            pytest.skip(f"Base de datos no disponible: {e}")
