# ⚡ Redis Auto-Start Enabled!

## What Changed

`run.py` now **automatically starts Redis** when you run it!

### How It Works

When you run `python run.py`:

1. ✅ Checks if Redis is running on `localhost:6379`
2. ❌ If Redis isn't running:
   - **Tries WSL2 first**: `wsl -u root -- sh -lc "service redis-server start"`
   - **Tries Windows next**: `redis-server.exe` (hidden background process)
3. ✅ Retries connection after auto-start
4. 🚀 Starts all your services (API, workers, frontend)

---

## Usage

### Simplest Way - Just Run It!
```bash
python run.py
```

That's it! No manual Redis setup needed. ✨

### Behind the Scenes

```
[CHECK]  Verifying Redis connection...
[AUTO]   Attempting to auto-start Redis...
         Trying WSL2: wsl -u root -- sh -lc "service redis-server start"
[DONE]   Redis started (WSL2)
[OK]     Redis connected after auto-start ✓

[START]  FastAPI Backend — ...
[START]  Celery Worker — ...
[START]  Celery Beat — ...
[START]  Next.js Frontend — ...

[RUNNING] All services started. Press Ctrl+C to stop.
```

---

## Prerequisites (One-Time Setup)

Choose **ONE** option:

### Option A: WSL2 (Recommended)
```bash
# In WSL2 terminal
sudo apt update
sudo apt install redis-server -y
```

### Option B: Windows Chocolatey
```powershell
# PowerShell as admin
choco install redis -y
```

### Option C: Windows Binary
Download from: https://github.com/microsoftarchive/redis/releases

---

## Verify Auto-Start Works

Run this in a new terminal (while `run.py` is running):
```bash
redis-cli ping
# Should output: PONG
```

---

## What You Don't Need To Do Anymore

❌ ~~Open separate terminal for Redis~~
❌ ~~Type `redis-server` manually~~
❌ ~~Remember to start Redis before running app~~
❌ ~~Deal with "Redis connection timeout" errors~~

---

## If Auto-Start Fails

The app will:
1. Show you which method failed
2. Suggest which option to setup manually
3. Continue anyway (workers might fail, but try)

Then manually check the setup guides:
- `docs/REDIS_SETUP_WINDOWS.md` - Quick setup
- `python diagnose_redis.py` - Diagnose issues

---

## Under the Hood

The auto-start logic in `run.py`:

```python
def auto_start_redis():
    # Try WSL2 first
    if wsl_available:
        subprocess.run(["wsl", "-u", "root", "--", "sh", "-lc", "service redis-server start"])
    
    # Try Windows (Chocolatey/binary)
    else if redis_server_in_path:
        subprocess.Popen(["redis-server.exe"])  # Hidden background process
    
    return success
```

---

## Features

✅ Auto-detects if Redis is running
✅ Tries to auto-start if not running  
✅ Tries multiple options (WSL2 → Windows)
✅ Runs Redis in hidden background process
✅ Retries connection after auto-start
✅ Provides helpful error messages
✅ One command: `python run.py` — that's all! 🎉

---

## Examples

### Works Without Any Manual Redis Setup
```bash
$ python run.py
[CHECK]  Verifying Redis connection...
[AUTO]   Attempting to auto-start Redis...
         Trying WSL2: wsl -u root -- sh -lc "service redis-server start"
[DONE]   Redis started (WSL2)
[OK]     Redis connected after auto-start ✓

[START]  FastAPI Backend ...
[RUNNING] All services started. Press Ctrl+C to stop.
```

### If Redis Already Running
```bash
$ python run.py
[CHECK]  Verifying Redis connection...
[OK]     Redis is accessible ✓

[START]  FastAPI Backend ...
[RUNNING] All services started. Press Ctrl+C to stop.
```

### If Auto-Start Fails (You'll See This)
```bash
$ python run.py
[CHECK]  Verifying Redis connection...
[FAIL]   Redis not running, auto-starting...
         Trying WSL2: wsl -u root -- sh -lc "service redis-server start"
         WSL2 not available, trying Chocolatey...
         Trying Windows: redis-server.exe
         Redis not found in PATH (need: choco install redis)
[FAIL]   Could not auto-start Redis

Manual setup options:
1. WSL2:      wsl -u root -- sh -lc "service redis-server start"
2. Windows:   redis-server.exe
3. Chocolatey: choco install redis

Then verify: redis-cli ping
```

---

## Summary

**Before**: Manual Redis startup needed ❌
**Now**: Full automation! 🚀

Just run `python run.py` and everything happens automatically!
