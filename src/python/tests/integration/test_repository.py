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
