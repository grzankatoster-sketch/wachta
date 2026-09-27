"""Grid index over cable and pipeline segments.

Without it, one AIS position costs a distance computation against every segment of every line. On a
day of Danish traffic that is half a million positions times thousands of segments — minutes of work
per run, and far worse once the ingestion runs continuously. The index buckets segments into
degree-sized cells, so a position only looks at what lies around it.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, cos, floor, radians

from wachta_detectors.infrastructure import Line, _point_segment_km, _to_local_km

DEFAULT_CELL_DEG = 0.2


@dataclass(frozen=True)
class Segment:
    line: Line
    a: tuple[float, float]  # (lat, lon)
    b: tuple[float, float]


class LineIndex:
    def __init__(self, lines: Iterable[Line], cell_deg: float = DEFAULT_CELL_DEG):
        self.cell_deg = cell_deg
        self._cells: dict[tuple[int, int], list[Segment]] = {}
        self._count = 0
        for line in lines:
            for a, b in zip(line.coords, line.coords[1:]):
                self._add(Segment(line, a, b))

    def __len__(self) -> int:
        return self._count

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return (floor(lat / self.cell_deg), floor(lon / self.cell_deg))

    def _add(self, segment: Segment) -> None:
        self._count += 1
        (lat1, lon1), (lat2, lon2) = segment.a, segment.b
        lat_from, lat_to = sorted((self._key(lat1, lon1)[0], self._key(lat2, lon2)[0]))
        lon_from, lon_to = sorted((self._key(lat1, lon1)[1], self._key(lat2, lon2)[1]))
        # A long segment spans several cells; register it in each one it crosses.
        for lat_cell in range(lat_from, lat_to + 1):
            for lon_cell in range(lon_from, lon_to + 1):
                self._cells.setdefault((lat_cell, lon_cell), []).append(segment)

    def nearest(self, lat: float, lon: float, max_km: float | None = None) -> tuple[Line, float] | None:
        """Nearest line and its distance in km, or None when nothing is within reach."""
        lat_cell, lon_cell = self._key(lat, lon)
        km_per_degree_lat = 111.0
        # A degree of longitude shrinks with latitude: 59 km at 58N, so the ring must be wider east-west.
        km_per_degree_lon = max(1.0, 111.0 * cos(radians(lat)))
        if max_km is None:
            reach_lat = reach_lon = 1
        else:
            reach_lat = max(1, ceil(max_km / (self.cell_deg * km_per_degree_lat)))
            reach_lon = max(1, ceil(max_km / (self.cell_deg * km_per_degree_lon)))
        px, py = _to_local_km(lat, lon, lat)

        best: tuple[Line, float] | None = None
        for d_lat in range(-reach_lat, reach_lat + 1):
            for d_lon in range(-reach_lon, reach_lon + 1):
                for segment in self._cells.get((lat_cell + d_lat, lon_cell + d_lon), ()):
                    (ax, ay) = _to_local_km(segment.a[0], segment.a[1], lat)
                    (bx, by) = _to_local_km(segment.b[0], segment.b[1], lat)
                    km = _point_segment_km(px, py, ax, ay, bx, by)
                    if best is None or km < best[1]:
                        best = (segment.line, km)

        if best is None or (max_km is not None and best[1] > max_km):
            return None
        return best
