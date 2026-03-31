#!/usr/bin/env python3
"""
Script automatizado para reemplazar except Exception genéricos.
Reemplaza con patrones específicos según el contexto.
"""

import re
import sys
from pathlib import Path

# Patrones de reemplazo según contexto
PATTERNS = {
    # En constructores de servicios
    r'(except)\s+(Exception)\s+(as\s+e:\s*\n\s*logger\.warning\s*\(\s*f["\'])([^"\']+no disponible)(["\'].*\))': 
        r'\1 (ImportError, ModuleNotFoundError, ConnectionError) \3\4\5\n            logger.error(f"Error inesperado: {e}", exc_info=True)',
    
    # En queries DB
    r'(except)\s+(Exception)\s+(as\s+e:\s*\n\s*logger\.error\s*\(\s*f?["\']?)([^"\']*Error[^"\']*|[^"\']*error[^"\']*)(["\']?.*\))':
        r'\1 (psycopg2.Error, DatabaseError) \3\4\5\n            logger.error(f"DB Error detallado: {e}", exc_info=True)',
}

def fix_file(filepath):
    """Corrige except Exception en un archivo."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    changes = 0
    
    # Reemplazo 1: Agregar exc_info=True a logger.error/warning en except Exception
    pattern1 = r'(except Exception as e:\s*\n)(\s*)(logger\.(error|warning|info)\(f?["\']?.*?\))(\s*\n)'
    
    def replace_with_exc_info(match):
        nonlocal changes
        changes += 1
        indent = match.group(2)
        log_call = match.group(3)
        if 'exc_info' not in log_call:
            # Agregar exc_info=True al final del log
            if log_call.endswith(')'):
                log_call = log_call[:-1] + ', exc_info=True)'
        return f'{match.group(1)}{indent}{log_call}{match.group(5)}'
    
    content = re.sub(pattern1, replace_with_exc_info, content, flags=re.MULTILINE)
    
    # Reemplazo 2: Capturar excepciones específicas comunes antes de Exception
    # Buscar patrones de DB
    if 'psycopg2' in content or 'execute' in content:
        pattern2 = r'(^\s*)(except Exception as e:)(\s*\n)(\s*)(logger\.(error|warning)\()'
        
        def replace_db_exceptions(match):
            nonlocal changes
            changes += 1
            indent = match.group(1)
            log_indent = match.group(4)
            return f'{indent}except (psycopg2.OperationalError, psycopg2.ProgrammingError) as e:\n{log_indent}logger.error(f"Error de BD: {e}")\n{indent}except Exception as e:\n{log_indent}'
        
        content = re.sub(pattern2, replace_db_exceptions, content, flags=re.MULTILINE)
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return changes
    return 0

def main():
    target_files = [
        'domain/services/executive_report_service.py',
        'domain/services/orchestrator/handlers/informe_handler.py',
        'domain/services/orchestrator/handlers/estado_actual_handler.py',
        'domain/services/intelligent_analysis_service.py',
        'domain/services/cu_service.py',
        'domain/services/notification_service.py',
        'domain/services/losses_nt_service.py',
        'domain/services/ai_service.py',
        'domain/services/generation_service.py',
        'domain/services/distribution_service.py',
    ]
    
    total_changes = 0
    for file_path in target_files:
        path = Path(file_path)
        if path.exists():
            changes = fix_file(path)
            if changes > 0:
                print(f"✅ {path}: {changes} cambios")
                total_changes += changes
            else:
                print(f"➖ {path}: sin cambios")
        else:
            print(f"❌ {path}: no encontrado")
    
    print(f"\n📊 Total cambios: {total_changes}")

if __name__ == "__main__":
    main()
