"""Joins D4 and D5 over a day of Danish AIS: a ship stopped alone next to somebody else's silence.

  python eval/feasibility/run_dark_sts.py [2024-12-25]
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.dark_sts import DarkStsRules, pair_up  # noqa: E402
from wachta_detectors.gaps import find_gaps, suspicious  # noqa: E402
from wachta_detectors.sanctions import SanctionIndex  # noqa: E402
from wachta_detectors.sts import StsRules, find_encounters, stationary_periods  # noqa: E402

# Holownik na budowie, pilotowka i jednostka straznicza stoja w miejscu z zawodu. Stojacy statek
# w ruchliwej ciesninie ma obok siebie czyjas cisze co chwile i nie znaczy to nic.
SLUZBOWE = {"Tug", "Pilot", "Port tender", "Law enforcement", "Search and Rescue",
            "Dredging", "Diving", "Military", "Medical transport"}
from wachta_detectors.infrastructure import load_lines  # noqa: E402
from wachta_detectors.spatial_index import LineIndex  # noqa: E402

sys.path.insert(0, str(ROOT / "eval" / "feasibility"))
from run_d4 import read_day  # noqa: E402

OUT = ROOT / "eval" / "fixtures" / "dark_sts_snapshot.json"
SANCTIONS = ROOT / "data" / "sanctions" / "maritime.csv"
CABLES = ROOT / "data" / "infrastructure" / "baltic_cables.geojson"


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else "2024-12-25"
    fixes, types, _names = read_day(day)

    sts_rules = StsRules()
    encounters = find_encounters(fixes, sts_rules)
    paired = {m for e in encounters for m in (e.mmsi_a, e.mmsi_b)}

    periods = stationary_periods(fixes, sts_rules)
    alone = [p for p in periods if p.mmsi not in paired]
    open_water = [p for p in alone if not p.in_anchorage and p.sailed_in]
    print(f"\npostojow w miejscu: {len(periods)}")
    print(f"  bez widocznego sasiada: {len(alone)}")
    print(f"  z tego poza kotwicowiskiem i po przyplynieciu: {len(open_water)}")

    gaps = suspicious(find_gaps(fixes))
    print(f"niewyjasnionych ciszy AIS (D4): {len(gaps)}")

    wszystkie = pair_up(open_water, gaps, DarkStsRules())
    hits = [d for d in wszystkie if types.get(d.visible_mmsi) not in SLUZBOWE]
    print("")
    print(f"par po tescie wykonalnosci drogi: {len(wszystkie)}")
    print(f"  po odjeciu jednostek sluzbowych jako stojacego statku: {len(hits)}")

    # Zero alarmow znaczy cos tylko wtedy, gdy wiadomo, ze detektor na tych danych w ogole moze
    # zadzialac. Rozluznienie progow pokazuje, gdzie dokladnie urywa sie lancuch.
    print("")
    print("czulosc - ile par przy luzniejszych progach (bez odsiewu jednostek sluzbowych):")
    sweep = []
    for stop_min, speed, km in ((30, 12.0, 25.0), (10, 12.0, 25.0), (10, 16.0, 25.0),
                                (10, 16.0, 50.0), (0, 20.0, 50.0)):
        r = DarkStsRules(max_km=km, speed_kt=speed, min_stop=timedelta(minutes=stop_min))
        ile = len(pair_up(open_water, gaps, r))
        sweep.append({"min_stop": stop_min, "speed_kt": speed, "max_km": km, "pairs": ile})
        print(f"  postoj >= {stop_min:2d} min, tempo {speed:4.1f} w., promien {km:4.0f} km  ->  {ile}")

    sankcje = SanctionIndex.from_csv(SANCTIONS) if SANCTIONS.exists() else None
    lines = LineIndex(load_lines(CABLES)) if CABLES.exists() else None

    wynik = []
    for d in hits:
        near = lines.nearest(d.lat, d.lon, max_km=15) if lines else None
        wpisy = {}
        for rola, mmsi in (("widoczny", d.visible_mmsi), ("zgaszony", d.dark_mmsi)):
            m = sankcje.match(mmsi=mmsi) if sankcje else None
            wpisy[rola] = m.category if m else None
        wynik.append({
            "visible_mmsi": d.visible_mmsi, "visible_name": d.visible_name,
            "visible_type": types.get(d.visible_mmsi),
            "dark_mmsi": d.dark_mmsi, "dark_name": d.dark_name,
            "dark_type": types.get(d.dark_mmsi),
            "from": d.start.isoformat(), "to": d.end.isoformat(),
            "overlap_min": d.overlap_min, "gap_min": d.gap_min,
            "distance_km": d.distance_km, "detour_km": d.detour_km,
            "spare_min": d.spare_min, "listeners": d.listeners,
            "lat": d.lat, "lon": d.lon,
            "wykaz_widoczny": wpisy["widoczny"], "wykaz_zgaszony": wpisy["zgaszony"],
            "near_line": near[0].name if near else None,
            "near_line_km": round(near[1], 1) if near else None,
        })

    for r in wynik[:15]:
        kabel = f"  {r['near_line_km']} km od: {r['near_line'][:22]}" if r["near_line"] else ""
        print(f"  {r['overlap_min']:4d} min wspolnie  {(r['visible_name'] or r['visible_mmsi'])[:18]:18s} "
              f"({r['visible_type'] or '?'}) stal {r['distance_km']:4.1f} km od miejsca, gdzie zamilkl "
              f"{(r['dark_name'] or r['dark_mmsi'])[:18]} ({r['dark_type'] or '?'}), "
              f"zostalo {r['spare_min']} min na postoj{kabel}")

    OUT.write_text(json.dumps({
        "day": day,
        "source": f"Danish Maritime Authority, aisdk-{day}",
        "note": ("Zlozenie dwoch detektorow, nie obserwacja. Statek moze stanac z powodu pogody albo "
                 "awarii, a czyjs transponder moze paść kilka kilometrow dalej bez zwiazku. To lista "
                 "miejsc do sprawdzenia, nie lista przeladunkow."),
        "rules": {"max_km": DarkStsRules().max_km,
                  "min_overlap_min": DarkStsRules().min_overlap.total_seconds() / 60},
        "stationary": len(periods), "alone": len(alone), "open_water": len(open_water),
        "gaps": len(gaps), "feasible": len(wszystkie), "found": len(hits),
        "sensitivity": sweep,
        "pairs": wynik,
    }), encoding="utf-8")
    print(f"\nzapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
