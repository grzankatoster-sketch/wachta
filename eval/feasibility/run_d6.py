"""Runs D6 (anchor dragging) over collected AIS tracks and reports how noisy it is.

The number that decides whether D6 is usable is not "did it fire" but "how often does it fire on
ordinary traffic". Measured on a full day of Danish waters (aisdk-2024-12-25, 904 tracked ships near
cables):

  all ships                     35 alerts / 24 h = 1.46 per hour   -> unusable
  cargo, tankers, passengers     1 alert  / 24 h = 0.04 per hour   -> usable

The difference is not a threshold tweak. The alerts on "all ships" are cable-laying and construction
vessels working on the very lines they sit over (Ostwind, Kriegers Flak, Fehmarn Belt, Kontek) plus
trawlers, which move slowly and erratically for a living. D6 is therefore a detector for commercial
traffic; work vessels belong on a separate list, not in the same alert stream.

  python eval/feasibility/run_d6.py [sciezka_do_tras]
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.anchor import AnchorRules, ShipFix, find_anchor_drag  # noqa: E402
from wachta_detectors.infrastructure import load_lines  # noqa: E402
from wachta_detectors.sanctions import SanctionIndex  # noqa: E402
from wachta_detectors.spatial_index import LineIndex  # noqa: E402

TRACKS = ROOT / "eval" / "fixtures" / "ship_tracks.json"
CABLES = ROOT / "data" / "infrastructure" / "baltic_cables.geojson"
SANCTIONS = ROOT / "data" / "sanctions" / "maritime.csv"

# AIS ship types as the Danish dataset spells them. Everything else - dredgers, tugs, fishing boats,
# "Undefined" work boats - is excluded on purpose: slow, wandering work over a cable is their job.
COMMERCIAL = {"Cargo", "Tanker", "Passenger"}


def ship_class(raw) -> str:
    """Danish files spell the type out; Digitraffic gives the AIS number. Bring both to one label."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float)):
        code = int(raw)
        if 60 <= code <= 69:
            return "Passenger"
        if 70 <= code <= 79:
            return "Cargo"
        if 80 <= code <= 89:
            return "Tanker"
        if 30 <= code <= 39:
            return "Fishing/Tug/Special"
    return "?"


def run(tracks: list[dict], index: LineIndex, only: set[str] | None) -> tuple[int, list]:
    ships, alerts = 0, []
    identity = {}
    for track in tracks:
        if only is not None and ship_class(track.get("ship_type")) not in only:
            continue
        fixes = [ShipFix(mmsi=track["mmsi"], ts=datetime.fromisoformat(f["ts"]), lat=f["lat"], lon=f["lon"],
                         sog=f.get("sog"), cog=f.get("cog"), name=track.get("name"))
                 for f in track["fixes"]]
        if len(fixes) < AnchorRules().min_fixes:
            continue
        ships += 1
        for alert in find_anchor_drag(fixes, index):
            identity[id(alert)] = (track.get("imo"), track["mmsi"])
            alerts.append(alert)
    return ships, alerts, identity


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else TRACKS
    if not path.exists():
        print(f"brak {path} - najpierw zbierz trasy (collect_ships.py albo dma_day.py)")
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    index = LineIndex(load_lines(CABLES))
    hours = ((datetime.fromisoformat(data["collected_to"]) - datetime.fromisoformat(data["collected_from"]))
             .total_seconds() / 3600)
    print(f"okno: {hours:.2f} h | tras w pliku: {len(data['tracks'])} | odcinkow infrastruktury: {len(index)}")
    print(f"zrodlo: {data.get('source', '?')}")

    sanctions = SanctionIndex.from_csv(SANCTIONS) if SANCTIONS.exists() else None
    if sanctions:
        print(f"lista sankcyjna: {len(sanctions)} statkow z numerem IMO")

    for label, only in (("wszystkie statki", None), ("tylko handlowe (Cargo/Tanker/Passenger)", COMMERCIAL)):
        ships, alerts, identity = run(data["tracks"], index, only)
        per_hour = len(alerts) / hours if hours else 0
        print(f"\n{label}: {ships} statkow z trasa, {len(alerts)} alarmow, {per_hour:.2f} na godzine")
        oznaczone = 0
        for a in sorted(alerts, key=lambda x: -x.score)[:10]:
            imo, mmsi = identity.get(id(a), (None, a.mmsi))
            match = sanctions.match(imo=imo, mmsi=mmsi) if sanctions else None
            etykieta = ""
            if match:
                oznaczone += 1
                etykieta = "  <- FLOTA CIENI" if match.is_shadow_fleet else f"  <- listy: {'; '.join(match.risk) or 'wpis'}"
            print(f"   {a.score:.2f}  {(a.name or a.mmsi)[:22]:22s} {a.line_name[:26]:26s} "
                  f"{a.min_distance_km:5.2f} km {a.mean_sog:5.1f} w. "
                  f"rozrzut {a.course_spread_deg:5.1f} st. {a.evidence['duration_minutes']:6.1f} min{etykieta}")
        if sanctions:
            wszystkie = sum(1 for a in alerts
                            if sanctions.match(imo=identity.get(id(a), (None, a.mmsi))[0],
                                               mmsi=identity.get(id(a), (None, a.mmsi))[1]))
            print(f"   alarmow dotyczacych statkow z list sankcji/ryzyka: {wszystkie}")

    types: dict[str, int] = {}
    for track in data["tracks"]:
        fixes = [ShipFix(track["mmsi"], datetime.fromisoformat(f["ts"]), f["lat"], f["lon"], f.get("sog"), f.get("cog"))
                 for f in track["fixes"]]
        if len(fixes) >= AnchorRules().min_fixes:
            for _ in find_anchor_drag(fixes, index):
                key = ship_class(track.get("ship_type"))
                types[key] = types.get(key, 0) + 1
    if types:
        print("\nalarmy wg typu statku z AIS:")
        for name, n in sorted(types.items(), key=lambda kv: -kv[1]):
            print(f"  {name:28s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
