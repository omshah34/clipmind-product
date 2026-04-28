import logging
import threading
import time
import uuid
from typing import Optional
import redis

logger = logging.getLogger(__name__)

class RobustRedisLock:
    """
    A robust Redis distributed lock with ownership verification and a heartbeat thread.
    Gap 203: Ensures locks are not orphaned on crash and don't expire during long tasks.
    """
    
    # Lua script to release the lock only if the token matches
    RELEASE_LUA = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    
    # Lua script to extend the lock only if the token matches
    EXTEND_LUA = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("pexpire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """

    def __init__(
        self, 
        redis_client: redis.Redis, 
        name: str, 
        timeout: int = 60, 
        heartbeat_interval: Optional[int] = None,
        blocking: bool = True,
        blocking_timeout: Optional[int] = None,
        retry_attempts: int = 1,
        retry_delay_seconds: float = 0.5
    ):
        self.redis = redis_client
        self.name = name
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self.blocking = blocking
        self.blocking_timeout = blocking_timeout
        self.retry_attempts = max(1, retry_attempts)
        self.retry_delay_seconds = retry_delay_seconds
        self.token = str(uuid.uuid4())
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()

    def acquire(self, blocking: Optional[bool] = None, blocking_timeout: Optional[int] = None) -> bool:
        """
        Acquire the lock with the unique token.
        Supports retries if retry_attempts > 1.
        Returns True if acquired, False otherwise.
        """
        should_block = self.blocking if blocking is None else blocking
        timeout_val = self.blocking_timeout if blocking_timeout is None else blocking_timeout
        
        attempts = 0
        while attempts < self.retry_attempts:
            start_time = time.time()
            while True:
                # nx=True ensures we only set if it doesn't exist
                # ex=self.timeout sets the TTL in seconds
                acquired = self.redis.set(self.name, self.token, ex=self.timeout, nx=True)
                if acquired:
                    logger.debug("Acquired lock %s with token %s", self.name, self.token)
                    if self.heartbeat_interval:
                        self._start_heartbeat()
                    return True
                
                if not should_block:
                    break # Break inner loop to check outer retry loop
                
                if timeout_val is not None and (time.time() - start_time) > timeout_val:
                    break # Break inner loop to check outer retry loop
                
                time.sleep(0.1)
            
            attempts += 1
            if attempts < self.retry_attempts:
                logger.debug("Lock %s acquisition failed, retrying in %fs (attempt %d/%d)", 
                             self.name, self.retry_delay_seconds, attempts + 1, self.retry_attempts)
                time.sleep(self.retry_delay_seconds)
        
        return False

    def release(self) -> bool:
        """
        Release the lock using the Lua script for ownership verification.
        """
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1.0)
            
        try:
            result = self.redis.eval(self.RELEASE_LUA, 1, self.name, self.token)
            if result:
                logger.debug("Released lock %s", self.name)
                return True
            else:
                logger.warning("Failed to release lock %s: Ownership mismatch or already expired", self.name)
                return False
        except Exception as e:
            logger.error("Error releasing lock %s: %s", self.name, e)
            return False

    def extend(self) -> bool:
        """
        Extend the lock TTL if we still own it.
        """
        try:
            # pexpire takes milliseconds
            result = self.redis.eval(self.EXTEND_LUA, 1, self.name, self.token, self.timeout * 1000)
            if result:
                logger.debug("Extended lock %s", self.name)
                return True
            else:
                logger.warning("Failed to extend lock %s: Ownership lost", self.name)
                return False
        except Exception as e:
            logger.error("Error extending lock %s: %s", self.name, e)
            return False

    def _start_heartbeat(self):
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat_loop(self):
        """
        Background loop to extend the lock periodically.
        """
        interval = self.heartbeat_interval or (self.timeout / 2)
        logger.debug("Starting heartbeat for lock %s every %ds", self.name, interval)
        
        while not self._stop_heartbeat.is_set():
            time.sleep(interval)
            if self._stop_heartbeat.is_set():
                break
            
            try:
                # extend() returns True on success, False on ownership loss or error
                # We want to distinguish between "lost lock" and "transient error"
                # So we call extend directly and check the result of eval
                result = self.redis.eval(self.EXTEND_LUA, 1, self.name, self.token, self.timeout * 1000)
                if result:
                    logger.debug("Extended lock %s", self.name)
                else:
                    logger.error("Heartbeat failed for lock %s: Lock lost or ownership mismatch", self.name)
                    break
            except Exception as e:
                logger.exception("Heartbeat thread encountered a transient error for lock %s: %s", self.name, e)
                # Don't break, try again next interval
        
        logger.debug("Heartbeat stopped for lock %s", self.name)

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Could not acquire lock {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
