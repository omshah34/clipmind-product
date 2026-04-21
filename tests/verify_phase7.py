"""File: tests/verify_phase7.py
Purpose: Automated verification of Phase 7: Real Platform Integration.
         Tests: Encryption, Provider Logic, Token Refresh, and Engine Routing.
"""

import sys
import os
import json
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.data_providers.encryption import SecretManager
from services.data_providers.youtube_provider import YoutubeProvider, PlatformQuotaError
from services.data_providers.tiktok_provider import TikTokProvider
from services.performance_engine import PerformanceEngine
from db.queries import save_platform_credentials, get_platform_credentials, engine
from sqlalchemy import text

def test_encryption():
    print("\n--- Testing Encryption Security ---")
    secret = "sk_test_token_123"
    encrypted = SecretManager.encrypt(secret)
    print(f"Encrypted token: {encrypted[:10]}...")
    assert encrypted != secret
    decrypted = SecretManager.decrypt(encrypted)
    print(f"Decrypted token: {decrypted}")
    assert decrypted == secret
    print("OK: Encryption identity verified.")

def test_youtube_provider_refresh():
    print("\n--- Testing YouTube JIT Refresh ---")
    user_id = str(uuid4())
    
    # 1. Setup expired credentials
    save_platform_credentials(
        user_id=user_id, platform="youtube",
        access_token_encrypted=SecretManager.encrypt("old_token"),
        refresh_token_encrypted=SecretManager.encrypt("refresh_001"),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        account_id="yt_unit_test", account_name="Test Creator", scopes=["youtube.readonly"]
    )
    
    provider = YoutubeProvider()
    
    # 2. Patch the Credentials class
    with patch("services.data_providers.youtube_provider.Credentials") as MockCreds:
        # Configure the mock instance
        mock_creds_instance = MockCreds.return_value
        mock_creds_instance.expired = True
        mock_creds_instance.expiry = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_creds_instance.token = "old_token"
        
        # Define refresh behavior
        def side_effect(request):
            mock_creds_instance.token = "new_refreshed_token"
            mock_creds_instance.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            mock_creds_instance.expired = False
            
        mock_creds_instance.refresh.side_effect = side_effect
        
        # Execute refresh logic
        creds_obj = provider._get_user_credentials(user_id)
        
        print(f"New Token: {creds_obj.token}")
        assert creds_obj.token == "new_refreshed_token"
        
        # Verify DB update
        updated_db = get_platform_credentials(user_id, "youtube")
        decrypted_new = SecretManager.decrypt(updated_db["access_token_encrypted"])
        print(f"DB Token: {decrypted_new}")
        assert decrypted_new == "new_refreshed_token"

    print("OK: YouTube JIT Refresh verified.")

def test_engine_revocation():
    print("\n--- Testing Engine Revocation (401 Handling) ---")
    user_id = str(uuid4())
    engine_obj = PerformanceEngine()
    
    save_platform_credentials(
        user_id=user_id, platform="youtube",
        access_token_encrypted=SecretManager.encrypt("will_fail"),
        account_id="yt_fail", account_name="Failing Account", scopes=[]
    )
    
    mock_provider = MagicMock()
    mock_provider.fetch_metrics_for_user.side_effect = Exception("401 Unauthorized: token revoked")
    mock_provider.platform_name = "youtube"
    
    with patch.object(engine_obj, "_get_provider_for_user", return_value=mock_provider):
        try:
            engine_obj.sync_clip_performance(
                user_id=user_id, job_id="job_1", clip_index=0,
                platform="youtube", platform_clip_id="vid_1",
                predicted_score=0.5, provider=mock_provider
            )
        except Exception:
            pass
            
    creds = get_platform_credentials(user_id, "youtube")
    print(f"Connection Active: {creds['is_active']}")
    assert creds["is_active"] is False
    assert "401" in creds["last_error"]
    print("OK: Engine handles revocation.")

def test_tiktok_mock_sync():
    print("\n--- Testing TikTok Scraper (Mocked) ---")
    provider = TikTokProvider()
    with patch("services.data_providers.tiktok_provider.TikTokApi") as mock_api:
        mock_instance = mock_api.return_value.__enter__.return_value
        mock_video = mock_instance.video.return_value
        mock_video.info_full.return_value = {
            "stats": {"playCount": 1000, "diggCount": 100, "shareCount": 10, "commentCount": 5}
        }
        with patch("services.data_providers.tiktok_provider.settings") as mock_settings:
            mock_settings.tiktok_session_id = "real_session_id"
            metrics = provider.fetch_metrics("vid_tiktok")
            
        print(f"TikTok Views: {metrics.views}")
        assert metrics.views == 1000
    print("OK: TikTok scraper logic verified.")

if __name__ == "__main__":
    try:
        test_encryption()
        test_youtube_provider_refresh()
        test_engine_revocation()
        test_tiktok_mock_sync()
        print("\nSUMMARY: PHASE 7 VERIFICATION SUCCESSFUL")
    except Exception as e:
        print(f"\n[X] VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
