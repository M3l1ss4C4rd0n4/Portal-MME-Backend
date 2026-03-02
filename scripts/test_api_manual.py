#!/usr/bin/env python3
"""
Script de prueba para la API RESTful del Portal Energético MME

Prueba los endpoints principales de la API para verificar su funcionamiento.

Uso:
    python api/test_api.py

Autor: Arquitectura Dashboard MME
Fecha: 3 de febrero de 2026
"""

import requests
import json
import sys
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class APITester:
    """Tester para la API RESTful"""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key} if api_key else {}
        self.passed = 0
        self.failed = 0
    
    def test(self, name: str, method: str, endpoint: str, expected_status: int = 200, **kwargs) -> bool:
        """
        Ejecuta un test de endpoint
        
        Args:
            name: Nombre del test
            method: Método HTTP (GET, POST, etc.)
            endpoint: Endpoint a probar
            expected_status: Código de estado esperado
            **kwargs: Argumentos adicionales para requests
            
        Returns:
            True si el test pasó, False si falló
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            print(f"\n{'='*70}")
            print(f"🧪 TEST: {name}")
            print(f"{'='*70}")
            print(f"📡 {method} {url}")
            
            # Merge headers
            headers = {**self.headers, **kwargs.pop("headers", {})}
            
            # Ejecutar request
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                timeout=30,
                **kwargs
            )
            
            # Mostrar resultado
            print(f"📊 Status Code: {response.status_code}")
            
            # Verificar código de estado
            if response.status_code == expected_status:
                print(f"✅ PASSED - Status code correcto: {response.status_code}")
                self.passed += 1
                
                # Mostrar respuesta si es JSON
                try:
                    data = response.json()
                    print(f"\n📋 Respuesta:")
                    print(json.dumps(data, indent=2, ensure_ascii=False)[:500])
                    if len(json.dumps(data)) > 500:
                        print("... (truncado)")
                except:
                    print(f"📋 Respuesta: {response.text[:200]}")
                
                return True
            else:
                print(f"❌ FAILED - Status code incorrecto")
                print(f"   Esperado: {expected_status}")
                print(f"   Recibido: {response.status_code}")
                print(f"   Respuesta: {response.text[:200]}")
                self.failed += 1
                return False
                
        except Exception as e:
            print(f"❌ FAILED - Excepción: {str(e)}")
            self.failed += 1
            return False
    
    def run_all_tests(self):
        """Ejecuta todos los tests de la API"""
        print("\n" + "="*70)
        print("🚀 INICIANDO TESTS DE LA API RESTful - Portal Energético MME")
        print("="*70)
        
        # Test 1: Health check
        self.test(
            name="Health Check",
            method="GET",
            endpoint="/health",
            expected_status=200
        )
        
        # Test 2: Root endpoint
        self.test(
            name="Root Endpoint",
            method="GET",
            endpoint="/",
            expected_status=200
        )
        
        # Test 3: Listar métricas
        self.test(
            name="Listar Métricas",
            method="GET",
            endpoint="/api/v1/metrics/",
            expected_status=200
        )
        
        # Test 4: Obtener serie temporal de generación
        today = datetime.now().date()
        start_date = (today - timedelta(days=30)).isoformat()
        end_date = today.isoformat()
        
        self.test(
            name="Serie Temporal - Generación",
            method="GET",
            endpoint=f"/api/v1/metrics/Gene?entity=Sistema&start_date={start_date}&end_date={end_date}",
            expected_status=200
        )
        
        # Test 5: Obtener predicción (puede fallar si Prophet no está instalado)
        self.test(
            name="Predicción ML - Prophet",
            method="GET",
            endpoint="/api/v1/predictions/Gene?horizon_days=7&model_type=prophet",
            expected_status=200
        )
        
        # Test 6: Sin API Key (debe fallar si está habilitado)
        old_headers = self.headers.copy()
        self.headers = {}
        self.test(
            name="Sin API Key (debe fallar)",
            method="GET",
            endpoint="/api/v1/metrics/Gene",
            expected_status=401
        )
        self.headers = old_headers
        
        # Test 7: API Key inválida (debe fallar)
        self.test(
            name="API Key Inválida (debe fallar)",
            method="GET",
            endpoint="/api/v1/metrics/Gene",
            expected_status=403,
            headers={"X-API-Key": "invalid-key"}
        )
        
        # Test 8: Parámetros inválidos
        self.test(
            name="Parámetros Inválidos (debe fallar)",
            method="GET",
            endpoint="/api/v1/predictions/Gene?horizon_days=9999",
            expected_status=400
        )
        
        # Resumen
        print("\n" + "="*70)
        print("📊 RESUMEN DE TESTS")
        print("="*70)
        total = self.passed + self.failed
        print(f"✅ Pasados: {self.passed}/{total}")
        print(f"❌ Fallidos: {self.failed}/{total}")
        print(f"📈 Tasa de éxito: {(self.passed/total*100):.1f}%")
        print("="*70)
        
        return self.failed == 0


def main():
    """Función principal"""
    # Leer configuración
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    api_url = os.getenv("API_URL", "http://localhost:8000")
    api_key = os.getenv("API_KEY", "mme-portal-energetico-2026-secret-key")
    
    print(f"\n📡 URL de la API: {api_url}")
    print(f"🔑 Usando API Key: {api_key[:20]}..." if api_key else "⚠️  Sin API Key")
    
    # Crear tester y ejecutar
    tester = APITester(base_url=api_url, api_key=api_key)
    success = tester.run_all_tests()
    
    # Exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
