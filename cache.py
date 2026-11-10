"""Semantic cache: return a stored answer when a new query's embedding is close enough
to a previous one. Brute-force scan here; swap the scan for an ANN index (FAISS, HNSW,
pgvector) once you pass ~100k entries."""
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from embeddings import Embedder, HashingEmbedder, cosine


def _numbers(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"\d+(?:\.\d+)?", text))


_NEGATIONS = {"not", "no", "never", "without", "cannot", "dont", "isnt", "wont"}


def _negated(text: str) -> bool:
    return bool(set(re.findall(r"[a-z]+", text.lower().replace("'", ""))) & _NEGATIONS)


@dataclass
class CacheEntry:
    id: int
    namespace: str
    query: str
    vec: list[float]
    response: str
    out_tokens: int
    created: float
    last_used: float
    ttl: Optional[float]
    hits: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Lookup:
    entry: Optional[CacheEntry]
    score: float  # best similarity seen, even on a miss (useful for tuning)


class SemanticCache:
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        threshold: float = 0.85,
        max_entries: int = 10_000,
        default_ttl: Optional[float] = 24 * 3600,
        clock=time.time,
    ):
        self.embedder = embedder or HashingEmbedder()
        self.threshold = threshold
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self.clock = clock
        self._entries: dict[int, CacheEntry] = {}
        self._next_id = 1

    def __len__(self) -> int:
        return len(self._entries)

    def lookup(self, query: str, namespace: str = "default", vec: Optional[list[float]] = None) -> Lookup:
        vec = vec or self.embedder.embed(query)
        now = self.clock()
        best, best_score = None, 0.0
        expired = []
        for e in self._entries.values():
            if e.ttl is not None and now - e.created > e.ttl:
                expired.append(e.id)
                continue
            if e.namespace != namespace:
                continue
            s = cosine(vec, e.vec)
            if s > best_score:
                best, best_score = e, s
        for i in expired:
            del self._entries[i]
        # Guards against the classic false positives of embedding similarity:
        # "revenue in 2023" vs "revenue in 2024", or "do X" vs "do not X".
        if best and best_score >= self.threshold:
            if _numbers(query) != _numbers(best.query) or _negated(query) != _negated(best.query):
                return Lookup(None, best_score)
            best.hits += 1
            best.last_used = now
            return Lookup(best, best_score)
        return Lookup(None, best_score)

    def put(self, query: str, response: str, out_tokens: int, namespace: str = "default",
            ttl: Optional[float] = None, vec: Optional[list[float]] = None, **meta) -> CacheEntry:
        vec = vec or self.embedder.embed(query)
        now = self.clock()
        if len(self._entries) >= self.max_entries:  # LRU eviction
            victim = min(self._entries.values(), key=lambda e: e.last_used)
            del self._entries[victim.id]
        e = CacheEntry(self._next_id, namespace, query, vec, response, out_tokens, now, now,
                       ttl if ttl is not None else self.default_ttl, meta=meta)
        self._entries[e.id] = e
        self._next_id += 1
        return e

    def invalidate(self, namespace: Optional[str] = None) -> int:
        """Drop a namespace (e.g. when the underlying corpus version changes) or everything."""
        ids = [i for i, e in self._entries.items() if namespace is None or e.namespace == namespace]
        for i in ids:
            del self._entries[i]
        return len(ids)