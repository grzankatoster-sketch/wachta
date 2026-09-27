from datetime import datetime, timezone

import h3

from wachta_detectors.jamming import JammingCell, aggregate_jamming
from wachta_detectors.models import Position

T = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
KALININGRAD = (54.9, 20.3)


def pos(hex_, nac_p, lat=KALININGRAD[0], lon=KALININGRAD[1], on_ground=False):
    return Position(hex=hex_, lat=lat, lon=lon, alt_ft=30000, on_ground=on_ground, nac_p=nac_p, ts=T)


def test_counts_each_aircraft_once_per_cell_by_majority():
    positions = [pos("a", 3), pos("a", 3), pos("a", 9)] + [pos(f"ok{i}", 10) for i in range(4)]
    [cell] = aggregate_jamming(positions, min_aircraft=5)
    assert cell.n_aircraft == 5
    assert cell.n_degraded == 1


def test_skips_ground_and_missing_nacp():
    positions = [pos(f"x{i}", 10) for i in range(5)] + [pos("g", 0, on_ground=True), pos("n", None)]
    [cell] = aggregate_jamming(positions, min_aircraft=5)
    assert cell.n_aircraft == 5
    assert cell.n_degraded == 0


def test_drops_cells_with_too_few_aircraft():
    assert aggregate_jamming([pos(f"x{i}", 2) for i in range(4)], min_aircraft=5) == []
    # default is ten: a handful of aircraft cannot carry a percentage
    assert aggregate_jamming([pos(f"x{i}", 2) for i in range(9)]) == []
    assert len(aggregate_jamming([pos(f"x{i}", 2) for i in range(10)])) == 1


def test_cell_id_matches_h3_resolution():
    [cell] = aggregate_jamming([pos(f"x{i}", 2) for i in range(5)], resolution=4, min_aircraft=5)
    assert cell.h3 == h3.latlng_to_cell(*KALININGRAD, 4)


def test_levels_are_decided_on_the_confidence_floor_not_the_raw_share():
    assert JammingCell("c", 100, 1).level == "low"
    assert JammingCell("c", 100, 8).level == "medium"
    assert JammingCell("c", 100, 20).level == "high"
    assert JammingCell("c", 100, 20).pct == 0.20


def test_a_small_sample_cannot_reach_high():
    """Two of ten aircraft is 20 percent raw, but the interval reaches down to ~6 percent."""
    small, large = JammingCell("c", 10, 2), JammingCell("c", 200, 40)
    assert small.pct == large.pct == 0.20
    assert small.level == "medium"
    assert large.level == "high"
    assert small.confidence_floor < large.confidence_floor


def test_confidence_floor_is_zero_for_no_affected_aircraft():
    assert JammingCell("c", 50, 0).confidence_floor == 0.0
    assert JammingCell("c", 50, 0).level == "low"
