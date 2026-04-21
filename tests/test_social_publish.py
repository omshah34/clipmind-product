import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from workers.publish_social import publish_to_platform
from services.youtube_publisher import YouTubeApiError

@patch("workers.publish_social.TokenManager.get_valid_token")
@patch("workers.publish_social.celery_app")
@patch.object(Path, "exists", return_value=True)
@patch.object(Path, "stat")
def test_publish_token_unavailable(mock_stat, mock_exists, mock_celery, mock_get_token):
    mock_get_token.return_value = None
    
    result = publish_to_platform.apply(args=[
        "user_123", "job_abc", 0, "youtube", "acc_999", "Cool clip!"
    ]).result
    
    assert result["status"] == "failed"
    assert result["error_code"] == "token_unavailable"

@patch("workers.publish_social.TokenManager.get_valid_token")
@patch("workers.publish_social.upload_to_youtube")
@patch.object(Path, "exists", return_value=True)
@patch.object(Path, "stat")
def test_youtube_publish_success(mock_stat, mock_exists, mock_upload, mock_get_token):
    mock_get_token.return_value = "fake_token"
    mock_upload.return_value = {"id": "yt_vid_123", "url": "https://youtu.be/123"}
    
    result = publish_to_platform.apply(args=[
        "user_123", "job_abc", 0, "youtube", "acc_999", "Cool clip!"
    ]).result
    
    assert result["status"] == "published"
    assert result["platform_id"] == "yt_vid_123"
    assert result["url"] == "https://youtu.be/123"

@patch("workers.publish_social.TokenManager.get_valid_token")
@patch("workers.publish_social.upload_to_youtube")
@patch.object(Path, "exists", return_value=True)
@patch.object(Path, "stat")
def test_youtube_quota_exceeded(mock_stat, mock_exists, mock_upload, mock_get_token):
    mock_get_token.return_value = "fake_token"
    mock_upload.side_effect = YouTubeApiError("Quota exceeded", error_code="quotaExceeded")
    
    result = publish_to_platform.apply(args=[
        "user_123", "job_abc", 0, "youtube", "acc_999", "Cool clip!"
    ]).result
    
    assert result["status"] == "failed"
    assert result["error_code"] == "youtube_quota_exceeded"

@patch("workers.publish_social.TokenManager.get_valid_token")
@patch("workers.publish_social.upload_to_tiktok")
@patch.object(Path, "exists", return_value=True)
@patch.object(Path, "stat")
def test_tiktok_publish_success(mock_stat, mock_exists, mock_upload, mock_get_token):
    mock_get_token.return_value = ("fake_token", "fake_openid")
    mock_stat.return_value.st_size = 1000000
    mock_upload.return_value = {"id": "tt_vid_789", "url": "https://tiktok.com/789"}
    
    result = publish_to_platform.apply(args=[
        "user_123", "job_abc", 0, "tiktok", "acc_789", "Tiktok clip!"
    ]).result
    
    assert result["status"] == "published"
    # Verify both token and open_id were passed
    args = mock_upload.call_args[0]
    assert "fake_token" in args or any("fake_token" in str(arg) for arg in args)
    assert "fake_openid" in args or any("fake_openid" in str(arg) for arg in args)
