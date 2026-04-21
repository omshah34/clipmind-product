import sys
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

# Add the project root to sys.path so pytest can discover modules 
# like 'services', 'api', and 'workers'.
# Since this file is in tests/, the root is one level up.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Mock the database and redis URLs for testing to use localhost
os.environ["DATABASE_URL"] = "postgresql://clipmind:your_secure_password@localhost:5432/clipmind"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

# --- Pytest bootstrap for local, writable temp/cache directories ---
_TMP_ROOT = _ROOT / ".tmp"
_PYTEST_TMP = _TMP_ROOT / "pytest-temp"
_PYTEST_CACHE = _TMP_ROOT / "pytest-cache"

for path in (_TMP_ROOT, _PYTEST_TMP, _PYTEST_CACHE):
    path.mkdir(parents=True, exist_ok=True)

for key in ("TMP", "TEMP", "TMPDIR"):
    os.environ[key] = str(_PYTEST_TMP)

tempfile.tempdir = str(_PYTEST_TMP)

class _WorkspaceTemporaryDirectory:
    def __init__(self, suffix: str | None = None, prefix: str | None = None, dir: str | None = None):
        base_dir = Path(dir) if dir else _PYTEST_TMP
        base_dir.mkdir(parents=True, exist_ok=True)
        suffix = suffix or ""
        prefix = prefix or "tmp"
        self.name = str(base_dir / f"{prefix}{uuid4().hex}{suffix}")
        Path(self.name).mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        shutil.rmtree(self.name, ignore_errors=True)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

tempfile.TemporaryDirectory = _WorkspaceTemporaryDirectory
