"""
Tests automatizados para validar cálculos críticos del dashboard.

Ejecutar: python3 -m pytest tests/test_metricas.py -v
O directamente: python3 tests/test_metricas.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date, timedelta
from utils._xm import fetch_metric_data
from utils.unit_validator import validar_unidades_energia, debe_convertir_unidades
import pandas as pd


def test_no_conversion_duplicada_aportes():
    """Verificar que AporEner no tenga conversión duplicada"""
    print("\n" + "="*70)
    print("TEST 1: Conversión duplicada en AporEner")
    print("="*70)
    
    fecha = (date.today() - timedelta(days=2)).strftime('%Y-%m-%d')
    data = fetch_metric_data('AporEner', 'Sistema', fecha, fecha)
    
    if data is None or data.empty:
        print("⚠️ Sin datos para la fecha")
        return
    
    valor = data['Value'].iloc[0]
    
    # Valor esperado: entre 50 y 500 GWh por día (rango razonable)
    assert 50 < valor < 500, f"❌ FALLO: Valor {valor:.2f} GWh fuera de rango esperado (50-500 GWh)"
    
    print(f"✅ PASÓ: AporEner = {valor:.2f} GWh (rango válido)")
    
    # Validar con el validador
    assert validar_unidades_energia('AporEner', data), "❌ Validación de unidades falló"
    print("✅ PASÓ: Validación de unidades")


def test_debe_convertir_correcto():
    """Verificar que el sistema sepa qué métricas convertir"""
    print("\n" + "="*70)
    print("TEST 2: Decisión de conversión")
    print("="*70)
    
    # AporEner NO debe convertirse (ya viene en GWh)
    necesita, factor = debe_convertir_unidades('AporEner')
    assert not necesita, "❌ FALLO: AporEner no debe convertirse"
    print("✅ PASÓ: AporEner correctamente marcado como NO convertir")
    
    # VoluUtilDiarEner SÍ debe convertirse
    necesita, factor = debe_convertir_unidades('VoluUtilDiarEner')
    assert necesita and factor == 1e9, "❌ FALLO: VoluUtilDiarEner debe convertirse con factor 1e9"
    print("✅ PASÓ: VoluUtilDiarEner correctamente marcado para convertir")


def test_calculo_aportes_vs_xm():
    """Verificar que el cálculo de aportes coincida con XM"""
    print("\n" + "="*70)
    print("TEST 3: Cálculo de aportes vs XM")
    print("="*70)
    
    # Usar fecha conocida: 10 de noviembre 2024
    fecha_fin = date(2024, 11, 10)
    fecha_inicio = fecha_fin.replace(day=1)
    
    df_aportes = fetch_metric_data('AporEner', 'Sistema', 
                                    fecha_inicio.strftime('%Y-%m-%d'), 
                                    fecha_fin.strftime('%Y-%m-%d'))
    df_media = fetch_metric_data('AporEnerMediHist', 'Sistema',
                                  fecha_inicio.strftime('%Y-%m-%d'),
                                  fecha_fin.strftime('%Y-%m-%d'))
    
    if df_aportes is None or df_media is None:
        print("⚠️ Sin datos para la fecha")
        return
    
    # Cálculo XM: promedio real / promedio histórico
    promedio_real = df_aportes['Value'].mean()
    promedio_hist = df_media['Value'].mean()
    porcentaje = (promedio_real / promedio_hist) * 100
    
    print(f"Promedio Real: {promedio_real:.2f} GWh")
    print(f"Promedio Histórico: {promedio_hist:.2f} GWh")
    print(f"Porcentaje: {porcentaje:.2f}%")
    
    # XM mostraba 74.53% para esta fecha
    assert 74 < porcentaje < 76, f"❌ FALLO: Porcentaje {porcentaje:.2f}% no coincide con XM (~74.53%)"
    print(f"✅ PASÓ: Porcentaje {porcentaje:.2f}% coincide con XM (74.53%)")
    
    # XM mostraba ~270 GWh (media histórica)
    assert 260 < promedio_hist < 280, f"❌ FALLO: Media histórica {promedio_hist:.2f} no coincide con XM (~270 GWh)"
    print(f"✅ PASÓ: Media histórica {promedio_hist:.2f} GWh coincide con XM (270.61 GWh)")


def test_reservas_precision():
    """Verificar que reservas tenga precisión adecuada"""
    print("\n" + "="*70)
    print("TEST 4: Precisión de reservas")
    print("="*70)
    
    fecha = (date.today() - timedelta(days=2)).strftime('%Y-%m-%d')
    
    df_vol = fetch_metric_data('VoluUtilDiarEner', 'Embalse', fecha, fecha)
    df_cap = fetch_metric_data('CapaUtilDiarEner', 'Embalse', fecha, fecha)
    
    if df_vol is None or df_cap is None:
        print("⚠️ Sin datos para la fecha")
        return
    
    # Convertir correctamente Wh → GWh
    vol_gwh = df_vol['Value'].sum() / 1e9
    cap_gwh = df_cap['Value'].sum() / 1e9
    
    print(f"Volumen: {vol_gwh:.2f} GWh")
    print(f"Capacidad: {cap_gwh:.2f} GWh")
    
    # Verificar que NO sea un número muy redondeado (ej: 14.00)
    decimales = vol_gwh - int(vol_gwh)
    assert decimales > 0.001, f"❌ FALLO: Volumen demasiado redondeado ({vol_gwh:.2f} GWh)"
    print(f"✅ PASÓ: Volumen con precisión adecuada ({vol_gwh:.2f} GWh)")


def run_all_tests():
    """Ejecutar todos los tests"""
    tests = [
        test_no_conversion_duplicada_aportes,
        test_debe_convertir_correcto,
        test_calculo_aportes_vs_xm,
        test_reservas_precision
    ]
    
    print("\n" + "="*70)
    print("EJECUTANDO SUITE DE TESTS DE VALIDACIÓN")
    print("="*70)
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ TEST FALLÓ: {e}")
            failed += 1
        except Exception as e:
            print(f"\n⚠️ ERROR EN TEST: {e}")
            failed += 1
    
    print("\n" + "="*70)
    print(f"RESULTADOS: {passed} pasados, {failed} fallidos")
    print("="*70)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
