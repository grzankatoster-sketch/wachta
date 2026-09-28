"""D8: places where the number of reported events suddenly jumps above their own normal.

A raw count says nothing: Kyiv always has more reports than Tallinn, and a busy news day lifts the
whole world at once. What matters is a place breaking its own rhythm. So each grid cell is compared
against its own baseline, and the comparison is a Poisson tail probability, not a ratio - with three
events expected, seeing six is unremarkable; with 0.2 expected, seeing six is not.

The output says "look here". Reported events are articles, not facts on the ground: a spike can mean
fighting, but it can equally mean one press conference that many outlets picked up.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from math import exp, lgamma, log

from wachta_detectors.events import Event
from wachta_detectors.geo import cell_of as _cell

DEFAULT_CELL_DEG = 0.5


@dataclass(frozen=True)
class Spike:
    lat: float
    lon: float
    place: str | None
    recent: int
    expected: float
    p_value: float
    kinds: tuple[str, ...]
    examples: tuple[str, ...]

    @property
    def times_over(self) -> float:
        """How many times above the baseline - for reading, not for thresholding."""
        return round(self.recent / self.expected, 1) if self.expected > 0 else float("inf")


def poisson_tail(k: int, lam: float) -> float:
    """P(X >= k) for a Poisson with mean lam. Computed in logs so large k does not overflow."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    # Sum the head P(X <= k-1) and subtract; k stays small here (counts of events per cell).
    head = 0.0
    for i in range(k):
        head += exp(-lam + i * log(lam) - lgamma(i + 1))
    return max(0.0, min(1.0, 1.0 - head))


def detect_spikes(
    events: Iterable[Event],
    now: datetime,
    window: timedelta = timedelta(hours=6),
    baseline: timedelta = timedelta(hours=42),
    cell_deg: float = DEFAULT_CELL_DEG,
    min_recent: int = 3,
    max_p_value: float = 0.01,
    conflict_only: bool = True,
) -> list[Spike]:
    """Cells whose recent count is improbable given their own baseline rate.

    Time comes from the event's DATEADDED stamp (seconds), not from its day: a six-hour window on a
    date column would put every one of today's events at midnight and therefore outside the window.
    Rows without a stamp fall back to midday of their day, so they land in the right day at least.
    """
    window_start = now - window
    baseline_start = window_start - baseline

    recent: dict[tuple[int, int], list[Event]] = {}
    before: dict[tuple[int, int], int] = {}
    for e in events:
        if conflict_only and not e.is_conflict:
            continue
        stamp = e.added or datetime.combine(e.day, time(12, 0), tzinfo=now.tzinfo)
        key = _cell(e.lat, e.lon, cell_deg)
        # Okno ma gorna granice. Bez niej zdarzenie ze znacznikiem z przyszlosci - zegar zrodla,
        # blad parsowania albo zastepcze poludnie dla dzisiejszej daty - wpada do biezacego okna i
        # potrafi samo wywolac alarm. Sprawdzone: osiem takich zdarzen wystarczylo.
        if stamp > now:
            continue
        if stamp >= window_start:
            recent.setdefault(key, []).append(e)
        elif stamp >= baseline_start:
            before[key] = before.get(key, 0) + 1

    hours_ratio = window.total_seconds() / baseline.total_seconds()
    spikes = []
    for key, group in recent.items():
        count = len(group)
        if count < min_recent:
            continue
        # Expected count in the window if the place kept its baseline rate. The floor keeps a cell
        # with no history from scoring infinite significance on three reports.
        expected = max(0.5, before.get(key, 0) * hours_ratio)
        p = poisson_tail(count, expected)
        if p > max_p_value:
            continue
        busiest = max(group, key=lambda e: e.mentions)
        spikes.append(Spike(
            lat=round(sum(e.lat for e in group) / count, 3),
            lon=round(sum(e.lon for e in group) / count, 3),
            place=busiest.place,
            recent=count,
            expected=round(expected, 2),
            p_value=p,
            kinds=tuple(sorted({e.kind for e in group})),
            examples=tuple(e.url for e in sorted(group, key=lambda e: -e.mentions)[:3] if e.url),
        ))
    return sorted(spikes, key=lambda s: s.p_value)
