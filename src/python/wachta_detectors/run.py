"""Detector loop: D1 every tick, D3 on its own interval, coverage for every closed hour.

The schedule and the slack live in RunnerConfig instead of in literals spread through the functions.
The one number here that is not a scheduling choice - how far back D1 reads - is derived from D1's
own rules, so widening max_gap widens the query with it.
"""
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from wachta_detectors import repository as repo
from wachta_detectors.airports import load_airports
from wachta_detectors.coverage import count_reports
from wachta_detectors.dark import DarkRules, find_dark_candidates, silent_aircraft, snapshot_inputs
from wachta_detectors.jamming import aggregate_jamming

log = logging.getLogger("wachta.detectors")
MAX_CATCHUP_HOURS = 48


@dataclass(frozen=True)
class RunnerConfig:
    """How often the loop runs and how much slack it gives itself - nothing about what counts as a find.

    Thresholds belong to the detectors and the schedule belongs here; the two must not be confused.
    The one place they meet is the data window, and it is derived (see d1_window) rather than typed
    in. A window written out by hand stops matching the rules the moment someone widens max_gap, and
    then the detector is looking for silences the query never hands it.
    """
    tick: timedelta = timedelta(seconds=60)
    d3_every: timedelta = timedelta(minutes=10)
    receiver_fresh: timedelta = timedelta(minutes=2)   # jak swiezy ma byc odbior, zeby uznac go za zywy
    fetch_margin: timedelta = timedelta(minutes=5)     # zapas na opoznienie zapisu i dlugosc cyklu
    # Pierwsze uruchomienie z pustym magazynem: zakres jawny, zeby start nie zalezal od tego, co
    # akurat jest w bazie. Bez tego pierwszy przebieg liczyl wylacznie biezaca (niepelna) godzine.
    d3_first_run_hours: int = 3
    coverage_first_run_hours: int = 1
    max_catchup_hours: int = MAX_CATCHUP_HOURS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RunnerConfig":
        """Schedule read from the environment, so a deployment can slow the loop without a rebuild."""
        env = os.environ if env is None else env
        pola = cls()

        def minuty(nazwa: str, domyslne: timedelta) -> timedelta:
            return timedelta(minutes=float(env[nazwa])) if nazwa in env else domyslne

        tick = timedelta(seconds=float(env["WACHTA_TICK_SECONDS"])) if "WACHTA_TICK_SECONDS" in env else pola.tick
        return cls(
            tick=tick,
            d3_every=minuty("WACHTA_D3_EVERY_MINUTES", pola.d3_every),
            receiver_fresh=minuty("WACHTA_RECEIVER_FRESH_MINUTES", pola.receiver_fresh),
            fetch_margin=minuty("WACHTA_FETCH_MARGIN_MINUTES", pola.fetch_margin),
            max_catchup_hours=int(env.get("WACHTA_MAX_CATCHUP_HOURS", pola.max_catchup_hours)),
        )


def d1_window(rules: DarkRules = DarkRules(), config: RunnerConfig = RunnerConfig()) -> timedelta:
    """How far back D1 has to read, taken from D1's own rules.

    Anything quiet for longer than max_gap is out of scope by definition, so that is the horizon; the
    margin covers the tick itself and the lag between a message arriving and being stored.
    """
    return rules.max_gap + config.fetch_margin


@dataclass
class Progress:
    """What the loop has already finished - deliberately kept apart from what it has written.

    Results are not a progress marker: an hour with no traffic writes no rows, so a max(hour) taken
    from the results never moves past it.
    """
    last_d3_run: datetime | None = None
    d3_done_through: datetime | None = None
    coverage_done_through: datetime | None = None


def run_d1(conn, airports, now, rules: DarkRules = DarkRules(), config: RunnerConfig = RunnerConfig()):
    last_seen = repo.last_seen_since(conn, now - d1_window(rules, config))
    coverage = repo.coverage_last_days(conn)
    alive = repo.alive_cells(conn, now - config.receiver_fresh)
    candidates = find_dark_candidates(last_seen, coverage, alive, airports, now, rules)
    alerted = {c.hex for c in candidates}

    # Freeze inputs for every silent aircraft, alerted or not — this is what recall is measured on.
    samples = [(s.hex, now, s.hex in alerted, snapshot_inputs(s, coverage, alive, airports, now, rules))
               for s in silent_aircraft(last_seen, now, rules)]
    # Jedna transakcja: probka mowi "alerted=True", wiec alert bez swojej probki (albo probka bez
    # swojego alertu) to niespojny material do pomiaru recall, a nie brakujacy wiersz.
    with conn.transaction():
        repo.insert_d1_samples(conn, samples)
        n_alerts = repo.insert_alerts(conn, "D1", candidates)
    log.info("D1: %d aircraft checked, %d silent, %d new alerts", len(last_seen), len(samples), n_alerts)


def hour_of(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def hours_to_finalise(current, done_through, stored_hour, first_run_hours, max_catchup_hours=MAX_CATCHUP_HOURS):
    """Closed hours still waiting to be computed, oldest first.

    done_through is the loop's own marker and advances over hours that produced nothing, which the
    stored results cannot do. stored_hour only seeds that marker after a restart, and is recomputed
    rather than skipped, because the newest stored hour may have been written while it was still
    partial. With neither, the first run covers an explicit window instead of nothing at all.
    """
    if done_through is not None:
        start = done_through + timedelta(hours=1)
    elif stored_hour is not None:
        start = stored_hour
    else:
        start = current - timedelta(hours=first_run_hours)
    start = max(start, current - timedelta(hours=max_catchup_hours))
    hours = []
    while start < current:
        hours.append(start)
        start += timedelta(hours=1)
    return hours


def run_d3(conn, now, progress, config: RunnerConfig = RunnerConfig()):
    """Finalise every closed hour we have not computed yet, then refresh the current (partial) hour."""
    current = hour_of(now)
    stored = repo.last_jamming_hour(conn) if progress.d3_done_through is None else None
    hours = hours_to_finalise(current, progress.d3_done_through, stored,
                              config.d3_first_run_hours, config.max_catchup_hours)
    for hour in hours:
        repo.replace_jamming(conn, hour, aggregate_jamming(repo.positions_between(conn, hour, hour + timedelta(hours=1))))
        # Znacznik po kazdej godzinie: przerwane nadrabianie nie zaczyna nastepnym razem od zera.
        progress.d3_done_through = hour
    cells = aggregate_jamming(repo.positions_between(conn, current, now))
    repo.replace_jamming(conn, current, cells)
    log.info("D3: %d closed hours recomputed, current hour %d cells, %d high",
             len(hours), len(cells), sum(c.level == "high" for c in cells))


def run_coverage(conn, now, progress, config: RunnerConfig = RunnerConfig()):
    current = hour_of(now)
    # Ten sam problem co w D3: upsert_coverage nic nie zapisuje dla pustej godziny, wiec max(hour)
    # z wynikow nigdy jej nie minie. Roznica wobec D3: pokrycie liczymy wylacznie dla godzin
    # zamknietych, wiec ostatnia zapisana godzina jest kompletna i nie ma jej po co przeliczac - stad
    # przesuniecie o godzine przed podaniem jej jako punktu startowego.
    stored = repo.last_coverage_hour(conn) if progress.coverage_done_through is None else None
    stored = stored + timedelta(hours=1) if stored is not None else None
    hours = hours_to_finalise(current, progress.coverage_done_through, stored,
                              config.coverage_first_run_hours, config.max_catchup_hours)
    for hour in hours:
        repo.upsert_coverage(conn, hour, count_reports(repo.positions_between(conn, hour, hour + timedelta(hours=1))))
        log.info("coverage: hour %s done", hour)
        progress.coverage_done_through = hour


def _guarded(name, detector, *args):
    """Run one detector and report whether it got through.

    A bad row in D1 must cost D1 this tick, not D3 and coverage as well. KeyboardInterrupt and
    SystemExit are BaseException, so they are not caught here and the process stays stoppable.
    """
    try:
        detector(*args)
        return True
    except Exception:
        log.exception("%s failed, skipping until the next tick", name)
        return False


def tick(conn, airports, now, progress, rules: DarkRules = DarkRules(), config: RunnerConfig = RunnerConfig()):
    _guarded("D1", run_d1, conn, airports, now, rules, config)
    _guarded("coverage", run_coverage, conn, now, progress, config)
    if progress.last_d3_run is None or now - progress.last_d3_run >= config.d3_every:
        # Znacznik przebiegu przesuwamy tylko po udanym D3, zeby awaria nie kasowala kolejnej proby.
        if _guarded("D3", run_d3, conn, now, progress, config):
            progress.last_d3_run = now


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    airports = load_airports(Path(os.environ.get("AIRPORTS_CSV", "data/airports.csv")))
    config = RunnerConfig.from_env()
    rules = DarkRules()
    log.info("runner: tick %ss, D3 co %s, okno danych D1 %s",
             config.tick.total_seconds(), config.d3_every, d1_window(rules, config))
    progress = Progress()
    while True:
        now = datetime.now(timezone.utc)
        try:
            # New connection each tick: a database restart must not silently kill the detectors forever.
            with psycopg.connect(os.environ["WACHTA_DB"], autocommit=True, connect_timeout=10) as conn:
                tick(conn, airports, now, progress, rules, config)
        except Exception:
            # Nie tylko psycopg.Error: blad danych albo geometrii ma kosztowac jeden cykl, nie caly
            # proces. KeyboardInterrupt i SystemExit to BaseException, wiec nadal zatrzymuja petle.
            log.exception("detector tick failed, retrying next tick")
        time.sleep(config.tick.total_seconds())


if __name__ == "__main__":
    main()
