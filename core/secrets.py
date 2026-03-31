"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                         SECRET MANAGER MODULE                                 ║
║                                                                               ║
║  Gestión segura de credenciales y API keys usando cifrado Fernet (AES-128)   ║
║  Fase 1 - Seguridad Crítica: Protección de secrets en reposición             ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Uso:
    from core.secrets import SecretManager, get_secret
    
    # Inicializar (automático en primera ejecución)
    sm = SecretManager()
    
    # Guardar secret
    sm.set_secret("GROQ_API_KEY", "gsk_...")
    
    # Recuperar secret
    api_key = get_secret("GROQ_API_KEY")
"""

import os
import base64
from infrastructure.logging.logger import get_logger
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = get_logger(__name__)

# Rutas configurables
VAULT_FILE = Path(__file__).parent.parent / ".env.vault"
KEY_FILE = Path(__file__).parent.parent / ".vault_key"
ENV_FILE = Path(__file__).parent.parent / ".env"


class SecretManager:
    """
    Gestor de secretos con cifrado Fernet.
    
    Los secrets se almacenan en un archivo cifrado (.env.vault)
    y la clave maestra puede estar:
    - En archivo .vault_key (modo desarrollo local)
    - En variable de entorno VAULT_KEY (modo producción)
    """
    
    def __init__(self, vault_path: Optional[Path] = None, key: Optional[str] = None):
        """
        Inicializa el SecretManager.
        
        Args:
            vault_path: Ruta al archivo vault (default: .env.vault)
            key: Clave de cifrado base64 (default: lee de VAULT_KEY o .vault_key)
        """
        self.vault_path = vault_path or VAULT_FILE
        self._key = key or self._load_key()
        self._fernet = Fernet(self._key)
        self._cache: Dict[str, str] = {}
        
    def _load_key(self) -> str:
        """Carga la clave de cifrado desde variable de entorno o archivo."""
        # 1. Intentar desde variable de entorno (producción)
        env_key = os.getenv("VAULT_KEY")
        if env_key:
            return env_key
            
        # 2. Intentar desde archivo (desarrollo local)
        if KEY_FILE.exists():
            key_data = KEY_FILE.read_text().strip()
            if key_data:
                return key_data
        
        # 3. Generar nueva clave (primera ejecución)
        logger.warning("No se encontró clave de vault. Generando nueva...")
        return self._generate_key()
    
    def _generate_key(self) -> str:
        """Genera una nueva clave de cifrado y la guarda."""
        key = Fernet.generate_key().decode()
        
        # Guardar en archivo (con permisos restrictivos)
        KEY_FILE.write_text(key)
        os.chmod(KEY_FILE, 0o600)  # Solo lectura/escritura dueño
        
        logger.info(f"Nueva clave de vault generada y guardada en {KEY_FILE}")
        logger.warning("IMPORTANTE: Haz backup de .vault_key - sin ella no se podrán recuperar los secrets")
        
        return key
    
    def _derive_key_from_password(self, password: str, salt: Optional[bytes] = None) -> tuple:
        """
        Deriva una clave Fernet desde una contraseña usando PBKDF2.
        
        Args:
            password: Contraseña maestra
            salt: Salt opcional (se genera si no se provee)
            
        Returns:
            Tuple (key_base64, salt)
        """
        if salt is None:
            salt = os.urandom(16)
            
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode(), salt
    
    def get_secret(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Recupera un secret del vault.
        
        Args:
            name: Nombre del secret
            default: Valor por defecto si no existe
            
        Returns:
            Valor del secret o default
        """
        # Cache primero
        if name in self._cache:
            return self._cache[name]
        
        # Si no existe vault, retornar default
        if not self.vault_path.exists():
            return default
        
        try:
            encrypted_data = self.vault_path.read_bytes()
            if not encrypted_data:
                return default
                
            decrypted = self._fernet.decrypt(encrypted_data).decode()
            
            # Parsear formato KEY=VALUE
            secrets = {}
            for line in decrypted.strip().split('\n'):
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    secrets[key.strip()] = value.strip()
            
            value = secrets.get(name, default)
            self._cache[name] = value
            return value
            
        except Exception as e:
            logger.error(f"Error leyendo secret '{name}': {e}")
            return default
    
    def set_secret(self, name: str, value: str) -> None:
        """
        Guarda un secret en el vault.
        
        Args:
            name: Nombre del secret
            value: Valor a guardar
        """
        # Leer secrets existentes
        secrets = {}
        if self.vault_path.exists():
            try:
                encrypted_data = self.vault_path.read_bytes()
                if encrypted_data:
                    decrypted = self._fernet.decrypt(encrypted_data).decode()
                    for line in decrypted.strip().split('\n'):
                        if '=' in line and not line.startswith('#'):
                            k, v = line.split('=', 1)
                            secrets[k.strip()] = v.strip()
            except Exception as e:
                logger.warning(f"No se pudo leer vault existente: {e}")
        
        # Actualizar/Agregar
        secrets[name] = value
        
        # Guardar
        lines = [f"# Vault de secrets - Portal Energético MME", f"# Generado: {__import__('datetime').datetime.now().isoformat()}"]
        for k, v in sorted(secrets.items()):
            lines.append(f"{k}={v}")
        
        decrypted_text = '\n'.join(lines)
        encrypted = self._fernet.encrypt(decrypted_text.encode())
        
        self.vault_path.write_bytes(encrypted)
        os.chmod(self.vault_path, 0o600)
        
        # Actualizar cache
        self._cache[name] = value
        
        logger.info(f"Secret '{name}' guardado en vault")
    
    def delete_secret(self, name: str) -> bool:
        """Elimina un secret del vault."""
        secrets = {}
        if self.vault_path.exists():
            try:
                encrypted_data = self.vault_path.read_bytes()
                if encrypted_data:
                    decrypted = self._fernet.decrypt(encrypted_data).decode()
                    for line in decrypted.strip().split('\n'):
                        if '=' in line and not line.startswith('#'):
                            k, v = line.split('=', 1)
                            secrets[k.strip()] = v.strip()
            except Exception as e:
                logger.warning(f"No se pudo leer vault existente: {e}")
        
        if name not in secrets:
            return False
        
        del secrets[name]
        
        # Guardar
        lines = [f"# Vault de secrets - Portal Energético MME"]
        for k, v in sorted(secrets.items()):
            lines.append(f"{k}={v}")
        
        decrypted_text = '\n'.join(lines)
        encrypted = self._fernet.encrypt(decrypted_text.encode())
        
        self.vault_path.write_bytes(encrypted)
        
        # Limpiar cache
        self._cache.pop(name, None)
        
        logger.info(f"Secret '{name}' eliminado del vault")
        return True
    
    def list_secrets(self) -> list:
        """Lista todos los nombres de secrets guardados."""
        if not self.vault_path.exists():
            return []
        
        try:
            encrypted_data = self.vault_path.read_bytes()
            if not encrypted_data:
                return []
            
            decrypted = self._fernet.decrypt(encrypted_data).decode()
            names = []
            for line in decrypted.strip().split('\n'):
                if '=' in line and not line.startswith('#'):
                    names.append(line.split('=', 1)[0].strip())
            return sorted(names)
        except Exception as e:
            logger.error(f"Error listando secrets: {e}")
            return []
    
    def migrate_from_env(self, env_path: Optional[Path] = None, 
                         secrets_to_migrate: Optional[list] = None) -> Dict[str, bool]:
        """
        Migra secrets desde un archivo .env al vault cifrado.
        
        Args:
            env_path: Ruta al archivo .env (default: .env)
            secrets_to_migrate: Lista de nombres a migrar (default: todos los que parecen secrets)
            
        Returns:
            Dict con {nombre: éxito}
        """
        env_path = env_path or ENV_FILE
        
        if not env_path.exists():
            raise FileNotFoundError(f"No existe archivo .env en {env_path}")
        
        # Secrets por defecto a migrar
        if secrets_to_migrate is None:
            secrets_to_migrate = [
                'GROQ_API_KEY', 'OPENROUTER_API_KEY', 'OPENROUTER_BASE_URL',
                'GNEWS_API_KEY', 'MEDIASTACK_API_KEY', 'TELEGRAM_BOT_TOKEN',
                'SMTP_PASSWORD', 'POSTGRES_PASSWORD', 'API_KEY'
            ]
        
        # Leer .env
        env_content = env_path.read_text()
        results = {}
        
        for line in env_content.split('\n'):
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                
                if key in secrets_to_migrate and value:
                    try:
                        self.set_secret(key, value)
                        results[key] = True
                    except Exception as e:
                        logger.error(f"Error migrando {key}: {e}")
                        results[key] = False
        
        return results


# Instancia global (singleton)
_secret_manager: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """Obtiene la instancia global de SecretManager."""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager()
    return _secret_manager


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Función de conveniencia para obtener un secret.
    
    Args:
        name: Nombre del secret
        default: Valor por defecto
        
    Returns:
        Valor del secret o default
    """
    return get_secret_manager().get_secret(name, default)


def set_secret(name: str, value: str) -> None:
    """Función de conveniencia para guardar un secret."""
    get_secret_manager().set_secret(name, value)


# Para compatibilidad con código existente durante migración
class SecretsCompat:
    """
    Clase de compatibilidad que permite transición gradual.
    Primero busca en vault, luego en variable de entorno.
    """
    
    def __init__(self):
        self._sm = get_secret_manager()
    
    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Busca en vault primero, luego en os.environ."""
        # 1. Intentar vault
        value = self._sm.get_secret(name)
        if value:
            return value
        
        # 2. Fallback a variable de entorno
        return os.getenv(name, default)


# Exportar para importación directa
__all__ = [
    'SecretManager',
    'get_secret_manager',
    'get_secret',
    'set_secret',
    'SecretsCompat',
]
