"""Canonical publish orchestration service."""

from __future__ import annotations
import hashlib

from datetime import datetime, timezone
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from sqlalchemy import text

from core.config import settings
from db.feature_flags import feature_flag_enabled
from db.connection import engine
from db.repositories.jobs import get_job
from db.repositories.publish import (
    add_to_publish_queue,
    create_published_clip,
    get_publish_queue_entry,
    list_platform_accounts,
    list_social_accounts,
    update_publish_status,
)
from services.llm_integration import optimize_captions_with_llm
from services.publishing_adapters import get_publish_adapter
from services.storage import storage_service
from core.redis import get_redis_client


class TokenRefreshError(Exception):
    pass


async def get_valid_token(platform: str, user_id: str) -> str:
    """
    Gap 281: Always returns a valid access token, refreshing if needed.
    """
    # Fetch integration from DB
    query = text(
        """
        SELECT id, platform, access_token_encrypted as access_token, 
               refresh_token_encrypted as refresh_token, expires_at
        FROM platform_credentials
        WHERE user_id = :user_id AND platform = :platform
        """
    )
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id), "platform": platform}).fetchone()

    if not row:
        raise TokenRefreshError(f"No integration found for {platform}")

    integration = dict(row._mapping)
    
    # In a real system, we'd decrypt access_token/refresh_token here using SecretManager
    # For this gap, we assume they are accessible or decrypted elsewhere
    
    # Check if token expires within next 5 minutes
    buffer_secs = 300
    expires_at = integration.get("expires_at")
    
    # Convert expires_at to timestamp if it's a datetime
    expires_ts = 0
    if isinstance(expires_at, datetime):
        expires_ts = expires_at.timestamp()
    elif isinstance(expires_at, (int, float)):
        expires_ts = expires_at

    if expires_ts and expires_ts - time.time() < buffer_secs:
        return await _refresh_token(integration, user_id)

    return integration["access_token"]


async def _refresh_token(integration: dict, user_id: str) -> str:
    REFRESH_URLS = {
        "youtube": "https://oauth2.googleapis.com/token",
        "tiktok": "https://open-api.tiktok.com/oauth/refresh_token/",
        "linkedin": "https://www.linkedin.com/oauth/v2/accessToken",
    }
    platform = integration["platform"]
    url = REFRESH_URLS.get(platform)
    if not url:
        raise TokenRefreshError(f"No refresh URL for platform: {platform}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, data={
            "grant_type": "refresh_token",
            "refresh_token": integration["refresh_token"],
            "client_id": settings.get_platform_client_id(platform),
            "client_secret": settings.get_platform_client_secret(platform),
        })

    if resp.status_code != 200:
        raise TokenRefreshError(
            f"Token refresh failed for {platform}: {resp.status_code} {resp.text}"
        )

    data = resp.json()
    new_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    new_expiry_dt = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc)

    # Persist refreshed token
    query = text(
        """
        UPDATE platform_credentials
        SET access_token_encrypted = :access_token,
            expires_at = :expires_at,
            refresh_token_encrypted = :refresh_token,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        """
    )
    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "id": integration["id"],
                "access_token": new_token,
                "expires_at": new_expiry_dt,
                "refresh_token": data.get("refresh_token", integration["refresh_token"]),
            }
        )
    return new_token


def _parse_hashtags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).lstrip("#") for item in value if str(item).strip()]
    if isinstance(value, str):
        tokens = value.replace(",", " ").split()
        return [token.lstrip("#") for token in tokens if token.strip()]
    return [str(value).lstrip("#")]


def _normalize_scheduled_for(
    scheduled_for: datetime | None,
    scheduled_timezone: str | None,
) -> datetime | None:
    if scheduled_for is None:
        return None
    if scheduled_for.tzinfo is not None:
        return scheduled_for.astimezone(timezone.utc)
    if not scheduled_timezone:
        return scheduled_for.replace(tzinfo=timezone.utc)

    try:
        tz = ZoneInfo(scheduled_timezone)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid scheduled timezone: {scheduled_timezone}") from exc

    fold_zero = scheduled_for.replace(tzinfo=tz, fold=0)
    fold_one = scheduled_for.replace(tzinfo=tz, fold=1)
    valid_candidates: list[datetime] = []
    for candidate in (fold_zero, fold_one):
        roundtrip = candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
        if roundtrip == scheduled_for:
            valid_candidates.append(candidate)

    if not valid_candidates:
        raise HTTPException(
            status_code=422,
            detail="Scheduled time does not exist in the selected timezone because of a daylight saving transition.",
        )

    # DECISION: during a DST fallback ambiguity, use the later occurrence so the
    # requested wall-clock time is never published earlier than the user intended.
    chosen = valid_candidates[-1]
    if len(valid_candidates) == 2 and valid_candidates[0].utcoffset() != valid_candidates[1].utcoffset():
        chosen = fold_one
    return chosen.astimezone(timezone.utc)


def generate_publish_idempotency_key(
    job_id: str,
    clip_index: int,
    platform: str,
    scheduled_at: datetime | None = None,
) -> str:
    """Gap 376: Deterministic key — same inputs always produce same key."""
    raw = f"{job_id}:{clip_index}:{platform}:{scheduled_at.isoformat() if scheduled_at else 'immediate'}"
    return "pub:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


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
        scheduled_timezone: str | None = None,
    ) -> dict:
        from workers.publish_social import publish_to_platform
        normalized_scheduled_for = _normalize_scheduled_for(scheduled_for, scheduled_timezone)

        publish_job_ids: list[str] = []
        for platform in platforms:
            existing = get_publish_queue_entry(user_id, job_id, clip_index, platform)
            if existing:
                publish_job_ids.append(str(existing["id"]))
                continue

            queue_entry = add_to_publish_queue(
                user_id=user_id,
                job_id=job_id,
                clip_index=clip_index,
                platform=platform,
                scheduled_for=normalized_scheduled_for or datetime.now(timezone.utc),
            )
            queue_id = queue_entry["id"]
            eta = (
                normalized_scheduled_for
                if normalized_scheduled_for and normalized_scheduled_for > datetime.now(timezone.utc)
                else None
            )
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
            "scheduled_at": normalized_scheduled_for or datetime.now(timezone.utc),
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
        scheduled_timezone: str | None = None,
    ) -> dict:
        job = get_job(job_id)
        if not job or str(job.user_id) != str(user_id):
            raise HTTPException(status_code=404, detail="Job not found")

        clip = job.clips_json[clip_index] if job.clips_json and clip_index < len(job.clips_json) else None
        if clip is None:
            raise HTTPException(status_code=404, detail="Clip not found")

        clip_data = clip.model_dump() if hasattr(clip, "model_dump") else dict(clip)

        platform_name = platform.lower()
        tags = _parse_hashtags(hashtags)
        connected_account = next(
            (account for account in _connected_accounts(str(user_id)) if account["platform"] == platform_name),
            None,
        )
        social_account_id = connected_account["account_id"] if connected_account else str(user_id)

        normalized_scheduled_for = _normalize_scheduled_for(scheduled_for, scheduled_timezone)

        queue_entry = add_to_publish_queue(
            user_id=str(user_id),
            job_id=job_id,
            clip_index=clip_index,
            platform=platform_name,
            scheduled_for=normalized_scheduled_for or datetime.now(timezone.utc),
        )

        if normalized_scheduled_for and normalized_scheduled_for > datetime.now(timezone.utc):
            published_row = create_published_clip(
                user_id=str(user_id),
                job_id=job_id,
                clip_index=clip_index,
                platform=platform_name,
                social_account_id=social_account_id,
                caption=caption,
                hashtags=tags,
                asset_path=str(clip_data.get("clip_url") or ""),
                scheduled_at=normalized_scheduled_for,
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
        
        # Gap 376: Workflow Idempotency (Double-Publish)
        idempotency_key = generate_publish_idempotency_key(job_id, clip_index, platform_name, normalized_scheduled_for)
        redis_client = get_redis_client()
        
        lock_key = f"publish_lock:{idempotency_key}"
        # Atomic check-and-set — prevents concurrent double-publish
        lock_acquired = redis_client.set(
            lock_key,
            "1",
            nx=True,     # Only set if not exists
            ex=3600,     # Lock expires in 1 hour
        )
        if not lock_acquired:
            logger.warning(f"Publishing attempt blocked by idempotency lock: {lock_key}")
            return {
                "status": "already_publishing",
                "message": "This clip is already being published to this platform."
            }
        
        try:
            result = adapter.publish(
                clip_path,
                user_id=str(user_id),
                metadata={"caption": caption, "hashtags": tags},
                idempotency_key=idempotency_key,
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
                    asset_path=str(clip_data.get("clip_url") or clip_path),
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
                asset_path=str(clip_data.get("clip_url") or clip_path),
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
        except Exception as e:
            # Release lock on failure so it can be retried
            redis_client.delete(lock_key)
            raise
        finally:
            try:
                if clip_path.exists():
                    resolved_clip_path = clip_path.resolve()
                    resolved_temp_dir = settings.temp_dir.resolve()
                    if str(resolved_clip_path).startswith(str(resolved_temp_dir)):
                        clip_path.unlink(missing_ok=True)
            except Exception:
                pass

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
