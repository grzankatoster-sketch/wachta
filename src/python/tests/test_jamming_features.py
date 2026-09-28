from datetime import datetime, timezone

import h3

from wachta_detectors.jamming_features import RESOLUTION, build_features
from wachta_detectors.models import Position

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def plane(lat: float, lon: float, nac_p: int | None = 10, alt: float | None = 33000.0,
          hexid: str = "abc123", on_ground: bool = False) -> Position:
    return Position(hexid, lat, lon, alt, on_ground, nac_p, NOW)


def cell_of(lat: float, lon: float) -> str:
    return h3.latlng_to_cell(lat, lon, RESOLUTION)


def around(cell: str, n: int, nac_p: int = 10, alt: float = 33000.0) -> list[Position]:
    lat, lon = h3.cell_to_latlng(cell)
    return [plane(lat + i * 1e-4, lon + i * 1e-4, nac_p, alt, hexid=f"h{i}") for i in range(n)]


def test_a_cell_with_too_few_aircraft_is_left_out():
    # Udzial policzony z dwoch samolotow to nie pomiar, tylko moneta.
    assert build_features(around(cell_of(57.0, 21.0), 2)) == []


def test_counts_and_share_match_what_went_in():
    cell = cell_of(57.0, 21.0)
    positions = around(cell, 6, nac_p=10) + around(cell, 4, nac_p=3)
    f = [c for c in build_features(positions) if c.h3 == cell][0]
    assert f.n_aircraft == 10
    assert f.n_degraded == 4
    assert f.share == 0.4


def test_threshold_is_the_same_as_the_rule_uses():
    cell = cell_of(57.0, 21.0)
    # nac_p 7 jest zaklocone (ponizej 8), nac_p 8 juz nie.
    assert [c for c in build_features(around(cell, 5, nac_p=7)) if c.h3 == cell][0].n_degraded == 5
    assert [c for c in build_features(around(cell, 5, nac_p=8)) if c.h3 == cell][0].n_degraded == 0


def test_wilson_is_below_the_raw_share_on_small_samples():
    cell = cell_of(57.0, 21.0)
    f = [c for c in build_features(around(cell, 3, nac_p=3)) if c.h3 == cell][0]
    assert f.share == 1.0
    assert f.wilson < 0.6, "trzy samoloty nie maja prawa krzyczec tak glosno jak trzysta"


def test_altitude_is_split_between_degraded_and_clean():
    cell = cell_of(57.0, 21.0)
    positions = around(cell, 4, nac_p=3, alt=35000.0) + around(cell, 4, nac_p=10, alt=8000.0)
    f = [c for c in build_features(positions) if c.h3 == cell][0]
    assert f.mean_alt_degraded == 35000
    assert f.mean_alt_clean == 8000


def test_missing_accuracy_field_is_counted_not_guessed():
    cell = cell_of(57.0, 21.0)
    positions = around(cell, 5, nac_p=10)
    positions += [plane(*h3.cell_to_latlng(cell), nac_p=None, hexid=f"x{i}") for i in range(5)]
    f = [c for c in build_features(positions) if c.h3 == cell][0]
    assert f.share_missing_nac_p == 0.5
    assert f.n_degraded == 0, "brak pola to nie to samo co zle pole"


def test_neighbours_are_seen_and_the_cell_itself_is_not_counted_twice():
    cell = cell_of(57.0, 21.0)
    positions = around(cell, 5, nac_p=10)
    for sasiad in [c for c in h3.grid_disk(cell, 1) if c != cell]:
        positions += around(sasiad, 4, nac_p=3)
    f = [c for c in build_features(positions) if c.h3 == cell][0]
    assert f.share == 0.0
    assert f.neighbour_share == 1.0, "cicha komorka w pierscieniu glosnych - tego regula nie widzi"
    assert f.neighbour_cells == 6


def test_a_cell_with_no_neighbours_reports_zero_not_an_error():
    f = [c for c in build_features(around(cell_of(0.0, -30.0), 5)) if True][0]
    assert f.neighbour_cells == 0
    assert f.neighbour_share == 0.0
    assert f.max_neighbour_share == 0.0


def test_aircraft_on_the_ground_are_ignored():
    cell = cell_of(57.0, 21.0)
    lat, lon = h3.cell_to_latlng(cell)
    positions = around(cell, 4, nac_p=10)
    positions += [plane(lat, lon, nac_p=1, hexid=f"g{i}", on_ground=True) for i in range(10)]
    f = [c for c in build_features(positions) if c.h3 == cell][0]
    assert f.n_aircraft == 4
    assert f.n_degraded == 0


def test_rows_are_sorted_so_output_is_stable():
    positions = around(cell_of(57.0, 21.0), 5) + around(cell_of(41.0, 29.0), 5)
    cells = [c.h3 for c in build_features(positions)]
    assert cells == sorted(cells)


def test_empty_input_gives_no_rows():
    assert build_features([]) == []
