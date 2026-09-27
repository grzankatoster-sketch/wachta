"""Exports one hour of positions from the database as the frozen D3 fixture."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

hour = datetime.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else (
    datetime.now(timezone.utc) - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
with psycopg.connect(os.environ["WACHTA_DB"]) as conn:
    rows = conn.execute(
        """SELECT hex, lat, lon, alt_baro_ft, on_ground, nac_p FROM aircraft_position
           WHERE ts >= %s AND ts < %s AND nac_p IS NOT NULL""",
        (hour, hour + timedelta(hours=1)),
    ).fetchall()

out = Path(__file__).parent / "fixtures" / "d3_hour.json"
out.write_text(json.dumps({"hour": hour.isoformat(), "positions": [
    {"hex": h, "lat": la, "lon": lo, "alt_ft": alt, "on_ground": g, "nac_p": n} for h, la, lo, alt, g, n in rows
]}), encoding="utf-8")
print(f"{len(rows)} positions from {hour:%Y-%m-%d %H:00} -> {out}")
