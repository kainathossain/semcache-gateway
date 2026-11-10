"""Cost-aware router: cheap heuristic complexity score -> small or large model.
Replace `complexity_score` with a trained classifier once you have labelled traffic;
the Gateway also escalates when the small model reports low confidence."""
import re
from dataclasses import dataclass

from embeddings import tokenize

HARD_PHRASES = [
    "explain why", "compare", "trade-off", "tradeoff", "design", "prove", "derive", "analyze",
    "analyse", "step by step", "optimize", "architecture", "debug", "refactor", "pros and cons",
    "implications", "evaluate", "why does", "justify", "root cause", "strategy",
]
EASY_PREFIXES = ("what is", "who is", "when", "where", "define", "what's", "how many", "list")


@dataclass
class Decision:
    tier: str  # "small" | "large"
    score: float
    reasons: list[str]


def complexity_score(query: str) -> tuple[float, list[str]]:
    q = query.lower().strip()
    reasons: list[str] = []
    score = min(len(tokenize(q)) / 80, 0.35)
    if score > 0.1:
        reasons.append("long")
    if "```" in query or re.search(r"\b(def|class|select|function)\b", q) or "{" in query:
        score += 0.25
        reasons.append("code")
    hits = [p for p in HARD_PHRASES if p in q]
    if hits:
        score += min(0.2 * len(hits), 0.5)
        reasons.append("reasoning:" + ",".join(hits[:2]))
    if q.count("?") > 1 or len(re.findall(r"\b(and then|also|additionally)\b", q)):
        score += 0.1
        reasons.append("multi-part")
    if q.startswith(EASY_PREFIXES) and not hits:
        score -= 0.15
        reasons.append("lookup-style")
    return max(0.0, min(score, 1.0)), reasons


class Router:
    def __init__(self, threshold: float = 0.4):
        self.threshold = threshold

    def route(self, query: str) -> Decision:
        score, reasons = complexity_score(query)
        return Decision("large" if score >= self.threshold else "small", score, reasons)