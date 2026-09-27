from datetime import datetime, timedelta, timezone

import h3

from wachta_detectors.coverage import COVERAGE_RESOLUTION
from wachta_detectors.dark import DarkRules, LastSeen, find_dark_candidates

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
LAT, LON = 55.5, 17.5  # open sea, south Baltic
CELL = h3.latlng_to_cell(LAT, LON, COVERAGE_RESOLUTION)
GOOD_COVERAGE = {c: 1000 for c in h3.grid_disk(CELL, 2)}
ALIVE = {CELL}
FAR_AIRPORTS = [(54.3776, 18.4662)]  # Gdansk, ~130 km away


def seen(**overrides):
    base = dict(hex="ae1234", flight="FORTE10", type_code="Q4", is_military=True, lat=LAT, lon=LON,
                alt_ft=30000, gs_kt=300.0, ts=NOW - timedelta(minutes=10), n_points=120,
                last_message_at=NOW - timedelta(minutes=10))
    base.update(overrides)
    return LastSeen(**base)


def run(items, coverage=GOOD_COVERAGE, alive=ALIVE, airports=FAR_AIRPORTS):
    return find_dark_candidates(items, coverage, alive, airports, NOW)


def test_disappearance_at_altitude_in_good_coverage_is_candidate():
    [c] = run([seen()])
    assert c.hex == "ae1234"
    assert c.score == 1.0
    assert c.evidence["nearest_airport_km"] > 40
    assert c.evidence["flight"] == "FORTE10"


def test_civil_aircraft_scores_lower():
    [c] = run([seen(is_military=False, n_points=50)])
    assert c.score == 0.6


def test_too_recent_or_too_old_gap_is_ignored():
    assert run([seen(ts=NOW - timedelta(minutes=2), last_message_at=NOW - timedelta(minutes=2))]) == []
    assert run([seen(ts=NOW - timedelta(minutes=45), last_message_at=NOW - timedelta(minutes=45))]) == []


def test_aircraft_still_transmitting_without_position_is_not_dark():
    """GPS jamming: position is 10 min old, but the aircraft was heard 20 s ago -> not a dark transponder."""
    assert run([seen(last_message_at=NOW - timedelta(seconds=20))]) == []


def test_low_or_slow_aircraft_is_ignored():
    assert run([seen(alt_ft=1500)]) == []
    assert run([seen(alt_ft=None)]) == []
    assert run([seen(gs_kt=60.0)]) == []


def test_near_airport_is_landing_not_dark():
    assert run([seen()], airports=[(LAT + 0.1, LON)]) == []


def test_edge_of_coverage_is_ignored():
    assert run([seen()], coverage={CELL: 1000}) == []


def test_no_other_aircraft_seen_after_means_receiver_outage():
    assert run([seen()], alive=set()) == []


def test_short_track_is_ignored():
    assert run([seen(n_points=3)]) == []


def test_rules_are_configurable():
    assert run([seen(alt_ft=2000)]) == []
    assert find_dark_candidates([seen(alt_ft=2000)], GOOD_COVERAGE, ALIVE, FAR_AIRPORTS, NOW, DarkRules(min_alt_ft=1000))
