"""File: api/routes/oauth.py
Purpose: OAuth authorization flow for TikTok and YouTube publishing integration.
         Creates/Updates ConnectedAccounts (`social_accounts` table).
"""

import os
from uuid import uuid4
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from api.dependencies.auth import AuthenticatedUser, get_current_user
from db.connection import engine

router = APIRouter(prefix="/oauth", tags=["oauth"])

def _frontend_base() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    
def _api_base() -> str:
    return os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

@router.get("/{platform}/authorize")
def authorize_platform(
    platform: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Step 1: Redirect user to the OAuth provider (TikTok or YouTube)
    """
    state_token = f"{user.user_id}::{uuid4().hex}"
    
    if platform == "tiktok":
        client_key = os.getenv("TIKTOK_CLIENT_KEY", "tiktok_mock_key")
        redirect_uri = f"{_api_base()}/oauth/tiktok/callback"
        auth_url = f"https://www.tiktok.com/v2/auth/authorize/?client_key={client_key}&response_type=code&scope=video.publish,user.info.basic&redirect_uri={redirect_uri}&state={state_token}"
        return RedirectResponse(auth_url)
    
    elif platform == "youtube":
        client_id = os.getenv("YOUTUBE_CLIENT_ID", "youtube_mock_id")
        redirect_uri = f"{_api_base()}/oauth/youtube/callback"
        auth_url = f"https://accounts.google.com/o/oauth2/auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=https://www.googleapis.com/auth/youtube.upload&access_type=offline&state={state_token}"
        return RedirectResponse(auth_url)
    else:
        return {"error": "Unsupported platform."}


@router.get("/{platform}/callback")
def oauth_callback(
    platform: str,
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None)
):
    """
    Step 2: Handle OAuth provider redirect, exchange code for tokens, and store in `social_accounts`.
    """
    if error:
        return RedirectResponse(url=f"{_frontend_base()}/settings/integrations?error={error}")
        
    if not code or not state:
        return RedirectResponse(url=f"{_frontend_base()}/settings/integrations?error=invalid_callback")
        
    try:
        user_id, _ = state.split("::")
    except ValueError:
        return RedirectResponse(url=f"{_frontend_base()}/settings/integrations?error=invalid_state")
        
    # Mock Token Exchange (In production, POST to provider's token endpoint)
    mock_access_token = f"mock_acc_{uuid4().hex[:10]}"
    mock_refresh_token = f"mock_ref_{uuid4().hex[:10]}"
    mock_account_id = f"acct_{uuid4().hex[:8]}"
    
    with engine.begin() as conn:
        _ts = "NOW()" if engine.dialect.name == "postgresql" else "CURRENT_TIMESTAMP"
        conn.execute(
            text(f"""
                INSERT INTO social_accounts 
                (user_id, platform, account_id, account_username, access_token_encrypted, refresh_token_encrypted, is_connected)
                VALUES (:user_id, :platform, :acct_id, :username, :acc_tok, :ref_tok, 1)
                ON CONFLICT (user_id, platform, account_id) 
                DO UPDATE SET 
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
                    is_connected = 1,
                    updated_at = {_ts}
            """),
            {
                "user_id": user_id,
                "platform": platform,
                "acct_id": mock_account_id,
                "username": f"{platform}_user_{mock_account_id[-4:]}",
                "acc_tok": mock_access_token,
                "ref_tok": mock_refresh_token
            }
        )

    return RedirectResponse(url=f"{_frontend_base()}/dashboard/integrations?success={platform}")
