"""Lightweight in-process metrics registry for observability (Phase 14).

A dependency-free Prometheus-style metrics collector. Counters and histograms are
held in memory and rendered in the Prometheus text exposition format at
``/metrics``. This avoids adding a heavy client library while still giving
operators something a Prometheus server can scrape.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# Default latency buckets in seconds.
_DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


@dataclass
class _Histogram:
    buckets: tuple[float, ...]
    counts: list[int] = field(default_factory=list)
    sum: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if not self.counts:
            self.counts = [0 for _ in self.buckets]

    def observe(self, value: float) -> None:
        self.sum += value
        self.count += 1
        for i, upper in enumerate(self.buckets):
            if value <= upper:
                self.counts[i] += 1


class MetricsRegistry:
    """Thread-safe registry of counters and latency histograms."""

    def __init__(self, buckets: tuple[float, ...] = _DEFAULT_BUCKETS) -> None:
        self._lock = threading.Lock()
        self._buckets = buckets
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], _Histogram] = {}

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        label_items = tuple(sorted((labels or {}).items()))
        return (name, label_items)

    def inc_counter(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            hist = self._histograms.get(key)
            if hist is None:
                hist = _Histogram(buckets=self._buckets)
                self._histograms[key] = hist
            hist.observe(value)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()

    @staticmethod
    def _format_labels(label_items: tuple[tuple[str, str], ...]) -> str:
        if not label_items:
            return ""
        inner = ",".join(f'{k}="{v}"' for k, v in label_items)
        return "{" + inner + "}"

    def render(self) -> str:
        """Render all metrics in Prometheus text exposition format."""
        lines: list[str] = []
        with self._lock:
            counter_names = {name for name, _ in self._counters}
            for name in sorted(counter_names):
                lines.append(f"# TYPE {name} counter")
                for (cname, label_items), value in sorted(self._counters.items()):
                    if cname != name:
                        continue
                    lines.append(f"{name}{self._format_labels(label_items)} {value}")

            hist_names = {name for name, _ in self._histograms}
            for name in sorted(hist_names):
                lines.append(f"# TYPE {name} histogram")
                for (hname, label_items), hist in sorted(self._histograms.items()):
                    if hname != name:
                        continue
                    cumulative = 0
                    base = self._format_labels(label_items)
                    for upper, bucket_count in zip(hist.buckets, hist.counts, strict=False):
                        cumulative += bucket_count
                        le_labels = dict(label_items)
                        le_labels["le"] = str(upper)
                        le_fmt = self._format_labels(tuple(sorted(le_labels.items())))
                        lines.append(f"{name}_bucket{le_fmt} {cumulative}")
                    inf_labels = dict(label_items)
                    inf_labels["le"] = "+Inf"
                    inf_fmt = self._format_labels(tuple(sorted(inf_labels.items())))
                    lines.append(f"{name}_bucket{inf_fmt} {hist.count}")
                    lines.append(f"{name}_sum{base} {hist.sum}")
                    lines.append(f"{name}_count{base} {hist.count}")

        return "\n".join(lines) + "\n"


# Module-level singleton shared across the app.
metrics = MetricsRegistry()
