"""Downloads full flight tracks of military aircraft and runs D2 over them.

adsb.lol keeps a full track per aircraft for the current UTC day, at the same address pattern
adsbexchange uses. One track is 700-3000 points, so this is the one place in the project where a
single aircraft costs more bytes than a whole hour of the sky - fetched one at a time, on purpose.

  python eval/feasibility/fetch_traces.py [ile_samolotow]
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.racetrack import TracePoint, find_loiters  # noqa: E402

OUT = ROOT / "eval" / "fixtures" / "loiters_snapshot.json"
MIL = "https://api.adsb.lol/v2/mil"
TRACE = "https://globe.adsb.lol/data/traces/{tail}/trace_full_{hex}.json"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}

# Typy ICAO, ktore wozza paliwo. Ksztalt toru nie mowi, po co samolot krazy - dopiero typ pozwala
# napisac "tankowanie" zamiast "dyzur w powietrzu".
# B762 jest tu, bo KC-46A Pegasus zglasza sie typem plaowca (767-2C) - sprawdzone na 17-46037.
# Poza lista wojskowa /v2/mil ten sam typ to zwykly samolot pasazerski, wiec mapowanie dziala
# tylko w tym kontekscie i nigdzie indziej.
TANKERS = {"K35R", "KC135", "R135", "KC46", "K46", "A332", "A310", "A30B", "KC30", "VC10", "B762"}
WATCHERS = {"E3TF", "E3CF", "E6", "P8", "RC35", "E3", "E8", "A319", "CL60", "GLF5", "P3", "ASTR"}


def kind_of(t: str | None) -> str:
    if not t:
        return "nieznany"
    if t.upper() in TANKERS:
        return "tankowiec"
    if t.upper() in WATCHERS:
        return "rozpoznanie"
    return "inny"


def fetch_trace(hex_id: str) -> dict | None:
    url = TRACE.format(tail=hex_id[-2:], hex=hex_id)
    try:
        response = requests.get(url, headers=HEADERS, timeout=90)
    except requests.RequestException as e:
        print(f"    {hex_id}: {type(e).__name__}")
        return None
    if response.status_code != 200:
        return None
    return response.json()


def to_points(trace: dict) -> list[TracePoint]:
    """The trace is a list of rows: seconds since the timestamp, lat, lon, altitude, speed, ..."""
    base = datetime.fromtimestamp(trace["timestamp"], tz=timezone.utc)
    points = []
    for row in trace.get("trace", []):
        alt = row[3] if isinstance(row[3], (int, float)) else None   # "ground" zamiast liczby
        gs = row[4] if len(row) > 4 and isinstance(row[4], (int, float)) else None
        points.append(TracePoint(t=base + timedelta(seconds=row[0]), lat=row[1], lon=row[2],
                                 alt_ft=alt, gs_kt=gs))
    return points


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 60

    print("pobieram liste samolotow wojskowych")
    aircraft = requests.get(MIL, headers=HEADERS, timeout=60).json().get("ac", [])
    print(f"w powietrzu: {len(aircraft)}")

    # Najpierw tankowce i rozpoznanie - to na ich torach detektor ma cos znalezc.
    aircraft.sort(key=lambda a: kind_of(a.get("t")) not in ("tankowiec", "rozpoznanie"))
    aircraft = aircraft[:limit]

    results, checked, no_trace = [], 0, 0
    sprawdzone: dict[str, int] = {}
    ze_wzorcem: dict[str, set] = {}
    for i, ac in enumerate(aircraft, start=1):
        hex_id = (ac.get("hex") or "").strip().lower()
        if not hex_id:
            continue
        trace = fetch_trace(hex_id)
        time.sleep(1.0)
        if not trace:
            no_trace += 1
            continue
        points = to_points(trace)
        checked += 1
        rodzaj = kind_of(ac.get("t"))
        sprawdzone[rodzaj] = sprawdzone.get(rodzaj, 0) + 1
        loiters = find_loiters(points)
        if loiters:
            ze_wzorcem.setdefault(rodzaj, set()).add(hex_id)
        if i % 10 == 0:
            print(f"  {i}/{len(aircraft)}, torow z wzorcem: {len(results)}", flush=True)
        for loiter in loiters:
            results.append({
                "hex": hex_id,
                "callsign": (ac.get("flight") or "").strip() or None,
                "type": ac.get("t"),
                "kind": kind_of(ac.get("t")),
                "registration": trace.get("r"),
                "pattern": loiter.kind,
                "start": loiter.start.isoformat(),
                "end": loiter.end.isoformat(),
                "minutes": round(loiter.duration.total_seconds() / 60),
                "lat": loiter.centre_lat, "lon": loiter.centre_lon,
                "radius_km": loiter.radius_km, "alt_ft": loiter.alt_ft,
                "alt_spread_ft": loiter.alt_spread_ft, "axis_deg": loiter.axis_deg,
                "reversals": loiter.reversals, "longest_leg_km": loiter.longest_leg_km,
                "straight_share": loiter.straight_share, "turn_deg": loiter.turn_deg,
                "trace_points": len(points),
            })

    results.sort(key=lambda r: -r["minutes"])
    print(f"\ntorow sprawdzonych: {checked}, bez toru w archiwum: {no_trace}")
    print(f"wzorcow znalezionych: {len(results)}")
    print("")
    print("ile samolotow danego rodzaju mialo wzorzec (to jest miara czulosci, nie deklaracja):")
    for rodzaj, ile in sorted(sprawdzone.items(), key=lambda kv: -kv[1]):
        print(f"  {rodzaj:12s} {len(ze_wzorcem.get(rodzaj, ())):2d} z {ile:2d}")
    for r in results[:15]:
        print(f"  {r['pattern']:14s} {r['minutes']:4d} min  {r['kind']:11s} {(r['type'] or '?'):6s} "
              f"{(r['callsign'] or '?'):9s} noga {r['longest_leg_km']:5.1f} km  "
              f"{r['alt_ft'] or 0:6.0f} ft  {r['lat']:.2f},{r['lon']:.2f}")

    OUT.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "adsb.lol /v2/mil + pelne tory dnia (globe.adsb.lol)",
        "checked": checked,
        "checked_by_kind": sprawdzone,
        "with_pattern_by_kind": {k: len(v) for k, v in ze_wzorcem.items()},
        "note": ("Ksztalt toru, nie misja. Tor wyscigowy tankowca zwykle oznacza dyzur tankowania, "
                 "ale ten sam ksztalt lata rozpoznanie i samolot czekajacy na lotnisko."),
        "loiters": results,
    }), encoding="utf-8")
    print(f"\nzapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
