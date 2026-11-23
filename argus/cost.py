"""Token usage and approximate cost for a run.

Prices are USD per million tokens, from Anthropic's pricing page in November 2026.
Check https://platform.claude.com/docs/en/about-claude/pricing if they look stale.
"""
from __future__ import annotations

PRICES = {
    # model: (input, output, cache write 5 min, cache read)
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
}


class Usage:
    def __init__(self, model: str):
        self.model = model
        self.input = self.output = self.cache_write = self.cache_read = 0
        self.calls = 0

    def add(self, resp) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return
        self.calls += 1
        self.input += getattr(u, "input_tokens", 0) or 0
        self.output += getattr(u, "output_tokens", 0) or 0
        self.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0
        self.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0

    def cost(self) -> float | None:
        p = PRICES.get(self.model)
        if not p:
            return None
        return (self.input * p[0] + self.output * p[1] + self.cache_write * p[2] + self.cache_read * p[3]) / 1e6

    def as_dict(self) -> dict:
        c = self.cost()
        return {"model": self.model, "api_calls": self.calls, "input_tokens": self.input,
                "output_tokens": self.output, "cache_write_tokens": self.cache_write,
                "cache_read_tokens": self.cache_read, "approx_cost_usd": round(c, 3) if c is not None else None}
