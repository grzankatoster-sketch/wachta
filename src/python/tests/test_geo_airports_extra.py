"""Extra edge cases for distance and airport loading.

Drafted by the local model (qwen3.5:9b), then verified by running: it got the Gdansk-Warsaw distance
wrong (296 km vs the actual 292.6) and asserted on a field the loader does not return. Both fixed here.
"""
import pytest

from wachta_detectors.airports import load_airports, nearest_airport_km
from wachta_detectors.geo import haversine_km

GDANSK = (54.3776, 18.4662)
WARSAW = (52.2297, 21.0122)


def write_csv(tmp_path, body):
    path = tmp_path / "airports.csv"
    path.write_text("id,ident,type,name,latitude_deg,longitude_deg\n" + body, encoding="utf-8")
    return path


def test_distance_to_the_same_point_is_zero():
    assert haversine_km(*GDANSK, *GDANSK) == pytest.approx(0.0, abs=1e-9)


def test_distance_is_symmetric():
    assert haversine_km(*GDANSK, *WARSAW) == pytest.approx(haversine_km(*WARSAW, *GDANSK), rel=1e-12)


def test_one_degree_of_longitude_at_the_equator():
    assert haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.19, rel=0.01)


def test_known_distance_gdansk_warsaw():
    assert haversine_km(*GDANSK, *WARSAW) == pytest.approx(292.6, rel=0.01)


def test_distance_across_the_antimeridian_is_short():
    """179.9E to 179.9W is 0.2 degrees apart, not 359.8 — the formula must not take the long way round."""
    assert haversine_km(0.0, 179.9, 0.0, -179.9) == pytest.approx(2 * 11.119, rel=0.01)


def test_nearest_airport_of_empty_list_is_infinite():
    assert nearest_airport_km([], *GDANSK) == float("inf")


def test_nearest_airport_picks_the_closer_one():
    airports = [GDANSK, WARSAW]
    assert nearest_airport_km(airports, 52.3, 21.0) < 10
    assert nearest_airport_km(airports, 54.4, 18.5) < 10


def test_loader_keeps_only_the_wanted_types_and_returns_coordinates(tmp_path):
    path = write_csv(tmp_path, "1,EPGD,large_airport,Gdansk,54.3776,18.4662\n"
                               "2,EPWA,small_airport,Warszawa,52.2297,21.0122\n"
                               "3,XX,heliport,Helipad,50.0,10.0\n"
                               "4,YY,closed,Closed field,51.0,11.0\n")
    assert load_airports(path) == [GDANSK, WARSAW]


def test_loader_on_a_header_only_file_returns_nothing(tmp_path):
    assert load_airports(write_csv(tmp_path, "")) == []


def test_loader_with_no_matching_type_returns_nothing(tmp_path):
    assert load_airports(write_csv(tmp_path, "1,XX,heliport,Helipad,50.0,10.0\n")) == []
