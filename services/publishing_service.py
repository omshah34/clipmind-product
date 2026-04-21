"""Canonical publish orchestration service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from core.config import settings
from db.feature_flags import feature_flag_enabled
from db.connection import engine
from db.repositories.jobs import get_job
from db.repositories.publish import (
    add_to_publish_queue,
    create_published_clip,
    list_platform_accounts,
    list_social_accounts,
    update_publish_status,
)
from services.llm_integration import optimize_captions_with_llm
from services.publishing_adapters import get_publish_adapter
from services.storage import storage_service


def _parse_hashtags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).lstrip("#") for item in value if str(item).strip()]
    if isinstance(value, str):
        tokens = value.replace(",", " ").split()
        return [token.lstrip("#") for token in tokens if token.strip()]
    return [str(value).lstrip("#")]


def _connected_accounts(user_id: str) -> list[dict]:
    accounts = []
    seen: set[tuple[str, str]] = set()

    for account in list_platform_accounts(user_id):
        platform = str(account.get("platform", "")).lower()
        key = (platform, str(account.get("account_id", "")))
        if not platform or key in seen:
            continue
        seen.add(key)
        accounts.append(
            {
                "account_id": str(account.get("account_id") or account.get("id")),
                "platform": platform,
                "username": account.get("account_name") or account.get("account_username") or platform,
                "connected_at": account.get("synced_at") or account.get("created_at"),
            }
        )

    for account in list_social_accounts(user_id):
        platform = str(account.get("platform", "")).lower()
        key = (platform, str(account.get("account_id", "")))
        if not platform or key in seen:
            continue
        seen.add(key)
        accounts.append(
            {
                "account_id": str(account.get("account_id") or account.get("id")),
                "platform": platform,
                "username": account.get("account_username") or account.get("account_name") or platform,
                "connected_at": account.get("created_at"),
            }
        )

    return accounts


class PublishingService:
    def list_connected_accounts(self, user_id: str) -> list[dict]:
        return _connected_accounts(user_id)

    def optimize_caption(
        self,
        user_id: str,
        job_id: str,
        clip_index: int,
        original_caption: str,
        platforms: list[str],
    ) -> dict[str, str]:
        if not platforms:
            return {}
        result = optimize_captions_with_llm(user_id, job_id, clip_index, original_caption, platforms)
        return result.get("captions", {})

    def schedule_multi_platform_publish(
        self,
        *,
        user_id: str,
        job_id: str,
        clip_index: int,
        platforms: list[str],
        caption: str,
        hashtags: Any,
        scheduled_for: datetime | None,
    ) -> dict:
        from workers.publish_social import publish_to_platform

        publish_job_ids: list[str] = []
        for platform in platforms:
            queue_entry = add_to_publish_queue(
                user_id=user_id,
                job_id=job_id,
                clip_index=clip_index,
                platform=platform,
                scheduled_for=scheduled_for or datetime.now(timezone.utc),
            )
            queue_id = queue_entry["id"]
            eta = scheduled_for if scheduled_for and scheduled_for > datetime.now(timezone.utc) else None
            publish_to_platform.apply_async(
                args=[
                    user_id,
                    str(job_id),
                    clip_index,
                    platform,
                    user_id,
                    caption,
                ],
                kwargs={
                    "hashtags": _parse_hashtags(hashtags),
                    "publish_queue_id": queue_id,
                },
                eta=eta,
            )
            publish_job_ids.append(queue_id)

        return {
            "status": "scheduled",
            "publish_job_ids": publish_job_ids,
            "scheduled_at": scheduled_for or datetime.now(timezone.utc),
        }

    def publish_clip(
        self,
        *,
        user_id: str,
        job_id: str,
        clip_index: int,
        platform: str,
        caption: str,
        hashtags: Any,
        scheduled_for: datetime | None = None,
    ) -> dict:
        job = get_job(job_id)
        if not job or str(job.user_id) != str(user_id):
            raise HTTPException(status_code=404, detail="Job not found")

        clip = job.clips_json[clip_index] if job.clips_json and clip_index < len(job.clips_json) else None
        if clip is None:
            raise HTTPException(status_code=404, detail="Clip not found")

        platform_name = platform.lower()
        tags = _parse_hashtags(hashtags)
        connected_account = next(
            (account for account in _connected_accounts(str(user_id)) if account["platform"] == platform_name),
            None,
        )
        social_account_id = connected_account["account_id"] if connected_account else str(user_id)

        if scheduled_for and scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)

        queue_entry = add_to_publish_queue(
            user_id=str(user_id),
            job_id=job_id,
            clip_index=clip_index,
            platform=platform_name,
            scheduled_for=scheduled_for or datetime.now(timezone.utc),
        )

        if scheduled_for and scheduled_for > datetime.now(timezone.utc):
            published_row = create_published_clip(
                user_id=str(user_id),
                job_id=job_id,
                clip_index=clip_index,
                platform=platform_name,
                social_account_id=social_account_id,
                caption=caption,
                hashtags=tags,
                scheduled_at=scheduled_for,
            )
            published_clip_id = str(published_row.get("id") or queue_entry["id"])
            update_publish_status(queue_entry["id"], "scheduled")
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE published_clips SET status = 'scheduled' WHERE id = :published_clip_id"),
                    {"published_clip_id": published_clip_id},
                )
            return {
                "published_clip_id": published_clip_id,
                "platform": platform_name,
                "platform_clip_id": None,
                "platform_url": "",
                "status": "scheduled",
                "engagement_metrics": {"views": 0, "likes": 0, "shares": 0},
            }

        direct_publish_enabled = feature_flag_enabled("publish_direct_enabled", default=True)
        adapter = get_publish_adapter(platform_name)
        if not direct_publish_enabled or not adapter.supports_direct_publish:
            published_row = create_published_clip(
                user_id=str(user_id),
                job_id=job_id,
                clip_index=clip_index,
                platform=platform_name,
                social_account_id=social_account_id,
                caption=caption,
                hashtags=tags,
            )
            published_clip_id = str(published_row.get("id") or queue_entry["id"])
            update_publish_status(queue_entry["id"], "queued")
            return {
                "published_clip_id": published_clip_id,
                "platform": platform_name,
                "platform_clip_id": None,
                "platform_url": "",
                "status": "queued",
                "engagement_metrics": {"views": 0, "likes": 0, "shares": 0},
            }

        clip_path = self._clip_asset_path(job_id, clip_index, clip)
        result = adapter.publish(
            clip_path,
            user_id=str(user_id),
            metadata={"caption": caption, "hashtags": tags},
        )
        if result.status == "published":
            published_row = create_published_clip(
                user_id=str(user_id),
                job_id=job_id,
                clip_index=clip_index,
                platform=platform_name,
                social_account_id=social_account_id,
                caption=caption,
                hashtags=tags,
                published_at=datetime.now(timezone.utc),
            )
            published_clip_id = str(published_row.get("id") or queue_entry["id"])
            update_publish_status(queue_entry["id"], "published", platform_url=result.platform_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE published_clips
                        SET status = 'published',
                            platform_clip_id = :platform_clip_id,
                            platform_url = :platform_url,
                            published_at = :published_at
                        WHERE id = :published_clip_id
                        """
                    ),
                    {
                        "platform_clip_id": result.platform_clip_id,
                        "platform_url": result.platform_url,
                        "published_at": datetime.now(timezone.utc),
                        "published_clip_id": published_clip_id,
                    },
                )
            return {
                "published_clip_id": published_clip_id,
                "platform": platform_name,
                "platform_clip_id": result.platform_clip_id,
                "platform_url": result.platform_url,
                "status": "published",
                "engagement_metrics": {"views": 0, "likes": 0, "shares": 0},
            }

        published_row = create_published_clip(
            user_id=str(user_id),
            job_id=job_id,
            clip_index=clip_index,
            platform=platform_name,
            social_account_id=social_account_id,
            caption=caption,
            hashtags=tags,
        )
        published_clip_id = str(published_row.get("id") or queue_entry["id"])
        update_publish_status(queue_entry["id"], "queued")
        return {
            "published_clip_id": published_clip_id,
            "platform": platform_name,
            "platform_clip_id": None,
            "platform_url": "",
            "status": "queued",
            "engagement_metrics": {"views": 0, "likes": 0, "shares": 0},
        }

    def _clip_asset_path(self, job_id: str, clip_index: int, clip: Any) -> Path:
        clip_data = clip.model_dump() if hasattr(clip, "model_dump") else dict(clip)
        clip_url = clip_data.get("clip_url")
        if not clip_url:
            raise HTTPException(status_code=409, detail="Clip asset is not ready yet.")

        local_target = settings.temp_dir / f"publish_{job_id}_{clip_index}.mp4"
        try:
            return storage_service.download_to_local(clip_url, local_target)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"Unable to access clip asset: {exc}")


publishing_service = PublishingService()
