import pytest

from wachta_detectors.infrastructure import Line, nearest_line
from wachta_detectors.spatial_index import LineIndex

CABLE = Line("Zatoka", "power", ((59.6, 25.0), (60.2, 25.0)))
FAR = Line("Daleki", "telecom", ((54.0, 18.0), (54.0, 19.0)))


def test_index_counts_segments_not_lines():
    zigzag = Line("Zygzak", "telecom", ((59.0, 24.0), (59.1, 24.1), (59.2, 24.0)))
    assert len(LineIndex([CABLE, zigzag])) == 3


def test_nearest_matches_the_plain_search():
    index = LineIndex([CABLE, FAR])
    for lat, lon in ((59.9, 25.02), (60.0, 24.9), (54.0, 18.5)):
        line, km = index.nearest(lat, lon, max_km=50)
        expected_line, expected_km = nearest_line([CABLE, FAR], lat, lon)
        assert line.name == expected_line.name
        assert km == pytest.approx(expected_km, rel=1e-9)


def test_nothing_within_reach_returns_none():
    index = LineIndex([CABLE])
    assert index.nearest(45.0, 10.0, max_km=5) is None


def test_long_segment_is_found_from_a_cell_in_its_middle():
    # A single segment spanning several cells must be reachable from the middle, not only from its ends.
    long_line = Line("Dlugi", "pipeline", ((55.0, 12.0), (55.0, 20.0)))
    index = LineIndex([long_line], cell_deg=0.2)
    found = index.nearest(55.01, 16.0, max_km=10)
    assert found is not None
    assert found[1] < 2


def test_empty_index():
    assert len(LineIndex([])) == 0
    assert LineIndex([]).nearest(59.9, 25.0, max_km=10) is None


def test_index_gives_the_same_answers_as_brute_force_on_a_grid():
    lines = [CABLE, FAR, Line("Krzywy", "telecom", ((58.0, 20.0), (58.5, 21.0), (59.0, 20.5)))]
    index = LineIndex(lines)
    for lat in (54.0, 56.0, 58.2, 59.9):
        for lon in (18.0, 20.5, 25.0):
            from_index = index.nearest(lat, lon, max_km=100)
            line, km = nearest_line(lines, lat, lon)
            if km <= 100:
                assert from_index is not None
                assert from_index[1] == pytest.approx(km, rel=1e-9)


def test_nearest_without_a_radius_searches_everywhere():
    """Znalezione w audycie: indeks zwracal None tam, gdzie funkcja globalna znajdowala linie.

    Bez promienia pytanie brzmi "co jest najblizej na swiecie", a jeden pierscien kratek na to nie
    odpowiada - odleglosc 1322 km wypadala poza zasieg i wychodzilo, ze infrastruktury nie ma.
    """
    from wachta_detectors.infrastructure import Line, nearest_line
    from wachta_detectors.spatial_index import LineIndex

    lines = [Line("Daleki kabel", "power", ((60.0, 30.0), (60.1, 30.1)))]
    globalnie = nearest_line(lines, 50.0, 20.0)
    przez_indeks = LineIndex(lines).nearest(50.0, 20.0, max_km=None)
    assert przez_indeks is not None
    assert przez_indeks[0].name == globalnie[0].name
    assert abs(przez_indeks[1] - globalnie[1]) < 1.0


def test_nearest_with_a_radius_still_refuses_what_is_too_far():
    from wachta_detectors.infrastructure import Line
    from wachta_detectors.spatial_index import LineIndex

    lines = [Line("Daleki kabel", "power", ((60.0, 30.0), (60.1, 30.1)))]
    assert LineIndex(lines).nearest(50.0, 20.0, max_km=10) is None
