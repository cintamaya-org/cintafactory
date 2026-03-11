from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Iterable


_lock = Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)


def _normalize_labels(labels: dict[str, object] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    normalized = []
    for key, value in labels.items():
        normalized.append((str(key), str(value)))
    normalized.sort(key=lambda item: item[0])
    return tuple(normalized)


def inc_counter(name: str, value: float = 1.0, *, labels: dict[str, object] | None = None) -> None:
    key = (name, _normalize_labels(labels))
    with _lock:
        _counters[key] += float(value)


def iter_counters() -> Iterable[tuple[str, dict[str, str], float]]:
    with _lock:
        snapshot = list(_counters.items())
    for (name, labels_tuple), value in snapshot:
        labels = {k: v for k, v in labels_tuple}
        yield name, labels, value
