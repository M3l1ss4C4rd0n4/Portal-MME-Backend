"""
╔══════════════════════════════════════════════════════════════╗
║                  TESTS UNITARIOS - ETL XM                    ║
║                                                              ║
║  Tests para validar funciones críticas del ETL               ║
╚══════════════════════════════════════════════════════════════╝
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
import pandas as pd
from etl.validaciones import (
    ValidadorDatos,
    validar_fecha_futura,
    validar_rango_valores,
    detectar_duplicados,
    eliminar_duplicados
)


class TestValidadorDatos(unittest.TestCase):
    """Tests para la clase ValidadorDatos"""
    
    def setUp(self):
        """Configuración antes de cada test"""
        self.validador = ValidadorDatos()
    
    def test_validar_fecha_actual(self):
        """Valida que fechas actuales sean aceptadas"""
        fecha = datetime.now()
        es_valida, error = self.validador.validar_fecha(fecha, 'Gene')
        self.assertTrue(es_valida)
        self.assertIsNone(error)
    
    def test_validar_fecha_futura_rechazada(self):
        """Valida que fechas futuras (>1 día) sean rechazadas"""
        fecha = datetime.now() + timedelta(days=5)
        es_valida, error = self.validador.validar_fecha(fecha, 'Gene')
        self.assertFalse(es_valida)
        self.assertIsNotNone(error)
        self.assertIn('futura', error.lower())
    
    def test_validar_fecha_antigua_rechazada(self):
        """Valida que fechas antiguas (<2015) sean rechazadas"""
        fecha = datetime(2010, 1, 1)
        es_valida, error = self.validador.validar_fecha(fecha, 'Gene')
        self.assertFalse(es_valida)
        self.assertIsNotNone(error)
        self.assertIn('antigua', error.lower())
    
    def test_validar_valor_positivo(self):
        """Valida que valores positivos razonables sean aceptados"""
        es_valido, error = self.validador.validar_valor(100.5, 'Gene', '_SISTEMA_')
        self.assertTrue(es_valido)
        self.assertIsNone(error)
    
    def test_validar_valor_negativo_rechazado(self):
        """Valida que valores negativos sean rechazados"""
        es_valido, error = self.validador.validar_valor(-10, 'Gene', '_SISTEMA_')
        self.assertFalse(es_valido)
        self.assertIsNotNone(error)
    
    def test_validar_valor_nan_rechazado(self):
        """Valida que NaN sea rechazado"""
        es_valido, error = self.validador.validar_valor(float('nan'), 'Gene', '_SISTEMA_')
        self.assertFalse(es_valido)
        self.assertIsNotNone(error)
    
    def test_normalizar_recurso_sistema(self):
        """Valida normalización de 'Sistema' a '_SISTEMA_'"""
        self.assertEqual(self.validador.normalizar_recurso('Sistema'), '_SISTEMA_')
        self.assertEqual(self.validador.normalizar_recurso('SISTEMA'), '_SISTEMA_')
        self.assertEqual(self.validador.normalizar_recurso('sistema'), '_SISTEMA_')
        self.assertEqual(self.validador.normalizar_recurso('  Sistema  '), '_SISTEMA_')
    
    def test_normalizar_recurso_otros(self):
        """Valida que otros recursos no se modifiquen"""
        self.assertEqual(self.validador.normalizar_recurso('SANCAR'), 'SANCAR')
        self.assertEqual(self.validador.normalizar_recurso('Embalse'), 'Embalse')
    
    def test_validar_registro_completo_valido(self):
        """Valida un registro completo válido"""
        fecha = datetime.now()
        es_valido, errores = self.validador.validar_registro(
            fecha, 'Gene', '_SISTEMA_', 250.5
        )
        self.assertTrue(es_valido)
        self.assertEqual(len(errores), 0)
    
    def test_validar_registro_completo_invalido(self):
        """Valida un registro con múltiples errores"""
        fecha = datetime.now() + timedelta(days=10)  # Fecha futura
        es_valido, errores = self.validador.validar_registro(
            fecha, 'Gene', '_SISTEMA_', -100  # Valor negativo
        )
        self.assertFalse(es_valido)
        self.assertGreater(len(errores), 0)
    
    def test_validar_dataframe(self):
        """Valida un DataFrame completo"""
        df = pd.DataFrame({
            'fecha': [datetime.now(), datetime.now() - timedelta(days=1)],
            'metrica': ['Gene', 'Gene'],
            'recurso': ['Sistema', 'SISTEMA'],
            'valor_gwh': [250.5, 300.0]
        })
        
        df_limpio, errores = self.validador.validar_dataframe(df, 'Gene')
        
        # Verificar normalización
        self.assertTrue(all(df_limpio['recurso'] == '_SISTEMA_'))
        self.assertEqual(len(df_limpio), 2)


class TestFuncionesUtilidad(unittest.TestCase):
    """Tests para funciones de utilidad"""
    
    def test_validar_fecha_futura_hoy(self):
        """Valida que la fecha de hoy sea aceptada"""
        self.assertTrue(validar_fecha_futura(datetime.now()))
    
    def test_validar_fecha_futura_manana(self):
        """Valida que mañana sea aceptado (margen de 1 día)"""
        self.assertTrue(validar_fecha_futura(datetime.now() + timedelta(days=1)))
    
    def test_validar_fecha_futura_lejana(self):
        """Valida que fechas futuras lejanas sean rechazadas"""
        self.assertFalse(validar_fecha_futura(datetime.now() + timedelta(days=5)))
    
    def test_validar_rango_valores(self):
        """Valida filtrado por rango de valores"""
        df = pd.DataFrame({
            'valor': [10, 50, 100, 150, 200]
        })
        
        df_filtrado = validar_rango_valores(df, 'valor', 50, 150)
        
        self.assertEqual(len(df_filtrado), 3)
        self.assertTrue(all(df_filtrado['valor'] >= 50))
        self.assertTrue(all(df_filtrado['valor'] <= 150))
    
    def test_detectar_duplicados(self):
        """Valida detección de duplicados"""
        df = pd.DataFrame({
            'metrica': ['Gene', 'Gene', 'Gene', 'DemaCome'],
            'fecha': ['2025-11-15', '2025-11-15', '2025-11-16', '2025-11-15'],
            'valor': [100, 100, 200, 50]
        })
        
        duplicados = detectar_duplicados(df, ['metrica', 'fecha'])
        
        self.assertEqual(len(duplicados), 2)  # Solo las 2 primeras filas
        self.assertTrue(all(duplicados['metrica'] == 'Gene'))
        self.assertTrue(all(duplicados['fecha'] == '2025-11-15'))
    
    def test_eliminar_duplicados_first(self):
        """Valida eliminación de duplicados manteniendo el primero"""
        df = pd.DataFrame({
            'metrica': ['Gene', 'Gene', 'Gene'],
            'fecha': ['2025-11-15', '2025-11-15', '2025-11-16'],
            'valor': [100, 150, 200]
        })
        
        df_limpio = eliminar_duplicados(df, ['metrica', 'fecha'], estrategia='first')
        
        self.assertEqual(len(df_limpio), 2)
        # Debe mantener el primer registro (valor=100)
        self.assertEqual(
            df_limpio[df_limpio['fecha'] == '2025-11-15']['valor'].iloc[0], 
            100
        )
    
    def test_eliminar_duplicados_last(self):
        """Valida eliminación de duplicados manteniendo el último"""
        df = pd.DataFrame({
            'metrica': ['Gene', 'Gene', 'Gene'],
            'fecha': ['2025-11-15', '2025-11-15', '2025-11-16'],
            'valor': [100, 150, 200]
        })
        
        df_limpio = eliminar_duplicados(df, ['metrica', 'fecha'], estrategia='last')
        
        self.assertEqual(len(df_limpio), 2)
        # Debe mantener el último registro (valor=150)
        self.assertEqual(
            df_limpio[df_limpio['fecha'] == '2025-11-15']['valor'].iloc[0], 
            150
        )
    
    def test_eliminar_duplicados_max(self):
        """Valida eliminación de duplicados manteniendo el valor máximo"""
        df = pd.DataFrame({
            'metrica': ['Gene', 'Gene', 'Gene'],
            'fecha': ['2025-11-15', '2025-11-15', '2025-11-16'],
            'valor_gwh': [100, 150, 200]
        })
        
        df_limpio = eliminar_duplicados(df, ['metrica', 'fecha'], estrategia='max')
        
        self.assertEqual(len(df_limpio), 2)
        # Debe mantener el valor máximo (150)
        self.assertEqual(
            df_limpio[df_limpio['fecha'] == '2025-11-15']['valor_gwh'].iloc[0], 
            150
        )


class TestUmbralesMetricas(unittest.TestCase):
    """Tests para umbrales específicos de métricas"""
    
    def setUp(self):
        self.validador = ValidadorDatos()
    
    def test_demanda_rango_valido(self):
        """Valida que demandas típicas (40-80 GWh) sean aceptadas"""
        es_valido, _ = self.validador.validar_valor(42.5, 'DemaCome', '_SISTEMA_')
        self.assertTrue(es_valido)
        
        es_valido, _ = self.validador.validar_valor(78.3, 'DemaCome', '_SISTEMA_')
        self.assertTrue(es_valido)
    
    def test_demanda_extrema(self):
        """Valida que demandas extremas (>100 GWh) generen advertencias"""
        self.validador.validar_valor(150, 'DemaCome', '_SISTEMA_')
        self.assertGreater(self.validador.estadisticas['advertencias'], 0)
    
    def test_generacion_rango_valido(self):
        """Valida que generación típica (100-300 GWh) sea aceptada"""
        es_valido, _ = self.validador.validar_valor(250.5, 'Gene', '_SISTEMA_')
        self.assertTrue(es_valido)
    
    def test_capacidad_util_porcentaje(self):
        """Valida que capacidad útil esté en rango 0-100%"""
        es_valido, _ = self.validador.validar_valor(85.5, 'CapaUtilDiarEner', 'Embalse')
        self.assertTrue(es_valido)
        
        # Valor > 100% debe generar advertencia
        self.validador.validar_valor(105, 'CapaUtilDiarEner', 'Embalse')
        self.assertGreater(self.validador.estadisticas['advertencias'], 0)


def run_tests():
    """Ejecuta todos los tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Agregar todos los tests
    suite.addTests(loader.loadTestsFromTestCase(TestValidadorDatos))
    suite.addTests(loader.loadTestsFromTestCase(TestFuncionesUtilidad))
    suite.addTests(loader.loadTestsFromTestCase(TestUmbralesMetricas))
    
    # Ejecutar
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    exito = run_tests()
    sys.exit(0 if exito else 1)
