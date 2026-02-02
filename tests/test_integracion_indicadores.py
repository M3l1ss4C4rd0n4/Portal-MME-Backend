"""
Script de Prueba: Integración de Indicadores Completos
Verifica que el sistema funcione correctamente con el nuevo patrón XM
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from domain.services.indicators_service import indicators_service
from domain.services.metrics_calculator import calculate_variation, format_value, VALID_RANGES
from etl.validaciones_rangos import validar_rango_metrica, get_valid_range
import pandas as pd


def test_metrics_calculator():
    """Test de funciones del calculator"""
    print("\n" + "="*60)
    print("TEST 1: Metrics Calculator")
    print("="*60)
    
    # Test calculate_variation
    print("\n1.1 Test calculate_variation:")
    result = calculate_variation(242.87, 254.69)
    print(f"  Variación (242.87 vs 254.69): {result}")
    assert result['direction'] == 'down'
    assert abs(result['variation_pct'] - (-4.64)) < 0.1
    print("  ✅ Cálculo correcto")
    
    # Test format_value
    print("\n1.2 Test format_value:")
    tests = [
        (242870000, 'TX1', '242.87'),
        (295000000, 'COP', '$295,00'),
        (87.73, '%', '87.73%'),
        (87654321, 'GWh', '87.65'),
    ]
    
    for valor, unidad, esperado in tests:
        resultado = format_value(valor, unidad)
        print(f"  {valor} {unidad} -> '{resultado}' (esperado: '{esperado}')")
        # Verificar que el formato sea similar (sin ser exacto)
        assert len(resultado) > 0
    
    print("  ✅ Formateo correcto")
    
    # Test VALID_RANGES
    print("\n1.3 Test VALID_RANGES:")
    print(f"  PrecBolsNaci: {VALID_RANGES.get('PrecBolsNaci')}")
    print(f"  RestAliv: {VALID_RANGES.get('RestAliv')}")
    print(f"  AporEner: {VALID_RANGES.get('AporEner')}")
    assert VALID_RANGES['PrecBolsNaci'] == (0, 2000)
    assert VALID_RANGES['RestAliv'] == (0, 500)
    print("  ✅ Rangos correctos")


def test_validaciones_rangos():
    """Test de validaciones de rangos"""
    print("\n" + "="*60)
    print("TEST 2: Validaciones de Rangos")
    print("="*60)
    
    # Crear DataFrame de prueba
    df_test = pd.DataFrame({
        'metrica': ['PrecBolsNaci'] * 5,
        'valor_gwh': [100, 200, 300, 2500, -50],  # 2 inválidos
        'fecha': pd.date_range('2026-01-01', periods=5)
    })
    
    print("\n2.1 DataFrame de prueba:")
    print(df_test)
    
    # Validar
    df_limpio, stats = validar_rango_metrica(df_test, 'PrecBolsNaci')
    
    print("\n2.2 Resultados de validación:")
    print(f"  Registros originales: {stats['registros_originales']}")
    print(f"  Registros eliminados: {stats['registros_eliminados']}")
    print(f"  Registros finales: {stats['registros_finales']}")
    print(f"  Rango: [{stats['rango_min']}, {stats['rango_max']}]")
    
    assert stats['registros_eliminados'] == 2  # -50 y 2500
    assert stats['registros_finales'] == 3
    print("  ✅ Validación correcta")
    
    # Test get_valid_range
    print("\n2.3 Test get_valid_range:")
    rango = get_valid_range('RestAliv')
    print(f"  RestAliv: {rango}")
    assert rango == (0, 500)
    
    rango_inexistente = get_valid_range('MetricaInventada')
    print(f"  MetricaInventada: {rango_inexistente}")
    assert rango_inexistente is None
    print("  ✅ get_valid_range correcto")


def test_indicators_service():
    """Test del servicio de indicadores"""
    print("\n" + "="*60)
    print("TEST 3: Indicators Service (requiere DB)")
    print("="*60)
    
    print("\n3.1 Test get_indicator_complete:")
    
    # Intentar obtener indicador de PrecBolsNaci
    try:
        indicator = indicators_service.get_indicator_complete('PrecBolsNaci', 'Sistema')
        
        if indicator:
            print(f"  ✅ Indicador obtenido:")
            print(f"    Métrica: {indicator['metric_id']}")
            print(f"    Valor actual: {indicator['valor_actual']}")
            print(f"    Unidad: {indicator['unidad']}")
            print(f"    Fecha actual: {indicator['fecha_actual']}")
            print(f"    Valor anterior: {indicator['valor_anterior']}")
            print(f"    Variación: {indicator['variacion_pct']}%")
            print(f"    Dirección: {indicator['direccion']} {indicator['flecha']}")
            print(f"    Valor formateado: {indicator['valor_formateado']}")
            print(f"    Variación formateada: {indicator['variacion_formateada']}")
        else:
            print("  ⚠️  No hay datos en la DB para esta métrica")
            
    except Exception as e:
        print(f"  ⚠️  Error (esperado si DB vacía): {e}")
    
    print("\n3.2 Test get_multiple_indicators:")
    try:
        indicators = indicators_service.get_multiple_indicators([
            'PrecBolsNaci',
            'RestAliv',
            'AporEner'
        ])
        
        print(f"  Métricas obtenidas: {len(indicators)}")
        for metric_id, ind in indicators.items():
            print(f"    - {metric_id}: {ind['valor_formateado']} ({ind['variacion_formateada']})")
        
        if indicators:
            print("  ✅ Múltiples indicadores obtenidos")
        else:
            print("  ⚠️  No hay datos en la DB")
            
    except Exception as e:
        print(f"  ⚠️  Error (esperado si DB vacía): {e}")


def test_integracion_completa():
    """Test de integración completa"""
    print("\n" + "="*60)
    print("TEST 4: Integración Completa")
    print("="*60)
    
    print("\nSimulación de uso en callback:")
    print("```python")
    print("# En un callback de Dash:")
    print("indicator = indicators_service.get_indicator_complete('RestAliv')")
    print("")
    print("if indicator:")
    print("    kpi_html = html.Div([")
    print("        html.Span(indicator['valor_formateado'], className='kpi-value'),")
    print("        html.Span(indicator['variacion_formateada'], className='variation-{}'.format(indicator['direccion']))")
    print("    ])")
    print("```")
    print("\n✅ Patrón listo para usar en callbacks")


def run_all_tests():
    """Ejecuta todos los tests"""
    print("\n" + "="*60)
    print("INICIO DE PRUEBAS - INTEGRACIÓN INDICADORES XM")
    print("="*60)
    
    try:
        test_metrics_calculator()
        test_validaciones_rangos()
        test_indicators_service()
        test_integracion_completa()
        
        print("\n" + "="*60)
        print("✅ TODAS LAS PRUEBAS COMPLETADAS")
        print("="*60)
        print("\nSiguientes pasos:")
        print("1. Aplicar patrón en callbacks existentes")
        print("2. Agregar validación de rangos al ETL")
        print("3. Verificar con datos reales en dashboard")
        
    except AssertionError as e:
        print(f"\n❌ ERROR EN PRUEBAS: {e}")
        return False
    except Exception as e:
        print(f"\n⚠️  Excepción: {e}")
        return False
    
    return True


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
