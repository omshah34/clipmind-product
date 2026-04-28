"""File: services/token_manager.py
Purpose: Centralized OAuth2 token management with JIT refresh logic.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from services.data_providers.encryption import SecretManager
from db.repositories.users import get_platform_credentials, save_platform_credentials
from core.config import settings

logger = logging.getLogger(__name__)

class IntegrationExpiredError(Exception):
    """Raised when an integration token is expired and cannot be refreshed."""
    pass

class TokenManager:
    """Manages decryption and JIT refreshing of platform tokens."""

    @classmethod
    def get_valid_token(cls, user_id: str, platform: str) -> str | tuple[str, str]:
        """
        Retrieve a valid access token for a platform.
        Refreshes automatically if expired or near expiry.
        """
        db_creds = get_platform_credentials(user_id, platform)
        if not db_creds or not db_creds.get("is_active"):
            raise IntegrationExpiredError(f"No active integration found for {platform}")

        # Decrypt tokens
        access_token = SecretManager.decrypt(db_creds.get("access_token_encrypted"))
        refresh_token = SecretManager.decrypt(db_creds.get("refresh_token_encrypted"))
        
        if platform == "youtube":
            return cls._handle_youtube_refresh(user_id, access_token, refresh_token, db_creds)
        elif platform == "tiktok":
            # TikTok refresh logic will be added in Phase 2
            open_id = db_creds.get("account_id") or db_creds.get("account_name") or ""
            if not open_id:
                raise IntegrationExpiredError("TikTok account identifier missing.")
            return access_token, str(open_id)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    @classmethod
    def _handle_youtube_refresh(
        cls, 
        user_id: str, 
        access_token: str | None, 
        refresh_token: str | None, 
        db_creds: dict
    ) -> str:
        """Specific JIT refresh logic for Google/YouTube OAuth2."""
        scopes = db_creds.get("scopes", "").split(",") if db_creds.get("scopes") else []
        
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            scopes=scopes
        )

        # Check if expired or near expiry (5 minute buffer)
        is_near_expiry = False
        if creds.expiry:
            is_near_expiry = creds.expiry < datetime.now(timezone.utc) + timedelta(minutes=5)
        
        if creds.expired or is_near_expiry:
            if not refresh_token:
                logger.error("[token_manager] No refresh token available for user %s", user_id)
                raise IntegrationExpiredError("YouTube session expired and no refresh token available.")

            logger.info("[token_manager] Refreshing YouTube token for user %s", user_id)
            try:
                creds.refresh(Request())
                # Save new token back to DB
                save_platform_credentials(
                    user_id=user_id,
                    platform="youtube",
                    access_token_encrypted=SecretManager.encrypt(creds.token),
                    refresh_token_encrypted=db_creds.get("refresh_token_encrypted"), # Keep old encrypted refresh
                    expires_at=creds.expiry,
                    account_id=db_creds.get("account_id"),
                    account_name=db_creds.get("account_name"),
                    scopes=scopes
                )
            except Exception as e:
                logger.error("[token_manager] YouTube token refresh failed: %s", e)
                raise IntegrationExpiredError(f"Failed to refresh YouTube integration: {str(e)}")

        return creds.token
