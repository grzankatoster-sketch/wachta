"""Runs D4 on a full day of Danish AIS, inside a box whose edge we can reason about.

The fixture built for D6 keeps only traffic near cables, which would ruin this measurement: a ship
sailing out of the kept area and back looks exactly like a ship switching its transponder off. So
this script re-reads the same cached day and keeps a plain rectangle instead, then throws away every
gap where the ship could physically have crossed the edge of that rectangle and come back.

The test is arithmetic, not judgement: at 25 knots a ship covers 46 km an hour. If the edge is
further away than half of what the ship could have sailed during its silence, it did not leave the
box - so the silence happened inside data we hold, and the absence is real.

  python eval/feasibility/run_d4.py [2024-12-25]
"""
import json
import math
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.anchor import ShipFix  # noqa: E402
from wachta_detectors.gaps import GapRules, find_gaps, impossible, suspicious  # noqa: E402
from wachta_detectors.sanctions import SanctionIndex  # noqa: E402

CACHE = ROOT / "data" / "dma"
OUT = ROOT / "eval" / "fixtures" / "gaps_snapshot.json"
SANCTIONS = ROOT / "data" / "sanctions" / "maritime.csv"

# Ciesniny dunskie: obszar w calosci pokryty tym zbiorem, z prosta granica do policzenia.
BOX = (54.5, 58.0, 9.0, 14.0)      # lat_min, lat_max, lon_min, lon_max
MAX_SHIP_KT = 25.0                 # szybciej niz to nie plynie nic, co wozi ladunek
MIN_FIXES = 5


def edge_km(lat: float, lon: float) -> float:
    """Distance to the nearest side of the box, in kilometres."""
    lat_min, lat_max, lon_min, lon_max = BOX
    lon_scale = 111.0 * max(0.1, abs(math.cos(math.radians(lat))))
    return min((lat - lat_min) * 111.0, (lat_max - lat) * 111.0,
               (lon - lon_min) * lon_scale, (lon_max - lon) * lon_scale)


def read_day(day: str) -> tuple[list[ShipFix], dict[str, str], dict[str, list[str]]]:
    """Positions inside the box, plus what each ship says it is - the type column is free, so take it."""
    archive = CACHE / f"aisdk-{day}.zip"
    if not archive.exists():
        print(f"brak {archive} - uruchom najpierw eval/feasibility/dma_day.py {day}")
        sys.exit(1)

    lat_min, lat_max, lon_min, lon_max = BOX
    per_ship: dict[str, dict[str, dict]] = defaultdict(dict)
    names: dict[str, str] = {}
    all_names: dict[str, set[str]] = defaultdict(set)
    types: dict[str, str] = {}
    rows = kept = 0

    with zipfile.ZipFile(archive) as z:
        member = z.namelist()[0]
        print(f"czytam {member}")
        with z.open(member) as raw:
            header = raw.readline().decode("utf-8", "replace").strip().split(",")
            # Pierwsza kolumna nazywa sie "# Timestamp" - krzyzyk i cudzyslowy trzeba zdjac.
            col = {name.strip().strip('"#').strip().lower(): i for i, name in enumerate(header)}
            for line in raw:
                rows += 1
                if rows % 2_000_000 == 0:
                    print(f"  {rows // 1_000_000} mln wierszy, zachowanych {kept}", flush=True)
                parts = line.decode("utf-8", "replace").split(",")
                if len(parts) <= (col.get("longitude") or 0):
                    continue
                try:
                    lat = float(parts[col["latitude"]])
                    lon = float(parts[col["longitude"]])
                except ValueError:
                    continue
                if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                    continue
                stamp = parts[col["timestamp"]].strip()
                try:
                    ts = datetime.strptime(stamp, "%d/%m/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                mmsi = parts[col["mmsi"]].strip()
                minute = ts.replace(second=0)
                if minute.isoformat() in per_ship[mmsi]:
                    continue        # jedna pozycja na minute wystarczy i nie zmienia luk
                try:
                    sog = float(parts[col["sog"]]) if parts[col["sog"]].strip() else None
                except (ValueError, KeyError):
                    sog = None
                per_ship[mmsi][minute.isoformat()] = {"ts": minute, "lat": lat, "lon": lon, "sog": sog}
                kept += 1
                if col.get("name") is not None and len(parts) > col["name"]:
                    nazwa = parts[col["name"]].strip()
                    if nazwa:
                        # Wszystkie nazwy, nie tylko pierwsza: jeden numer pod dwiema nazwami to
                        # sygnal dla D7, a przy zapamietaniu tylko pierwszej znika bez sladu.
                        all_names[mmsi].add(nazwa)
                        names.setdefault(mmsi, nazwa)
                # "Undefined" tez jest wartoscia, wiec zapisana jako pierwsza zaslonilaby prawdziwy
                # typ z pozniejszej wiadomosci statycznej. Konkret zawsze wygrywa z brakiem wiedzy.
                if col.get("ship type") is not None and len(parts) > col["ship type"]:
                    kind = parts[col["ship type"]].strip()
                    if kind and kind not in ("Undefined", "Unknown") and types.get(mmsi) != kind:
                        types[mmsi] = kind
                    elif kind and mmsi not in types:
                        types[mmsi] = kind

    fixes = []
    for mmsi, points in per_ship.items():
        if len(points) < MIN_FIXES:
            continue
        for p in points.values():
            fixes.append(ShipFix(mmsi=mmsi, ts=p["ts"], lat=p["lat"], lon=p["lon"],
                                 sog=p["sog"], name=names.get(mmsi)))
    print(f"wierszy: {rows}, pozycji w prostokacie: {kept}, statkow: {len(per_ship)}, "
          f"po odsiewie krotkich tras: {len(set(f.mmsi for f in fixes))}")
    return fixes, types, {k: sorted(v) for k, v in all_names.items()}


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else "2024-12-25"
    fixes, _types, _names = read_day(day)

    alerts = find_gaps(fixes, GapRules())
    print(f"\nzanikow lacznie: {len(alerts)}")
    licz: dict[str, int] = {}
    for a in alerts:
        licz[a.verdict] = licz.get(a.verdict, 0) + 1
    for werdykt, ile in sorted(licz.items(), key=lambda kv: -kv[1]):
        print(f"  {werdykt:34s} {ile}")
    ruch: dict[str, int] = {}
    for a in alerts:
        ruch[a.motion] = ruch.get(a.motion, 0) + 1
    print("")
    print("co robil statek w czasie ciszy:")
    for co, ile in sorted(ruch.items(), key=lambda kv: -kv[1]):
        print(f"  {co:38s} {ile}")

    # Statek, ktory mogl wyplynac poza prostokat i wrocic, nie jest dowodem na nic.
    pewne = []
    for a in suspicious(alerts):
        hours = a.duration.total_seconds() / 3600
        zasieg_km = MAX_SHIP_KT * 1.852 * hours
        if edge_km(a.vanish_lat, a.vanish_lon) > zasieg_km / 2:
            pewne.append(a)
    print(f"\nz tego ciszy, ktorej nie tlumaczy wyjscie poza prostokat: {len(pewne)}")

    sankcje = SanctionIndex.from_csv(SANCTIONS) if SANCTIONS.exists() else None
    print("\nnajdluzsze przypadki:")
    for a in sorted(pewne, key=lambda x: -x.duration.total_seconds())[:15]:
        match = sankcje.match(mmsi=a.mmsi) if sankcje else None
        lista = "  <- na liscie" if match else ""
        print(f"  {a.mmsi} {(a.name or '?')[:20]:20s} {a.duration.total_seconds() / 60:5.0f} min  "
              f"{a.shift_km:6.1f} km  {a.implied_kt:5.1f} w.  swiadkow {a.listeners:3d}  "
              f"{a.vanish_lat:.2f},{a.vanish_lon:.2f}{lista}")

    OUT.write_text(json.dumps({
        "day": day,
        "source": f"Danish Maritime Authority, aisdk-{day}, prostokat {BOX}",
        "note": ("Luka w AIS nie jest dowodem. Zachowane sa tylko te, w ktorych w tej samej kratce "
                 "slychac bylo inne statki, nie zamilkl nikt wiecej naraz, a statek nie mogl zdazyc "
                 "wyplynac poza prostokat i wrocic."),
        "rules": {"min_gap_min": 45, "min_listeners": 3, "max_simultaneous": 2,
                  "max_ship_kt": MAX_SHIP_KT},
        "counts": licz,
        "total": len(alerts),
        "confirmed": len(pewne),
        "motion_counts": ruch,
        "impossible": [{"mmsi": a.mmsi, "name": a.name, "shift_km": a.shift_km,
                        "minutes": round(a.duration.total_seconds() / 60),
                        "implied_kt": a.implied_kt} for a in impossible(alerts)],
        "gaps": [{
            "mmsi": a.mmsi, "name": a.name,
            "from": a.vanished_at.isoformat(), "to": a.resumed_at.isoformat(),
            "minutes": round(a.duration.total_seconds() / 60),
            "lat": a.vanish_lat, "lon": a.vanish_lon,
            "resume_lat": a.resume_lat, "resume_lon": a.resume_lon,
            "shift_km": a.shift_km, "implied_kt": a.implied_kt,
            "sog_before": a.sog_before, "listeners": a.listeners,
            "simultaneous": a.simultaneous,
            "sanctioned": bool(sankcje and sankcje.match(mmsi=a.mmsi)),
        } for a in sorted(pewne, key=lambda x: -x.duration.total_seconds())],
    }), encoding="utf-8")
    print(f"\nzapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
