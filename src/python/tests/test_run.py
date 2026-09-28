"""Detector loop: what one bad tick may cost, and what counts as progress.

Everything here runs against a fake connection and a fake repository. The loop's job is scheduling
and failure containment, and neither needs a database to be wrong.
"""
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from wachta_detectors import run as loop

NOW = datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc)
HOUR = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


class FakeConn:
    """psycopg stand-in that records the order of writes and the transaction wrapped around them."""

    def __init__(self):
        self.log: list[str] = []

    @contextmanager
    def transaction(self):
        self.log.append("begin")
        try:
            yield self
        except BaseException:
            self.log.append("rollback")
            raise
        self.log.append("commit")


class FakeRepo:
    def __init__(self, conn):
        self.conn = conn
        self.since = {}
        self.stored_jamming = None
        self.stored_coverage = None
        self.fail_alerts = False
        self.jamming_hours: list[datetime] = []
        self.coverage_hours: list[datetime] = []
        self.ship_fixes: list = []
        self.inserted_ships: list = []
        self.alert_rows: list = []

    def last_seen_since(self, conn, since):
        self.since["last_seen"] = since
        return []

    def coverage_last_days(self, conn):
        return {}

    def alive_cells(self, conn, since):
        self.since["alive"] = since
        return set()

    def insert_d1_samples(self, conn, samples):
        self.conn.log.append("samples")

    def insert_alerts(self, conn, detector, candidates):
        self.conn.log.append("alerts")
        if self.fail_alerts:
            raise RuntimeError("polaczenie zerwane w polowie zapisu")
        return len(candidates)

    def last_jamming_hour(self, conn):
        return self.stored_jamming

    def last_coverage_hour(self, conn):
        return self.stored_coverage

    def positions_between(self, conn, start, end):
        return []

    def replace_jamming(self, conn, hour, cells):
        self.jamming_hours.append(hour)

    def upsert_coverage(self, conn, hour, counts):
        self.coverage_hours.append(hour)

    def insert_ship_positions(self, conn, source_id, ships, fetched_at):
        self.inserted_ships.append((source_id, ships, fetched_at))
        return len(ships)

    def recent_ship_fixes(self, conn, since):
        self.since["ships"] = since
        return self.ship_fixes

    def insert_alert_rows(self, conn, rows):
        rows = list(rows)
        self.alert_rows.extend(rows)
        return len(rows)


@pytest.fixture
def fake(monkeypatch):
    conn = FakeConn()
    repo = FakeRepo(conn)
    monkeypatch.setattr(loop, "repo", repo)
    # Zaden test tick()/main() nie ma dotykac sieci: bez tego pierwszy tick kazdego testu probowalby
    # naprawde polaczyc sie z Digitraffic, bo last_ships_fetch startuje jako None (jak D3 przy starcie).
    monkeypatch.setattr(loop, "fetch_ships", lambda: [])
    return conn, repo


class TestD1Writes:
    def test_samples_and_alerts_land_in_one_transaction(self, fake):
        conn, _ = fake
        loop.run_d1(conn, [], NOW)
        assert conn.log == ["begin", "samples", "alerts", "commit"]

    def test_a_failed_alert_write_takes_the_samples_with_it(self, fake):
        # Probka niesie pole alerted, wiec probka bez swojego alertu to nie brakujacy wiersz,
        # tylko material, na ktorym pozniejszy pomiar recall wyjdzie falszywie wysoki.
        conn, repo = fake
        repo.fail_alerts = True
        with pytest.raises(RuntimeError):
            loop.run_d1(conn, [], NOW)
        assert conn.log == ["begin", "samples", "alerts", "rollback"]


class TestProgressMarker:
    def test_first_run_on_an_empty_store_covers_an_explicit_window(self, fake):
        conn, repo = fake
        loop.run_d3(conn, NOW, loop.Progress())
        assert repo.jamming_hours == [HOUR - timedelta(hours=3), HOUR - timedelta(hours=2),
                                      HOUR - timedelta(hours=1), HOUR]

    def test_hours_that_produced_nothing_are_not_recomputed_every_tick(self, fake):
        conn, repo = fake
        repo.stored_jamming = datetime(2026, 9, 22, 6, tzinfo=timezone.utc)  # potem cisza w danych
        progress = loop.Progress()

        loop.run_d3(conn, NOW, progress)
        catchup = list(repo.jamming_hours)
        repo.jamming_hours.clear()
        loop.run_d3(conn, NOW + timedelta(minutes=10), progress)

        assert catchup[0] == datetime(2026, 9, 22, 6, tzinfo=timezone.utc)
        assert catchup[-1] == HOUR
        assert repo.jamming_hours == [HOUR]  # drugi przebieg: juz tylko biezaca, niepelna godzina

    def test_coverage_hours_without_reports_are_not_recomputed_every_tick(self, fake):
        conn, repo = fake
        repo.stored_coverage = datetime(2026, 9, 22, 6, tzinfo=timezone.utc)
        progress = loop.Progress()

        loop.run_coverage(conn, NOW, progress)
        first = list(repo.coverage_hours)
        repo.coverage_hours.clear()
        loop.run_coverage(conn, NOW + timedelta(minutes=10), progress)

        assert first == [datetime(2026, 9, 22, h, tzinfo=timezone.utc) for h in range(7, 12)]
        assert repo.coverage_hours == []

    def test_catchup_stays_capped_after_a_long_outage(self):
        hours = loop.hours_to_finalise(HOUR, None, HOUR - timedelta(days=30), 3, max_catchup_hours=48)
        assert len(hours) == 48
        assert hours[0] == HOUR - timedelta(hours=48)


class TestFailureContainment:
    def test_a_data_error_in_one_detector_does_not_take_the_others_down(self, fake):
        conn, repo = fake

        def boom(conn, since):
            raise ValueError("zla geometria")

        repo.last_seen_since = boom
        progress = loop.Progress()
        loop.tick(conn, [], NOW, progress)

        assert repo.coverage_hours  # pokrycie policzone mimo awarii D1
        assert repo.jamming_hours
        assert progress.last_d3_run == NOW

    def test_a_failed_d3_is_retried_on_the_next_tick(self, fake):
        conn, repo = fake

        def boom(conn, start, end):
            raise ValueError("zla geometria")

        repo.positions_between = boom
        progress = loop.Progress()
        loop.tick(conn, [], NOW, progress)
        assert progress.last_d3_run is None

    @pytest.mark.parametrize("stop", [KeyboardInterrupt, SystemExit])
    def test_a_stop_signal_inside_a_detector_is_never_swallowed(self, fake, stop):
        conn, repo = fake

        def boom(conn, since):
            raise stop()

        repo.last_seen_since = boom
        with pytest.raises(stop):
            loop.tick(conn, [], NOW, loop.Progress())


class TestMainLoop:
    @staticmethod
    def _patch(monkeypatch, tick, sleep):
        @contextmanager
        def connect(*args, **kwargs):
            yield FakeConn()

        monkeypatch.setattr(loop, "load_airports", lambda path: [])
        monkeypatch.setattr(loop.psycopg, "connect", connect)
        monkeypatch.setattr(loop, "tick", tick)
        monkeypatch.setattr(loop.time, "sleep", sleep)
        monkeypatch.setenv("WACHTA_DB", "postgresql://fake")

    def test_a_data_error_costs_one_tick_not_the_process(self, monkeypatch):
        ticks = []

        def tick(conn, airports, now, progress, *reszta):
            ticks.append(now)
            raise ValueError("zla geometria")  # nie psycopg.Error

        def sleep(seconds):
            if len(ticks) >= 3:
                raise KeyboardInterrupt

        self._patch(monkeypatch, tick, sleep)
        with pytest.raises(KeyboardInterrupt):
            loop.main()
        assert len(ticks) == 3

    @pytest.mark.parametrize("stop", [KeyboardInterrupt, SystemExit])
    def test_a_stop_signal_ends_the_loop(self, monkeypatch, stop):
        def tick(conn, airports, now, progress, *reszta):
            raise stop()

        def sleep(seconds):
            raise RuntimeError("petla polknela sygnal zatrzymania")

        self._patch(monkeypatch, tick, sleep)
        with pytest.raises(stop):
            loop.main()


class TestKonfiguracjaUruchomieniowa:
    """Znalezione w audycie: okno danych, swiezosc odbioru i odstep D3 byly zaszyte w runnerze.

    Okno bylo tu najgorsze, bo nie jest ustawieniem harmonogramu: mowi, ktore samoloty w ogole
    trafia do detektora. Napisane z reki 35 minut przestawalo pasowac w chwili, w ktorej ktos
    rozszerzyl max_gap - i D1 szukal ciszy, ktorych zapytanie mu nie podawalo.
    """

    def test_the_data_window_is_derived_from_the_d1_rules(self):
        from wachta_detectors.dark import DarkRules

        szerokie = DarkRules(max_gap=timedelta(minutes=90))
        assert loop.d1_window() == timedelta(minutes=35)          # 30 min max_gap + 5 min zapasu
        assert loop.d1_window(szerokie) == timedelta(minutes=95)

    def test_widening_max_gap_widens_the_query(self, fake):
        from wachta_detectors.dark import DarkRules

        conn, repo = fake
        loop.run_d1(conn, [], NOW, DarkRules(max_gap=timedelta(minutes=90)))
        assert NOW - repo.since["last_seen"] == timedelta(minutes=95)

    def test_receiver_freshness_is_a_setting(self, fake):
        conn, repo = fake
        config = loop.RunnerConfig(receiver_fresh=timedelta(minutes=7))
        loop.run_d1(conn, [], NOW, config=config)
        assert NOW - repo.since["alive"] == timedelta(minutes=7)

    def test_the_d3_interval_is_a_setting_not_a_literal(self, fake):
        conn, repo = fake
        config = loop.RunnerConfig(d3_every=timedelta(hours=1))
        progress = loop.Progress()

        loop.tick(conn, [], NOW, progress, config=config)
        repo.jamming_hours.clear()
        loop.tick(conn, [], NOW + timedelta(minutes=10), progress, config=config)
        assert repo.jamming_hours == []          # dziesiec minut to za wczesnie przy odstepie godzinnym

        loop.tick(conn, [], NOW + timedelta(hours=1), progress, config=config)
        assert repo.jamming_hours

    def test_the_schedule_can_come_from_the_environment(self):
        config = loop.RunnerConfig.from_env({"WACHTA_TICK_SECONDS": "30",
                                             "WACHTA_D3_EVERY_MINUTES": "45",
                                             "WACHTA_MAX_CATCHUP_HOURS": "12"})
        assert config.tick == timedelta(seconds=30)
        assert config.d3_every == timedelta(minutes=45)
        assert config.max_catchup_hours == 12
        assert config.receiver_fresh == loop.RunnerConfig().receiver_fresh   # nieustawione zostaje domyslne

    def test_the_catchup_cap_is_taken_from_the_config(self, fake):
        conn, repo = fake
        repo.stored_jamming = HOUR - timedelta(days=10)
        loop.run_d3(conn, NOW, loop.Progress(), loop.RunnerConfig(max_catchup_hours=5))
        assert len(repo.jamming_hours) == 5 + 1          # piec zamknietych godzin plus biezaca


class TestFetchShips:
    """Digitraffic parsing, isolated from the network: _get_json is the only seam that talks HTTP."""

    def _locations(self):
        now = datetime.now(timezone.utc)
        fresh_ms = now.timestamp() * 1000 - 2 * 60000        # 2 min temu: swieza
        stale_ms = now.timestamp() * 1000 - 45 * 60000       # 45 min temu: za stara
        return {"features": [
            {"properties": {"mmsi": 111, "sog": 12.0, "cog": 90.0, "timestampExternal": fresh_ms},
             "geometry": {"coordinates": [24.9, 59.9]}},
            {"properties": {"mmsi": 222, "sog": 0.1, "cog": 0.0, "timestampExternal": stale_ms},
             "geometry": {"coordinates": [25.0, 60.0]}},
        ]}

    VESSELS = [{"mmsi": 111, "name": " ALFA ", "imo": 1234567, "shipType": 70}]

    def test_positions_are_joined_with_vessel_metadata(self, monkeypatch):
        locations = self._locations()
        monkeypatch.setattr(loop, "_get_json", lambda url, timeout: (
            locations if url == loop.DIGITRAFFIC_LOCATIONS else self.VESSELS
        ))
        ships = loop.fetch_ships()
        assert [s["mmsi"] for s in ships] == ["111"]     # statek 222 odsiany jako stara pozycja
        assert ships[0]["name"] == "ALFA"
        assert ships[0]["imo"] == "1234567"
        assert ships[0]["ship_type"] == "70"
        assert ships[0]["lat"] == 59.9 and ships[0]["lon"] == 24.9

    def test_digitraffic_headers_are_always_sent(self, monkeypatch):
        # Znalezione w audycie: Digitraffic odmawia (403) bez User-Agent i Digitraffic-User, dokladnie
        # jak adsb.lol wczesniej. Mutacja: usuniecie ktoregokolwiek naglowka ma zepsuc ten test.
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"[]"

        def fake_request(url, headers=None):
            captured[url] = headers
            return url

        monkeypatch.setattr(loop.urllib.request, "Request", fake_request)
        monkeypatch.setattr(loop.urllib.request, "urlopen", lambda req, timeout: FakeResponse())
        loop._get_json(loop.DIGITRAFFIC_LOCATIONS, 5.0)
        assert captured[loop.DIGITRAFFIC_LOCATIONS]["User-Agent"]
        assert captured[loop.DIGITRAFFIC_LOCATIONS]["Digitraffic-User"]

    def test_a_gzip_response_is_decompressed_before_parsing(self, monkeypatch):
        # Znalezione na zywym Digitraffic: serwer odsyla gzip niezaleznie od naszego naglowka, a
        # urllib (w przeciwienstwie do requests) nie dekompresuje samo - bez tego UnicodeDecodeError.
        import gzip as gzip_module

        payload = gzip_module.compress(json.dumps([{"mmsi": 1}]).encode("utf-8"))

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return payload

        monkeypatch.setattr(loop.urllib.request, "Request", lambda url, headers=None: url)
        monkeypatch.setattr(loop.urllib.request, "urlopen", lambda req, timeout: FakeResponse())
        assert loop._get_json(loop.DIGITRAFFIC_LOCATIONS, 5.0) == [{"mmsi": 1}]


class TestShipIngest:
    def test_fetched_ships_are_written_with_provenance(self, fake, monkeypatch):
        conn, repo = fake
        fake_ships = [{"mmsi": "1", "ts": NOW, "lat": 60.0, "lon": 25.0}]
        monkeypatch.setattr(loop, "fetch_ships", lambda: fake_ships)
        loop.run_ship_ingest(conn, NOW)
        [(source_id, ships, fetched_at)] = repo.inserted_ships
        assert source_id == loop.SHIP_SOURCE_ID == "digitraffic-ais"
        assert ships == fake_ships
        assert fetched_at == NOW


class TestD4Wiring:
    """run_d4 must write only what suspicious(find_gaps(...)) already vouches for - not every gap."""

    T0 = datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc)

    def _sailing(self, mmsi, start, stop, step=5.0, lat=59.90, lon=26.00, sog=10.0):
        from wachta_detectors.anchor import ShipFix
        out, minute = [], start
        while minute <= stop:
            out.append(ShipFix(mmsi=mmsi, ts=self.T0 + timedelta(minutes=minute),
                               lat=lat, lon=lon + (minute - start) * 0.002, sog=sog))
            minute += step
        return out

    def _crowd(self):
        out = []
        for i in range(5):
            out += self._sailing(f"crowd{i}", 0, 240, lat=59.90 + i * 0.01, lon=26.01)
        return out

    def test_a_suspicious_gap_becomes_a_d4_alert(self, fake):
        conn, repo = fake
        track = self._sailing("111", 0, 30) + self._sailing("111", 150, 180, lon=26.30)
        repo.ship_fixes = track + self._crowd()
        loop.run_d4(conn, self.T0 + timedelta(hours=4))
        [(detector, entity_id, started_at, lat, lon, score, evidence)] = repo.alert_rows
        assert detector == "D4"
        assert entity_id == "111"
        assert 0.0 < score <= 1.0
        assert evidence["mmsi"] == "111"
        assert evidence["note"].startswith("Candidate")

    def test_a_gap_with_no_witnesses_is_not_an_alert(self, fake):
        conn, repo = fake
        # Sama luka statku "111", bez zadnego innego ruchu w kratce - brak swiadkow.
        repo.ship_fixes = self._sailing("111", 0, 30) + self._sailing("111", 150, 180, lon=26.30)
        loop.run_d4(conn, self.T0 + timedelta(hours=4))
        assert repo.alert_rows == []

    def test_the_query_window_comes_from_config(self, fake):
        conn, repo = fake
        loop.run_d4(conn, NOW, window_hours=7)
        assert NOW - repo.since["ships"] == timedelta(hours=7)


class TestD6Wiring:
    """run_d6 must split fixes by ship before handing them to find_anchor_drag (see anchor.py)."""

    T0 = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
    CABLE_LAT = (59.6, 25.0)

    def _index(self):
        from wachta_detectors.infrastructure import Line
        from wachta_detectors.spatial_index import LineIndex
        return LineIndex([Line("Kabel testowy", "power", ((59.6, 25.0), (60.2, 25.0)))])

    def _wandering_track(self, mmsi):
        from wachta_detectors.anchor import ShipFix
        courses = [10.0, 70.0, 350.0, 120.0, 40.0, 300.0, 80.0, 20.0]
        return [ShipFix(mmsi=mmsi, ts=self.T0 + timedelta(minutes=5 * i), lat=59.9, lon=24.99,
                        sog=3.0, cog=courses[i]) for i in range(8)]

    def test_a_wandering_ship_over_a_cable_becomes_a_d6_alert(self, fake):
        conn, repo = fake
        repo.ship_fixes = self._wandering_track("999888777")
        loop.run_d6(conn, self.T0 + timedelta(hours=1), self._index())
        [(detector, entity_id, started_at, lat, lon, score, evidence)] = repo.alert_rows
        assert detector == "D6"
        assert entity_id == "999888777"
        assert evidence["line"] == "Kabel testowy"

    def test_two_ships_near_the_same_cable_are_not_spliced_into_one_run(self, fake):
        # Bez podzialu po mmsi find_anchor_drag() sortuje wszystkie fixy razem i skleja dwa statki
        # w jeden "przebieg" - test lapie dokladnie ten blad.
        conn, repo = fake
        repo.ship_fixes = self._wandering_track("111") + self._wandering_track("222")
        loop.run_d6(conn, self.T0 + timedelta(hours=1), self._index())
        mmsi_in_alerts = {row[1] for row in repo.alert_rows}
        assert mmsi_in_alerts == {"111", "222"}

    def test_a_ship_holding_course_is_not_flagged(self, fake):
        from wachta_detectors.anchor import ShipFix
        conn, repo = fake
        repo.ship_fixes = [ShipFix(mmsi="111", ts=self.T0 + timedelta(minutes=5 * i),
                                   lat=59.9, lon=24.99, sog=3.0, cog=90.0) for i in range(8)]
        loop.run_d6(conn, self.T0 + timedelta(hours=1), self._index())
        assert repo.alert_rows == []


class TestMaritimeScheduling:
    """Ships fetch and D4/D6 run on their own cadence, like D3 already does - see TestKonfiguracjaUruchomieniowa."""

    def test_ships_are_fetched_on_their_own_cadence(self, fake, monkeypatch):
        conn, repo = fake
        calls = []
        monkeypatch.setattr(loop, "fetch_ships", lambda: calls.append(1) or [])
        config = loop.RunnerConfig(ships_every=timedelta(minutes=10))
        progress = loop.Progress()

        loop.tick(conn, [], NOW, progress, config=config)
        loop.tick(conn, [], NOW + timedelta(minutes=2), progress, config=config)
        assert len(calls) == 1                            # za wczesnie na drugie pobranie

        loop.tick(conn, [], NOW + timedelta(minutes=11), progress, config=config)
        assert len(calls) == 2

    def test_d4_and_d6_run_on_their_own_cadence_not_every_tick(self, fake):
        conn, repo = fake
        config = loop.RunnerConfig(d4_every=timedelta(minutes=10), d6_every=timedelta(minutes=10))
        progress = loop.Progress()
        index = loop.LineIndex([])

        loop.tick(conn, [], NOW, progress, config=config, cable_index=index)
        first_since = repo.since.get("ships")
        assert first_since is not None

        del repo.since["ships"]
        loop.tick(conn, [], NOW + timedelta(minutes=5), progress, config=config, cable_index=index)
        assert "ships" not in repo.since                  # D4/D6 nie odpytaly bazy przed uplywem odstepu

        loop.tick(conn, [], NOW + timedelta(minutes=11), progress, config=config, cable_index=index)
        assert "ships" in repo.since

    def test_no_cable_index_disables_d6_without_failing_the_tick(self, fake):
        conn, repo = fake
        progress = loop.Progress()
        loop.tick(conn, [], NOW, progress, cable_index=None)
        assert progress.last_d6_run is None
