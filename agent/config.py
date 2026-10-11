"""Agent configuration: models per role, retry limit, cost cap. Everything overridable by env."""
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


@dataclass(frozen=True)
class AgentConfig:
    # Strong model where accuracy lives (SQL), cheap fast model for routing and prose.
    sql_model: str = field(default_factory=lambda: _env("SQL_MODEL", "claude-sonnet-5-5"))
    router_model: str = field(default_factory=lambda: _env("ROUTER_MODEL", "claude-haiku-5-5"))
    answer_model: str = field(default_factory=lambda: _env("ANSWER_MODEL", "claude-haiku-5-5"))
    judge_model: str = field(default_factory=lambda: _env("JUDGE_MODEL", "claude-sonnet-5-5"))
    sql_effort: str = field(default_factory=lambda: _env("SQL_EFFORT", "medium"))
    router_effort: str = "low"
    answer_effort: str = "low"
    judge_effort: str = "low"
    max_retries: int = 3                 # repair attempts after the first try
    semantic_check: bool = True          # LLM reviews a successful result against the question
    max_cost_usd_per_question: float = 0.50
    data_as_of: str = "2026-10-01"       # the dataset is a fixed snapshot; relative dates resolve from here
    tables_k: int = 4
    structure_k: int = 2
    examples_k: int = 3
    prompt_version: str = "p1"

    def now_note(self) -> str:
        """Tell the model what 'now' is. The data is a frozen snapshot, so 'now' is the snapshot instant,
        and 'today' is its Eastern-time calendar date (the snapshot is 20:00 the evening before in ET)."""
        instant = datetime.fromisoformat(self.data_as_of).replace(tzinfo=timezone.utc)
        local = instant.astimezone(ZoneInfo("America/New_York"))
        return (f"The current time is {local:%Y-%m-%d %H:%M %Z} ({instant:%Y-%m-%d %H:%M} UTC), the moment the data "
                f"snapshot was taken; there is no data after it. Today in Eastern time is {local:%Y-%m-%d}.")
