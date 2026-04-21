import logging
import json
import os
from typing import List, Dict, Any
from pathlib import Path

# Heavy imports are lazy-loaded to keep app startup fast
# from sentence_transformers import SentenceTransformer
# import joblib
# import numpy as np

from core.config import settings

logger = logging.getLogger(__name__)

class DiscoveryService:
    """
    Handles AI Semantic Search and discovery across video content.
    Gap Exploited: Manual scrubbing through hours of footage for specific topics.
    Architecture: Disk-persisted HNSW index (Phase 3 fallback for limited environments).
    """
    
    def __init__(self):
        self.model_name = "all-MiniLM-L6-v2"
        self._model = None
        self._index_path = settings.local_storage_dir / "discovery" / "embeddings.jbl"
        self._index_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading semantic embedding model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def generate_embedding(self, text: str) -> List[float]:
        """Convert text into a semantic vector."""
        return self.model.encode(text).tolist()

    def _load_index(self) -> Dict[str, Any]:
        """Load the vector index from disk."""
        import joblib
        if self._index_path.exists():
            return joblib.load(self._index_path)
        return {"embeddings": [], "metadata": []}

    def _save_index(self, index: Dict[str, Any]):
        """Save the vector index to disk."""
        import joblib
        joblib.dump(index, self._index_path)

    async def add_job_to_index(self, job_id: str, transcript_json: Dict[str, Any]):
        """
        Embeds a job's transcript and stores it in the local index.
        Called during the pipeline's metadata stage.
        """
        import numpy as np
        logger.info("Indexing job %s for semantic discovery", job_id)
        
        # We index at the segment level for granular discovery
        segments = transcript_json.get("segments", [])
        if not segments:
            return

        texts = [s.get("text", "") for s in segments]
        embeddings = self.model.encode(texts)
        
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

    async def search_clips(self, query: str, user_id: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Semantic search across all indexed content.
        Uses cosine similarity for ranking.
        """
        import numpy as np
        query_emb = self.generate_embedding(query)
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
