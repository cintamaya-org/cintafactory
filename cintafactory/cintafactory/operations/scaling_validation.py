from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class LoadSummary:
    scenario: str
    total_requests: int
    error_count: int
    p95_ms: float
    p99_ms: float

    @property
    def error_rate(self) -> float:
        if self.total_requests <= 0:
            return 0.0
        return float(self.error_count) / float(self.total_requests)


def percentile_ms(samples: Iterable[float], percentile: float) -> float:
    values = sorted(float(v) for v in samples)
    if not values:
        return 0.0
    if percentile <= 0:
        return values[0]
    if percentile >= 100:
        return values[-1]
    rank = (percentile / 100.0) * (len(values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    fraction = rank - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def evaluate_slo(summary: LoadSummary) -> dict[str, object]:
    failures: list[str] = []
    suggestions: list[str] = []

    if summary.scenario == "web":
        if summary.p95_ms >= 800.0:
            failures.append("web p95 >= 800ms")
            suggestions.append("Increase `web` replicas and review Traefik buffering/timeouts.")
        if summary.error_rate >= 0.005:
            failures.append("web 5xx rate >= 0.5%")
            suggestions.append("Check app errors and increase web/worker capacity before raising load.")
    elif summary.scenario == "proxy":
        if summary.p95_ms >= 1200.0:
            failures.append("proxy p95 >= 1200ms")
            suggestions.append("Increase proxy limits or isolate proxy-heavy traffic to dedicated web replicas.")
        if summary.error_rate >= 0.005:
            failures.append("proxy 5xx rate >= 0.5%")
            suggestions.append("Review draw.io/LikeC4 upstream health and Traefik timeout settings.")
    elif summary.scenario == "drawio_export":
        if summary.p95_ms >= 10000.0:
            failures.append("drawio export p95 >= 10s")
            suggestions.append("Scale `drawio-export` replicas and verify queue-worker ratio.")
    elif summary.scenario == "likec4_export":
        if summary.p95_ms >= 45000.0:
            failures.append("likec4 export p95 >= 45s")
            suggestions.append("Scale `likec4-exporter` replicas and increase worker pool.")

    if summary.error_rate >= 0.02:
        suggestions.append("Critical error rate exceeded 2%; pause scaling and inspect logs first.")

    return {
        "scenario": summary.scenario,
        "passed": len(failures) == 0,
        "failures": failures,
        "suggestions": suggestions,
        "metrics": {
            "total_requests": summary.total_requests,
            "error_count": summary.error_count,
            "error_rate": round(summary.error_rate, 6),
            "p95_ms": round(summary.p95_ms, 3),
            "p99_ms": round(summary.p99_ms, 3),
        },
    }
