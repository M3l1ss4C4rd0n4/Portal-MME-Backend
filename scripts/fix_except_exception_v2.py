#!/usr/bin/env python3
"""
Script simplificado para agregar exc_info=True a logs en except Exception.
"""

import re
from pathlib import Path

def fix_file(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    changes = 0
    in_except = False
    except_indent = 0
    
    new_lines = []
    for i, line in enumerate(lines):
        # Detectar except Exception
        if re.match(r'^(\s*)except Exception as e:', line):
            in_except = True
            except_indent = len(line) - len(line.lstrip())
            new_lines.append(line)
        # Detectar logger.* dentro de except Exception
        elif in_except and re.match(rf'^{" "*except_indent}\s+logger\.(error|warning|info)\(', line):
            # Verificar si ya tiene exc_info
            if 'exc_info' not in line:
                # Agregar exc_info=True antes del último paréntesis
                line = line.rstrip()
                if line.endswith(')'):
                    line = line[:-1] + ', exc_info=True)\n'
                else:
                    line = line + '\n'
                changes += 1
            new_lines.append(line)
        # Detectar fin del bloque except
        elif in_except and line.strip() and not line.startswith('#'):
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= except_indent and not line.strip().startswith('except'):
                in_except = False
            new_lines.append(line)
        else:
            new_lines.append(line)
    
    if changes > 0:
        with open(filepath, 'w') as f:
            f.writelines(new_lines)
    
    return changes

target_files = [
    'domain/services/cu_service.py',
    'domain/services/notification_service.py',
    'domain/services/losses_nt_service.py',
    'domain/services/ai_service.py',
    'domain/services/generation_service.py',
    'domain/services/distribution_service.py',
]

total = 0
for fp in target_files:
    p = Path(fp)
    if p.exists():
        c = fix_file(p)
        if c > 0:
            print(f"✅ {p.name}: {c} cambios")
            total += c
        else:
            print(f"➖ {p.name}: sin cambios")

print(f"\n📊 Total: {total} cambios")
