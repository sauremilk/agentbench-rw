"""Token counter instrument — provider-agnostic token accounting."""

from __future__ import annotations

from dataclasses import dataclass, field

# Default pricing per 1M tokens (USD) — configurable
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "local": {"input": 0.0, "output": 0.0},
}


@dataclass
class TokenRecord:
    """One token usage record."""

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "unknown"

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TokenCounter:
    """Accumulates token usage across turns and computes cost.

    Usage:
        counter = TokenCounter(model="claude-sonnet-4")
        counter.add(input_tokens=1200, output_tokens=350)
        counter.add(input_tokens=800, output_tokens=200)
        print(counter.total_tokens)  # 2550
        print(counter.cost_usd())    # ~$0.009
    """

    model: str = "unknown"
    pricing: dict[str, dict[str, float]] = field(default_factory=lambda: DEFAULT_PRICING.copy())
    _records: list[TokenRecord] = field(default_factory=list, repr=False)

    def add(self, input_tokens: int = 0, output_tokens: int = 0, model: str | None = None) -> None:
        """Record a token usage event."""
        self._records.append(
            TokenRecord(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model or self.model,
            )
        )

    @property
    def total_input(self) -> int:
        return sum(r.input_tokens for r in self._records)

    @property
    def total_output(self) -> int:
        return sum(r.output_tokens for r in self._records)

    @property
    def total_tokens(self) -> int:
        return self.total_input + self.total_output

    @property
    def turn_count(self) -> int:
        return len(self._records)

    def cost_usd(self, model_override: str | None = None) -> float:
        """Compute total cost in USD based on pricing table."""
        total = 0.0
        for record in self._records:
            model = model_override or record.model
            prices = self.pricing.get(model, {"input": 0.0, "output": 0.0})
            total += (record.input_tokens / 1_000_000) * prices["input"]
            total += (record.output_tokens / 1_000_000) * prices["output"]
        return total

    def per_turn_stats(self) -> dict[str, float]:
        """Return per-turn token statistics."""
        if not self._records:
            return {"median": 0, "p95": 0, "mean": 0}
        totals = sorted(r.total for r in self._records)
        n = len(totals)
        return {
            "median": totals[n // 2],
            "p95": totals[min(int(0.95 * n), n - 1)],
            "mean": sum(totals) / n,
        }

    def reset(self) -> None:
        self._records.clear()
