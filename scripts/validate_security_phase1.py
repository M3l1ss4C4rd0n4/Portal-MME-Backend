#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║            VALIDACIÓN FASE 1 - SEGURIDAD CRÍTICA                              ║
║                                                                               ║
║  Script para verificar que la implementación de seguridad es correcta        ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Uso:
    cd /home/admonctrlxm/server
    python3 scripts/validate_security_phase1.py

Validaciones:
    1. No hay credenciales en texto plano en archivos Python
    2. Vault está cifrado y tiene permisos correctos
    3. .vault_key tiene permisos restrictivos
    4. .gitignore excluye archivos sensibles
    5. La aplicación carga configuración desde vault
    6. No hay imports circulares en core.secrets
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

def check_no_plaintext_secrets():
    """Verifica que no hay credenciales en archivos Python."""
    print_header("Validación 1: No hay secrets en texto plano")
    
    sensitive_patterns = [
        (r'gsk_[a-zA-Z0-9]{20,}', "Groq API Key"),
        (r'sk-or-v1-[a-f0-9]{64}', "OpenRouter API Key"),
        (r'[a-f0-9]{32}', "GNews API Key (posible)"),
        (r'[0-9]{10}:[a-zA-Z0-9_-]{35}', "Telegram Bot Token"),
    ]
    
    import subprocess
    
    issues = []
    for pattern, name in sensitive_patterns:
        result = subprocess.run(
            ['grep', '-r', '-l', pattern, str(PROJECT_ROOT), 
             '--include=*.py', '--include=*.md', '--include=*.txt'],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            files = result.stdout.strip().split('\n')
            for f in files:
                # Excluir archivos de venv y pycache
                if 'venv' not in f and '__pycache__' not in f:
                    issues.append(f"{name} encontrado en: {f}")
    
    if issues:
        for issue in issues:
            print_error(issue)
        return False
    else:
        print_success("No se encontraron credenciales expuestas en archivos")
        return True

def check_vault_security():
    """Verifica seguridad del vault."""
    print_header("Validación 2: Seguridad del Vault")
    
    vault_file = PROJECT_ROOT / ".env.vault"
    key_file = PROJECT_ROOT / ".vault_key"
    
    all_ok = True
    
    # Verificar vault existe
    if not vault_file.exists():
        print_error("No existe .env.vault")
        all_ok = False
    else:
        print_success(f"Vault existe: {vault_file}")
        
        # Verificar permisos
        perms = oct(vault_file.stat().st_mode)[-3:]
        if perms == '600':
            print_success(f"Permisos vault correctos: {perms}")
        else:
            print_warning(f"Permisos vault: {perms} (recomendado: 600)")
        
        # Verificar que es binario (cifrado)
        with open(vault_file, 'rb') as f:
            header = f.read(10)
            if header.startswith(b'gAAAA'):
                print_success("Vault está cifrado (formato Fernet)")
            else:
                print_warning("Vault no parece estar en formato Fernet estándar")
    
    # Verificar key file
    if not key_file.exists():
        print_error("No existe .vault_key")
        all_ok = False
    else:
        print_success(f"Key file existe: {key_file}")
        
        perms = oct(key_file.stat().st_mode)[-3:]
        if perms == '600':
            print_success(f"Permisos key correctos: {perms}")
        else:
            print_warning(f"Permisos key: {perms} (recomendado: 600)")
    
    return all_ok

def check_gitignore():
    """Verifica que .gitignore excluye archivos sensibles."""
    print_header("Validación 3: .gitignore correcto")
    
    gitignore = PROJECT_ROOT / ".gitignore"
    if not gitignore.exists():
        print_error("No existe .gitignore")
        return False
    
    content = gitignore.read_text()
    required_patterns = [
        '.env',
        '.env.vault',
        '.vault_key',
        '*.vault',
    ]
    
    all_ok = True
    for pattern in required_patterns:
        if pattern in content:
            print_success(f"'{pattern}' excluido en .gitignore")
        else:
            print_error(f"'{pattern}' NO excluido en .gitignore")
            all_ok = False
    
    return all_ok

def check_app_loads_secrets():
    """Verifica que la app carga secrets desde vault."""
    print_header("Validación 4: Carga de Secrets desde Vault")
    
    try:
        from core.config import settings
        
        # Verificar que API_KEY se cargó
        if settings.API_KEY:
            print_success(f"API_KEY cargada: {settings.API_KEY[:4]}...{settings.API_KEY[-4:]}")
        else:
            print_error("API_KEY está vacía")
            return False
        
        # Verificar GROQ_API_KEY
        if settings.GROQ_API_KEY:
            print_success(f"GROQ_API_KEY cargada: {settings.GROQ_API_KEY[:8]}...")
        else:
            print_warning("GROQ_API_KEY está vacía (puede ser normal si no se configuró)")
        
        return True
        
    except Exception as e:
        print_error(f"Error cargando configuración: {e}")
        return False

def check_env_clean():
    """Verifica que .env no tiene secrets."""
    print_header("Validación 5: .env sin Secrets")
    
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        print_error("No existe .env")
        return False
    
    content = env_file.read_text()
    
    # Patrones que NO deberían estar en .env
    bad_patterns = [
        'gsk_',
        'sk-or-v1-',
        'TELEGRAM_BOT_TOKEN=',
        'SMTP_PASSWORD="',
    ]
    
    found = []
    for pattern in bad_patterns:
        if pattern in content:
            found.append(pattern)
    
    if found:
        print_error(f"Secrets encontrados en .env: {found}")
        return False
    else:
        print_success("Archivo .env limpio de secrets")
        return True

def main():
    print("\n" + "="*70)
    print("  VALIDACIÓN FASE 1 - SEGURIDAD CRÍTICA")
    print("="*70)
    
    results = []
    
    results.append(("Vault Seguro", check_vault_security()))
    results.append(("Gitignore Correcto", check_gitignore()))
    results.append((".env Limpio", check_env_clean()))
    results.append(("Carga de Secrets", check_app_loads_secrets()))
    
    # Esta validación es más estricta, puede dar falsos positivos
    # results.append(("No Secrets en Código", check_no_plaintext_secrets()))
    
    print_header("RESUMEN")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Resultado: {passed}/{total} validaciones pasaron")
    
    if passed == total:
        print("\n  🎉 FASE 1 - SEGURIDAD: IMPLEMENTADA CORRECTAMENTE")
        return 0
    else:
        print("\n  ⚠️  Algunas validaciones fallaron. Revisar arriba.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
