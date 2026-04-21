"""Platform-specific publishing adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.tiktok_publisher import TikTokApiError, upload_to_tiktok
from services.token_manager import IntegrationExpiredError, TokenManager
from services.youtube_publisher import YouTubeApiError, upload_to_youtube


@dataclass(frozen=True)
class PublishResult:
    platform_clip_id: str | None
    platform_url: str
    status: str
    error: str | None = None


class PublishAdapter:
    platform: str = ""
    supports_direct_publish: bool = False

    def publish(
        self,
        file_path: Path,
        *,
        user_id: str,
        metadata: dict[str, Any],
    ) -> PublishResult:
        raise NotImplementedError


class YouTubePublishAdapter(PublishAdapter):
    platform = "youtube"
    supports_direct_publish = True

    def publish(self, file_path: Path, *, user_id: str, metadata: dict[str, Any]) -> PublishResult:
        access_token = TokenManager.get_valid_token(user_id, self.platform)
        result = upload_to_youtube(file_path, metadata, access_token)  # type: ignore[arg-type]
        return PublishResult(platform_clip_id=result.get("id"), platform_url=result.get("url", ""), status="published")


class TikTokPublishAdapter(PublishAdapter):
    platform = "tiktok"
    supports_direct_publish = True

    def publish(self, file_path: Path, *, user_id: str, metadata: dict[str, Any]) -> PublishResult:
        token_data = TokenManager.get_valid_token(user_id, self.platform)
        if not isinstance(token_data, tuple) or len(token_data) != 2:
            raise IntegrationExpiredError("TikTok integration is incomplete.")
        access_token, open_id = token_data
        result = upload_to_tiktok(file_path, metadata, access_token, open_id)
        return PublishResult(platform_clip_id=result.get("id"), platform_url=result.get("url", ""), status="published")


class QueueOnlyPublishAdapter(PublishAdapter):
    supports_direct_publish = False

    def __init__(self, platform: str) -> None:
        self.platform = platform

    def publish(self, file_path: Path, *, user_id: str, metadata: dict[str, Any]) -> PublishResult:
        return PublishResult(platform_clip_id=None, platform_url="", status="queued", error="Unsupported platform")


def get_publish_adapter(platform: str) -> PublishAdapter:
    normalized = platform.lower()
    if normalized == "youtube":
        return YouTubePublishAdapter()
    if normalized == "tiktok":
        return TikTokPublishAdapter()
    return QueueOnlyPublishAdapter(normalized)

