"""Receiver coverage model: where do we normally see aircraft? Gaps outside coverage are not evidence."""
from collections import Counter
from collections.abc import Iterable, Mapping

import h3

from wachta_detectors.models import Position

COVERAGE_RESOLUTION = 5


def count_reports(positions: Iterable[Position], resolution: int = COVERAGE_RESOLUTION) -> dict[str, int]:
    return dict(Counter(h3.latlng_to_cell(p.lat, p.lon, resolution) for p in positions if not p.on_ground))


def is_well_covered(
    coverage: Mapping[str, int],
    lat: float,
    lon: float,
    min_reports: int = 200,
    resolution: int = COVERAGE_RESOLUTION,
) -> bool:
    center = h3.latlng_to_cell(lat, lon, resolution)
    return all(coverage.get(cell, 0) >= min_reports for cell in h3.grid_disk(center, 1))
