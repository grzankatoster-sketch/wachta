"""Detector loop: what one bad tick may cost, and what counts as progress.

Everything here runs against a fake connection and a fake repository. The loop's job is scheduling
and failure containment, and neither needs a database to be wrong.
"""
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


@pytest.fixture
def fake(monkeypatch):
    conn = FakeConn()
    repo = FakeRepo(conn)
    monkeypatch.setattr(loop, "repo", repo)
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
