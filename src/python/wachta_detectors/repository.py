import json
from datetime import datetime

import h3
import psycopg

from wachta_detectors.coverage import COVERAGE_RESOLUTION
from wachta_detectors.dark import DarkCandidate, LastSeen
from wachta_detectors.jamming import JammingCell
from wachta_detectors.models import Position


def positions_between(conn: psycopg.Connection, start: datetime, end: datetime) -> list[Position]:
    rows = conn.execute(
        "SELECT hex, lat, lon, alt_baro_ft, on_ground, nac_p, ts FROM aircraft_position WHERE ts >= %s AND ts < %s",
        (start, end),
    ).fetchall()
    return [Position(*r) for r in rows]


def last_seen_since(conn: psycopg.Connection, since: datetime) -> list[LastSeen]:
    """Last position per aircraft + when it was last heard at all (aircraft_contact)."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (p.hex) p.hex, p.flight, p.type_code, p.is_military, p.lat, p.lon, p.alt_baro_ft, p.gs_kt, p.ts,
               count(*) OVER (PARTITION BY p.hex) AS n_points,
               COALESCE(c.last_message_at, p.ts) AS last_message_at
        FROM aircraft_position p
        LEFT JOIN aircraft_contact c USING (hex)
        WHERE p.ts >= %s
        ORDER BY p.hex, p.ts DESC
        """,
        (since,),
    ).fetchall()
    return [LastSeen(*r) for r in rows]


def alive_cells(conn: psycopg.Connection, since: datetime, resolution: int = COVERAGE_RESOLUTION) -> set[str]:
    rows = conn.execute("SELECT DISTINCT lat, lon FROM aircraft_position WHERE ts >= %s AND NOT on_ground", (since,)).fetchall()
    return {h3.latlng_to_cell(lat, lon, resolution) for lat, lon in rows}


def coverage_last_days(conn: psycopg.Connection, days: int = 7) -> dict[str, int]:
    rows = conn.execute(
        "SELECT h3, sum(n_reports)::int FROM coverage_hourly WHERE hour > now() - make_interval(days => %s) GROUP BY h3",
        (days,),
    ).fetchall()
    return dict(rows)


def replace_jamming(conn: psycopg.Connection, hour: datetime, cells: list[JammingCell]) -> None:
    """Whole hour is recomputed: stale cells must disappear, so delete first, then insert, in one transaction."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM jamming_cell WHERE hour = %s", (hour,))
        if cells:
            cur.executemany(
                "INSERT INTO jamming_cell (hour, h3, n_aircraft, n_degraded) VALUES (%s, %s, %s, %s)",
                [(hour, c.h3, c.n_aircraft, c.n_degraded) for c in cells],
            )


def last_jamming_hour(conn: psycopg.Connection) -> datetime | None:
    return conn.execute("SELECT max(hour) FROM jamming_cell").fetchone()[0]


def last_coverage_hour(conn: psycopg.Connection) -> datetime | None:
    return conn.execute("SELECT max(hour) FROM coverage_hourly").fetchone()[0]


def upsert_coverage(conn: psycopg.Connection, hour: datetime, counts: dict[str, int]) -> None:
    if not counts:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO coverage_hourly (hour, h3, n_reports) VALUES (%s, %s, %s)
               ON CONFLICT (hour, h3) DO UPDATE SET n_reports = EXCLUDED.n_reports""",
            [(hour, cell, n) for cell, n in counts.items()],
        )


def insert_d1_samples(conn: psycopg.Connection, samples: list[tuple[str, datetime, bool, dict]]) -> None:
    if not samples:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO d1_sample (hex, evaluated_at, alerted, inputs) VALUES (%s, %s, %s, %s)
               ON CONFLICT (hex, evaluated_at) DO NOTHING""",
            [(hex_, at, alerted, json.dumps(inputs)) for hex_, at, alerted, inputs in samples],
        )


def insert_alerts(conn: psycopg.Connection, detector: str, candidates: list[DarkCandidate]) -> int:
    inserted = 0
    for c in candidates:
        cur = conn.execute(
            """INSERT INTO alert (detector, entity_id, started_at, lat, lon, score, evidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (detector, c.hex, c.last_seen, c.lat, c.lon, c.score, json.dumps(c.evidence)),
        )
        inserted += cur.rowcount
    return inserted
