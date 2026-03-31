#!/usr/bin/env python3
"""
Script para migrar except Exception genéricos a manejo específico.

Uso:
    python scripts/migrate_except_exception.py [archivo]
    
    Si no se especifica archivo, procesa todos los archivos del directorio domain/services/
"""

import re
import sys
from pathlib import Path


def migrate_file(filepath):
    """Migra except Exception genéricos en un archivo."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    changes = []
    
    # Patrón 1: except Exception as e: logger.error(e) → except Exception as e: logger.error(..., exc_info=True)
    pattern1 = r'(except Exception as e:\s*\n\s*logger\.(error|warning|info)\()(.*?)(\))'
    
    def replace1(match):
        log_func = match.group(2)
        log_msg = match.group(3).strip()
        if 'exc_info' not in log_msg:
            return f'{match.group(1)}{log_msg}, exc_info=True{match.group(4)}'
        return match.group(0)
    
    content = re.sub(pattern1, replace1, content)
    
    # Patrón 2: except Exception as e: (sin logger) → except Exception as e: logger.error(..., exc_info=True)
    # Solo si hay un pass o no hay manejo
    pattern2 = r'(except Exception as e:\s*\n)(\s*pass\s*$)'
    
    def replace2(match):
        indent = len(match.group(2)) - len(match.group(2).lstrip())
        spaces = ' ' * indent
        return f'{match.group(1)}{spaces}logger.error(f"Error inesperado: {e}", exc_info=True)\n{match.group(2)}'
    
    content = re.sub(pattern2, replace2, content, flags=re.MULTILINE)
    
    # Contar cambios
    if content != original_content:
        changes.append(f"Archivo modificado: {filepath}")
        with open(filepath, 'w') as f:
            f.write(content)
        return True, changes
    
    return False, []


def main():
    if len(sys.argv) > 1:
        # Procesar archivo específico
        filepath = Path(sys.argv[1])
        if filepath.exists():
            modified, changes = migrate_file(filepath)
            if modified:
                print(f"✅ {filepath} modificado")
            else:
                print(f"➖ {filepath} sin cambios")
        else:
            print(f"❌ Archivo no encontrado: {filepath}")
    else:
        # Procesar todos los archivos
        base_path = Path('domain/services')
        files = list(base_path.glob('*.py')) + list(base_path.glob('orchestrator/handlers/*.py'))
        
        modified_count = 0
        for filepath in files:
            if '__pycache__' in str(filepath):
                continue
            modified, _ = migrate_file(filepath)
            if modified:
                modified_count += 1
                print(f"✅ {filepath}")
        
        print(f"\n📊 Total archivos modificados: {modified_count}")


if __name__ == "__main__":
    main()
