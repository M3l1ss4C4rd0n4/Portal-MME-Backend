#!/usr/bin/env python3
"""
Script para hacer seguimiento del progreso de calidad del código.

Mide métricas clave como:
- SQL injection potenciales
- except Exception genéricos
- Imports ilegítimos Domain→Infrastructure
- Cobertura de tests
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime


def run_grep(pattern: str, path: str = ".", exclude_dirs=None) -> int:
    """Ejecuta grep y cuenta resultados."""
    exclude_dirs = exclude_dirs or ['venv', '__pycache__', '.git', 'htmlcov']
    
    cmd = ['grep', '-r', pattern, '--include=*.py', path]
    for d in exclude_dirs:
        cmd.extend(['--exclude-dir', d])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        lines = [l for l in result.stdout.split('\n') if l.strip()]
        return len(lines), lines
    except Exception:
        return 0, []


def check_sql_injection() -> dict:
    """Busca potenciales SQL injection."""
    count, lines = run_grep('execute.*f"')
    
    # Filtrar solo los de nuestro código (no venv)
    our_code = [l for l in lines if not l.startswith('./venv/')]
    
    return {
        'total': len(our_code),
        'details': our_code[:10]  # Primeros 10
    }


def check_except_exception() -> dict:
    """Cuenta except Exception genéricos."""
    count, lines = run_grep('except Exception', 'domain/')
    return {
        'total': count,
        'by_file': {}
    }


def check_domain_infra_imports() -> dict:
    """Cuenta imports ilegítimos Domain→Infrastructure."""
    count, lines = run_grep('from infrastructure', 'domain/')
    return {
        'total': count,
        'details': lines[:10]
    }


def check_direct_db_connections() -> dict:
    """Cuenta conexiones directas psycopg2."""
    count, lines = run_grep('psycopg2.connect')
    our_code = [l for l in lines if not l.startswith('./venv/')]
    # Excluir connection_manager que es la forma correcta
    direct = [l for l in our_code if 'connection_manager' not in l]
    return {
        'total': len(direct),
        'details': direct[:10]
    }


def generate_report():
    """Genera reporte de calidad."""
    print("=" * 80)
    print(" 📊 REPORTE DE CALIDAD DEL CÓDIGO - Portal Energético MME")
    print("=" * 80)
    print(f" Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # SQL Injection
    sql = check_sql_injection()
    print(f" 🔴 SQL Injection potenciales: {sql['total']}")
    if sql['details']:
        print("    Detalles:")
        for d in sql['details'][:5]:
            print(f"      - {d[:70]}...")
    print()
    
    # except Exception
    exc = check_except_exception()
    print(f" 🟡 except Exception genéricos: {exc['total']}")
    print()
    
    # Domain→Infrastructure imports
    imp = check_domain_infra_imports()
    print(f" 🟠 Imports Domain→Infrastructure: {imp['total']}")
    if imp['details']:
        print("    Ejemplos:")
        for d in imp['details'][:5]:
            print(f"      - {d[:70]}")
    print()
    
    # Direct DB connections
    db = check_direct_db_connections()
    print(f" 🟢 Conexiones DB directas: {db['total']}")
    print()
    
    print("=" * 80)
    print(" RESUMEN DE METAS:")
    print("=" * 80)
    print(f"   SQL Injection:      {sql['total']:>4} / 0     {'✅' if sql['total'] == 0 else '⚠️'}")
    print(f"   except Exception:   {exc['total']:>4} / <20   {'✅' if exc['total'] < 20 else '⚠️'}")
    print(f"   Domain→Infra:       {imp['total']:>4} / 0     {'✅' if imp['total'] == 0 else '⚠️'}")
    print(f"   Conexiones directas: {db['total']:>3} / 0     {'✅' if db['total'] == 0 else '⚠️'}")
    print("=" * 80)


if __name__ == "__main__":
    generate_report()
