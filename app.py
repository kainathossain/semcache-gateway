"""Live entry point (e.g. Render).  Start command:  python app.py

Serves the dashboard plus a real-time API:
    POST /api/ask    {"query": "...", "namespace": "optional"}  -> answer + cost/latency
    GET  /api/stats  live aggregates (what the dashboard polls)
    GET  /healthz    health check

Environment variables (all optional):
    PORT               port to listen on (Render sets this)
    GATEWAY_API_KEY    if set, /api/* requires header  X-API-Key: <key>
    ANTHROPIC_API_KEY  if set, use real Claude models (requires GATEWAY_API_KEY too)
    SMALL_MODEL        default claude-haiku-5-5
    LARGE_MODEL        default claude-sonnet-5-5
    SMALL_PRICE        "input,output" USD per 1M tokens, default 0.25,1.25
    LARGE_PRICE        "input,output" USD per 1M tokens, default 3,15
    CACHE_THRESHOLD    similarity threshold, default 0.85
    METRICS_DB         SQLite file for the request log, default in-memory
    SEED_DEMO          set to 1 to preload simulated traffic (demo only)
"""
import os
import sys

from dashboard import serve
from gateway import Gateway
from cache import SemanticCache
from llm import LARGE, SMALL, MockLLM, ModelSpec
from metrics import MetricsStore


def _spec(base: ModelSpec, env: str) -> ModelSpec:
    raw = os.environ.get(env)
    if not raw:
        return base
    inp, out = (float(x) for x in raw.split(","))
    return ModelSpec(base.name, inp, out, base.base_latency_s, base.s_per_token)


def build_gateway(api_key: str) -> Gateway:
    small_spec, large_spec = _spec(SMALL, "SMALL_PRICE"), _spec(LARGE, "LARGE_PRICE")
    if os.environ.get("ANTHROPIC_API_KEY"):
        if not api_key:
            sys.exit("Refusing to start: ANTHROPIC_API_KEY is set but GATEWAY_API_KEY is not. "
                     "Without it anyone with the URL could spend your money.")
        from llm import AnthropicLLM
        small = AnthropicLLM(small_spec, os.environ.get("SMALL_MODEL", "claude-haiku-5-5"))
        large = AnthropicLLM(large_spec, os.environ.get("LARGE_MODEL", "claude-sonnet-5-5"))
        print("Backend: real Anthropic models", flush=True)
    else:
        small, large = MockLLM(small_spec), MockLLM(large_spec)
        print("Backend: MOCK models (set ANTHROPIC_API_KEY to use real ones)", flush=True)
    return Gateway(
        cache=SemanticCache(threshold=float(os.environ.get("CACHE_THRESHOLD", "0.85"))),
        small=small, large=large,
        metrics=MetricsStore(os.environ.get("METRICS_DB", ":memory:")),
    )


def main():
    api_key = os.environ.get("GATEWAY_API_KEY", "")
    gw = build_gateway(api_key)
    if os.environ.get("SEED_DEMO") == "1":
        from demo import make_workload
        for q in make_workload(1500):
            gw.ask(q)
    port = int(os.environ.get("PORT", "8765"))
    print("API key required" if api_key else "WARNING: no GATEWAY_API_KEY set, API is open", flush=True)
    serve(gw.metrics, port=port, host="0.0.0.0", gateway=gw, api_key=api_key)


if __name__ == "__main__":
    main()