"""Anthropic client wrapper: structured output, effort control, token and cost accounting.

Models in this project (prices per 1M tokens, input/output, from the Claude API docs, 2026-10):
  claude-haiku-5-5   $0.10 / $0.50     routing, answer prose
  claude-sonnet-5-5  $2.00 / $10.00    SQL generation, result review
  claude-opus-5-5    $4.00 / $20.00    available, not used by default
Sonnet/Opus 5.5 reject temperature and forced tool_choice, so we use structured outputs and effort.
"""
import time
from dataclasses import dataclass
from typing import TypeVar

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

PRICES_PER_MILLION = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
T = TypeVar("T", bound=BaseModel)


class LLMRefusal(Exception):
    """The model declined (stop_reason == 'refusal')."""


@dataclass
class CallUsage:
    model: str
    input_tokens: int
    output_tokens: int
    seconds: float

    @property
    def cost_usd(self) -> float:
        p_in, p_out = PRICES_PER_MILLION.get(self.model, (0.0, 0.0))
        return (self.input_tokens * p_in + self.output_tokens * p_out) / 1_000_000


class AnthropicLLM:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(max_retries=3)  # SDK retries 429/5xx with backoff

    async def parse(self, *, model: str, system: str, user: str, schema: type[T], effort: str = "medium",
                    max_tokens: int = 8000) -> tuple[T, CallUsage]:
        started = time.perf_counter()
        response = await self.client.messages.parse(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema, output_config={"effort": effort},
        )
        if response.stop_reason == "refusal":
            raise LLMRefusal(f"{model} refused")
        if response.parsed_output is None:
            raise ValueError(f"{model} returned no parsable output (stop_reason={response.stop_reason})")
        usage = CallUsage(model, response.usage.input_tokens, response.usage.output_tokens,
                          time.perf_counter() - started)
        return response.parsed_output, usage


class Meter:
    """Per-question totals: tokens, dollars, calls, wall time by call."""

    def __init__(self):
        self.calls: list[CallUsage] = []

    def add(self, usage: CallUsage):
        self.calls.append(usage)

    @property
    def cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    def summary(self) -> dict:
        return {"llm_calls": len(self.calls), "input_tokens": sum(c.input_tokens for c in self.calls),
                "output_tokens": sum(c.output_tokens for c in self.calls), "cost_usd": round(self.cost_usd, 6)}
