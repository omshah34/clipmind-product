import time
import logging
import functools
from typing import Callable, Any, Type, Optional

try:
    import redis
except ImportError:
    # Fallback to a mock if redis is not installed (though it should be)
    redis = None

from core.config import settings

logger = logging.getLogger(__name__)

class CircuitBreakerError(Exception):
    """Exception raised when the circuit breaker is in 'Open' state."""
    pass

class RedisCircuitBreaker:
    """
    A global, distributed circuit breaker using Redis.
    Ensures that if a service (like Whisper/Groq) fails across multiple workers,
    the entire fleet stops hammering it and enters a cooldown period.
    """
    
    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half-open"

    def __init__(
        self,
        name: str,
        fail_threshold: int = 5,
        recovery_timeout: int = 300,  # 5 minutes
        failure_window: int = 60,     # 1 minute
        expected_exceptions: tuple[Type[Exception], ...] = (Exception,)
    ):
        self.name = f"cb:{name}"
        self.fail_threshold = fail_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_window = failure_window
        self.expected_exceptions = expected_exceptions
        
        # Lazy initialization of Redis client
        self._redis: Optional[redis.Redis] = None

    @property
    def redis(self) -> Optional[redis.Redis]:
        if self._redis is None and redis is not None:
            try:
                self._redis = redis.Redis.from_url(
                    settings.redis_url, 
                    decode_responses=True,
                    socket_timeout=2,
                    socket_connect_timeout=2
                )
                self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis unavailable for circuit breaker {self.name}: {e}. Falling back to 'Closed' state.")
                return None
        return self._redis

    def get_state(self) -> str:
        r = self.redis
        if not r:
            return self.STATE_CLOSED
            
        state = r.get(f"{self.name}:state") or self.STATE_CLOSED
        
        if state == self.STATE_OPEN:
            # Check if cooldown has expired
            opened_at = r.get(f"{self.name}:opened_at")
            if not opened_at or (time.time() - float(opened_at)) > self.recovery_timeout:
                self.set_state(self.STATE_HALF_OPEN)
                return self.STATE_HALF_OPEN
                
        return state

    def set_state(self, state: str):
        r = self.redis
        if not r:
            return
            
        logger.info(f"CircuitBreaker [{self.name}] transition: {state}")
        r.set(f"{self.name}:state", state)
        if state == self.STATE_OPEN:
            r.set(f"{self.name}:opened_at", time.time())
        elif state == self.STATE_CLOSED:
            r.delete(f"{self.name}:opened_at")
            r.delete(f"{self.name}:failures")

    def record_failure(self):
        r = self.redis
        if not r:
            return

        now = time.time()
        key = f"{self.name}:failures"
        
        # Use a sorted set to track failure timestamps within the window
        pipe = r.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.zremrangebyscore(key, 0, now - self.failure_window)
        pipe.zcard(key)
        pipe.expire(key, self.failure_window * 2)
        _, _, fail_count, _ = pipe.execute()
        
        if fail_count >= self.fail_threshold:
            self.set_state(self.STATE_OPEN)

    def __call__(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            state = self.get_state()
            
            if state == self.STATE_OPEN:
                raise CircuitBreakerError(f"Circuit {self.name} is OPEN. Service is in cooldown.")

            try:
                result = func(*args, **kwargs)
                
                # If we were in half-open and succeeded, close the circuit
                if state == self.STATE_HALF_OPEN:
                    self.set_state(self.STATE_CLOSED)
                
                return result
            except self.expected_exceptions as e:
                # We only count specific exceptions as failures for the breaker
                self.record_failure()
                raise e
            except Exception as e:
                # Re-raise other exceptions without tripping the breaker
                raise e
                
        return wrapper

# Standard breakers for the application
whisper_breaker = RedisCircuitBreaker(
    name="whisper",
    fail_threshold=5,
    recovery_timeout=300,
    failure_window=60
)

groq_breaker = RedisCircuitBreaker(
    name="groq",
    fail_threshold=10,
    recovery_timeout=120,
    failure_window=30
)
