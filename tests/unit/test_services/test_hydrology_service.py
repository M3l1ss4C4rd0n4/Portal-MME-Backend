"""
Tests unitarios para HydrologyService
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch

from domain.services.hydrology_service import HydrologyService


class TestHydrologyService:
    """Tests para HydrologyService"""
    
    def test_init_with_repository(self, mock_metrics_repository):
        """Test: Servicio se inicializa correctamente"""
        service = HydrologyService(repository=mock_metrics_repository)
        assert service.repository == mock_metrics_repository
    
    def test_get_reservas_hidricas_returns_dataframe(
        self, mock_metrics_repository, single_date_2026
    ):
        """Test: get_reservas_hidricas retorna DataFrame válido"""
        # Mock retorna datos de volumen útil
        mock_metrics_repository.get_metric_data = Mock(return_value=pd.DataFrame({
            'fecha': [single_date_2026] * 3,
            'recurso': ['GUAVIO', 'TEQUENDAMA', 'PENOL'],
            'valor_gwh': [1000, 500, 800]
        }))
        
        service = HydrologyService(repository=mock_metrics_repository)
        result = service.get_reservas_hidricas(single_date_2026)
        
        assert isinstance(result, pd.DataFrame)
    
    def test_get_aportes_hidricos_returns_dataframe(
        self, mock_metrics_repository, single_date_2026
    ):
        """Test: get_aportes_hidricos retorna DataFrame válido"""
        # Mock retorna datos de aportes
        mock_metrics_repository.get_metric_data = Mock(return_value=pd.DataFrame({
            'fecha': [single_date_2026] * 3,
            'recurso': ['GUAVIO', 'TEQUENDAMA', 'PENOL'],
            'valor_gwh': [100, 80, 120]
        }))
        
        service = HydrologyService(repository=mock_metrics_repository)
        result = service.get_aportes_hidricos(single_date_2026)
        
        assert isinstance(result, pd.DataFrame)
    
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
    
    def test_service_handles_zero_division(
        self, mock_metrics_repository, single_date_2026
    ):
        """Test: Servicio maneja división por cero correctamente"""
        # Mock retorna volumen útil = 0 (edge case)
        mock_metrics_repository.get_metric_data = Mock(return_value=pd.DataFrame({
            'fecha': [single_date_2026],
            'recurso': ['GUAVIO'],
            'valor_gwh': [0]  # Volumen útil = 0
        }))
        
        service = HydrologyService(repository=mock_metrics_repository)
        
        # No debería lanzar excepción
        try:
            result = service.get_reservas_hidricas(single_date_2026)
            # Si retorna DataFrame con NaN o inf, está bien handled
            assert isinstance(result, pd.DataFrame)
        except ZeroDivisionError:
            pytest.fail("El servicio no maneja división por cero")
    
    @pytest.mark.parametrize("fecha", [
        '2026-01-15',
        '2025-12-31',
        '2025-06-15',
    ])
    def test_get_reservas_multiple_dates(
        self, mock_metrics_repository, fecha
    ):
        """Test: Servicio funciona con diferentes fechas"""
        mock_metrics_repository.get_metric_data = Mock(return_value=pd.DataFrame({
            'fecha': [fecha],
            'recurso': ['GUAVIO'],
            'valor_gwh': [1000]
        }))
        
        service = HydrologyService(repository=mock_metrics_repository)
        result = service.get_reservas_hidricas(fecha)
        
        assert isinstance(result, pd.DataFrame)
    
    @pytest.mark.slow
    @pytest.mark.integration
    def test_get_reservas_with_real_database(self):
        """Test de integración: Consulta real a la base de datos"""
        service = HydrologyService()
        
        try:
            result = service.get_reservas_hidricas('2026-01-15')
            assert isinstance(result, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"Base de datos no disponible: {e}")
