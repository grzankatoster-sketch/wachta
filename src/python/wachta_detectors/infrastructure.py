"""Submarine cables and pipelines, and how far a ship is from them (input for D6).

Distances use a local equirectangular projection: at Baltic latitudes and the ranges that matter
(a few kilometres around a cable) the error is well under a percent, and it is far cheaper than a
proper geodesic for every AIS position.
"""
import json
from dataclasses import dataclass
from math import cos, radians, sqrt
from pathlib import Path

from .geo import EARTH_RADIUS_KM


@dataclass(frozen=True)
class Line:
    name: str
    kind: str  # power | telecom | pipeline
    coords: tuple[tuple[float, float], ...]  # (lat, lon)
    operator: str | None = None


def load_lines(path: Path) -> list[Line]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lines = []
    for f in data.get("features", []):
        geometry, props = f.get("geometry") or {}, f.get("properties") or {}
        if geometry.get("type") != "LineString":
            continue
        coords = tuple((lat, lon) for lon, lat in geometry.get("coordinates", []))
        if len(coords) < 2:
            continue
        lines.append(Line(props.get("name", "?"), props.get("kind", "?"), coords, props.get("operator")))
    return lines


def _to_local_km(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    """Metres-ish plane around latitude lat0: x east, y north, in kilometres."""
    return (radians(lon) * cos(radians(lat0)) * EARTH_RADIUS_KM, radians(lat) * EARTH_RADIUS_KM)


def _point_segment_km(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))  # clamp: beyond the ends the nearest point is the endpoint
    return sqrt((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2)


def distance_to_line_km(lat: float, lon: float, line: Line) -> float:
    px, py = _to_local_km(lat, lon, lat)
    projected = [_to_local_km(plat, plon, lat) for plat, plon in line.coords]
    return min(
        _point_segment_km(px, py, ax, ay, bx, by)
        for (ax, ay), (bx, by) in zip(projected, projected[1:])
    )


def nearest_line(lines: list[Line], lat: float, lon: float) -> tuple[Line, float] | None:
    if not lines:
        return None
    return min(((line, distance_to_line_km(lat, lon, line)) for line in lines), key=lambda pair: pair[1])


def lines_within_km(lines: list[Line], lat: float, lon: float, radius_km: float) -> list[tuple[Line, float]]:
    found = ((line, distance_to_line_km(lat, lon, line)) for line in lines)
    return sorted(((line, km) for line, km in found if km <= radius_km), key=lambda pair: pair[1])
