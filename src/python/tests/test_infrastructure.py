import json

import pytest

from wachta_detectors.infrastructure import Line, distance_to_line_km, lines_within_km, load_lines, nearest_line

# A straight east-west segment at 60N, roughly across the Gulf of Finland.
GULF = Line("Testowy kabel", "power", ((60.0, 24.0), (60.0, 26.0)))
ONE_DEGREE_LAT_KM = 111.19


def test_point_on_the_line_is_at_zero_distance():
    assert distance_to_line_km(60.0, 25.0, GULF) == pytest.approx(0.0, abs=0.01)


def test_perpendicular_distance_matches_latitude_difference():
    # 0.1 degrees of latitude north of the cable is about 11.1 km.
    assert distance_to_line_km(60.1, 25.0, GULF) == pytest.approx(0.1 * ONE_DEGREE_LAT_KM, rel=0.02)


def test_beyond_the_end_the_distance_is_to_the_endpoint():
    # Two degrees of longitude east of the end, at 60N one degree of longitude is ~55.6 km.
    expected = 2 * ONE_DEGREE_LAT_KM * 0.5  # cos(60 degrees) = 0.5
    assert distance_to_line_km(60.0, 28.0, GULF) == pytest.approx(expected, rel=0.02)


def test_nearest_line_picks_the_closer_one():
    far = Line("Daleki", "telecom", ((54.0, 18.0), (54.0, 19.0)))
    line, km = nearest_line([far, GULF], 60.05, 25.0)
    assert line.name == "Testowy kabel"
    assert km < 10


def test_nearest_line_of_nothing_is_none():
    assert nearest_line([], 60.0, 25.0) is None


def test_lines_within_radius_are_sorted_by_distance():
    near = Line("Blisko", "telecom", ((60.02, 24.0), (60.02, 26.0)))
    result = lines_within_km([GULF, near], 60.03, 25.0, radius_km=10)
    assert [line.name for line, _ in result] == ["Blisko", "Testowy kabel"]
    assert all(km <= 10 for _, km in result)


def test_loader_reads_geojson_and_flips_coordinates(tmp_path):
    path = tmp_path / "cables.geojson"
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature",
             "properties": {"name": "Estlink 2", "kind": "power", "operator": "Fingrid"},
             "geometry": {"type": "LineString", "coordinates": [[26.0, 60.0], [26.5, 59.5]]}},
            {"type": "Feature",  # ignored: a point is not a line
             "properties": {"name": "Punkt", "kind": "power"},
             "geometry": {"type": "Point", "coordinates": [26.0, 60.0]}},
            {"type": "Feature",  # ignored: a single coordinate is not a line
             "properties": {"name": "Ogryzek", "kind": "power"},
             "geometry": {"type": "LineString", "coordinates": [[26.0, 60.0]]}},
        ],
    }), encoding="utf-8")

    [line] = load_lines(path)
    assert line.name == "Estlink 2"
    assert line.operator == "Fingrid"
    assert line.coords == ((60.0, 26.0), (59.5, 26.5))  # GeoJSON is lon,lat - we store lat,lon
