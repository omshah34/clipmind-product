#!/usr/bin/env python
"""
Redis Connection Diagnostics Script
Quickly tests Redis connectivity and configuration.
Usage: python diagnose_redis.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import settings
import redis


def test_redis_connection():
    """Test basic Redis connection."""
    print("\n" + "="*70)
    print("CLIPMIND REDIS DIAGNOSTICS")
    print("="*70)
    
    print(f"\n🔍 Configuration:")
    print(f"   REDIS_URL: {mask_redis_url(settings.redis_url)}")
    print(f"   Socket Timeout: {settings.redis_socket_timeout}s")
    print(f"   Connect Timeout: {settings.redis_socket_connect_timeout}s")
    
    print(f"\n🧪 Testing Redis Connection...")
    
    try:
        # Parse connection type
        is_tls = settings.redis_url.startswith("rediss://")
        
        # Create Redis client with same timeouts as Celery
        r = redis.Redis.from_url(
            settings.redis_url,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            socket_keepalive=True,
            decode_responses=True,
            health_check_interval=30,
        )
        
        # Test PING
        response = r.ping()
        
        if response:
            print(f"   ✅ SUCCESS: Connected to Redis")
            print(f"   Protocol: {'TLS' if is_tls else 'Plain TCP'}")
            
            # Get info
            info = r.info()
            print(f"\n📊 Redis Info:")
            print(f"   Version: {info.get('redis_version', 'Unknown')}")
            print(f"   Mode: {info.get('redis_mode', 'standalone')}")
            print(f"   Connected Clients: {info.get('connected_clients', 0)}")
            print(f"   Used Memory: {info.get('used_memory_human', 'Unknown')}")
            print(f"   Uptime: {info.get('uptime_in_seconds', 0)} seconds")
            
            return True
            
    except redis.exceptions.ConnectionError as e:
        print(f"   ❌ CONNECTION FAILED")
        print(f"   Error: {str(e)[:100]}")
        print(f"\n   Possible causes:")
        print(f"   - Redis is not running")
        print(f"   - Wrong REDIS_URL in .env")
        print(f"   - Firewall blocking connection")
        print(f"   - Invalid credentials (for remote Redis)")
        return False
        
    except redis.exceptions.TimeoutError as e:
        print(f"   ❌ TIMEOUT")
        print(f"   Error: {str(e)[:100]}")
        print(f"\n   Possible causes:")
        print(f"   - Redis is slow or unresponsive")
        print(f"   - Network latency too high")
        print(f"   - Socket timeout too short ({settings.redis_socket_timeout}s)")
        print(f"\n   Try increasing timeouts in .env:")
        print(f"   REDIS_SOCKET_TIMEOUT=60")
        print(f"   REDIS_SOCKET_CONNECT_TIMEOUT=60")
        return False
        
    except Exception as e:
        print(f"   ❌ ERROR: {type(e).__name__}: {str(e)[:100]}")
        return False


def test_celery_connection():
    """Test Celery can connect to Redis."""
    print(f"\n🧪 Testing Celery-Redis Connection...")
    
    try:
        from workers.celery_app import celery_app
        
        # Attempt to create a connection
        with celery_app.connection() as conn:
            print(f"   ✅ Celery connected successfully")
            return True
            
    except Exception as e:
        print(f"   ❌ Celery connection failed: {type(e).__name__}")
        print(f"   Error: {str(e)[:100]}")
        return False


def mask_redis_url(url: str) -> str:
    """Mask sensitive parts of Redis URL."""
    if "rediss://" in url or "redis://" in url:
        # Replace password with ***
        if "@" in url:
            parts = url.split("@")
            proto_part = parts[0].split("://")[0] + "://"
            host_part = "@".join(parts[1:])
            credentials = "*" * 10
            return f"{proto_part}{credentials}@{host_part}"
    return url


def main():
    """Run all diagnostics."""
    redis_ok = test_redis_connection()
    celery_ok = test_celery_connection()
    
    print("\n" + "="*70)
    if redis_ok and celery_ok:
        print("✅ All checks passed! Redis is ready.")
        print("="*70 + "\n")
        return 0
    else:
        print("❌ Some checks failed. See troubleshooting guide:")
        print("   docs/REDIS_CELERY_TROUBLESHOOTING.md")
        print("="*70 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
