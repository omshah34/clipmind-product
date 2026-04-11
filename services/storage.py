from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from supabase import Client, create_client

from config import settings


def _safe_name(filename: str) -> str:
    return "".join(
        char if char.isalnum() or char in {".", "-", "_"} else "_"
        for char in filename
    )


class StorageService:
    def __init__(self) -> None:
        self.local_root = settings.local_storage_dir
        self.supabase: Client | None = None
        if settings.supabase_url and settings.supabase_key:
            self.supabase = create_client(settings.supabase_url, settings.supabase_key)

    def upload_file(self, local_path: Path, folder: str, filename: str) -> str:
        safe_name = f"{uuid4()}_{_safe_name(filename)}"
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

    def download_to_local(self, source_url: str, job_id: str, suffix: str) -> Path:
        local_target = settings.temp_dir / f"{job_id}_{uuid4().hex}{suffix}"
        local_target.parent.mkdir(parents=True, exist_ok=True)

        if source_url.startswith("file://"):
            source_path = Path(urlparse(source_url).path.lstrip("/"))
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
