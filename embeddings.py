"""Embedders. The default is a dependency-free hashing embedder so the project runs
anywhere; swap in a real model by implementing the same `embed(text) -> list[float]`
interface (unit-normalised vectors)."""
import hashlib
import math
import re
from typing import Protocol

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "in", "on", "for",
    "what", "whats", "which", "who", "how", "do", "does", "did", "can", "could", "you",
    "me", "i", "please", "tell", "about", "it", "its", "this", "that", "and", "or",
}


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class HashingEmbedder:
    """Signed feature hashing over words, word bigrams and char trigrams."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _bucket(self, feature: str) -> tuple[int, float]:
        h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        return h % self.dim, 1.0 if (h >> 63) & 1 else -1.0

    def embed(self, text: str) -> list[float]:
        words = [w for w in tokenize(text) if w not in STOPWORDS] or tokenize(text)
        feats: list[tuple[str, float]] = [(f"w:{w}", 1.0) for w in words]
        feats += [(f"b:{a}_{b}", 0.6) for a, b in zip(words, words[1:])]
        for w in words:
            padded = f"^{w}$"
            feats += [(f"c:{padded[i:i + 3]}", 0.25) for i in range(len(padded) - 2)]
        vec = [0.0] * self.dim
        for f, weight in feats:
            idx, sign = self._bucket(f)
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))