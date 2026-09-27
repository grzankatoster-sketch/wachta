"""D1: aircraft that stop transmitting mid-air inside good receiver coverage. Output = 'to check', never a verdict."""
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import h3

from wachta_detectors.airports import nearest_airport_km
from wachta_detectors.coverage import COVERAGE_RESOLUTION, is_well_covered


@dataclass(frozen=True)
class LastSeen:
    hex: str
    flight: str | None
    type_code: str | None
    is_military: bool
    lat: float
    lon: float
    alt_ft: int | None
    gs_kt: float | None
    ts: datetime
    n_points: int
    last_message_at: datetime


@dataclass(frozen=True)
class DarkCandidate:
    hex: str
    lat: float
    lon: float
    last_seen: datetime
    score: float
    evidence: dict = field(hash=False)


@dataclass(frozen=True)
class DarkRules:
    min_gap: timedelta = timedelta(minutes=5)
    max_gap: timedelta = timedelta(minutes=30)
    min_alt_ft: int = 3000
    min_gs_kt: float = 100
    airport_radius_km: float = 40.0
    min_points: int = 10
    min_cell_reports: int = 200


def snapshot_inputs(
    s: LastSeen,
    coverage: Mapping[str, int],
    alive_cells: set[str],
    airports: list[tuple[float, float]],
    now: datetime,
    rules: DarkRules = DarkRules(),
) -> dict:
    """Everything the rules look at, frozen so a labelled case can be replayed offline."""
    cell = h3.latlng_to_cell(s.lat, s.lon, COVERAGE_RESOLUTION)
    disk = h3.grid_disk(cell, 1)
    return {
        "last_seen": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(s).items()},
        "now": now.isoformat(),
        "coverage": {c: coverage.get(c, 0) for c in disk},
        "alive": sorted(alive_cells & set(disk)),
        "airports": [[round(a_lat, 4), round(a_lon, 4)] for a_lat, a_lon in airports
                     if nearest_airport_km([(a_lat, a_lon)], s.lat, s.lon) <= rules.airport_radius_km * 3],
    }


def silent_aircraft(last_seen: Iterable[LastSeen], now: datetime, rules: DarkRules = DarkRules()) -> list[LastSeen]:
    """Everything that went quiet for min_gap..max_gap — the population to sample and label."""
    return [s for s in last_seen if rules.min_gap <= now - s.last_message_at <= rules.max_gap]


def find_dark_candidates(
    last_seen: Iterable[LastSeen],
    coverage: Mapping[str, int],
    alive_cells: set[str],
    airports: list[tuple[float, float]],
    now: datetime,
    rules: DarkRules = DarkRules(),
) -> list[DarkCandidate]:
    candidates = []
    for s in last_seen:
        # Silence of messages, not absence of position: a jammed aircraft keeps transmitting without a position.
        gap = now - s.last_message_at
        if not rules.min_gap <= gap <= rules.max_gap:
            continue
        if s.alt_ft is None or s.alt_ft < rules.min_alt_ft or s.gs_kt is None or s.gs_kt < rules.min_gs_kt:
            continue
        if s.n_points < rules.min_points:
            continue
        airport_km = nearest_airport_km(airports, s.lat, s.lon)
        if airport_km <= rules.airport_radius_km:
            continue
        if not is_well_covered(coverage, s.lat, s.lon, rules.min_cell_reports):
            continue
        cell = h3.latlng_to_cell(s.lat, s.lon, COVERAGE_RESOLUTION)
        if not alive_cells & set(h3.grid_disk(cell, 1)):
            continue

        score = 0.5 + 0.3 * s.is_military + 0.2 * min(1.0, s.n_points / 100)
        evidence = {
            **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(s).items()},
            "gap_minutes": round(gap.total_seconds() / 60, 1),
            "position_gap_minutes": round((now - s.ts).total_seconds() / 60, 1),
            "nearest_airport_km": round(airport_km, 1),
            "cell": cell,
            "cell_reports": coverage.get(cell, 0),
            "inputs": snapshot_inputs(s, coverage, alive_cells, airports, now, rules),
            "note": "Candidate to check, not a verdict.",
        }
        candidates.append(DarkCandidate(s.hex, s.lat, s.lon, s.ts, round(score, 3), evidence))
    return candidates
