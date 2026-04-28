import time
import unittest
from unittest.mock import MagicMock, patch
import redis
from core.redis_utils import RobustRedisLock

class TestRobustRedisLock(unittest.TestCase):
    def setUp(self):
        self.mock_redis = MagicMock(spec=redis.Redis)
        self.lock_name = "test_lock"
        self.token_pattern = r"^[0-9a-f-]{36}$"

    def test_acquire_success(self):
        self.mock_redis.set.return_value = True
        lock = RobustRedisLock(self.mock_redis, self.lock_name, timeout=10)
        
        result = lock.acquire(blocking=False)
        
        self.assertTrue(result)
        self.mock_redis.set.assert_called_once()
        # Verify it uses NX and EX
        args, kwargs = self.mock_redis.set.call_args
        self.assertEqual(args[0], self.lock_name)
        self.assertEqual(kwargs["ex"], 10)
        self.assertTrue(kwargs["nx"])

    def test_acquire_fail_no_blocking(self):
        self.mock_redis.set.return_value = False
        lock = RobustRedisLock(self.mock_redis, self.lock_name)
        
        result = lock.acquire(blocking=False)
        
        self.assertFalse(result)

    def test_ownership_verification_on_release(self):
        # Mock eval for Lua script
        # Lua returns 1 for success, 0 for failure
        self.mock_redis.eval.return_value = 1
        lock = RobustRedisLock(self.mock_redis, self.lock_name)
        lock.token = "my-unique-token"
        
        result = lock.release()
        
        self.assertTrue(result)
        # Verify Lua script is called with correct token
        self.mock_redis.eval.assert_called_once()
        args = self.mock_redis.eval.call_args[0]
        self.assertEqual(args[2], self.lock_name)
        self.assertEqual(args[3], "my-unique-token")

    def test_release_failure_wrong_owner(self):
        self.mock_redis.eval.return_value = 0
        lock = RobustRedisLock(self.mock_redis, self.lock_name)
        
        result = lock.release()
        
        self.assertFalse(result)

    def test_heartbeat_thread_extension(self):
        self.mock_redis.set.return_value = True
        self.mock_redis.eval.return_value = 1
        
        # Use a short timeout and heartbeat for testing
        lock = RobustRedisLock(self.mock_redis, self.lock_name, timeout=2, heartbeat_interval=0.1)
        
        lock.acquire()
        time.sleep(0.25) # Wait for at least two heartbeats
        lock.release()
        
        # Verify extend (via eval) was called multiple times
        # We need to filter eval calls since release also uses eval
        extend_calls = [
            call for call in self.mock_redis.eval.call_args_list 
            if "pexpire" in str(call)
        ]
        self.assertGreaterEqual(len(extend_calls), 1)

    def test_heartbeat_failure_stops_thread(self):
        self.mock_redis.set.return_value = True
        # First extend fails
        self.mock_redis.eval.return_value = 0
        
        lock = RobustRedisLock(self.mock_redis, self.lock_name, timeout=2, heartbeat_interval=0.1)
        
        with patch('core.redis_utils.logger') as mock_logger:
            lock.acquire()
            time.sleep(0.2)
            
            # Verify error was logged
            mock_logger.error.assert_any_call("Heartbeat failed for lock %s: Lock lost or ownership mismatch", self.lock_name)
            
            # Verify thread is no longer active (eventually)
            # (In reality, the loop breaks)
            self.assertFalse(lock._heartbeat_thread.is_alive())

    def test_acquire_with_retries(self):
        # Fail first two times, succeed on third
        self.mock_redis.set.side_effect = [False, False, True]
        lock = RobustRedisLock(
            self.mock_redis, self.lock_name, 
            retry_attempts=3, retry_delay_seconds=0.1
        )
        
        result = lock.acquire(blocking=False)
        
        self.assertTrue(result)
        self.assertEqual(self.mock_redis.set.call_count, 3)

    def test_heartbeat_exception_resilience(self):
        self.mock_redis.set.return_value = True
        # First extend raises exception, second succeeds
        self.mock_redis.eval.side_effect = [Exception("Redis error"), 1]
        
        lock = RobustRedisLock(self.mock_redis, self.lock_name, timeout=2, heartbeat_interval=0.1)
        
        with patch('core.redis_utils.logger.exception') as mock_exc:
            lock.acquire()
            time.sleep(0.6) # Wait for multiple heartbeats
            lock.release()
            
            # Verify exception was logged at least once
            self.assertTrue(mock_exc.called, "logger.exception was not called")
            # Verify the thread kept running after the exception and called eval again
            self.assertGreaterEqual(self.mock_redis.eval.call_count, 2)

if __name__ == "__main__":
    unittest.main()
