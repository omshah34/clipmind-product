import hashlib
import json
from typing import Any

def make_idempotency_key(*parts: Any) -> str:
    """
    Generate a deterministic SHA-256 idempotency key from multiple parts.
    Ensures that retries of the same logical operation produce the same key.
    """
    processed_parts = []
    for part in parts:
        if isinstance(part, (dict, list)):
            # Deterministic JSON string for complex objects
            processed_parts.append(json.dumps(part, sort_keys=True))
        else:
            processed_parts.append(str(part))
            
    payload = "|".join(processed_parts)
    return hashlib.sha256(payload.encode()).hexdigest()
