# 🚀 Redis Setup for Windows (No Docker)

Choose ONE of these options:

## Option 1: WSL2 (Easiest - Linux on Windows)

### Step 1: Install WSL2 (one-time)
```powershell
# PowerShell (as admin)
wsl --install -d Ubuntu-22.04

# Restart your computer when prompted
```

### Step 2: Start Redis in WSL2
```bash
# Open WSL2 terminal and run:
sudo apt update && sudo apt install redis-server -y
redis-server
```

Keep this terminal open. Redis will run in the foreground.

### Step 3: Run ClipMind (new terminal)
```bash
# In Windows PowerShell, in your project directory:
python run.py
```

**Done!** Your app will auto-detect Redis. ✅

---

## Option 2: Windows Native Redis

### Step 1: Install Chocolatey (one-time)
If you don't have Chocolatey:
```powershell
# Open PowerShell as admin and run:
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

### Step 2: Install & Start Redis
```powershell
# PowerShell (as admin)
choco install redis -y

# After install, start Redis:
redis-server.exe
```

Keep this terminal open. Redis runs in the foreground.

### Step 3: Run ClipMind (new terminal)
```bash
# New PowerShell terminal, in your project:
python run.py
```

**Done!** Your app will connect to Redis. ✅

---

## Option 3: Docker (Alternative)

If you change your mind and want Docker:
```bash
docker compose up -d
python run.py
```

---

## Verify Redis is Running

In a new terminal:
```bash
redis-cli ping
```

Should output: `PONG`

If this fails, Redis isn't running. Start it again using Option 1 or 2 above.

---

## Troubleshoot

```bash
# Check Redis connection
python diagnose_redis.py

# Should output:
# ✅ All checks passed! Redis is ready.
```

---

## Recommended: WSL2 (Option 1)

- ✅ Easiest setup
- ✅ Standard Linux Redis
- ✅ Works like production
- ✅ No Windows-specific issues

Start with Option 1. If you have issues, try Option 2.
