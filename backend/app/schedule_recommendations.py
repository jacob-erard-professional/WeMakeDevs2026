"""Build a small set of optimal, non-overlapping schedules from ranked talks."""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from typing import Any


def _talk_time(value: Any) -> datetime:
    """Parse Elasticsearch's ISO timestamps, including its common ``Z`` suffix."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Talk times must be timezone-aware")
    return parsed


def best_schedules(talks: list[dict[str, Any]], count: int = 3) -> list[dict[str, Any]]:
    """Return up to ``count`` highest-relevance, conflict-free schedules.

    This is k-best weighted interval scheduling.  Elasticsearch ranks individual talks;
    dynamic programming finds combinations whose total relevance is maximal without
    overlapping sessions.  Malformed talks are ignored rather than making a profile
    recommendation unavailable.
    """
    if count < 1:
        return []

    intervals: list[tuple[datetime, datetime, float, int, dict[str, Any]]] = []
    for position, talk in enumerate(talks):
        try:
            start, end = _talk_time(talk["start_time"]), _talk_time(talk["end_time"])
            relevance = max(float(talk.get("relevance", 0)), 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        if end > start:
            intervals.append((start, end, relevance, position, talk))

    intervals.sort(key=lambda item: (item[1], item[0], str(item[4].get("talk_id", ""))))
    ends = [interval[1] for interval in intervals]
    predecessors = [
        bisect_right(ends, interval[0], hi=index) - 1 for index, interval in enumerate(intervals)
    ]

    # A state is (total relevance, indices into ``intervals``).  Keeping only the top
    # ``count`` states per prefix makes this O(n * count), while still yielding the
    # global k best schedules.
    states: list[list[tuple[float, tuple[int, ...]]]] = [[(0.0, ())]]
    for index, interval in enumerate(intervals):
        candidates = states[-1] + [
            (score + interval[2], chosen + (index,))
            for score, chosen in states[predecessors[index] + 1]
        ]
        unique = {chosen: score for score, chosen in candidates}
        states.append(
            sorted(
                ((score, chosen) for chosen, score in unique.items()),
                key=lambda state: (-state[0], -len(state[1]), state[1]),
            )[:count]
        )

    schedules: list[dict[str, Any]] = []
    for score, chosen in states[-1]:
        if not chosen:
            continue
        selected = sorted((intervals[index] for index in chosen), key=lambda item: item[0])
        schedules.append(
            {
                "relevance": round(score, 6),
                "talks": [dict(interval[4]) for interval in selected],
            }
        )
    return schedules
