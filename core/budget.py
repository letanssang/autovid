from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

WARN_RATIO = 0.8


@dataclass
class BudgetTracker:
    """Cumulative cost ledger for one project, persisted as budget_ledger.json."""

    project_root: Path
    cap_usd: float
    spent_usd: float = 0.0

    @property
    def ledger_path(self) -> Path:
        return self.project_root / "budget_ledger.json"

    def load(self) -> None:
        if self.ledger_path.exists():
            data = json.loads(self.ledger_path.read_text())
            self.spent_usd = data.get("spent_usd", 0.0)

    def record(
        self,
        capability: str,
        provider: str,
        cost_usd: float,
        estimated_usd: float | None = None,
        usage: dict | None = None,
    ) -> None:
        entries = []
        if self.ledger_path.exists():
            entries = json.loads(self.ledger_path.read_text()).get("entries", [])
        self.spent_usd += cost_usd
        entry = {
            "ts": datetime.datetime.now(datetime.UTC).isoformat(),
            "capability": capability,
            "provider": provider,
            "cost_usd": cost_usd,
            "estimated_usd": estimated_usd if estimated_usd is not None else cost_usd,
        }
        if usage:
            entry["usage"] = usage
        entries.append(entry)
        self.ledger_path.write_text(json.dumps({"spent_usd": self.spent_usd, "entries": entries}, indent=2))

    def remaining(self) -> float:
        return self.cap_usd - self.spent_usd

    def check(self) -> str:
        """Returns 'ok', 'warn' (>=80% of cap), or 'stop' (cap reached)."""
        ratio = self.spent_usd / self.cap_usd if self.cap_usd else 0.0
        if ratio >= 1.0:
            return "stop"
        if ratio >= WARN_RATIO:
            return "warn"
        return "ok"
