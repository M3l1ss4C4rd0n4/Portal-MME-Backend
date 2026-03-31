#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    SETUP SECRETS - MIGRACIÓN DE CREDENCIALES                  ║
║                                                                               ║
║  Script para migrar secrets de .env (texto plano) a .env.vault (cifrado)     ║
║  Fase 1 - Seguridad Crítica                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Uso:
    cd /home/admonctrlxm/server
    python3 scripts/setup_secrets.py

El script:
    1. Genera clave de cifrado maestra (.vault_key)
    2. Migra secrets de .env a .env.vault (cifrado)
    3. Crea .env.new con placeholders
    4. Valida la migración
    5. Muestra instrucciones para completar
"""

import sys
import os
from pathlib import Path

# Asegurar que el proyecto está en path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.secrets import SecretManager, VAULT_FILE, KEY_FILE, ENV_FILE


def print_header(text):
    """Imprime header formateado."""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)


def print_success(text):
    print(f"  ✅ {text}")


def print_warning(text):
    print(f"  ⚠️  {text}")


def print_error(text):
    print(f"  ❌ {text}")


def print_info(text):
    print(f"  ℹ️  {text}")


def main():
    print_header("SETUP SECRETS - MIGRACIÓN DE CREDENCIALES")
    
    # Verificar que existe .env
    if not ENV_FILE.exists():
        print_error(f"No se encontró archivo .env en {ENV_FILE}")
        print_info("Crea un archivo .env con las variables necesarias primero")
        sys.exit(1)
    
    print_success(f"Archivo .env encontrado: {ENV_FILE}")
    
    # Paso 1: Inicializar SecretManager (genera clave si no existe)
    print_header("PASO 1: Generando clave de cifrado maestra")
    
    try:
        sm = SecretManager()
        print_success(f"SecretManager inicializado")
        
        if KEY_FILE.exists():
            print_info(f"Clave existente: {KEY_FILE}")
            print_warning("IMPORTANTE: Si pierdes este archivo, NO podrás recuperar los secrets")
        else:
            print_success(f"Nueva clave generada: {KEY_FILE}")
            print_warning("IMPORTANTE: Haz backup de .vault_key inmediatamente!")
            
    except Exception as e:
        print_error(f"Error inicializando SecretManager: {e}")
        sys.exit(1)
    
    # Paso 2: Migrar secrets
    print_header("PASO 2: Migrando secrets desde .env")
    
    secrets_to_migrate = [
        'GROQ_API_KEY',
        'OPENROUTER_API_KEY', 
        'OPENROUTER_BASE_URL',
        'GNEWS_API_KEY',
        'MEDIASTACK_API_KEY',
        'TELEGRAM_BOT_TOKEN',
        'SMTP_PASSWORD',
        'POSTGRES_PASSWORD',
        'API_KEY'
    ]
    
    try:
        results = sm.migrate_from_env(ENV_FILE, secrets_to_migrate)
        
        migrated = [k for k, v in results.items() if v]
        failed = [k for k, v in results.items() if not v]
        
        if migrated:
            print_success(f"Migrados exitosamente: {len(migrated)}")
            for key in migrated:
                print_info(f"  - {key}")
        
        if failed:
            print_error(f"Fallaron: {len(failed)}")
            for key in failed:
                print_info(f"  - {key}")
        
        # También migrar otras variables que parecen secrets
        env_content = ENV_FILE.read_text()
        for line in env_content.split('\n'):
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                
                # Detectar posibles secrets por nombre
                keywords = ['KEY', 'TOKEN', 'PASSWORD', 'SECRET', 'API']
                if any(kw in key.upper() for kw in keywords) and key not in secrets_to_migrate:
                    if value and len(value) > 5:
                        try:
                            sm.set_secret(key, value)
                            print_success(f"Migrado adicional: {key}")
                        except Exception as e:
                            print_error(f"Error migrando {key}: {e}")
        
    except Exception as e:
        print_error(f"Error en migración: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Paso 3: Crear .env.new
    print_header("PASO 3: Creando .env.new (sin secrets)")
    
    try:
        env_new_content = """# Portal Energético MME - Variables de Entorno
# NOTA: Secrets sensibles ahora están en .env.vault (cifrado)
# La clave de descifrado está en .vault_key (NO versionar)

# PostgreSQL Database (solo host/port, no password)
USE_POSTGRES=True
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=portal_energetico
POSTGRES_USER=postgres
# POSTGRES_PASSWORD ahora está en vault

# Configuración del Dashboard
DASH_DEBUG=False
DASH_PORT=8050

# Redis (broker Celery + cache API)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
# REDIS_PASSWORD ahora está en vault (si aplica)

# Cargos regulados CREG (no sensibles, se mantienen aquí)
CARGO_TRANSMISION_COP_KWH=8.5
CARGO_DISTRIBUCION_COP_KWH=35.0
CARGO_COMERCIALIZACION_COP_KWH=12.0
FACTOR_PERDIDAS_DISTRIBUCION=0.085

# TRM de referencia
TRM_REF_COP_USD=4200.0

# API Node.js (para integración)
API_ENERGIA_URL=http://localhost:3000

# Configuración Email (solo servidor, no password)
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SMTP_USER="portal.energetico@minenergia.gov.co"
EMAIL_FROM_NAME="Portal Energético MME"
# SMTP_PASSWORD ahora está en vault

# WhatsApp Bot Integration
WHATSAPP_BOT_URL=http://localhost:8001
WHATSAPP_BOT_TIMEOUT=10

# Email destinatarios (públicos)
VICEMINISTRO_EMAIL=vjpaternina@minenergia.gov.co
DIRECTOR_EMAIL=direccion.energia@minenergia.gov.co

# MLflow Basic Auth (solo si aplica)
# MLFLOW_ADMIN_PASSWORD ahora está en vault

# Clave de vault (solo para desarrollo local, en prod usar variable de entorno)
# VAULT_KEY=<clave de .vault_key>
"""
        
        env_new_path = PROJECT_ROOT / ".env.new"
        env_new_path.write_text(env_new_content)
        os.chmod(env_new_path, 0o600)
        
        print_success(f"Creado: {env_new_path}")
        
    except Exception as e:
        print_error(f"Error creando .env.new: {e}")
        sys.exit(1)
    
    # Paso 4: Validación
    print_header("PASO 4: Validando migración")
    
    try:
        # Verificar que vault existe y tiene contenido
        if VAULT_FILE.exists() and VAULT_FILE.stat().st_size > 0:
            print_success(f"Vault cifrado creado: {VAULT_FILE}")
        else:
            print_error("Vault no se creó correctamente")
            sys.exit(1)
        
        # Verificar que podemos leer secrets
        secrets_in_vault = sm.list_secrets()
        print_info(f"Secrets en vault: {len(secrets_in_vault)}")
        for secret_name in secrets_in_vault[:5]:
            value = sm.get_secret(secret_name)
            masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "****"
            print_info(f"  - {secret_name}: {masked}")
        
        if len(secrets_in_vault) > 5:
            print_info(f"  ... y {len(secrets_in_vault) - 5} más")
        
        # Verificar permisos
        vault_perms = oct(VAULT_FILE.stat().st_mode)[-3:]
        key_perms = oct(KEY_FILE.stat().st_mode)[-3:]
        
        if vault_perms == '600':
            print_success(f"Permisos vault correctos: {vault_perms}")
        else:
            print_warning(f"Permisos vault: {vault_perms} (debería ser 600)")
            os.chmod(VAULT_FILE, 0o600)
        
        if key_perms == '600':
            print_success(f"Permisos key correctos: {key_perms}")
        else:
            print_warning(f"Permisos key: {key_perms} (debería ser 600)")
            os.chmod(KEY_FILE, 0o600)
        
    except Exception as e:
        print_error(f"Error en validación: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Resumen final
    print_header("MIGRACIÓN COMPLETADA")
    
    print_success("Secrets migrados exitosamente al vault cifrado")
    print_info("")
    print_info("ARCHIVOS IMPORTANTES:")
    print_info(f"  - Vault cifrado:     {VAULT_FILE}")
    print_info(f"  - Clave maestra:     {KEY_FILE} (GUARDAR BACKUP)")
    print_info(f"  - Nuevo .env:        {env_new_path}")
    print_info("")
    print_warning("PASOS FINALES MANUALES:")
    print_warning("  1. Haz backup de .vault_key en lugar seguro (ej: password manager)")
    print_warning("  2. Reemplaza .env con .env.new:  mv .env.new .env")
    print_warning("  3. Asegúrate de que .vault_key está en .gitignore")
    print_warning("  4. Prueba que la aplicación arranca: python -c 'from core.config import settings'")
    print_warning("  5. Una vez confirmado, elimina .env.backup.* antiguos")
    print_info("")
    print_info("Para rotar credenciales en el futuro:")
    print_info("  python scripts/rotate_credentials.py")


if __name__ == "__main__":
    main()
