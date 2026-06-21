"""Macro data helpers with safe offline defaults."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class MacroSnapshot:
    as_of: date
    usd_npr: float | None = None
    policy_rate: float | None = None
    inflation: float | None = None


class MacroDataService:
    """Stores macro observations and provides a simple regime tag."""

    def __init__(self) -> None:
        self._snapshots: list[MacroSnapshot] = []

    def add_snapshot(self, snapshot: MacroSnapshot) -> None:
        self._snapshots.append(snapshot)

    def latest(self) -> MacroSnapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    def detect_regime(self, snapshot: MacroSnapshot | None = None) -> str:
        snap = snapshot or self.latest()
        if snap is None:
            return "neutral"
        if (snap.inflation or 0.0) > 7.0 or (snap.policy_rate or 0.0) > 10.0:
            return "tight"
        if (snap.usd_npr or 0.0) > 140.0:
            return "stress"
        return "neutral"
