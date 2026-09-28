import json
from datetime import datetime

import h3
import psycopg

from wachta_detectors.anchor import ShipFix
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


def insert_alert_rows(
    conn: psycopg.Connection,
    rows: list[tuple[str, str, datetime, float, float, float, dict]],
) -> int:
    """Generic alert write - (detector, entity_id, started_at, lat, lon, score, evidence) per row.

    D1 candidates and D4/D6 candidates share nothing but this shape (DarkCandidate keys off `hex`,
    GapAlert and AnchorAlert off `mmsi`), so the shared write lives here instead of being duplicated
    per detector, or forcing every detector's dataclass to use the same field names.
    """
    inserted = 0
    for detector, entity_id, started_at, lat, lon, score, evidence in rows:
        cur = conn.execute(
            """INSERT INTO alert (detector, entity_id, started_at, lat, lon, score, evidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (detector, entity_id, started_at, lat, lon, score, json.dumps(evidence)),
        )
        inserted += cur.rowcount
    return inserted


def insert_alerts(conn: psycopg.Connection, detector: str, candidates: list[DarkCandidate]) -> int:
    return insert_alert_rows(
        conn,
        [(detector, c.hex, c.last_seen, c.lat, c.lon, c.score, c.evidence) for c in candidates],
    )


# --- Warstwa morska (AIS) ---------------------------------------------------
# Digitraffic to jedno zrodlo dzis, ale kolumny mowia o kazdym: source_id i fetched_at licza sie tak
# samo, jak przy samolotach - bez tego drugie zrodlo (AISStream) nie dalo by sie odroznic od pierwszego.

def insert_ship_positions(
    conn: psycopg.Connection,
    source_id: str,
    ships: list[dict],
    fetched_at: datetime,
) -> int:
    """Write one AIS snapshot with provenance - mirrors how aircraft positions are ingested."""
    if not ships:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO ship_position
               (ts, mmsi, name, imo, ship_type, nav_status, lat, lon, sog_kt, cog_deg, source_id, fetched_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(
                s["ts"], s["mmsi"], s.get("name"), s.get("imo"), s.get("ship_type"), s.get("nav_status"),
                s["lat"], s["lon"], s.get("sog"), s.get("cog"), source_id, fetched_at,
            ) for s in ships],
        )
    return len(ships)


def recent_ship_fixes(conn: psycopg.Connection, since: datetime) -> list[ShipFix]:
    """Ship positions since `since`, as ShipFix - the one shape both D4 and D6 consume."""
    rows = conn.execute(
        "SELECT mmsi, ts, lat, lon, sog_kt, cog_deg, name FROM ship_position WHERE ts >= %s",
        (since,),
    ).fetchall()
    return [ShipFix(mmsi=r[0], ts=r[1], lat=r[2], lon=r[3], sog=r[4], cog=r[5], name=r[6]) for r in rows]


# --- Odczyt dla serwera MCP -------------------------------------------------
# Model pyta o stan biezacy, nie o przeliczanie detektorow, wiec te funkcje tylko czytaja i zawsze
# dostaja limit z gory. Limit jedzie jako parametr zapytania, a nie w sklejonym napisie - inaczej
# argument od modelu trafialby do SQL-a jako tekst do wykonania.

LIVE_AIRCRAFT_COLUMNS = ("hex", "flight", "type_code", "is_military", "lat", "lon",
                         "alt_baro_ft", "gs_kt", "track_deg", "nac_p", "ts")
JAMMING_COLUMNS = ("hour", "h3", "n_aircraft", "n_degraded")
ALERT_COLUMNS = ("detector", "entity_id", "started_at", "lat", "lon", "score", "state",
                 "created_at", "evidence")
TRACK_COLUMNS = ("ts", "lat", "lon", "alt_baro_ft", "gs_kt", "track_deg", "nac_p", "on_ground")


def _dicts(rows, columns: tuple[str, ...]) -> list[dict]:
    return [dict(zip(columns, row)) for row in rows]


def live_aircraft(conn: psycopg.Connection, since: datetime, limit: int) -> list[dict]:
    """Newest position of each aircraft heard since `since`, freshest first."""
    rows = conn.execute(
        """
        SELECT hex, flight, type_code, is_military, lat, lon, alt_baro_ft, gs_kt, track_deg, nac_p, ts
        FROM (
            SELECT DISTINCT ON (hex) hex, flight, type_code, is_military, lat, lon, alt_baro_ft,
                   gs_kt, track_deg, nac_p, ts
            FROM aircraft_position
            WHERE ts >= %s
            ORDER BY hex, ts DESC
        ) ostatnie
        ORDER BY ts DESC
        LIMIT %s
        """,
        (since, limit),
    ).fetchall()
    return _dicts(rows, LIVE_AIRCRAFT_COLUMNS)


def position_window(conn: psycopg.Connection, since: datetime) -> dict:
    """How much data the window actually holds and how old it is - the answer must say so itself.

    A stack started ten minutes ago looks exactly like a quiet sky. Counting separately from the
    limited listing is what lets the answer say "3 rows shown out of 812" rather than implying 3.
    """
    row = conn.execute(
        """SELECT count(DISTINCT hex), count(*), min(ts), max(ts)
           FROM aircraft_position WHERE ts >= %s""",
        (since,),
    ).fetchone()
    return dict(zip(("n_aircraft", "n_positions", "oldest", "newest"), row))


def jamming_cells_since(conn: psycopg.Connection, since: datetime, limit: int) -> list[dict]:
    """GPS interference cells computed for the hours from `since` on, worst share first."""
    rows = conn.execute(
        """SELECT hour, h3, n_aircraft, n_degraded FROM jamming_cell
           WHERE hour >= %s
           ORDER BY n_degraded::float / NULLIF(n_aircraft, 0) DESC NULLS LAST, hour DESC
           LIMIT %s""",
        (since, limit),
    ).fetchall()
    return _dicts(rows, JAMMING_COLUMNS)


def jamming_window(conn: psycopg.Connection, since: datetime) -> dict:
    row = conn.execute(
        """SELECT count(*), min(hour), max(hour) FROM jamming_cell WHERE hour >= %s""",
        (since,),
    ).fetchone()
    return dict(zip(("n_cells", "oldest", "newest"), row))


def recent_alerts(conn: psycopg.Connection, since: datetime, limit: int,
                  detector: str | None = None) -> list[dict]:
    """Detector alerts raised since `since`, newest first; `detector` None means all of them.

    The optional filter is still a bound parameter - `%s IS NULL` inside the WHERE clause instead of
    a clause assembled in Python, so no caller can shape the statement by choosing a detector name.
    """
    rows = conn.execute(
        """SELECT detector, entity_id, started_at, lat, lon, score, state, created_at, evidence
           FROM alert
           WHERE created_at >= %s AND (%s::text IS NULL OR detector = %s::text)
           ORDER BY created_at DESC
           LIMIT %s""",
        (since, detector, detector, limit),
    ).fetchall()
    return _dicts(rows, ALERT_COLUMNS)


def alert_window(conn: psycopg.Connection, since: datetime, detector: str | None = None) -> dict:
    row = conn.execute(
        """SELECT count(*), min(created_at), max(created_at) FROM alert
           WHERE created_at >= %s AND (%s::text IS NULL OR detector = %s::text)""",
        (since, detector, detector),
    ).fetchone()
    return dict(zip(("n_alerts", "oldest", "newest"), row))


def aircraft_track(conn: psycopg.Connection, hex_: str, since: datetime, limit: int) -> list[dict]:
    """Track of one aircraft since `since`, newest point first."""
    rows = conn.execute(
        """SELECT ts, lat, lon, alt_baro_ft, gs_kt, track_deg, nac_p, on_ground
           FROM aircraft_position
           WHERE hex = %s AND ts >= %s
           ORDER BY ts DESC
           LIMIT %s""",
        (hex_, since, limit),
    ).fetchall()
    return _dicts(rows, TRACK_COLUMNS)


def aircraft_summary(conn: psycopg.Connection, hex_: str, since: datetime) -> dict:
    row = conn.execute(
        """SELECT count(*), min(ts), max(ts), max(flight), max(type_code), bool_or(is_military)
           FROM aircraft_position WHERE hex = %s AND ts >= %s""",
        (hex_, since),
    ).fetchone()
    return dict(zip(("n_points", "oldest", "newest", "flight", "type_code", "is_military"), row))
