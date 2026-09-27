"""Writes the synthetic D1 seed cases (same scenarios as tests/test_dark.py) to eval/fixtures/d1_cases.jsonl."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "python"))
import h3  # noqa: E402

from wachta_detectors.coverage import COVERAGE_RESOLUTION  # noqa: E402

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
LAT, LON = 55.5, 17.5
CELL = h3.latlng_to_cell(LAT, LON, COVERAGE_RESOLUTION)
GOOD = {c: 1000 for c in h3.grid_disk(CELL, 2)}
FAR = [[54.3776, 18.4662]]


def case(name, expected, coverage=GOOD, alive=(CELL,), airports=FAR, **over):
    s = dict(hex="ae1234", flight="FORTE10", type_code="Q4", is_military=True, lat=LAT, lon=LON,
             alt_ft=30000, gs_kt=300.0, ts=(NOW - timedelta(minutes=10)).isoformat(), n_points=120,
             last_message_at=(NOW - timedelta(minutes=10)).isoformat())
    s.update(over)
    return {"case": name, "last_seen": s, "now": NOW.isoformat(), "coverage": coverage,
            "alive": list(alive), "airports": airports, "expected": expected}


cases = [
    case("dark_in_coverage", True),
    case("civil_dark_in_coverage", True, is_military=False, n_points=50),
    case("gap_too_recent", False, ts=(NOW - timedelta(minutes=2)).isoformat(),
         last_message_at=(NOW - timedelta(minutes=2)).isoformat()),
    case("gap_too_old", False, ts=(NOW - timedelta(minutes=45)).isoformat(),
         last_message_at=(NOW - timedelta(minutes=45)).isoformat()),
    case("jammed_but_still_transmitting", False, last_message_at=(NOW - timedelta(seconds=20)).isoformat()),
    case("low_altitude", False, alt_ft=1500),
    case("slow", False, gs_kt=60.0),
    case("near_airport", False, airports=[[LAT + 0.1, LON]]),
    case("edge_of_coverage", False, coverage={CELL: 1000}),
    case("receiver_outage", False, alive=()),
]
out = Path(__file__).parent / "fixtures" / "d1_cases.jsonl"
out.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
print(f"wrote {len(cases)} cases to {out}")
