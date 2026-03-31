"""
Vault - Sistema de gestión de secretos cifrados

Gestiona el cifrado y descifrado de secretos sensibles usando Fernet (AES-128).
Los secretos se almacenan en .env.vault y la clave en .vault_key
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Vault:
    """
    Sistema de vault para gestión segura de secretos.
    
    Uso:
        vault = get_vault()
        password = vault.get_secret('POSTGRES_PASSWORD')
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if Vault._initialized:
            return
            
        self._key: Optional[bytes] = None
        self._fernet: Optional[Fernet] = None
        self._secrets: Dict[str, str] = {}
        self._vault_file = Path('.env.vault')
        self._key_file = Path('.vault_key')
        
        self._load_key()
        self._load_vault()
        Vault._initialized = True
    
    def _load_key(self) -> bool:
        """Carga la clave de cifrado desde .vault_key"""
        try:
            # Intentar desde archivo
            if self._key_file.exists():
                self._key = self._key_file.read_bytes().strip()
                self._fernet = Fernet(self._key)
                logger.debug("✅ Clave de vault cargada desde archivo")
                return True
            
            # Intentar desde variable de entorno
            env_key = os.getenv('VAULT_KEY')
            if env_key:
                self._key = env_key.encode()
                self._fernet = Fernet(self._key)
                logger.debug("✅ Clave de vault cargada desde VAULT_KEY")
                return True
            
            logger.warning("⚠️ No se encontró clave de vault (.vault_key o VAULT_KEY)")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error cargando clave de vault: {e}")
            return False
    
    def _load_vault(self) -> bool:
        """Carga y descifra los secretos desde .env.vault"""
        if not self._fernet:
            return False
        
        try:
            if not self._vault_file.exists():
                logger.warning(f"⚠️ Archivo de vault no encontrado: {self._vault_file}")
                return False
            
            encrypted_data = self._vault_file.read_bytes()
            if not encrypted_data:
                logger.warning("⚠️ Archivo de vault vacío")
                return False
            
            # Descifrar
            decrypted = self._fernet.decrypt(encrypted_data)
            vault_content = decrypted.decode('utf-8')
            
            # Parsear formato KEY=VALUE
            for line in vault_content.strip().split('\n'):
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    self._secrets[key.strip()] = value.strip().strip('"').strip("'")
            
            logger.info(f"✅ Vault cargado: {len(self._secrets)} secretos disponibles")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error descifrando vault: {e}")
            return False
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Obtiene un secreto del vault.
        
        Args:
            key: Nombre del secreto
            default: Valor por defecto si no existe
            
        Returns:
            Valor del secreto o default
        """
        # Primero intentar desde el vault cargado
        if key in self._secrets:
            return self._secrets[key]
        
        # Fallback a variable de entorno
        env_value = os.getenv(key)
        if env_value:
            return env_value
        
        return default
    
    def get_postgres_password(self) -> Optional[str]:
        """Obtiene la contraseña de PostgreSQL"""
        return self.get_secret('POSTGRES_PASSWORD')
    
    def get_smtp_password(self) -> Optional[str]:
        """Obtiene la contraseña SMTP"""
        return self.get_secret('SMTP_PASSWORD')
    
    def get_telegram_token(self) -> Optional[str]:
        """Obtiene el token del bot de Telegram"""
        return self.get_secret('TELEGRAM_BOT_TOKEN')
    
    def is_configured(self) -> bool:
        """Verifica si el vault está configurado correctamente"""
        return self._fernet is not None and len(self._secrets) > 0
    
    def list_secrets(self) -> list:
        """Lista los nombres de secretos disponibles (sin valores)"""
        return list(self._secrets.keys())


# Instancia singleton
_vault_instance = None


def get_vault() -> Vault:
    """Obtiene la instancia singleton del vault"""
    global _vault_instance
    if _vault_instance is None:
        _vault_instance = Vault()
    return _vault_instance


def init_vault() -> bool:
    """Inicializa el vault y carga los secretos"""
    vault = get_vault()
    return vault.is_configured()


# Para uso directo como módulo
if __name__ == '__main__':
    # Test básico
    vault = get_vault()
    print(f"Vault configurado: {vault.is_configured()}")
    print(f"Secretos disponibles: {vault.list_secrets()}")
