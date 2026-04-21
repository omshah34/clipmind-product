# Redis & Celery Connection Troubleshooting

## Common Errors

### 1. **TimeoutError: Timeout reading from socket**
```
redis.exceptions.TimeoutError: Timeout reading from socket
TimeoutError: [WinError 10060] A connection attempt failed...
```

**Cause**: Redis is unreachable or not responding.

**Solution**:
- Check if Redis is running
- Verify the `REDIS_URL` in `.env`
- Increase socket timeouts if using remote Redis

---

## Setup Options

### Option A: WSL2 (Easiest for Windows)

WSL2 has native Linux support and Redis installs seamlessly.

#### 1. Install WSL2 + Ubuntu
If you don't have WSL2:
```powershell
# In PowerShell (as admin)
wsl --install -d Ubuntu-22.04
```

#### 2. Install Redis in WSL2
```bash
# In WSL2 terminal
sudo apt update
sudo apt install redis-server -y
```

#### 3. Start Redis
```bash
# Option A: foreground (see logs)
redis-server

# Option B: background service
sudo service redis-server start
sudo service redis-server status
```

#### 4. Test Connection
```bash
redis-cli ping
# Expected: PONG
```

#### 5. Set REDIS_URL in .env
```env
REDIS_URL=redis://localhost:6379/0
```

#### 6. Run Your App (Windows Terminal)
```bash
python run.py
```

---

### Option B: Windows Native Redis

Microsoft used to maintain a Windows port. You have two choices:

#### Option B1: GitHub Release Binary
```powershell
# Download Redis for Windows from:
# https://github.com/microsoftarchive/redis/releases
# Download: Redis-x64-5.0.10.msi

# Install and it will add redis-server to PATH
# To start:
redis-server.exe

# In another terminal, test:
redis-cli ping
# Expected: PONG
```

#### Option B2: Chocolatey Package Manager
```powershell
# Install Chocolatey first if needed: https://chocolatey.org/
choco install redis -y

# Start Redis
redis-server.exe

# Test
redis-cli ping
```

#### Update .env
```env
REDIS_URL=redis://localhost:6379/0
REDIS_SOCKET_TIMEOUT=30
REDIS_SOCKET_CONNECT_TIMEOUT=30
```

---

### Option C: Local Docker (Optional)

If using Upstash, verify your Redis URL is correct:

1. Go to [Upstash Console](https://console.upstash.com/)
2. Select your Redis database
3. Click "Connect" tab
4. Copy the **Celery** URL (format: `rediss://...`)
5. Paste into `.env`:
   ```
   REDIS_URL=rediss://default:YOUR_PASSWORD@your-host.upstash.io:6380
   ```

**Note**: Upstash URLs use port **6380** (TLS), not 6379.

---

### Option C: Windows Subsystem for Linux (WSL2)

If you have WSL2 installed:

```bash
# In WSL2 terminal
sudo apt-get update
sudo apt-get install redis-server
wsl -u root -- sh -lc "service redis-server start"

# Verify
redis-cli ping  # Should output: PONG
```

Update `.env`:
```
REDIS_URL=redis://localhost:6379/0
```

---

## Troubleshooting Steps

### 1. Check Redis is Running

**Docker:**
```bash
docker compose ps
# Should show "Up" status for redis service
```

**Local (WSL2/Linux/Mac):**
```bash
redis-cli ping
# Expected: PONG
```

---

### 2. Test Celery Connection

```bash
# In the virtual environment
python -c "from workers.celery_app import celery_app; print(celery_app.connection())"
```

If successful, you'll see connection info. If it hangs for >10 seconds, Redis is unreachable.

---

### 3. Increase Socket Timeouts

If Redis is slow or remote, update `.env`:

```bash
# Increase from default 30s to 60s
REDIS_SOCKET_TIMEOUT=60
REDIS_SOCKET_CONNECT_TIMEOUT=60
```

---

### 4. View Celery Logs

Check detailed error logs:
```bash
# Run worker with verbose logging
python -m celery -A workers.celery_app worker -l debug
```

Look for full stack trace to identify the exact connection issue.

---

### 5. Check Network Connectivity

For remote Redis (Upstash):
```powershell
# Test if you can reach the Redis host
Test-NetConnection -ComputerName intimate-ladybug-66317.upstash.io -Port 6380
```

If this fails, check:
- Firewall rules
- VPN connectivity
- ISP blocking port 6380

---

## Configuration Recommendations

### Development (Local - No Docker)
```env
REDIS_URL=redis://localhost:6379/0
REDIS_SOCKET_TIMEOUT=30
REDIS_SOCKET_CONNECT_TIMEOUT=30

# Setup:
# Option A (WSL2): sudo apt install redis-server && redis-server
# Option B (Windows): choco install redis && redis-server.exe
```

### Production (Upstash Cloud)
```env
REDIS_URL=rediss://default:PASSWORD@host.upstash.io:6380
REDIS_SOCKET_TIMEOUT=60
REDIS_SOCKET_CONNECT_TIMEOUT=45
```

---

## Quick Start

1. **Choose your setup** (Option A recommended):
   - **Option A (WSL2)**: `sudo apt install redis-server && redis-server`
   - **Option B (Windows native)**: Download from GitHub or `choco install redis`
   - **Option C (Docker)**: `docker compose up -d`

2. **Verify Redis is running**:
   ```bash
   redis-cli ping
   # Should output: PONG
   ```

3. **Test your app setup**:
   ```bash
   python diagnose_redis.py
   # Should output: ✅ All checks passed! Redis is ready.
   ```

4. **Start your app**:
   ```bash
   python run.py
   ```

---

## Still Not Working?

1. Check `.env` file exists and has valid `REDIS_URL`
2. Verify Redis is actually running: `docker ps` or `redis-cli ping`
3. Look at worker logs for full error: `python -m celery -A workers.celery_app worker -l debug`
4. Try local Redis first before troubleshooting remote

If you continue to have issues, share the full error output from the Celery worker command above.
