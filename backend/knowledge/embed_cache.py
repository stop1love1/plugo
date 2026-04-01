"""LRU embedding cache to avoid redundant API calls."""

import hashlib
import time
from collections import OrderedDict

from config import settings


class EmbeddingCache:
    """In-memory LRU cache for query embeddings with TTL."""

    def __init__(
        self,
        max_size: int = settings.embedding_cache_size if hasattr(settings, "embedding_cache_size") else 1000,
        ttl_seconds: int = settings.embedding_cache_ttl if hasattr(settings, "embedding_cache_ttl") else 3600,
    ):
        self._cache: OrderedDict[str, tuple[list[float], float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.strip().lower().encode()).hexdigest()

    def get(self, text: str) -> list[float] | None:
        key = self._key(text)
        if key in self._cache:
            embedding, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                self._cache.move_to_end(key)
                return embedding
            del self._cache[key]
        return None

    def put(self, text: str, embedding: list[float]):
        key = self._key(text)
        self._cache[key] = (embedding, time.time())
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._cache)


# Singleton instance
embed_cache = EmbeddingCache()
