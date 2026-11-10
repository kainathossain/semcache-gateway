import unittest

from cache import SemanticCache
from gateway import Gateway
from llm import LARGE, SMALL
from metrics import MetricsStore
from router import Router


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class CacheTests(unittest.TestCase):
    def test_paraphrase_hits_and_unrelated_misses(self):
        c = SemanticCache()
        c.put("What is the capital of France?", "Paris", 5)
        self.assertIsNotNone(c.lookup("capital of France?").entry)
        self.assertIsNone(c.lookup("How do I reset my password?").entry)

    def test_number_guard(self):
        c = SemanticCache()
        c.put("What was our revenue in 2023?", "x", 5)
        self.assertIsNone(c.lookup("What was our revenue in 2024?").entry)

    def test_negation_guard(self):
        c = SemanticCache()
        c.put("Should I enable the cache for writes?", "yes", 5)
        self.assertIsNone(c.lookup("Should I not enable the cache for writes?").entry)

    def test_ttl_namespace_and_lru(self):
        clk = Clock()
        c = SemanticCache(default_ttl=10, max_entries=2, clock=clk)
        c.put("alpha question one", "a", 1, namespace="t1")
        self.assertIsNone(c.lookup("alpha question one", namespace="t2").entry)  # tenant isolation
        self.assertIsNotNone(c.lookup("alpha question one", namespace="t1").entry)
        clk.t += 11
        self.assertIsNone(c.lookup("alpha question one", namespace="t1").entry)  # expired
        c.put("first topic here", "1", 1); clk.t += 1
        c.put("second topic there", "2", 1); clk.t += 1
        c.put("third topic anywhere", "3", 1)
        self.assertEqual(len(c), 2)  # LRU evicted one

    def test_invalidate(self):
        c = SemanticCache()
        c.put("what is x", "a", 1, namespace="v1")
        self.assertEqual(c.invalidate("v1"), 1)
        self.assertEqual(len(c), 0)


class RouterTests(unittest.TestCase):
    def test_tiers(self):
        r = Router()
        self.assertEqual(r.route("What is the capital of France?").tier, "small")
        hard = "Design a sharding strategy and analyze the trade-offs step by step."
        self.assertEqual(r.route(hard).tier, "large")


class GatewayTests(unittest.TestCase):
    def test_hit_is_cheaper_and_cost_math(self):
        gw = Gateway(metrics=MetricsStore())
        a = gw.ask("What is the capital of France?")
        b = gw.ask("capital of France?")
        self.assertEqual(a.outcome, "small")
        self.assertEqual(b.outcome, "hit")
        self.assertLess(b.cost, a.cost / 10)
        self.assertLess(b.latency_s, a.latency_s)
        s = gw.metrics.stats()
        self.assertEqual(s["requests"], 2)
        self.assertAlmostEqual(s["cost"], a.cost + b.cost, places=12)
        self.assertGreater(s["savings"], 0)

    def test_small_cheaper_than_large_same_tokens(self):
        self.assertLess(SMALL.cost(100, 100), LARGE.cost(100, 100))

    def test_escalation_pays_for_both(self):
        gw = Gateway(escalate_below=1.01)  # force escalation of every small-routed query
        r = gw.ask("What is the capital of France?")
        self.assertEqual(r.outcome, "escalated")
        self.assertGreaterEqual(r.cost, r.baseline_cost)  # misrouting costs more than baseline


if __name__ == "__main__":
    unittest.main()