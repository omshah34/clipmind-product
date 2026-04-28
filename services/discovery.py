import asyncio
import logging
import json
import os
import re
import warnings
from typing import List, Dict, Any
from pathlib import Path

# Heavy imports are lazy-loaded to keep app startup fast
# from sentence_transformers import SentenceTransformer
# import joblib
# import numpy as np

from core.config import settings

logger = logging.getLogger(__name__)


def _quiet_embedding_dependency_warnings() -> None:
    """Keep optional embedding downloads from polluting worker logs."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    warnings.filterwarnings(
        "ignore",
        message=r".*unauthenticated requests to the HF Hub.*",
    )
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("transformers").setLevel(logging.ERROR)
    try:
        from huggingface_hub.utils import logging as hf_logging
        from transformers.utils import logging as transformers_logging

        hf_logging.set_verbosity_error()
        transformers_logging.set_verbosity_error()
    except Exception:
        pass

class DiscoveryIndexLockError(Exception):
    """Raised when the discovery index lock cannot be acquired."""
    pass

class DiscoveryService:
    """
    Handles AI Semantic Search and discovery across video content.
    Gap Exploited: Manual scrubbing through hours of footage for specific topics.
    Architecture: Disk-persisted HNSW index (Phase 3 fallback for limited environments).
    """
    
    def __init__(self):
        self.model_name = "all-MiniLM-L6-v2"
        self._model = None
        
        # Gap 191: Isolate index spaces per model to prevent dimension mismatch crashes
        safe_model_name = self.model_name.replace("/", "_").replace("\\", "_")
        self._index_path = settings.local_storage_dir / "discovery" / f"embeddings_{safe_model_name}.json"
        self._index_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            _quiet_embedding_dependency_warnings()
            from sentence_transformers import SentenceTransformer
            logger.info("Loading semantic embedding model: %s", self.model_name)
            kwargs = {"token": settings.hf_token} if settings.hf_token else {}
            try:
                self._model = SentenceTransformer(self.model_name, **kwargs)
            except TypeError:
                self._model = SentenceTransformer(self.model_name)
        return self._model

    def generate_embedding(self, text: str) -> List[float]:
        """Convert text into a semantic vector (CPU-bound, not async-safe)."""
        return self.model.encode(text).tolist()

    async def _generate_embedding_async(self, text: str) -> List[float]:
        """Offload CPU-bound embedding to a thread so the event loop is not blocked (Gap 36)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate_embedding, text)

    async def _encode_texts_async(self, texts: List[str]):
        """Batch encode texts in a thread executor (Gap 36)."""
        import functools
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self.model.encode, texts))

    def _load_index(self) -> Dict[str, Any]:
        """Load the vector index from disk (JSON — no unsafe pickle, Gap 32)."""
        if self._index_path.exists():
            try:
                with self._index_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Discovery index corrupt or unreadable, resetting: %s", e)
        return {"embeddings": [], "metadata": []}

    def _save_index(self, index: Dict[str, Any]):
        """Persist the vector index as JSON (Gap 32 — replaces joblib/pickle)."""
        with self._index_path.open("w", encoding="utf-8") as f:
            import numpy as np
            # Convert numpy arrays to lists for JSON serialisability
            safe = {
                "embeddings": [
                    emb.tolist() if hasattr(emb, "tolist") else emb
                    for emb in index["embeddings"]
                ],
                "metadata": index["metadata"],
            }
            json.dump(safe, f)

    async def add_job_to_index(self, job_id: str, transcript_json: Dict[str, Any]):
        """
        Embeds a job's transcript and stores it in the local index.
        Called during the pipeline's metadata stage.
        """
        import numpy as np
        import redis
        
        logger.info("Indexing job %s for semantic discovery", job_id)
        
        # We index at the segment level for granular discovery
        segments = transcript_json.get("segments", [])
        if not segments:
            return

        texts = [s.get("text", "") for s in segments]
        # Gap 36: Run CPU-bound encoding in a thread pool so we don't block the event loop
        embeddings = await self._encode_texts_async(texts)
        
        # Gap 203: Robust Redis-backed atomic lock for concurrent index updates
        from core.redis_utils import RobustRedisLock
        r = redis.from_url(settings.redis_url)
        lock = RobustRedisLock(
            r, "discovery_index_lock", 
            timeout=120, heartbeat_interval=30, 
            blocking=True, blocking_timeout=15
        )
        
        try:
            with lock:
                index = self._load_index()
                for i, emb in enumerate(embeddings):
                    index["embeddings"].append(emb)
                    index["metadata"].append({
                        "job_id": job_id,
                        "start": segments[i].get("start"),
                        "end": segments[i].get("end"),
                        "text": segments[i].get("text")
                    })
                
                self._save_index(index)
                logger.debug("Added %d segments from job %s to semantic index", len(segments), job_id)
        except RuntimeError as e:
            # RobustRedisLock.__enter__ raises RuntimeError if acquisition fails
            logger.error("Could not acquire discovery index lock for job %s: %s", job_id, e)
            raise DiscoveryIndexLockError(f"Could not acquire index lock after 15s")

    async def remove_job_from_index(self, job_id: str):
        """
        Gap 198: Remove all vectors associated with a job_id to prevent stale ghost results.
        """
        import redis
        logger.info("Removing job %s from semantic discovery index", job_id)
        
        # Gap 203: Robust Redis-backed atomic lock
        from core.redis_utils import RobustRedisLock
        r = redis.from_url(settings.redis_url)
        lock = RobustRedisLock(
            r, "discovery_index_lock", 
            timeout=120, heartbeat_interval=30,
            blocking=True, blocking_timeout=15
        )
        
        try:
            with lock:
                index = self._load_index()
                if not index["metadata"]:
                    return
                    
                # Filter out the job
                keep_indices = [i for i, meta in enumerate(index["metadata"]) if str(meta.get("job_id")) != str(job_id)]
                
                if len(keep_indices) == len(index["metadata"]):
                    return # Nothing to remove
                    
                index["embeddings"] = [index["embeddings"][i] for i in keep_indices]
                index["metadata"] = [index["metadata"][i] for i in keep_indices]
                
                self._save_index(index)
                logger.debug("Removed job %s from semantic index", job_id)
        except RuntimeError as e:
            logger.error("Could not acquire discovery index lock to remove job %s: %s", job_id, e)
            raise DiscoveryIndexLockError(f"Could not acquire index lock after 15s")

    async def search_clips(self, query: str, user_id: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Semantic search across all indexed content.
        Uses cosine similarity for ranking.
        Gap 52: Input sanitized — length-capped and stripped of control chars.
        """
        import numpy as np
        # Gap 52: Sanitize query — strip non-printable chars and cap length
        query = re.sub(r"[^\x20-\x7E\u00A0-\uFFFF]", "", query).strip()
        if not query:
            return []
        query = query[:512]  # Cap at 512 chars to prevent embedding model abuse
        limit = max(1, min(limit, 20))  # Cap limit between 1 and 20

        # Gap 36: Offload embedding to executor
        query_emb = await self._generate_embedding_async(query)
        index = self._load_index()
        
        if not index["embeddings"]:
            return []

        # Convert to numpy for fast distance calculation
        embeddings = np.array(index["embeddings"])
        query_vec = np.array(query_emb)
        
        # Simple cosine similarity: (A . B) / (||A|| ||B||)
        # Note: SentenceTransformer models often return normalized vectors, 
        # so dot product is sufficient.
        similarities = np.dot(embeddings, query_vec)
        
        # Get top-N indices
        top_indices = np.argsort(similarities)[::-1][:limit]
        
        results = []
        for idx in top_indices:
            results.append({
                "score": float(similarities[idx]),
                **index["metadata"][idx]
            })
            
        return results

def get_discovery_service() -> DiscoveryService:
    return DiscoveryService()
