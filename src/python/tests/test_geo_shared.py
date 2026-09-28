"""Znalezione w audycie: promien Ziemi, mila morska, azymut, siatka i grupowanie torow byly
przepisane osobno w siedmiu modulach.

Kopie zgadzaly sie co do wartosci - i wlasnie to jest grozne, bo nic nie wychwyciloby dnia, w
ktorym jedna zostanie poprawiona, a reszta nie. Jedna para juz sie rozjechala: przy kratce 0,1
stopnia punkt na szerokosci 1,0 trafial w gaps do kwadratu 9, a w anomalies do kwadratu 10.

Te testy pilnuja zrodla, nie wyniku. Dwie rowne sobie stale nie sa jedna stala.
"""
import inspect
from datetime import datetime, timedelta, timezone
from math import isinf
from pathlib import Path

import pytest

from wachta_detectors import (
    anchor,
    anomalies,
    dark_sts,
    gaps,
    geo,
    identity,
    infrastructure,
    racetrack,
    spatial_index,
    sts,
)
from wachta_detectors.anchor import ShipFix

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
MODULY = (anchor, anomalies, dark_sts, gaps, identity, infrastructure, racetrack, spatial_index, sts)


class TestJednoZrodloStalych:
    def test_the_earth_radius_is_one_constant(self):
        assert infrastructure.EARTH_RADIUS_KM is geo.EARTH_RADIUS_KM

    @pytest.mark.parametrize("literal", ["6371.0", "1.852", "111.0"])
    def test_no_detector_spells_a_shared_constant_out_again(self, literal):
        winne = [m.__name__ for m in MODULY if literal in inspect.getsource(m)]
        assert winne == [], f"{literal} ma byc tylko w geo.py, a jest w {winne}"

    def test_the_nautical_mile_is_named(self):
        assert geo.KM_PER_NM == 1.852
        assert geo.KM_PER_DEG_LAT == 111.0


class TestJedenAzymut:
    def test_every_caller_uses_the_same_bearing(self):
        assert anchor.bearing_deg is geo.bearing_deg
        assert racetrack.bearing_deg is geo.bearing_deg

    def test_bearing_still_points_north_and_east(self):
        assert geo.bearing_deg(0.0, 0.0, 1.0, 0.0) == pytest.approx(0.0, abs=0.1)
        assert geo.bearing_deg(0.0, 0.0, 0.0, 1.0) == pytest.approx(90.0, abs=0.1)


class TestJednaKratka:
    def test_every_grid_uses_the_same_cell_function(self):
        assert gaps._cell is geo.cell_of
        assert sts._cell is geo.cell_of
        assert anomalies._cell is geo.cell_of

    def test_the_case_where_the_two_implementations_disagreed(self):
        # int(1.0 // 0.1) == 9, floor(1.0 / 0.1) == 10. Ten sam punkt w dwoch roznych kwadratach.
        assert geo.cell_of(1.0, 0.0, 0.1) == (10, 0)
        assert gaps._cell(1.0, 0.0, 0.1) == anomalies._cell(1.0, 0.0, 0.1) == sts._cell(1.0, 0.0, 0.1)

    def test_the_index_and_the_detectors_agree_on_a_boundary(self):
        indeks = spatial_index.LineIndex([], cell_deg=0.1)
        assert indeks._key(1.0, 1.0) == geo.cell_of(1.0, 1.0, 0.1)


class TestJednoGrupowanieTorow:
    def test_every_detector_groups_tracks_with_the_same_function(self):
        assert gaps.by_ship is anchor.by_ship
        assert identity.by_ship is anchor.by_ship

    def test_grouping_sorts_each_track_in_time(self):
        fixes = [ShipFix("A", T0 + timedelta(minutes=10), 54.0, 18.0),
                 ShipFix("B", T0, 55.0, 19.0),
                 ShipFix("A", T0, 54.1, 18.1)]
        tracks = anchor.by_ship(fixes)
        assert sorted(tracks) == ["A", "B"]
        assert [f.ts for f in tracks["A"]] == [T0, T0 + timedelta(minutes=10)]

    def test_sts_no_longer_carries_its_own_grouping_loop(self):
        for fn in (sts._under_way, sts.slow_fixes):
            assert "setdefault(fix.mmsi" not in inspect.getsource(fn), fn.__name__


class TestJednaPredkosc:
    """Zerowy odstep czasu znaczyl trzy rozne rzeczy naraz, zaleznie od tego, kogo zapytac."""

    def test_a_bad_interval_has_one_stated_answer(self):
        assert isinf(geo.implied_kt(111.0, 0.0))
        assert geo.implied_kt(0.0, 0.0) == 0.0

    def test_the_same_instant_tolerance_is_a_parameter_not_a_rule(self):
        assert geo.implied_kt(0.5, 0.0, same_instant_km=1.0) == 0.0
        assert isinf(geo.implied_kt(5.0, 0.0, same_instant_km=1.0))

    def test_a_normal_interval_is_kilometres_over_the_nautical_mile(self):
        assert geo.implied_kt(18.52, 1.0) == pytest.approx(10.0)

    def test_identity_speaks_through_the_shared_function(self):
        a = ShipFix("1", T0, 54.0, 18.0)
        b = ShipFix("1", T0, 55.0, 18.0)          # ok. 111 km w tej samej sekundzie
        assert isinf(identity.implied_kt(a, b))
        assert "1.852" not in inspect.getsource(identity.implied_kt)


def test_geo_is_the_only_module_that_defines_these():
    zrodlo = Path(inspect.getsourcefile(geo)).name
    assert zrodlo == "geo.py"
    for nazwa in ("EARTH_RADIUS_KM", "KM_PER_NM", "KM_PER_DEG_LAT", "cell_of", "bearing_deg", "implied_kt"):
        assert hasattr(geo, nazwa), nazwa
