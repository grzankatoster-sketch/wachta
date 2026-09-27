from datetime import datetime, timezone

import h3

from wachta_detectors.coverage import COVERAGE_RESOLUTION, count_reports, is_well_covered
from wachta_detectors.models import Position

T = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
LAT, LON = 55.0, 18.0
CENTER = h3.latlng_to_cell(LAT, LON, COVERAGE_RESOLUTION)


def test_count_reports_ignores_ground():
    positions = [Position("a", LAT, LON, 30000, False, 9, T), Position("b", LAT, LON, None, True, 9, T)]
    assert count_reports(positions) == {CENTER: 1}


def test_well_covered_requires_center_and_all_neighbours():
    coverage = {c: 500 for c in h3.grid_disk(CENTER, 1)}
    assert is_well_covered(coverage, LAT, LON)


def test_edge_of_coverage_is_not_well_covered():
    coverage = {c: 500 for c in h3.grid_disk(CENTER, 1)}
    neighbour = next(c for c in coverage if c != CENTER)
    coverage[neighbour] = 3
    assert not is_well_covered(coverage, LAT, LON)


def test_unknown_area_is_not_well_covered():
    assert not is_well_covered({}, LAT, LON)
