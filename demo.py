"""Simulate RAG-style traffic: a Zipf-distributed mix of simple and hard questions, each
asked in several paraphrases, and report cost/latency vs. an all-large-model baseline.
Usage: python demo.py [N_REQUESTS] [--serve]"""
import random
import sys

from dashboard import export_html, serve
from gateway import Gateway

# (simple?, paraphrase templates)
TOPICS = [
    ("capital of France", ["What is the capital of France?", "capital of France?", "Tell me the capital of France"]),
    ("refund window", ["What is your refund policy window?", "How long is the refund window?", "refund policy window please"]),
    ("reset password", ["How do I reset my password?", "reset my password steps", "I forgot my password, how to reset it?"]),
    ("pricing tiers", ["What are the pricing tiers?", "List the pricing tiers", "pricing tiers available?"]),
    ("business hours", ["When is support open?", "What are your support hours?", "support hours?"]),
    ("api rate limit", ["What is the API rate limit?", "API rate limit per minute?", "how many API requests per minute"]),
    ("sso setup", ["Where do I find SSO settings?", "where are the SSO settings", "SSO settings location"]),
    ("invoice download", ["Where can I download my invoice?", "download invoice where", "How to download an invoice?"]),
    ("retry design", ["Explain why exponential backoff with jitter beats fixed retries and compare the trade-offs.",
                      "Compare exponential backoff with jitter to fixed retries and explain why one wins.",
                      "why is jittered exponential backoff better than fixed retry? compare trade-offs"]),
    ("sharding", ["Design a sharding strategy for a multi-tenant Postgres and analyze the trade-offs step by step.",
                  "Analyze trade-offs of multi-tenant Postgres sharding, step by step, and design a strategy."]),
    ("debug latency", ["Debug why p99 latency doubled after we enabled the new cache layer and evaluate the root cause.",
                       "Evaluate the root cause: p99 latency doubled after enabling the new cache layer, debug it."]),
    ("code review", ["```def f(x): return x*2``` refactor this and explain the implications.",
                     "Refactor ```def f(x): return x*2``` and explain implications."]),
]
def make_workload(n: int, seed: int = 7) -> list[str]:
    rng = random.Random(seed)
    weights = [1 / (i + 1) for i in range(len(TOPICS))]  # Zipf-ish popularity
    out = []
    for i in range(n):
        if rng.random() < 0.2:
            # long tail: every query unique (distinct order id), so never cacheable
            out.append(f"What is the status of order {100000 + i} and also when does it ship?")
        else:
            _, variants = rng.choices(TOPICS, weights)[0]
            out.append(rng.choice(variants))
    return out


def main():
    n = int(next((a for a in sys.argv[1:] if a.isdigit()), 2000))
    gw = Gateway()
    for q in make_workload(n):
        gw.ask(q)
    s = gw.metrics.stats()
    print(f"requests          {s['requests']}")
    print(f"cache hit rate    {s['hit_rate']:.1%}   outcomes: {s['outcomes']}")
    print(f"spend             ${s['cost']:.4f}  vs baseline ${s['baseline_cost']:.4f}  -> savings {s['savings_pct']:.1%}")
    print(f"cost / 1k reqs    ${s['cost_per_1k']:.4f}  vs ${s['baseline_per_1k']:.4f}")
    L = s["latency"]
    print(f"latency p50/p95   {L['p50']*1000:.0f} ms / {L['p95']*1000:.0f} ms   (hit p50 {L['hit_p50']*1000:.1f} ms, miss p50 {L['miss_p50']*1000:.0f} ms)")
    print("wrote", export_html(gw.metrics, "dashboard.html"))
    if "--serve" in sys.argv:
        serve(gw.metrics)


if __name__ == "__main__":
    main()