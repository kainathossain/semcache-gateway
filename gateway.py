"""Gateway: cache lookup -> route -> (escalate) -> cache store, logging cost and latency."""
import time
from dataclasses import dataclass
from typing import Optional

from cache import SemanticCache
from llm import EMBEDDING_PER_MTOK, LARGE, SMALL, LLM, MockLLM, est_tokens
from metrics import MetricsStore
from router import Router


@dataclass
class Response:
    text: str
    outcome: str      # hit | small | large | escalated
    model: str
    cost: float
    baseline_cost: float
    latency_s: float
    similarity: float


class Gateway:
    def __init__(self, cache: Optional[SemanticCache] = None, router: Optional[Router] = None,
                 small: Optional[LLM] = None, large: Optional[LLM] = None,
                 metrics: Optional[MetricsStore] = None, escalate_below: float = 0.6):
        self.cache = cache or SemanticCache()
        self.router = router or Router()
        self.small = small or MockLLM(SMALL)
        self.large = large or MockLLM(LARGE)
        self.metrics = metrics or MetricsStore()
        self.escalate_below = escalate_below

    def ask(self, query: str, namespace: str = "default") -> Response:
        t0 = time.perf_counter()
        in_tok = est_tokens(query)
        embed_cost = in_tok * EMBEDDING_PER_MTOK / 1_000_000
        vec = self.cache.embedder.embed(query)
        look = self.cache.lookup(query, namespace, vec)
        decision = self.router.route(query)

        if look.entry:
            e = look.entry
            cost = embed_cost
            # Baseline = what the naive setup (always the large model) would have paid.
            baseline = self.large.spec.cost(in_tok, e.out_tokens)
            latency = time.perf_counter() - t0 + 0.005  # + nominal vector-store round trip
            resp = Response(e.response, "hit", "cache", cost, baseline, latency, look.score)
            out_tok, outcome, model = e.out_tokens, "hit", "cache"
        else:
            comp = (self.large if decision.tier == "large" else self.small).generate(query)
            spec = self.large.spec if decision.tier == "large" else self.small.spec
            cost, latency = embed_cost + spec.cost(comp.in_tokens, comp.out_tokens), comp.latency_s
            outcome, model = decision.tier, spec.name
            if decision.tier == "small" and comp.confidence < self.escalate_below:
                big = self.large.generate(query)  # pay for both: the cost of a wrong routing guess
                cost += self.large.spec.cost(big.in_tokens, big.out_tokens)
                latency += big.latency_s
                comp, outcome, model = big, "escalated", self.large.spec.name
            baseline = self.large.spec.cost(comp.in_tokens, comp.out_tokens)
            self.cache.put(query, comp.text, comp.out_tokens, namespace, vec=vec)
            out_tok = comp.out_tokens
            resp = Response(comp.text, outcome, model, cost, baseline, latency, look.score)

        self.metrics.record(namespace=namespace, query=query, outcome=outcome, model=model,
                            similarity=look.score, complexity=decision.score, in_tokens=in_tok,
                            out_tokens=out_tok, cost=resp.cost, baseline_cost=resp.baseline_cost,
                            latency_s=resp.latency_s)
        return resp