"""One read of AIS from Digitraffic (Fintraffic), joined with vessel metadata.

No key needed. Coverage is Finnish waters only (measured 2026-09-22: nothing south of 57.7N), so the
southern Baltic will need AISStream once the key is in place — this is the part of the maritime layer
that can be built today.

  python eval/feasibility/fetch_ships.py
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "ships_snapshot.json"
HEADERS = {
    "User-Agent": "wachta-demo/0.1 (non-commercial portfolio project)",
    "Digitraffic-User": "wachta/demo",
    "Accept-Encoding": "gzip",
}
LOCATIONS = "https://meri.digitraffic.fi/api/ais/v1/locations"
VESSELS = "https://meri.digitraffic.fi/api/ais/v1/vessels"

# AIS ship types: 80-89 tankers, 70-79 cargo, 60-69 passenger, 30-39 fishing/tug/sailing.
def ship_class(ship_type: int | None) -> str:
    if ship_type is None:
        return "inne"
    if 80 <= ship_type <= 89:
        return "tankowiec"
    if 70 <= ship_type <= 79:
        return "towarowy"
    if 60 <= ship_type <= 69:
        return "pasazerski"
    return "inne"


# AIS navigational status: 1 at anchor, 2 not under command, 5 moored, 6 aground.
NAV_STATUS = {0: "w drodze", 1: "na kotwicy", 2: "bez sterownosci", 3: "ograniczona zwrotnosc",
              5: "przy nabrzezu", 6: "na mieliznie", 8: "pod zaglami", 15: "nieokreslony"}


def main() -> int:
    print("pobieram pozycje statkow")
    locations = requests.get(LOCATIONS, headers=HEADERS, timeout=120).json()["features"]
    time.sleep(3)
    print("pobieram metadane statkow")
    vessels = {v["mmsi"]: v for v in requests.get(VESSELS, headers=HEADERS, timeout=120).json()}

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    ships = []
    for f in locations:
        props, (lon, lat) = f["properties"], f["geometry"]["coordinates"]
        mmsi = props["mmsi"]
        meta = vessels.get(mmsi, {})
        age_min = (now_ms - props.get("timestampExternal", now_ms)) / 60000
        if age_min > 30:  # stale position, do not draw it as if it were current
            continue
        ships.append({
            "mmsi": mmsi,
            "imo": meta.get("imo") or None,
            "name": (meta.get("name") or "").strip() or None,
            "class": ship_class(meta.get("shipType")),
            "ship_type": meta.get("shipType"),
            "destination": (meta.get("destination") or "").strip() or None,
            "eta": meta.get("eta"),
            "callsign": (meta.get("callSign") or "").strip() or None,
            # Digitraffic podaje zanurzenie w decymetrach (90 = 9,0 m) - przeliczamy od razu,
            # bo "90 m" w dymku na mapie wyglada jak awaria, a nie jak dane.
            "draught_m": round(meta["draught"] / 10, 1) if isinstance(meta.get("draught"), (int, float)) and meta["draught"] else None,
            "lat": lat,
            "lon": lon,
            "sog": props.get("sog"),
            "cog": props.get("cog"),
            "nav_status": NAV_STATUS.get(props.get("navStat"), str(props.get("navStat"))),
            "age_min": round(age_min, 1),
        })

    by_class: dict[str, int] = {}
    for s in ships:
        by_class[s["class"]] = by_class.get(s["class"], 0) + 1
    lats = [s["lat"] for s in ships]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Digitraffic (Fintraffic), otwarte dane",
        "ships": ships,
    }), encoding="utf-8")

    print(f"statkow: {len(ships)} | {by_class}")
    print(f"zakres szerokosci: {min(lats):.1f}N - {max(lats):.1f}N" if lats else "brak pozycji")
    print(f"z numerem IMO: {sum(1 for s in ships if s['imo'])} | zapisano do {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
