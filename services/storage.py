"""File: services/storage.py
Purpose: Supabase Storage upload and download helpers for source videos,
         audio files, and final clips. Handles file naming and URL generation.
"""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from urllib.parse import urlparse, unquote
from uuid import uuid4

import httpx

try:
    from supabase import Client, create_client as _create_supabase_client  # type: ignore
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    Client = None  # type: ignore
    _create_supabase_client = None  # type: ignore

from core.config import settings


def _safe_name(filename: str) -> str:
    return "".join(
        char if char.isalnum() or char in {".", "-", "_"} else "_"
        for char in filename
    )


class StorageService:
    def __init__(self) -> None:
        self.local_root = settings.local_storage_dir
        self.supabase: "Client | None" = None
        if _SUPABASE_AVAILABLE and settings.supabase_url and settings.supabase_key:
            self.supabase = _create_supabase_client(settings.supabase_url, settings.supabase_key)

    def is_cloud_storage_enabled(self) -> bool:
        return self.supabase is not None

    def build_object_path(self, folder: str, filename: str) -> str:
        safe_name = f"{uuid4()}_{_safe_name(filename)}"
        return f"{folder}/{safe_name}"

    def build_public_url(self, object_path: str) -> str:
        if self.supabase is None:
            return (self.local_root / object_path).resolve().as_uri()
        return self.supabase.storage.from_(settings.storage_bucket).get_public_url(object_path)

    def create_signed_upload_url(self, folder: str, filename: str) -> tuple[str, str, str]:
        """Create a signed browser-upload URL for a new object path."""
        if self.supabase is None:
            raise RuntimeError("Supabase storage is not configured")

        object_path = self.build_object_path(folder, filename)
        signed = self.supabase.storage.from_(settings.storage_bucket).create_signed_upload_url(object_path)
        signed_url = signed["signed_url"] if isinstance(signed, dict) else signed.signed_url
        token = signed["token"] if isinstance(signed, dict) else signed.token
        return object_path, signed_url, token

    def upload_file(self, local_path: Path, folder: str, filename: str) -> str:
        safe_name = self.build_object_path(folder, filename).split("/", 1)[1]
        if self.supabase is None:
            destination = self.local_root / folder / safe_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, destination)
            return destination.resolve().as_uri()

        content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        object_path = f"{folder}/{safe_name}"
        with local_path.open("rb") as file_handle:
            self.supabase.storage.from_(settings.storage_bucket).upload(
                path=object_path,
                file=file_handle,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        return self.supabase.storage.from_(settings.storage_bucket).get_public_url(object_path)

    def download_to_local(self, source_url: str, local_target: Path) -> Path:
        local_target.parent.mkdir(parents=True, exist_ok=True)

        if source_url.startswith("file://"):
            source_path = Path(unquote(urlparse(source_url).path).lstrip("/"))
            if not source_path.exists():
                raise FileNotFoundError(f"Local source file not found: {source_path}")
            shutil.copy2(source_path, local_target)
            return local_target

        if "://" not in source_url:
            source_path = Path(source_url)
            shutil.copy2(source_path, local_target)
            return local_target

        with httpx.stream("GET", source_url, timeout=60.0) as response:
            response.raise_for_status()
            with local_target.open("wb") as file_handle:
                for chunk in response.iter_bytes():
                    file_handle.write(chunk)
        return local_target


storage_service = StorageService()
