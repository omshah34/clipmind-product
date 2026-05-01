import redis
from core.config import settings

def get_redis_client():
    """Returns a Redis client using settings."""
    return redis.from_url(
        settings.redis_url,
        socket_timeout=settings.redis_socket_timeout,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
    )
