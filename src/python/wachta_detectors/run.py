"""Detector loop: D1 every minute, D3 (current hour) every 10 minutes, coverage for the previous hour once per hour."""
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from wachta_detectors import repository as repo
from wachta_detectors.airports import load_airports
from wachta_detectors.coverage import COVERAGE_RESOLUTION, count_reports
from wachta_detectors.dark import find_dark_candidates, silent_aircraft, snapshot_inputs
from wachta_detectors.jamming import aggregate_jamming

log = logging.getLogger("wachta.detectors")
TICK_SECONDS = 60


def run_d1(conn, airports, now):
    last_seen = repo.last_seen_since(conn, now - timedelta(minutes=35))
    coverage = repo.coverage_last_days(conn)
    alive = repo.alive_cells(conn, now - timedelta(minutes=2))
    candidates = find_dark_candidates(last_seen, coverage, alive, airports, now)
    alerted = {c.hex for c in candidates}

    # Freeze inputs for every silent aircraft, alerted or not — this is what recall is measured on.
    samples = [(s.hex, now, s.hex in alerted, snapshot_inputs(s, coverage, alive, airports, now))
               for s in silent_aircraft(last_seen, now)]
    repo.insert_d1_samples(conn, samples)
    log.info("D1: %d aircraft checked, %d silent, %d new alerts",
             len(last_seen), len(samples), repo.insert_alerts(conn, "D1", candidates))


def hour_of(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def run_d3(conn, now, max_catchup_hours=48):
    """Finalise every closed hour we have not computed yet, then refresh the current (partial) hour."""
    current = hour_of(now)
    last_done = repo.last_jamming_hour(conn)
    hour = max(last_done, current - timedelta(hours=max_catchup_hours)) if last_done else current
    finalised = 0
    while hour < current:
        repo.replace_jamming(conn, hour, aggregate_jamming(repo.positions_between(conn, hour, hour + timedelta(hours=1))))
        hour += timedelta(hours=1)
        finalised += 1
    cells = aggregate_jamming(repo.positions_between(conn, current, now))
    repo.replace_jamming(conn, current, cells)
    log.info("D3: %d closed hours recomputed, current hour %d cells, %d high",
             finalised, len(cells), sum(c.level == "high" for c in cells))


def run_coverage(conn, now, max_catchup_hours=48):
    current = hour_of(now)
    last_done = repo.last_coverage_hour(conn)
    hour = (last_done + timedelta(hours=1)) if last_done else current - timedelta(hours=1)
    hour = max(hour, current - timedelta(hours=max_catchup_hours))
    while hour < current:
        repo.upsert_coverage(conn, hour, count_reports(repo.positions_between(conn, hour, hour + timedelta(hours=1))))
        log.info("coverage: hour %s done", hour)
        hour += timedelta(hours=1)


def tick(conn, airports, now, last_d3):
    run_d1(conn, airports, now)
    run_coverage(conn, now)
    if last_d3 is None or now - last_d3 >= timedelta(minutes=10):
        run_d3(conn, now)
        return now
    return last_d3


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    airports = load_airports(Path(os.environ.get("AIRPORTS_CSV", "data/airports.csv")))
    last_d3 = None
    while True:
        now = datetime.now(timezone.utc)
        try:
            # New connection each tick: a database restart must not silently kill the detectors forever.
            with psycopg.connect(os.environ["WACHTA_DB"], autocommit=True, connect_timeout=10) as conn:
                last_d3 = tick(conn, airports, now, last_d3)
        except psycopg.Error:
            log.exception("detector tick failed, retrying next tick")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
