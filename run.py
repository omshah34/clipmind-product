"""
run.py - ClipMind One-Command Dev Launcher
==========================================
Starts all services in parallel:
  1. FastAPI backend (Uvicorn)
  2. Celery worker
  3. Celery Beat scheduler
  4. Next.js frontend (npm run dev)

* REDIS AUTO-START: Automatically starts Redis via WSL2 -> Docker -> Native Windows.
  You never need to touch the terminal for Redis.

Usage:
    python run.py              # Start everything (Redis auto-starts)
    python run.py --no-beat    # Skip Celery Beat
    python run.py --backend    # Backend + workers only (no frontend)
    python run.py --frontend   # Frontend only
"""

import subprocess
import sys
import os
import time
import signal
import argparse
import threading
import platform
import shutil
import re
from pathlib import Path

# -- Config --------------------------------------------------------------------

ROOT    = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
IS_WINDOWS = platform.system() == "Windows"

# Prefer virtual environment Python if it exists
VENV_PYTHON = ROOT / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

LOG_DIR = ROOT / "log"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"
LOG_FILE.write_text("", encoding="utf-8")   # Fresh log on each start

# Colour helpers (works on Windows 10+ terminals)
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def red(t):    return _c("91", t)
def green(t):  return _c("92", t)
def yellow(t): return _c("93", t)
def cyan(t):   return _c("96", t)
def bold(t):   return _c("1",  t)

# -- Redis Helpers -------------------------------------------------------------

def _redis_client(redis_url: str, socket_timeout: int = 5, socket_connect_timeout: int = 5):
    import redis
    return redis.Redis.from_url(
        redis_url,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        decode_responses=True,
    )


def _is_redis_alive(redis_url: str) -> bool:
    """Single quick check - returns True if Redis responds to PING."""
    try:
        import redis as redislib
        _redis_client(redis_url, socket_timeout=3, socket_connect_timeout=3).ping()
        return True
    except Exception:
        return False


def _wait_for_redis(redis_url: str, *, attempts: int = 15, delay: float = 1.0) -> bool:
    """Poll until Redis is up or budget runs out."""
    for i in range(attempts):
        if _is_redis_alive(redis_url):
            return True
        if i == 0:
            print(f"        Waiting for Redis to be ready", end="", flush=True)
        else:
            print(".", end="", flush=True)
        time.sleep(delay)
    print()   # newline after dots
    return False

# -- Redis Auto-Start Strategies -----------------------------------------------

def _try_wsl(redis_url: str) -> bool:
    """Start Redis inside WSL2 and wait for it to answer."""
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return False

    print(f"        Strategy 1 -> WSL2 redis-server")

    # Try the standard service manager first, then fallback to direct daemon
    commands = [
        "service redis-server start",
        "redis-server --daemonize yes --bind 0.0.0.0",
    ]
    for cmd in commands:
        try:
            result = subprocess.run(
                [wsl, "-u", "root", "--", "sh", "-lc", cmd],
                capture_output=True, text=True, timeout=15,
            )
            out = (result.stdout + result.stderr).lower()
            if result.returncode == 0 or "already" in out or "running" in out or "started" in out:
                print(f"{green('        [WSL2]')}  Redis started via: {cmd}")
                time.sleep(2)
                if _wait_for_redis(redis_url, attempts=10):
                    return True
        except Exception as exc:
            print(f"        WSL2 cmd failed ({cmd[:30]}...): {exc}")

    return False


def _try_docker(redis_url: str) -> bool:
    """
    Pull & run redis:alpine in Docker.
    Works on Docker Desktop for Windows with no extra setup.
    """
    docker = shutil.which("docker.exe") or shutil.which("docker")
    if not docker:
        return False

    print(f"        Strategy 2 -> Docker redis:alpine")

    # Check if container already exists and is running
    try:
        check = subprocess.run(
            [docker, "inspect", "--format", "{{.State.Running}}", "clipmind-redis"],
            capture_output=True, text=True, timeout=10,
        )
        if check.stdout.strip() == "true":
            print(f"{green('        [Docker]')}  clipmind-redis container already running")
            return _wait_for_redis(redis_url, attempts=5)
    except Exception:
        pass

    # Remove stale container if it exists but is stopped
    subprocess.run(
        [docker, "rm", "-f", "clipmind-redis"],
        capture_output=True, timeout=10,
    )

    try:
        result = subprocess.run(
            [
                docker, "run", "-d",
                "--name", "clipmind-redis",
                "-p", "6379:6379",
                "--restart", "unless-stopped",
                "redis:alpine",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            print(f"{green('        [Docker]')}  redis:alpine container started")
            time.sleep(2)
            if _wait_for_redis(redis_url, attempts=15):
                return True
        else:
            print(f"        Docker run failed: {result.stderr.strip()[:80]}")
    except subprocess.TimeoutExpired:
        print(f"        Docker timed out (image pull may be slow on first run)")
    except Exception as exc:
        print(f"        Docker error: {exc}")

    return False


def _try_native_windows(redis_url: str) -> bool:
    """
    Launch redis-server.exe directly if it's on PATH
    (e.g. installed via Chocolatey: choco install redis).
    """
    redis_exe = shutil.which("redis-server.exe") or shutil.which("redis-server")
    if not redis_exe or not IS_WINDOWS:
        return False

    print(f"        Strategy 3 -> Native redis-server.exe")

    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE   # Run hidden - no console popup

        proc = subprocess.Popen(
            [redis_exe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=si,
        )
        # Track it so shutdown() can kill it too
        processes.append(proc)

        print(f"{green('        [Native]')}  redis-server.exe started (PID {proc.pid})")
        time.sleep(2)
        if _wait_for_redis(redis_url, attempts=10):
            return True
    except Exception as exc:
        print(f"        Native redis-server failed: {exc}")

    return False


def auto_start_redis(redis_url: str | None = None) -> bool:
    """
    Try every available strategy in order:
      1. WSL2 service
      2. Docker Desktop
      3. Native redis-server.exe (Chocolatey)

    Returns True if any strategy succeeds.
    """
    redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")

    print(f"\n{yellow('[AUTO]')}  Redis not running - trying auto-start strategies...\n")

    for strategy in (_try_wsl, _try_docker, _try_native_windows):
        if strategy(redis_url):
            return True
        print()   # blank line between strategies

    return False


def check_redis() -> bool:
    """
    Full Redis readiness check with auto-start fallback.
    Returns True if Redis is (or becomes) ready, False if all strategies fail.
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_socket_timeout         = int(os.getenv("REDIS_SOCKET_TIMEOUT", "30"))
    redis_socket_connect_timeout = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "30"))

    print(f"{yellow('[CHECK]')} Verifying Redis at {redis_url} ...")

    if _is_redis_alive(redis_url):
        print(f"{green('[OK]')}    Redis is ready\n")
        return True

    # Not running - try to start it
    if auto_start_redis(redis_url):
        print(f"\n{green('[OK]')}    Redis connected after auto-start\n")
        return True

    # All strategies failed - print clear instructions
    print(f"\n{red('[FAIL]')}  Could not auto-start Redis automatically.\n")
    print(f"  Manual options (choose one):\n")
    print(f"  A) Docker Desktop  ->  {bold('docker run -d -p 6379:6379 --name clipmind-redis redis:alpine')}")
    print(f"  B) Chocolatey      ->  {bold('choco install redis')}  then  {bold('redis-server')}")
    print(f"  C) WSL2            ->  {bold('wsl -u root -- service redis-server start')}")
    print(f"\n  Verify with:  {bold('redis-cli ping')}  (expected: PONG)\n")
    return False

# -- Service Definitions -------------------------------------------------------

SERVICES = {
    "api": {
        "label": "FastAPI Backend",
        "color": green,
        "cmd": [
            PYTHON, "-m", "uvicorn", "api.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
            "--log-level", "info",
        ],
        "cwd": str(ROOT),
    },
    "worker": {
        "label": "Celery Worker",
        "color": cyan,
        "cmd": [
            PYTHON, "-m", "celery",
            "-A", "workers.celery_app",
            "worker",
            "--loglevel=warning",
            "--concurrency=2",
            "--pool=solo",   # solo pool avoids Windows fork issues
        ] if IS_WINDOWS else [
            PYTHON, "-m", "celery",
            "-A", "workers.celery_app",
            "worker",
            "--loglevel=warning",
            "--concurrency=4",
        ],
        "cwd": str(ROOT),
    },
    "beat": {
        "label": "Celery Beat",
        "color": yellow,
        "cmd": [
            PYTHON, "-m", "celery",
            "-A", "workers.celery_app",
            "beat",
            "--loglevel=warning",
        ],
        "cwd": str(ROOT),
    },
    "web": {
        "label": "Next.js Frontend",
        "color": lambda t: _c("95", t),
        "cmd": ["npm.cmd" if IS_WINDOWS else "npm", "run", "dev"],
        "cwd": str(WEB_DIR),
    },
}

# -- Process Manager -----------------------------------------------------------

processes: list[subprocess.Popen] = []
stop_event = threading.Event()
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def log_stream(proc: subprocess.Popen, label: str, color_fn):
    """Stream subprocess stdout+stderr to log/app.log with source-file extraction."""
    prefix = f"[{label}]"
    # Matches structured log format: ... [filename.py:123] ...
    source_re = re.compile(r'\[(\w+\.py:\d+)\]')
    # Matches Python traceback lines: File "path/to/file.py", line 123
    tb_file_re = re.compile(r'File "(.+?)", line (\d+)')
    last_source_file = ""

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        for line in iter(proc.stdout.readline, b""):
            if stop_event.is_set():
                break
            text       = line.decode(errors="replace")
            clean_text = ansi_escape.sub("", text).strip("\r\n")
            if not clean_text.strip():
                continue

            lower = clean_text.lower()

            # Extract source file from structured logs or tracebacks
            source_match = source_re.search(clean_text)
            if source_match:
                last_source_file = source_match.group(1)

            tb_match = tb_file_re.search(clean_text)
            if tb_match:
                filepath = tb_match.group(1)
                lineno = tb_match.group(2)
                # Extract just the filename from the full path
                fname = filepath.replace("\\", "/").split("/")[-1]
                last_source_file = f"{fname}:{lineno}"

            if any(k in lower for k in ["error", "traceback", "exception", "failed", "x"]):
                severity = "[ERROR]"
                source_tag = f" ({last_source_file})" if last_source_file else ""
            elif "warn" in lower:
                severity = "[WARN]"
                source_tag = ""
            else:
                severity = "[INFO]"
                source_tag = ""

            f.write(f"{severity} {prefix}{source_tag} {clean_text}\n")
            f.flush()


def start_service(key: str, svc: dict) -> subprocess.Popen | None:
    label = svc["label"]
    color = svc["color"]
    cmd   = svc["cmd"]
    cwd   = svc.get("cwd", str(ROOT))

    exe = cmd[0]
    if shutil.which(str(exe)) is None and not Path(str(exe)).exists():
        print(f"{red('[SKIP]')} {label} - executable not found: {exe}")
        return None

    print(f"{color('[START]')} {bold(label)}")

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ},
    )
    processes.append(proc)

    threading.Thread(
        target=log_stream, args=(proc, key.upper(), color), daemon=True
    ).start()

    return proc


def check_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        env_example = ROOT / ".env.example"
        print(f"\n{yellow('[WARN]')} No .env file found.")
        if env_example.exists():
            print(f"       Run: {bold('cp .env.example .env')} and fill in values.\n")
        return False

    required = ["REDIS_URL", "OPENAI_API_KEY"]
    missing  = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"\n{yellow('[WARN]')} Missing env vars: {', '.join(missing)}")
        print(f"       Some services may fail. Check your .env file.\n")
    return True


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ[key.strip()] = val.strip()


def check_frontend_deps():
    node_modules = WEB_DIR / "node_modules"
    if not node_modules.exists():
        print(f"{yellow('[SETUP]')} node_modules missing - running npm install...")
        result = subprocess.run(
            ["npm.cmd" if IS_WINDOWS else "npm", "install"],
            cwd=str(WEB_DIR),
        )
        if result.returncode != 0:
            print(f"{red('[ERROR]')} npm install failed.")
            return False
    return True


def shutdown(sig=None, frame=None):
    try:
        print(f"\n{red('[SHUTDOWN]')} Stopping all services...")
    except RuntimeError:
        pass
    stop_event.set()
    for proc in processes:
        if proc and proc.poll() is None:
            proc.terminate() if IS_WINDOWS else proc.send_signal(signal.SIGTERM)
    time.sleep(1)
    for proc in processes:
        if proc and proc.poll() is None:
            proc.kill()
    try:
        print(green("[DONE] All services stopped."))
        LOG_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass
    sys.exit(0)

# -- Main ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ClipMind Dev Launcher")
    parser.add_argument("--no-beat",   action="store_true", help="Skip Celery Beat")
    parser.add_argument("--backend",   action="store_true", help="Backend + workers only")
    parser.add_argument("--frontend",  action="store_true", help="Frontend only")
    parser.add_argument("--no-worker", action="store_true", help="Skip Celery worker")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, shutdown)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, shutdown)

    print("\n" + "="*40)
    print("       ClipMind Dev Launcher")
    print("="*40 + "\n")

    load_env()
    check_env()

    # -- Determine which services to run --------------------------------------
    run_keys: list[str] = []

    if args.frontend:
        run_keys = ["web"]
    elif args.backend:
        run_keys = ["api", "worker"]
        if not args.no_beat:
            run_keys.append("beat")
    else:
        run_keys = ["api"]
        if not args.no_worker:
            run_keys.append("worker")
        if not args.no_beat:
            run_keys.append("beat")
        run_keys.append("web")

    # -- Redis: check + auto-start BEFORE workers launch ----------------------
    if ("worker" in run_keys or "beat" in run_keys) and not args.frontend:
        if not check_redis():
            print(f"{yellow('[WARN]')}  Skipping worker + beat (Redis unavailable).\n")
            run_keys = [k for k in run_keys if k not in {"worker", "beat"}]

    # -- Frontend deps ---------------------------------------------------------
    if "web" in run_keys:
        if not check_frontend_deps():
            run_keys.remove("web")

    if not run_keys:
        print(red("[ERROR] Nothing to start. Check logs above."))
        sys.exit(1)

    print(f"\n{bold('Starting:')} {', '.join(SERVICES[k]['label'] for k in run_keys)}\n")

    # -- Launch services with staggered startup --------------------------------
    started: list[tuple[str, subprocess.Popen]] = []
    for i, key in enumerate(run_keys):
        proc = start_service(key, SERVICES[key])
        if proc:
            started.append((key, proc))
        if i < len(run_keys) - 1:
            time.sleep(1.5)

    if not started:
        print(red("[ERROR] No services started."))
        sys.exit(1)

    print(f"\n{green('[RUNNING]')} All services up. Press {bold('Ctrl+C')} to stop.\n")
    print(f"  {bold('API:')}     http://localhost:8000")
    print(f"  {bold('Docs:')}    http://localhost:8000/docs")
    print(f"  {bold('Web:')}     http://localhost:3000\n")
    print(f"{green(bold('>>> CLIPMIND IS READY <<<'))}\n")

    # -- Monitor & auto-restart crashed services -------------------------------
    while True:
        time.sleep(2)
        for key, proc in list(started):
            if proc.poll() is not None:
                svc = SERVICES[key]
                print(f"\n{red('[CRASH]')} {svc['label']} exited (code {proc.returncode}). Restarting in 3s...")
                time.sleep(3)
                new_proc = start_service(key, svc)
                if new_proc:
                    idx = started.index((key, proc))
                    started[idx] = (key, new_proc)
                    if proc in processes:
                        processes.remove(proc)


if __name__ == "__main__":
    main()
