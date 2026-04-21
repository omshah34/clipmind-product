"""File: services/data_providers/encryption.py
Purpose: encryption utility for securing platform OAuth tokens at rest.
"""

from __future__ import annotations
import logging
from cryptography.fernet import Fernet
from core.config import settings

logger = logging.getLogger(__name__)

class SecretManager:
    """Manages encryption and decryption of sensitive platform credentials."""
    
    _fernet: Fernet | None = None

    @classmethod
    def _get_fernet(cls) -> Fernet:
        """Initialize Fernet lazily with the key from settings."""
        if cls._fernet is None:
            key = settings.fernet_key
            if not key:
                logger.error("[security] No FERNET_KEY found in settings. Encryption will fail.")
                raise ValueError("Missing FERNET_KEY in environment.")
            
            try:
                cls._fernet = Fernet(key.encode())
            except Exception as e:
                logger.error("[security] Invalid FERNET_KEY format: %s", e)
                raise
        return cls._fernet

    @classmethod
    def encrypt(cls, plain_text: str | None) -> str | None:
        """Encrypt a string. Returns None if input is None."""
        if plain_text is None:
            return None
        
        f = cls._get_fernet()
        return f.encrypt(plain_text.encode()).decode()

    @classmethod
    def decrypt(cls, encrypted_text: str | None) -> str | None:
        """Decrypt a string. Returns None if input is None."""
        if encrypted_text is None:
            return None
        
        f = cls._get_fernet()
        try:
            return f.decrypt(encrypted_text.encode()).decode()
        except Exception as e:
            logger.error("[security] Decryption failed: %s", e)
            return None
