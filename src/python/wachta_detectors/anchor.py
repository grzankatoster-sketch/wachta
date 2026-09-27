"""D6: a ship behaving as if it were dragging its anchor across a cable or pipeline.

The pattern comes from the Baltic incidents (Eagle S over Estlink 2 on 2024-12-25, Yi Peng 3 over
C-Lion 1 in November 2024): a vessel crosses the line at a speed far below its transit speed but
above a standstill, and its course wanders instead of holding steady — an anchor on the seabed
steers the ship as much as its rudder does.

Output is a candidate to check. A ship can slow down and wander for a dozen honest reasons: weather,
traffic, a pilot boarding, engine trouble. The detector says "look here", never "this one did it".
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import atan2, cos, degrees, log, radians, sin, sqrt

from wachta_detectors.infrastructure import Line
from wachta_detectors.spatial_index import LineIndex


@dataclass(frozen=True)
class ShipFix:
    mmsi: str
    ts: datetime
    lat: float
    lon: float
    sog: float | None = None          # wezly
    cog: float | None = None          # stopnie
    name: str | None = None


@dataclass(frozen=True)
class AnchorRules:
    buffer_km: float = 2.0            # dokladnosc tras kabli z OSM nie uzasadnia wezszego bufora
    min_sog: float = 1.0              # ponizej tego statek stoi, a nie wlecze
    max_sog: float = 7.0              # powyzej tego kotwica nie siegnelaby dna
    min_duration: timedelta = timedelta(minutes=15)
    min_fixes: int = 5
    min_course_spread_deg: float = 20.0


@dataclass(frozen=True)
class AnchorAlert:
    mmsi: str
    name: str | None
    line_name: str
    started_at: datetime
    ended_at: datetime
    lat: float
    lon: float
    min_distance_km: float
    mean_sog: float
    course_spread_deg: float
    score: float
    evidence: dict = field(hash=False)

    @property
    def duration(self) -> timedelta:
        return self.ended_at - self.started_at


def course_spread_deg(courses: Sequence[float]) -> float:
    """Circular spread of headings. A ship holding its course scores a few degrees, a wandering one tens."""
    usable = [c for c in courses if c is not None]
    if len(usable) < 2:
        return 0.0
    x = sum(cos(radians(c)) for c in usable) / len(usable)
    y = sum(sin(radians(c)) for c in usable) / len(usable)
    r = sqrt(x * x + y * y)
    if r >= 0.999999:
        return 0.0
    if r <= 1e-9:
        return 180.0
    return min(180.0, degrees(sqrt(-2.0 * log(r))))


def _runs_near_lines(fixes: Sequence[ShipFix], index: LineIndex, rules: AnchorRules):
    """Maximal runs of consecutive fixes that are near a line and inside the speed window."""
    current: list[tuple[ShipFix, float, Line]] = []
    for fix in fixes:
        nearest = index.nearest(fix.lat, fix.lon, max_km=rules.buffer_km)
        in_speed = fix.sog is not None and rules.min_sog <= fix.sog <= rules.max_sog
        if nearest and nearest[1] <= rules.buffer_km and in_speed:
            current.append((fix, nearest[1], nearest[0]))
            continue
        if current:
            yield current
            current = []
    if current:
        yield current


def find_anchor_drag(
    fixes: Iterable[ShipFix],
    lines: list[Line] | LineIndex,
    rules: AnchorRules = AnchorRules(),
) -> list[AnchorAlert]:
    """`lines` can be a list or a prebuilt index - pass the index when scanning many ships."""
    ordered = sorted(fixes, key=lambda f: f.ts)
    if not ordered:
        return []
    index = lines if isinstance(lines, LineIndex) else LineIndex(lines)
    if not len(index):
        return []

    alerts = []
    for run in _runs_near_lines(ordered, index, rules):
        if len(run) < rules.min_fixes:
            continue
        first, last = run[0][0], run[-1][0]
        duration = last.ts - first.ts
        if duration < rules.min_duration:
            continue

        spread = course_spread_deg([f.cog for f, _, _ in run])
        if spread < rules.min_course_spread_deg:
            continue

        distances = [km for _, km, _ in run]
        speeds = [f.sog for f, _, _ in run if f.sog is not None]
        closest = min(run, key=lambda item: item[1])
        line = closest[2]
        mean_sog = sum(speeds) / len(speeds)

        # Slower, closer and more erratic all read as "worth a look"; the score only orders the list.
        score = round(min(1.0, 0.4
                          + 0.2 * (1 - min(distances) / rules.buffer_km)
                          + 0.2 * min(1.0, spread / 60.0)
                          + 0.2 * min(1.0, duration / timedelta(hours=1))), 3)

        alerts.append(AnchorAlert(
            mmsi=first.mmsi,
            name=first.name,
            line_name=line.name,
            started_at=first.ts,
            ended_at=last.ts,
            lat=closest[0].lat,
            lon=closest[0].lon,
            min_distance_km=round(min(distances), 3),
            mean_sog=round(mean_sog, 2),
            course_spread_deg=round(spread, 1),
            score=score,
            evidence={
                "line": line.name,
                "line_kind": line.kind,
                "fixes": len(run),
                "duration_minutes": round(duration.total_seconds() / 60, 1),
                "min_distance_km": round(min(distances), 3),
                "max_distance_km": round(max(distances), 3),
                "mean_sog_kn": round(mean_sog, 2),
                "course_spread_deg": round(spread, 1),
                "rules": {"buffer_km": rules.buffer_km, "speed_window_kn": [rules.min_sog, rules.max_sog],
                          "min_duration_minutes": rules.min_duration.total_seconds() / 60,
                          "min_course_spread_deg": rules.min_course_spread_deg},
                "note": "Candidate to check, not a verdict.",
            },
        ))
    return alerts


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing between two points, for tests and for filling in a missing COG."""
    d_lon = radians(lon2 - lon1)
    y = sin(d_lon) * cos(radians(lat2))
    x = cos(radians(lat1)) * sin(radians(lat2)) - sin(radians(lat1)) * cos(radians(lat2)) * cos(d_lon)
    return (degrees(atan2(y, x)) + 360.0) % 360.0
