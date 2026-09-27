"""Collects one hour of ADS-B positions straight from adsb.lol into the D3 fixture format.

Normally the fixture is exported from the database (eval/export_d3_fixture.py), but that needs the
ingestion service running. This script is the standalone version used before the stack exists:
same polling interval, same AOI, same fields.

  python eval/feasibility/collect_hour.py [minuty]
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

AOI = {
    "baltic-south": "https://api.adsb.lol/v2/point/55.0/20.0/250",
    "baltic-north": "https://api.adsb.lol/v2/point/60.0/24.0/250",
}
INTERVAL_SECONDS = 30      # zmierzone: 3 zrodla naraz co 15 s dostaja HTTP 429
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "d3_hour.json"
HEADERS = {"User-Agent": "wachta-fixture-collector/0.1 (non-commercial portfolio project)"}


def collect(minutes: float) -> None:
    started = datetime.now(timezone.utc)
    deadline = time.time() + minutes * 60
    positions: list[dict] = []
    seen: set[tuple[str, int]] = set()  # (hex, source clock second) — no duplicates from repeated payloads
    polls = errors = 0
    codes: dict = {}

    while time.time() < deadline:
        for url in AOI.values():
            try:
                response = requests.get(url, headers=HEADERS, timeout=30)
                polls += 1
                if response.status_code != 200:
                    errors += 1
                    codes[response.status_code] = codes.get(response.status_code, 0) + 1
                    time.sleep(10)          # rozsun zrodla zamiast strzelac seria
                    continue
                body = response.json()
            except Exception as e:
                errors += 1
                codes[type(e).__name__] = codes.get(type(e).__name__, 0) + 1
                continue
            time.sleep(10)                  # odstep miedzy obszarami w tej samej rundzie

            source_now = int(body.get("now", 0)) // 1000
            for a in body.get("ac", []):
                if "lat" not in a or "lon" not in a or "hex" not in a:
                    continue
                key = (a["hex"], source_now - int(a.get("seen_pos", 0)))
                if key in seen:
                    continue
                seen.add(key)
                alt = a.get("alt_baro")
                positions.append({
                    "hex": a["hex"],
                    "lat": a["lat"],
                    "lon": a["lon"],
                    "alt_ft": alt if isinstance(alt, (int, float)) else None,
                    "on_ground": alt == "ground",
                    "nac_p": a.get("nac_p"),
                })
        print(f"{datetime.now(timezone.utc):%H:%M:%S}  pozycji: {len(positions)}  odpytan: {polls}  bledow: {errors} {codes}", flush=True)
        time.sleep(INTERVAL_SECONDS)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "hour": started.replace(minute=0, second=0, microsecond=0).isoformat(),
        "collected_from": started.isoformat(),
        "collected_to": datetime.now(timezone.utc).isoformat(),
        "source": "adsb.lol /v2/point (ODbL)",
        "aoi": list(AOI),
        "positions": positions,
    }), encoding="utf-8")
    print(f"zapisano {len(positions)} pozycji do {OUT}")


if __name__ == "__main__":
    collect(float(sys.argv[1]) if len(sys.argv) > 1 else 60.0)
