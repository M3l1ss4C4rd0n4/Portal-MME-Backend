#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║            VALIDACIÓN FASE 2 - ESTABILIDAD Y DEUDA TÉCNICA                    ║
║                                                                               ║
║  Script para verificar que la estabilidad del sistema es correcta            ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Uso:
    cd /home/admonctrlxm/server
    python3 scripts/validate_stability_phase2.py

Validaciones:
    1. whatsapp_bot/venv fue eliminado
    2. DatabaseManager usa PostgreSQLConnectionManager internamente
    3. No hay imports circulares en core
    4. core/error_handlers.py funciona correctamente
    5. Todos los módulos principales importan sin errores
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)


def print_success(text):
    print(f"  ✅ {text}")


def print_error(text):
    print(f"  ❌ {text}")


def print_warning(text):
    print(f"  ⚠️  {text}")


def check_whatsapp_venv_removed():
    """Verifica que whatsapp_bot/venv fue eliminado."""
    print_header("Validación 1: Eliminación de venv anidado")
    
    venv_path = PROJECT_ROOT / "whatsapp_bot" / "venv"
    
    if venv_path.exists():
        print_error(f"whatsapp_bot/venv aún existe: {venv_path}")
        size = sum(f.stat().st_size for f in venv_path.rglob('*') if f.is_file()) / (1024**3)
        print_error(f"   Tamaño: {size:.2f} GB")
        return False
    else:
        print_success("whatsapp_bot/venv eliminado correctamente")
        
        # Verificar tamaño reducido
        wb_size = sum(f.stat().st_size for f in (PROJECT_ROOT / "whatsapp_bot").rglob('*') if f.is_file()) / (1024**2)
        print_success(f"   Tamaño actual de whatsapp_bot: {wb_size:.1f} MB")
        return True


def check_database_manager_wrapper():
    """Verifica que DatabaseManager usa PostgreSQLConnectionManager."""
    print_header("Validación 2: DatabaseManager como wrapper")
    
    try:
        from infrastructure.database.manager import DatabaseManager, db_manager
        from infrastructure.database.connection import PostgreSQLConnectionManager
        
        # Verificar que es singleton
        dm1 = DatabaseManager()
        dm2 = DatabaseManager()
        
        if dm1 is not dm2:
            print_error("DatabaseManager no es singleton")
            return False
        
        print_success("DatabaseManager es singleton")
        
        # Verificar que tiene connection manager interno
        if not hasattr(dm1, '_connection_manager'):
            print_error("DatabaseManager no tiene _connection_manager")
            return False
        
        if not isinstance(dm1._connection_manager, PostgreSQLConnectionManager):
            print_error("DatabaseManager no usa PostgreSQLConnectionManager internamente")
            return False
        
        print_success("DatabaseManager delega a PostgreSQLConnectionManager")
        
        # Verificar que db_manager global funciona
        if db_manager is None:
            print_error("db_manager global es None")
            return False
        
        print_success("Instancia global db_manager disponible")
        
        return True
        
    except Exception as e:
        print_error(f"Error verificando DatabaseManager: {e}")
        return False


def check_no_circular_imports():
    """Verifica que no hay imports circulares en core."""
    print_header("Validación 3: No hay imports circulares")
    
    modules_to_test = [
        'core.config',
        'core.container',
        'core.app_factory',
        'core.secrets',
        'core.error_handlers',
    ]
    
    all_ok = True
    for module in modules_to_test:
        try:
            # Limpiar cache para forzar reimport
            if module in sys.modules:
                del sys.modules[module]
            
            __import__(module)
            print_success(f"{module} - OK")
        except ImportError as e:
            print_error(f"{module} - ImportError: {e}")
            all_ok = False
        except Exception as e:
            print_error(f"{module} - Error: {e}")
            all_ok = False
    
    return all_ok


def check_error_handlers():
    """Verifica que core/error_handlers.py funciona."""
    print_header("Validación 4: Error Handlers")
    
    try:
        from core.error_handlers import (
            DatabaseConnectionError,
            DatabaseQueryError,
            APIConnectionError,
            safe_db_operation,
            safe_api_call,
            SafeDBContext,
        )
        
        print_success("Error handlers importados correctamente")
        
        # Verificar que las excepciones funcionan
        try:
            raise DatabaseConnectionError("Test error")
        except DatabaseConnectionError as e:
            print_success("DatabaseConnectionError funciona")
        
        # Verificar decoradores
        @safe_db_operation("test_operation")
        def test_db_func():
            return "OK"
        
        result = test_db_func()
        if result == "OK":
            print_success("safe_db_operation decorador funciona")
        
        return True
        
    except Exception as e:
        print_error(f"Error en error_handlers: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_main_modules_import():
    """Verifica que los módulos principales importan sin errores."""
    print_header("Validación 5: Módulos principales")
    
    modules = [
        'api.main',
        'core.app_factory',
        'tasks.etl_tasks',
        'tasks.anomaly_tasks',
    ]
    
    all_ok = True
    for module in modules:
        try:
            # No recargar, solo verificar que está importado
            if module not in sys.modules:
                __import__(module)
            print_success(f"{module} - OK")
        except Exception as e:
            print_error(f"{module} - Error: {e}")
            all_ok = False
    
    return all_ok


def check_specific_exceptions():
    """Verifica que se usan excepciones específicas en lugar de genéricas."""
    print_header("Validación 6: Uso de excepciones específicas")
    
    # Verificar que error_handlers.py existe y tiene contenido
    error_handlers_path = PROJECT_ROOT / "core" / "error_handlers.py"
    
    if not error_handlers_path.exists():
        print_error("core/error_handlers.py no existe")
        return False
    
    content = error_handlers_path.read_text()
    
    # Verificar que tiene las excepciones principales
    required_exceptions = [
        'DatabaseConnectionError',
        'DatabaseQueryError',
        'APIConnectionError',
        'APIResponseError',
    ]
    
    all_ok = True
    for exc in required_exceptions:
        if exc in content:
            print_success(f"Excepción {exc} definida")
        else:
            print_error(f"Excepción {exc} NO definida")
            all_ok = False
    
    return all_ok


def main():
    print("\n" + "="*70)
    print("  VALIDACIÓN FASE 2 - ESTABILIDAD Y DEUDA TÉCNICA")
    print("="*70)
    
    results = []
    
    results.append(("Venv anidado eliminado", check_whatsapp_venv_removed()))
    results.append(("DatabaseManager wrapper", check_database_manager_wrapper()))
    results.append(("No imports circulares", check_no_circular_imports()))
    results.append(("Error handlers", check_error_handlers()))
    results.append(("Módulos principales", check_main_modules_import()))
    results.append(("Excepciones específicas", check_specific_exceptions()))
    
    print_header("RESUMEN")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Resultado: {passed}/{total} validaciones pasaron")
    
    if passed == total:
        print("\n  🎉 FASE 2 - ESTABILIDAD: IMPLEMENTADA CORRECTAMENTE")
        return 0
    else:
        print("\n  ⚠️  Algunas validaciones fallaron. Revisar arriba.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
