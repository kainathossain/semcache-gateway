"""Model specs, pricing and backends. MockLLM is deterministic and sleeps nothing, so
benchmarks are reproducible; AnthropicLLM is a thin adapter for real calls."""
import hashlib
from dataclasses import dataclass
from typing import Protocol

from router import complexity_score


@dataclass(frozen=True)
class ModelSpec:
    name: str
    in_per_mtok: float   # USD per 1M input tokens (illustrative; set your real prices)
    out_per_mtok: float  # USD per 1M output tokens
    base_latency_s: float
    s_per_token: float

    def cost(self, in_tokens: int, out_tokens: int) -> float:
        return (in_tokens * self.in_per_mtok + out_tokens * self.out_per_mtok) / 1_000_000


SMALL = ModelSpec("small", 0.25, 1.25, 0.25, 0.004)
LARGE = ModelSpec("large", 3.00, 15.00, 0.80, 0.012)
EMBEDDING_PER_MTOK = 0.02  # cost of embedding the query for the cache lookup


@dataclass
class Completion:
    text: str
    in_tokens: int
    out_tokens: int
    latency_s: float
    confidence: float


class LLM(Protocol):
    spec: ModelSpec

    def generate(self, prompt: str, context_tokens: int = 0) -> Completion: ...


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockLLM:
    def __init__(self, spec: ModelSpec):
        self.spec = spec

    def generate(self, prompt: str, context_tokens: int = 0) -> Completion:
        h = int.from_bytes(hashlib.blake2b(prompt.encode(), digest_size=4).digest(), "big")
        c, _ = complexity_score(prompt)
        out_tokens = int(60 + 400 * c + (h % 60))
        # Small models are less sure on hard prompts; large models stay confident.
        conf = 0.97 if self.spec.name == "large" else max(0.2, 1.0 - 1.1 * c - (h % 10) / 100)
        latency = self.spec.base_latency_s + out_tokens * self.spec.s_per_token
        return Completion(f"[{self.spec.name}] answer to: {prompt[:60]}", est_tokens(prompt) + context_tokens,
                          out_tokens, latency, conf)


class AnthropicLLM:
    """Real backend. Requires `pip install anthropic` and ANTHROPIC_API_KEY.
    Confidence is a placeholder (0.9); derive it from a logprob-free signal such as a
    self-rating or a verifier if you want escalation to be meaningful."""

    def __init__(self, spec: ModelSpec, model_id: str, max_tokens: int = 1024):
        import anthropic  # lazy import
        self.spec, self.model_id, self.max_tokens = spec, model_id, max_tokens
        self.client = anthropic.Anthropic()

    def generate(self, prompt: str, context_tokens: int = 0) -> Completion:
        import time
        t = time.perf_counter()
        r = self.client.messages.create(model=self.model_id, max_tokens=self.max_tokens,
                                        messages=[{"role": "user", "content": prompt}])
        return Completion(r.content[0].text, r.usage.input_tokens, r.usage.output_tokens,
                          time.perf_counter() - t, 0.9)