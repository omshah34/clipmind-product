"""File: services/storage.py
Purpose: Supabase Storage upload and download helpers for source videos,
         audio files, and final clips. Handles file naming and URL generation.

Gap 237: Content-Addressable Storage (CAS)
  - upload_file_deduplicated() computes SHA-256 before every upload and
    checks the `cas_assets` table for a matching digest.
  - On hit  → returns the canonical URL and bumps ref_count; no upload.
  - On miss → uploads normally and registers the new asset in cas_assets.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import hashlib
import shutil
import tempfile
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from urllib.parse import urlparse, unquote, urlunparse
from uuid import uuid4

import httpx

_cas_logger = logging.getLogger(__name__)

try:
    from supabase import Client, create_client as _create_supabase_client  # type: ignore
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    Client = None  # type: ignore
    _create_supabase_client = None  # type: ignore

from core.config import settings


def _safe_name(filename: str) -> str:
    """Sanitize filename to prevent path traversal and shell injection."""
    # Remove any directory components
    name = Path(filename).name
    # Filter for allowed characters
    return "".join(
        char if char.isalnum() or char in {".", "-", "_"} else "_"
        for char in name
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
        token = uuid4().hex
        safe_name = f"{token}_{_safe_name(filename)}"
        return f"{folder}/{token[:2]}/{token[2:4]}/{safe_name}"

    def build_public_url(self, object_path: str) -> str:
        if self.supabase is None:
            return (self.local_root / object_path).resolve().as_uri()
        return self.supabase.storage.from_(settings.storage_bucket).get_public_url(object_path)

    def _decorate_public_url(self, url: str, checksum: str) -> str:
        return url

    def _extract_expected_checksum(self, url: str) -> str | None:
        parsed = urlparse(url)
        raw_query = parsed.query
        if not raw_query:
            return None
        for part in raw_query.split("&"):
            if part.startswith("cm_sha256="):
                return part.split("=", 1)[1]
        return None

    def _sidecar_reference(self, url: str) -> str | None:
        parsed = urlparse(url)

        if parsed.scheme == "file":
            local_path = self._local_path_from_file_uri(url)
            sidecar = local_path.with_name(f"{local_path.name}.sha256")
            return sidecar.as_uri()

        if "://" not in url:
            sidecar = Path(url).with_name(f"{Path(url).name}.sha256")
            return str(sidecar)

        if parsed.scheme in {"http", "https"}:
            return urlunparse(parsed._replace(path=f"{parsed.path}.sha256", query="", fragment=""))

        return None

    def _local_path_from_file_uri(self, url: str) -> Path:
        parsed = urlparse(url)
        raw_path = unquote(parsed.path)
        if os.name == "nt" and raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
            raw_path = raw_path.lstrip("/")
        return Path(raw_path)

    def _read_text_reference(self, reference: str) -> str | None:
        if not reference:
            return None

        try:
            if reference.startswith("file://"):
                parsed = urlparse(reference)
                path = Path(unquote(parsed.path))
                if os.name == "nt" and path.as_posix().startswith("/") and ":" in path.as_posix()[1:3]:
                    path = Path(path.as_posix().lstrip("/"))
                return path.read_text(encoding="utf-8").strip()

            if "://" not in reference:
                path = Path(reference)
                if path.exists():
                    return path.read_text(encoding="utf-8").strip()
                return None

            with httpx.Client(timeout=10.0) as client:
                response = client.get(reference)
                response.raise_for_status()
                return response.text.strip()
        except Exception:
            return None

    def _get_expected_checksum(self, source_url: str) -> str | None:
        checksum = self._extract_expected_checksum(source_url)
        if checksum:
            return checksum

        sidecar = self._sidecar_reference(source_url)
        if sidecar:
            return self._read_text_reference(sidecar)
        return None

    def _file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def create_signed_upload_url(self, folder: str, filename: str) -> tuple[str, str, str]:
        """Create a signed browser-upload URL for a new object path."""
        if self.supabase is None:
            raise RuntimeError("Supabase storage is not configured")

        object_path = self.build_object_path(folder, filename)
        signed = self.supabase.storage.from_(settings.storage_bucket).create_signed_upload_url(object_path)
        signed_url = signed["signed_url"] if isinstance(signed, dict) else signed.signed_url
        token = signed["token"] if isinstance(signed, dict) else signed.token
        return object_path, signed_url, token

    def create_signed_url(self, object_path: str, expires_in: int = 3600) -> str:
        """Create a temporary signed URL for private object access (Gap 65)."""
        if self.supabase is None:
            # For local storage, just return the public URL (simulated)
            return self.build_public_url(object_path)
            
        res = self.supabase.storage.from_(settings.storage_bucket).create_signed_url(
            path=object_path,
            expires_in=expires_in
        )
        # Handle both dict and object response formats from different supabase-py versions
        return res["signed_url"] if isinstance(res, dict) else res

    def extract_object_path(self, url: str) -> str | None:
        """Extract a storage object path from a public Supabase URL."""
        if not url or "://" not in url:
            return None

        if self.supabase:
            parsed = urlparse(url)
            public_prefix = f"/storage/v1/object/public/{settings.storage_bucket}/"
            alt_public_prefix = f"/storage/v1/object/public/"
            for prefix in (public_prefix, alt_public_prefix):
                if prefix in parsed.path:
                    tail = parsed.path.split(prefix, 1)[1]
                    if prefix == alt_public_prefix and tail.startswith(f"{settings.storage_bucket}/"):
                        tail = tail.split("/", 1)[1]
                    return tail
        return None

    def object_exists(self, object_path: str) -> bool:
        """Best-effort check that a storage object is present before completion."""
        if self.supabase is None:
            return (self.local_root / object_path).exists()

        parent = Path(object_path).parent.as_posix()
        filename = Path(object_path).name
        try:
            items = self.supabase.storage.from_(settings.storage_bucket).list(
                parent if parent != "." else ""
            )
        except Exception:
            items = []

        for item in items:
            if isinstance(item, dict):
                name = item.get("name")
            else:
                name = getattr(item, "name", None)
            if name == filename:
                return True

        try:
            self.supabase.storage.from_(settings.storage_bucket).download(object_path)
            return True
        except Exception:
            return False

    def get_presigned_url(self, url: str, expires_in: int = 3600) -> str:
        """Convert a public URL or object path into a signed URL if needed."""
        if not url:
            return url

        object_path = self.extract_object_path(url)
        if object_path:
            if self.supabase:
                return self.create_signed_url(object_path, expires_in)
            return self.build_public_url(object_path)

        if "://" not in url:
            return url # Already an object path or empty

        return url

    def upload_file(self, local_path: Path, folder: str, filename: str) -> str:
        """Upload a file to Supabase storage.
        
        Gap 54: For files > 5GB, Supabase requires TUS (Resumable) or Multipart.
        Standard 'upload' will fail on extremely large source files.
        Roadmap: Implement TUS protocol via tus-py-client for 5GB+ stability.
        """
        checksum = self._file_sha256(local_path)
        safe_name = self.build_object_path(folder, filename).split("/", 1)[1]
        if self.supabase is None:
            destination = self.local_root / folder / safe_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp") as temp_handle:
                temp_path = Path(temp_handle.name)
            try:
                shutil.copy2(local_path, temp_path)
                with temp_path.open("r+b") as temp_reader:
                    os.fsync(temp_reader.fileno())
                temp_path.replace(destination)
            finally:
                temp_path.unlink(missing_ok=True)
            destination.with_name(f"{destination.name}.sha256").write_text(checksum, encoding="utf-8")
            return destination.resolve().as_uri()

        content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        object_path = f"{folder}/{safe_name}"
        def _perform_upload() -> str:
            with local_path.open("rb") as file_handle:
                self.supabase.storage.from_(settings.storage_bucket).upload(
                    path=object_path,
                    file=file_handle,
                    file_options={"content-type": content_type, "upsert": "true"},
                )
            try:
                sidecar_content = io.BytesIO(checksum.encode("utf-8"))
                self.supabase.storage.from_(settings.storage_bucket).upload(
                    path=f"{object_path}.sha256",
                    file=sidecar_content,
                    file_options={"content-type": "text/plain", "upsert": "true"},
                )
            except Exception:
                _cas_logger.warning("Checksum sidecar upload failed for %s (non-fatal)", object_path, exc_info=True)
            return self.supabase.storage.from_(settings.storage_bucket).get_public_url(object_path)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_perform_upload)
            try:
                public_url = future.result(timeout=settings.storage_upload_timeout_seconds)
            except FutureTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"Storage upload exceeded {settings.storage_upload_timeout_seconds}s for {filename}"
                ) from exc

        return public_url

    def download_to_local(self, source_url: str, local_target: Path) -> Path:
        local_target.parent.mkdir(parents=True, exist_ok=True)
        max_bytes = settings.max_upload_size_bytes
        expected_checksum = self._get_expected_checksum(source_url)

        if source_url.startswith("file://"):
            source_path = self._local_path_from_file_uri(source_url)
            if not source_path.exists():
                raise FileNotFoundError(f"Local source file not found: {source_path}")
            shutil.copy2(source_path, local_target)
            if expected_checksum and self._file_sha256(local_target) != expected_checksum:
                local_target.unlink(missing_ok=True)
                raise ValueError("Downloaded artifact checksum did not match expected SHA-256.")
            return local_target

        if "://" not in source_url:
            source_path = Path(source_url)
            shutil.copy2(source_path, local_target)
            if expected_checksum and self._file_sha256(local_target) != expected_checksum:
                local_target.unlink(missing_ok=True)
                raise ValueError("Downloaded artifact checksum did not match expected SHA-256.")
            return local_target

        with httpx.stream("GET", source_url, timeout=settings.storage_download_timeout_seconds) as response:
            try:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        content_length_value = int(content_length)
                    except ValueError:
                        logger.debug("Ignoring invalid Content-Length header for %s", source_url)
                    else:
                        if content_length_value > max_bytes:
                            raise ValueError(f"Remote file is too large to download safely ({content_length} bytes)")
                with local_target.open("wb") as file_handle:
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError(f"Remote file exceeded the maximum download size of {max_bytes} bytes")
                        file_handle.write(chunk)
            except Exception:
                local_target.unlink(missing_ok=True)
                raise
        if expected_checksum and self._file_sha256(local_target) != expected_checksum:
            local_target.unlink(missing_ok=True)
            raise ValueError("Downloaded artifact checksum did not match expected SHA-256.")
        return local_target

    def purge_cached_asset(self, asset_url: str) -> bool:
        if not asset_url or not settings.cdn_purge_url:
            return False

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if settings.cdn_purge_token:
            headers["Authorization"] = f"Bearer {settings.cdn_purge_token}"

        payload = {"files": [asset_url]}
        with httpx.Client(timeout=10.0) as client:
            response = client.post(settings.cdn_purge_url, json=payload, headers=headers)
            response.raise_for_status()
        return True

    async def delete_file(self, url: str) -> bool:
        """Delete a file from storage given its public URL or file URI (Gap 27).
        
        Returns:
            True if deletion was attempted, False if URL was invalid/empty.
        """
        import os
        if not url:
            return False

        allowed_roots = [
            self.local_root.resolve(),
            settings.temp_dir.resolve(),
        ]

        def _is_allowed(path: Path) -> bool:
            try:
                resolved = path.resolve()
            except FileNotFoundError:
                resolved = path.absolute()
            return any(str(resolved).startswith(str(root)) for root in allowed_roots)

        # 1. Handle local file URIs
        if url.startswith("file://"):
            path = self._local_path_from_file_uri(url)

            if path.exists() and _is_allowed(path):
                try:
                    path.unlink()
                    return True
                except Exception:
                    # Reraise or log? Calling code handles it.
                    raise
            if path.exists():
                raise ValueError(f"Refusing to delete path outside managed storage roots: {path}")
            return False

        # 2. Handle Cloud Storage (Supabase)
        if self.supabase:
            object_path = self.extract_object_path(url)
            if object_path:
                try:
                    # Note: Python Supabase client storage methods are currently synchronous
                    self.supabase.storage.from_(settings.storage_bucket).remove([object_path])
                    return True
                except Exception:
                    raise

        if "://" not in url:
            path = Path(url)
            if path.exists() and _is_allowed(path):
                path.unlink()
                return True
            if path.exists():
                raise ValueError(f"Refusing to delete path outside managed storage roots: {path}")
        
        return False


    # ------------------------------------------------------------------ #
    # Gap 237: Content-Addressable Storage helpers                         #
    # ------------------------------------------------------------------ #

    def lookup_cas_asset(self, sha256: str) -> str | None:
        """Return the canonical URL if this digest is already stored, else None."""
        try:
            from sqlalchemy import text as _text
            from db.connection import engine as _engine
            _ts = "NOW()" if _engine.dialect.name == "postgresql" else "CURRENT_TIMESTAMP"
            with _engine.connect() as conn:
                row = conn.execute(
                    _text(
                        "UPDATE cas_assets "
                        f"SET ref_count = ref_count + 1, last_seen_at = {_ts} "
                        "WHERE sha256 = :sha256 "
                        "RETURNING canonical_url"
                    ),
                    {"sha256": sha256},
                ).one_or_none()
                conn.commit()
            if row:
                _cas_logger.info("CAS hit sha256=%s … reusing canonical URL", sha256[:12])
                return row[0]
        except Exception as exc:
            _cas_logger.warning("CAS lookup failed (non-fatal): %s", exc)
        return None

    def register_cas_asset(self, sha256: str, canonical_url: str, size_bytes: int) -> None:
        """Upsert a canonical URL for the given digest in the CAS table."""
        try:
            from sqlalchemy import text as _text
            from db.connection import engine as _engine
            _ts = "NOW()" if _engine.dialect.name == "postgresql" else "CURRENT_TIMESTAMP"
            with _engine.begin() as conn:
                conn.execute(
                    _text(
                        "INSERT INTO cas_assets (sha256, canonical_url, size_bytes) "
                        "VALUES (:sha256, :url, :size) "
                        "ON CONFLICT (sha256) DO UPDATE "
                        "SET ref_count = cas_assets.ref_count + 1, "
                        f"    last_seen_at = {_ts}"
                    ),
                    {"sha256": sha256, "url": canonical_url, "size": size_bytes},
                )
        except Exception as exc:
            _cas_logger.warning("CAS register failed (non-fatal): %s", exc)

    def upload_file_deduplicated(
        self,
        local_path: Path,
        folder: str,
        filename: str,
    ) -> str:
        """Upload *local_path* only when its SHA-256 is not already stored.

        Returns the canonical public/decorated URL for the asset, whether it
        was freshly uploaded or reused from the CAS registry (Gap 237).
        """
        sha256 = self._file_sha256(local_path)

        # 1. CAS lookup — skip upload entirely on a hit
        cached_url = self.lookup_cas_asset(sha256)
        if cached_url:
            return cached_url

        # 2. CAS miss — perform normal upload
        canonical_url = self.upload_file(local_path, folder, filename)

        # 3. Register in CAS so future uploads of the same content are deduplicated
        self.register_cas_asset(sha256, canonical_url, local_path.stat().st_size)

        _cas_logger.info(
            "CAS miss sha256=%s … stored as %s",
            sha256[:12],
            canonical_url[:60],
        )
        return canonical_url


storage_service = StorageService()
