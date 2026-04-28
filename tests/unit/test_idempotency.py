import unittest
from core.utils import make_idempotency_key

class TestIdempotency(unittest.TestCase):
    def test_make_idempotency_key_deterministic(self):
        parts = ("event_type", {"data": 123}, "user_id")
        key1 = make_idempotency_key(*parts)
        key2 = make_idempotency_key(*parts)
        self.assertEqual(key1, key2)
        
    def test_make_idempotency_key_different_inputs(self):
        key1 = make_idempotency_key("event1", {"a": 1})
        key2 = make_idempotency_key("event1", {"a": 2})
        self.assertNotEqual(key1, key2)
        
    def test_make_idempotency_key_dict_sorting(self):
        # Keys in dict are different order but content is same
        key1 = make_idempotency_key({"a": 1, "b": 2})
        key2 = make_idempotency_key({"b": 2, "a": 1})
        self.assertEqual(key1, key2)

if __name__ == "__main__":
    unittest.main()
