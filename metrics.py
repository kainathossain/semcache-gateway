"""Per-request cost/latency log (SQLite) and the aggregates the dashboard needs."""
import sqlite3
import threading
import time
from typing import Any, Optional


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


class MetricsStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, namespace TEXT, query TEXT,
            outcome TEXT,            -- hit | small | large | escalated
            model TEXT, similarity REAL, complexity REAL,
            in_tokens INTEGER, out_tokens INTEGER,
            cost REAL, baseline_cost REAL, latency_s REAL)""")
        self.db.commit()

    def record(self, **r: Any) -> None:
        r.setdefault("ts", time.time())
        cols = ",".join(r)
        with self.lock:
            self.db.execute(f"INSERT INTO requests ({cols}) VALUES ({','.join('?' * len(r))})", list(r.values()))
            self.db.commit()

    def _rows(self, since: Optional[float] = None) -> list[dict]:
        q, args = "SELECT * FROM requests", []
        if since:
            q, args = q + " WHERE ts >= ?", [since]
        with self.lock:
            cur = self.db.execute(q + " ORDER BY id", args)
            names = [c[0] for c in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]

    def stats(self, buckets: int = 20, recent: int = 15, since: Optional[float] = None) -> dict:
        rows = self._rows(since)
        n = len(rows)
        if not n:
            return {"requests": 0}
        cost = sum(r["cost"] for r in rows)
        base = sum(r["baseline_cost"] for r in rows)
        hits = [r for r in rows if r["outcome"] == "hit"]
        misses = [r for r in rows if r["outcome"] != "hit"]
        outcomes: dict[str, int] = {}
        for r in rows:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        size = max(1, -(-n // buckets))
        series = []
        for i in range(0, n, size):
            chunk = rows[i:i + size]
            series.append({"from_id": chunk[0]["id"], "cost": sum(r["cost"] for r in chunk),
                           "baseline": sum(r["baseline_cost"] for r in chunk),
                           "hit_rate": sum(r["outcome"] == "hit" for r in chunk) / len(chunk)})
        lat = [r["latency_s"] for r in rows]
        return {
            "requests": n, "cost": cost, "baseline_cost": base, "savings": base - cost,
            "savings_pct": (base - cost) / base if base else 0.0,
            "hit_rate": len(hits) / n, "outcomes": outcomes,
            "cost_per_1k": cost / n * 1000, "baseline_per_1k": base / n * 1000,
            "latency": {"p50": _pct(lat, .5), "p95": _pct(lat, .95), "p99": _pct(lat, .99),
                        "hit_p50": _pct([r["latency_s"] for r in hits], .5),
                        "miss_p50": _pct([r["latency_s"] for r in misses], .5)},
            "series": series,
            "recent": [{k: r[k] for k in ("id", "query", "outcome", "model", "similarity", "cost", "latency_s")}
                       for r in rows[-recent:][::-1]],
        }