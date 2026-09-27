"""Checks the frozen OSM cable file the D6 detector will run on.

Skipped until the file is fetched (eval/feasibility/fetch_cables.py), so the suite stays runnable
on a clean checkout without network access.
"""
from pathlib import Path

import pytest

from wachta_detectors.infrastructure import distance_to_line_km, load_lines, nearest_line

CABLES = Path(__file__).resolve().parents[3] / "data" / "infrastructure" / "baltic_cables.geojson"
pytestmark = pytest.mark.skipif(not CABLES.exists(), reason="brak data/infrastructure/baltic_cables.geojson")

# Cables and pipelines behind the incidents D6 is evaluated against. OSM names them inconsistently
# ("Balticconnector" on land, "Baltic Connector" at sea; "HVDC Estlink 2"), so matching ignores
# spaces, hyphens and prefixes — an exact comparison gave a false alarm on data that was complete.
INCIDENT_LINES = ["estlink2", "clion1", "bcsnorth", "balticconnector"]


def normalise(name: str) -> str:
    return name.lower().replace(" ", "").replace("-", "")


@pytest.fixture(scope="module")
def lines():
    return load_lines(CABLES)


def test_incident_lines_are_present(lines):
    names = [normalise(line.name) for line in lines]
    missing = [needle for needle in INCIDENT_LINES if not any(needle in n for n in names)]
    assert missing == [], f"brak linii z incydentow: {missing}"


def test_every_line_has_a_usable_geometry(lines):
    assert lines, "plik bez linii"
    assert all(len(line.coords) >= 2 for line in lines)
    assert all(-90 <= lat <= 90 and -180 <= lon <= 180 for line in lines for lat, lon in line.coords)


def estlink(lines):
    return next(line for line in lines if "estlink2" in normalise(line.name))


def test_estlink_runs_through_the_gulf_of_finland(lines):
    line = estlink(lines)
    lats = [lat for lat, _ in line.coords]
    lons = [lon for _, lon in line.coords]
    assert 59.0 < min(lats) and max(lats) < 61.0
    assert 24.0 < min(lons) and max(lons) < 28.0


def test_a_point_on_the_route_is_close_and_kaliningrad_is_far(lines):
    line = estlink(lines)
    lat, lon = line.coords[len(line.coords) // 2]
    assert distance_to_line_km(lat, lon, line) < 0.1
    assert distance_to_line_km(54.71, 20.51, line) > 400  # Kaliningrad


def test_nearest_line_to_a_point_on_estlink_is_a_line_in_that_corridor(lines):
    line = estlink(lines)
    lat, lon = line.coords[len(line.coords) // 2]
    nearest, km = nearest_line(lines, lat, lon)
    assert km < 1.0
    # Several cables share the Gulf of Finland corridor, so only require one of them, not Estlink itself.
    assert nearest.kind in {"power", "telecom", "pipeline"}
