"""Collects AIS tracks from Digitraffic: repeated reads joined into per-ship tracks.

One snapshot says where ships are; the D6 detector needs how they moved. This is the standalone
version of what the ingestion service will do once the stack runs.

  python eval/feasibility/collect_ships.py [minuty] [odstep_sekund]
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "ship_tracks.json"
HEADERS = {
    "User-Agent": "wachta-fixture-collector/0.1 (non-commercial portfolio project)",
    "Digitraffic-User": "wachta/lab",
    "Accept-Encoding": "gzip",
}
LOCATIONS = "https://meri.digitraffic.fi/api/ais/v1/locations"
VESSELS = "https://meri.digitraffic.fi/api/ais/v1/vessels"


def collect(minutes: float, interval: int) -> None:
    started = datetime.now(timezone.utc)
    deadline = time.time() + minutes * 60
    fixes: dict[str, list[dict]] = {}
    seen: set[tuple[str, int]] = set()
    polls = errors = 0

    names: dict[int, dict] = {}
    try:
        names = {v["mmsi"]: v for v in requests.get(VESSELS, headers=HEADERS, timeout=120).json()}
        print(f"metadane: {len(names)} statkow")
    except Exception as e:
        print("metadane niedostepne:", type(e).__name__)

    while time.time() < deadline:
        try:
            features = requests.get(LOCATIONS, headers=HEADERS, timeout=120).json()["features"]
            polls += 1
        except Exception as e:
            errors += 1
            print(f"  blad {type(e).__name__}", flush=True)
            time.sleep(interval)
            continue

        for f in features:
            props, (lon, lat) = f["properties"], f["geometry"]["coordinates"]
            mmsi = str(props["mmsi"])
            stamp = int(props.get("timestampExternal", 0)) // 1000
            if not stamp or (mmsi, stamp) in seen:
                continue
            seen.add((mmsi, stamp))
            fixes.setdefault(mmsi, []).append({
                "ts": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                "lat": lat, "lon": lon,
                "sog": props.get("sog"), "cog": props.get("cog"),
                "nav_status": props.get("navStat"),
            })

        tracked = sum(1 for v in fixes.values() if len(v) >= 5)
        print(f"{datetime.now(timezone.utc):%H:%M:%S}  statkow: {len(fixes)}  z trasa >=5 punktow: {tracked}  "
              f"pozycji: {len(seen)}  odpytan: {polls}  bledow: {errors}", flush=True)
        time.sleep(interval)

    tracks = []
    for mmsi, points in fixes.items():
        meta = names.get(int(mmsi), {})
        tracks.append({
            "mmsi": mmsi,
            "imo": meta.get("imo") or None,
            "name": (meta.get("name") or "").strip() or None,
            "ship_type": meta.get("shipType"),
            "fixes": sorted(points, key=lambda p: p["ts"]),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "collected_from": started.isoformat(),
        "collected_to": datetime.now(timezone.utc).isoformat(),
        "source": "Digitraffic (Fintraffic), otwarte dane",
        "interval_seconds": interval,
        "tracks": tracks,
    }), encoding="utf-8")
    long_tracks = sum(1 for t in tracks if len(t["fixes"]) >= 5)
    print(f"zapisano {len(tracks)} tras ({long_tracks} z co najmniej 5 punktami) do {OUT}")


if __name__ == "__main__":
    collect(float(sys.argv[1]) if len(sys.argv) > 1 else 50.0,
            int(sys.argv[2]) if len(sys.argv) > 2 else 120)
