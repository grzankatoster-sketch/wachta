"""Applies the real C# migration scripts to a TimescaleDB container and exercises the repository."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from wachta_detectors import repository as repo
from wachta_detectors.dark import DarkCandidate
from wachta_detectors.jamming import JammingCell

pytestmark = pytest.mark.integration
SCRIPTS = Path(__file__).resolve().parents[3] / "dotnet" / "Wachta.Db" / "Scripts"


@pytest.fixture(scope="module")
def conn():
    with PostgresContainer("timescale/timescaledb-ha:pg17", username="postgres", password="postgres", dbname="wachta") as pg:
        url = pg.get_connection_url(driver=None)
        with psycopg.connect(url, autocommit=True) as c:
            for script in sorted(SCRIPTS.glob("*.sql")):
                c.execute(script.read_text(encoding="utf-8"))
            yield c


def insert(conn, hex_, minutes_ago, lat=55.5, lon=17.5, nac_p=9, mil=True):
    conn.execute(
        """INSERT INTO aircraft_position (ts, hex, flight, type_code, is_military, lat, lon, alt_baro_ft, on_ground,
           gs_kt, track_deg, nic, nac_p, source_id, fetched_at)
           VALUES (now() - make_interval(mins => %s), %s, 'F1', 'P8', %s, %s, %s, 30000, false, 300, 90, 8, %s, 'adsblol-mil', now())""",
        (minutes_ago, hex_, mil, lat, lon, nac_p),
    )


def test_last_seen_returns_latest_point_count_and_contact(conn):
    for m in (20, 15, 10):
        insert(conn, "rep001", m)
    now = datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO aircraft_contact (hex, last_message_at, last_position_at, source_id, updated_at)
           VALUES ('rep001', %s, %s, 'adsblol-mil', %s)
           ON CONFLICT (hex) DO UPDATE SET last_message_at = EXCLUDED.last_message_at""",
        (now - timedelta(seconds=30), now - timedelta(minutes=10), now),
    )
    [s] = [x for x in repo.last_seen_since(conn, now - timedelta(minutes=30)) if x.hex == "rep001"]
    assert s.n_points == 3
    assert timedelta(minutes=9) < now - s.ts < timedelta(minutes=11)
    assert now - s.last_message_at < timedelta(minutes=1)  # still transmitting -> D1 must not fire


def test_positions_between_and_alive_cells(conn):
    insert(conn, "rep002", 1)
    now = datetime.now(timezone.utc)
    assert any(p.hex == "rep002" for p in repo.positions_between(conn, now - timedelta(minutes=5), now))
    assert repo.alive_cells(conn, now - timedelta(minutes=2), 5)


def test_replace_jamming_overwrites_and_drops_stale_cells(conn):
    hour = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    repo.replace_jamming(conn, hour, [JammingCell("841f053ffffffff", 10, 3), JammingCell("841f05bffffffff", 8, 0)])
    repo.replace_jamming(conn, hour, [JammingCell("841f053ffffffff", 12, 4)])
    rows = conn.execute("SELECT h3, n_aircraft FROM jamming_cell WHERE hour=%s", (hour,)).fetchall()
    assert rows == [("841f053ffffffff", 12)]
    assert repo.last_jamming_hour(conn) >= hour
    repo.upsert_coverage(conn, hour, {"851f0533fffffff": 5})
    repo.upsert_coverage(conn, hour, {"851f0533fffffff": 7})
    assert conn.execute("SELECT n_reports FROM coverage_hourly WHERE hour=%s", (hour,)).fetchone()[0] == 7


def test_insert_alerts_skips_duplicates(conn):
    c = DarkCandidate("rep003", 55.5, 17.5, datetime(2026, 9, 22, 11, 50, tzinfo=timezone.utc), 0.9, {"note": "x"})
    assert repo.insert_alerts(conn, "D1", [c]) == 1
    assert repo.insert_alerts(conn, "D1", [c]) == 0


def test_insert_alert_rows_is_the_shared_write_behind_d1_and_the_maritime_detectors(conn):
    # D1 gets there through insert_alerts(); D4/D6 write here directly (different dataclasses, same table).
    rows = [("D6", "mmsi-anchor-1", datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc), 59.9, 25.0, 0.7, {"line": "x"})]
    assert repo.insert_alert_rows(conn, rows) == 1
    assert repo.insert_alert_rows(conn, rows) == 0   # sama para (detector, entity_id, started_at) -> duplikat
    row = conn.execute("SELECT detector, entity_id, score FROM alert WHERE entity_id = 'mmsi-anchor-1'").fetchone()
    assert row == ("D6", "mmsi-anchor-1", 0.7)


def test_ship_positions_are_written_with_provenance_and_read_back_as_shipfix(conn):
    ts = datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc)
    fetched_at = datetime(2026, 9, 27, 8, 0, 5, tzinfo=timezone.utc)
    ships = [
        {"mmsi": "230123456", "ts": ts, "lat": 60.15, "lon": 24.95, "sog": 8.2, "cog": 91.0,
         "name": "TESTOWIEC", "imo": "9123456", "ship_type": "70", "nav_status": "0"},
        {"mmsi": "230999999", "ts": ts, "lat": 60.20, "lon": 24.99, "sog": None, "cog": None},
    ]
    n = repo.insert_ship_positions(conn, "digitraffic-ais", ships, fetched_at)
    assert n == 2

    fixes = repo.recent_ship_fixes(conn, ts - timedelta(minutes=1))
    by_mmsi = {f.mmsi: f for f in fixes if f.mmsi in ("230123456", "230999999")}
    assert by_mmsi["230123456"].name == "TESTOWIEC"
    assert by_mmsi["230123456"].sog == 8.2
    assert by_mmsi["230999999"].sog is None    # brakujaca predkosc nie ma stac sie zerem

    source_id = conn.execute(
        "SELECT source_id FROM ship_position WHERE mmsi = '230123456'"
    ).fetchone()[0]
    assert source_id == "digitraffic-ais"


def test_recent_ship_fixes_excludes_positions_before_since(conn):
    old = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
    new = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    repo.insert_ship_positions(conn, "digitraffic-ais",
                               [{"mmsi": "230111222", "ts": old, "lat": 60.0, "lon": 25.0}], old)
    repo.insert_ship_positions(conn, "digitraffic-ais",
                               [{"mmsi": "230111222", "ts": new, "lat": 60.0, "lon": 25.0}], new)
    fixes = repo.recent_ship_fixes(conn, new - timedelta(minutes=1))
    assert [f.ts for f in fixes if f.mmsi == "230111222"] == [new]
