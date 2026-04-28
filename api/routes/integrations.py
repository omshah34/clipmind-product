from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from api.dependencies import get_current_user, AuthenticatedUser
from db.connection import engine
from db.repositories.users import (
    save_platform_credentials,
    delete_platform_credentials,
)
from sqlalchemy import text
from services.data_providers.encryption import SecretManager
from core.config import settings
import logging

logger = logging.getLogger(__name__)

integrations_router = APIRouter(prefix="/integrations", tags=["integrations"])


@integrations_router.get("/")
def list_integrations(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """List all connected platforms and their status."""
    user_id = str(user.user_id)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT platform, account_name, is_active, last_error, synced_at FROM platform_credentials WHERE user_id = :u"),
            {"u": user_id}
        ).fetchall()
    
    return {
        "integrations": [
            {
                "platform": r.platform,
                "account_name": r.account_name,
                "is_active": r.is_active,
                "last_error": r.last_error,
                "last_sync": r.synced_at
            } for r in rows
        ]
    }


@integrations_router.get("/{platform}/connect")
def connect_platform(platform: str, user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Get the OAuth authorization URL for a platform."""
    user_id = str(user.user_id)
    if platform == "youtube":
        # Standard Google OAuth2 URL construction
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": settings.youtube_client_id,
            "redirect_uri": f"{settings.frontend_url}/api/integrations/youtube/callback",
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "state": user_id 
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return {"url": f"{base_url}?{query_string}"}
    
    raise HTTPException(status_code=400, detail=f"OAuth not yet implemented for {platform}")

@integrations_router.post("/{platform}/refresh")
def refresh_platform_token(platform: str, user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Force a token refresh for a platform."""
    from services.token_manager import TokenManager
    user_id = str(user.user_id)
    try:
        new_token = TokenManager.get_valid_token(user_id, platform)
        return {"status": "success", "message": f"{platform} token refreshed"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@integrations_router.delete("/{platform}")
def disconnect_platform(platform: str, user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Revoke access and delete credentials for a platform."""
    user_id = str(user.user_id)
    success = delete_platform_credentials(user_id, platform)
    if not success:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    return {"status": "success", "message": f"Disconnected {platform}"}


@integrations_router.get("/{platform}/callback")
def oauth_callback(
    platform: str, 
    code: str, 
    state: str,
    user: AuthenticatedUser = Depends(get_current_user)
) -> dict:
    """
    Handle the OAuth redirect callback.
    Exchanges code for tokens and saves them encrypted.
    """
    user_id = str(user.user_id)
    
    if platform == "youtube":
        import requests
        
        # 1. Exchange code for token
        logger.info("[oauth] Exchanging code for tokens: %s", platform)
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "redirect_uri": f"{settings.frontend_url}/api/integrations/youtube/callback",
            "grant_type": "authorization_code",
        }
        
        response = requests.post(token_url, data=data)
        if not response.ok:
            logger.error("[oauth] YouTube token exchange failed: %s", response.text)
            raise HTTPException(status_code=400, detail="YouTube token exchange failed")
            
        token_data = response.json()
        
        # 2. Extract and Save credentials
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        
        # Fetch account info (optional but good for UI)
        account_name = "YouTube Channel"
        account_id = "yt_user" # Placeholder
        
        save_platform_credentials(
            user_id=user_id,
            platform="youtube",
            access_token_encrypted=SecretManager.encrypt(access_token),
            refresh_token_encrypted=SecretManager.encrypt(refresh_token) if refresh_token else None,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            account_id=account_id,
            account_name=account_name,
            scopes=token_data.get("scope", "").split(" ")
        )
        
        # 3. Trigger immediate sync to populate initial data
        from workers.analytics import sync_all_active_performance
        sync_all_active_performance.delay()
        
        return {"status": "success", "message": "YouTube connected successfully"}

    raise HTTPException(status_code=400, detail="Unsupported platform callback")
