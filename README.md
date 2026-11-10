# semcache-gateway

A small, dependency-free gateway that sits in front of an LLM and cuts cost and latency:

1. **Semantic cache** - returns a stored answer when a new query's embedding is close to a previous one.
2. **Cost-aware router** - sends simple questions to a small model and hard ones to a large model, escalating when the small model is unsure.
3. **Metrics + dashboard** - logs cost and latency per request (SQLite) and shows savings against an "always use the large model" baseline.

## Layout

```
semcache-gateway/
├── semcache/
│   ├── __init__.py
│   ├── embeddings.py   # hashing embedder (swap for a real embedding model)
│   ├── cache.py        # similarity lookup, TTL, LRU, namespaces, number/negation guards
│   ├── router.py       # complexity score -> small/large tier
│   ├── llm.py          # model specs, pricing, MockLLM, AnthropicLLM adapter
│   ├── metrics.py      # SQLite request log and aggregates
│   ├── gateway.py      # cache -> route -> escalate -> store, logging everything
│   └── dashboard.py    # live server and static HTML export
├── examples/
│   └── demo.py         # simulated traffic, writes dashboard.html
├── tests/
│   └── test_gateway.py
├── README.md
└── .gitignore
```

Requires Python 3.9+ and nothing else (standard library only).

## Quick start

```bash
# run the tests
python -m unittest discover tests

# simulate 2000 requests and write dashboard.html
python -m examples.demo 2000

# same, then serve a live dashboard at http://127.0.0.1:8765
python -m examples.demo 2000 --serve
```

## Use it in code

```python
from semcache import Gateway

gw = Gateway()
r = gw.ask("What is the capital of France?")
print(r.outcome, r.cost, r.latency_s)   # small / large / escalated / hit
r = gw.ask("capital of France?")        # paraphrase -> served from cache
print(r.outcome)                        # hit
```

## Tuning knobs

| Setting | Where | Effect |
|---|---|---|
| `threshold` (default 0.85) | `SemanticCache` | Higher = fewer wrong hits, lower hit rate |
| `default_ttl`, `max_entries` | `SemanticCache` | Freshness and memory bound |
| `namespace` | `Gateway.ask` | Isolate tenants or corpus versions; call `cache.invalidate(ns)` when documents change |
| `threshold` (default 0.4) | `Router` | Higher = more traffic to the small model |
| `escalate_below` (default 0.6) | `Gateway` | Confidence under which a small-model answer is redone by the large model |

## Before production

- Replace `HashingEmbedder` with a real embedding model (same `embed(text) -> list[float]` interface, unit-normalised).
- Replace the brute-force scan in `SemanticCache.lookup` with an ANN index (FAISS, HNSW, pgvector) beyond a few thousand entries.
- Replace the heuristic router with a classifier trained on your labelled traffic.
- Replace `MockLLM` with `AnthropicLLM` (or your own backend) and set real prices in `llm.py`.
- Tune the similarity threshold on your own queries; the demo numbers come from synthetic traffic and are optimistic.