"""Runs D5 over a day of Danish AIS and reports how noisy it is before anyone trusts it.

The question that decides whether the detector is usable is not "does it find transfers" but "how
many meetings does it call a transfer when nothing happened". A day of real traffic answers that,
and the anchorages it has to exclude are read off the same day rather than taken on faith.

  python eval/feasibility/run_d5.py [2024-12-25]
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.sanctions import SanctionIndex  # noqa: E402
from wachta_detectors.spatial_index import LineIndex  # noqa: E402
from wachta_detectors.infrastructure import load_lines  # noqa: E402
from wachta_detectors.sts import StsRules, anchorages, find_encounters, offshore  # noqa: E402

sys.path.insert(0, str(ROOT / "eval" / "feasibility"))
from run_d4 import read_day  # noqa: E402

OUT = ROOT / "eval" / "fixtures" / "sts_snapshot.json"

# Holowniki, pilotowki, lodzie serwisowe i ratownicze podchodza burta w burte z zawodu. To nadal
# prawdziwe spotkania, tylko nie sa niczyja tajemnica, wiec licza sie osobno.
LADUNKOWE = {"Cargo", "Tanker"}
SANCTIONS = ROOT / "data" / "sanctions" / "maritime.csv"
CABLES = ROOT / "data" / "infrastructure" / "baltic_cables.geojson"


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else "2024-12-25"
    fixes, types, _names = read_day(day)

    rules = StsRules()
    parked = anchorages(fixes, rules)
    print(f"\nkotwicowisk wyprowadzonych z ruchu: {len(parked)} kratek "
          f"(co najmniej {rules.anchorage_min_ships} roznych statkow stojacych w kratce)")

    encounters = find_encounters(fixes, rules)
    sea = offshore(encounters)
    print(f"spotkan burta w burte co najmniej {rules.min_duration.total_seconds() / 60:.0f} min: "
          f"{len(encounters)}")
    poza = [e for e in encounters if not e.in_anchorage]
    print(f"  na kotwicowiskach: {len(encounters) - len(poza)}")
    print(f"  poza kotwicowiskiem: {len(poza)}")
    print(f"  z tego takich, gdzie oba statki gdzies plynely: {len(sea)} (reszta stoi przy nabrzezu)")

    sankcje = SanctionIndex.from_csv(SANCTIONS) if SANCTIONS.exists() else None
    lines = LineIndex(load_lines(CABLES)) if CABLES.exists() else None

    ladunek = [e for e in sea
               if types.get(e.mmsi_a) in LADUNKOWE and types.get(e.mmsi_b) in LADUNKOWE]
    print(f"  z tego oba statki to ladunkowce albo tankowce: {len(ladunek)}")
    rodzaje: dict[str, int] = {}
    for e in sea:
        para = " + ".join(sorted((types.get(e.mmsi_a) or "?", types.get(e.mmsi_b) or "?")))
        rodzaje[para] = rodzaje.get(para, 0) + 1
    print("")
    print("jakie pary sie spotykaja poza kotwicowiskiem:")
    for para, ile in sorted(rodzaje.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {para:34s} {ile}")

    wynik = []
    for e in sea:
        a = sankcje.match(mmsi=e.mmsi_a) if sankcje else None
        b = sankcje.match(mmsi=e.mmsi_b) if sankcje else None
        near = lines.nearest(e.lat, e.lon, max_km=10) if lines else None
        wynik.append({
            "mmsi_a": e.mmsi_a, "mmsi_b": e.mmsi_b, "name_a": e.name_a, "name_b": e.name_b,
            "from": e.start.isoformat(), "to": e.end.isoformat(),
            "minutes": round(e.duration.total_seconds() / 60),
            "lat": e.lat, "lon": e.lon,
            "min_km": e.min_separation_km, "mean_km": e.mean_separation_km,
            "sog": e.mean_sog, "drift_km": e.drift_km, "samples": e.samples,
            "type_a": types.get(e.mmsi_a), "type_b": types.get(e.mmsi_b),
            "cargo_pair": types.get(e.mmsi_a) in LADUNKOWE and types.get(e.mmsi_b) in LADUNKOWE,
            "listed_a": bool(a), "listed_b": bool(b),
            "near_line": near[0].name if near else None,
            "near_line_km": round(near[1], 1) if near else None,
        })

    print("")
    print("spotkania dwoch ladunkowcow lub tankowcow poza kotwicowiskiem:")
    for r in sorted([w for w in wynik if w["cargo_pair"]], key=lambda x: -x["minutes"])[:15]:
        lista = "  <- na liscie" if (r["listed_a"] or r["listed_b"]) else ""
        kabel = f"  {r['near_line_km']} km od: {r['near_line'][:24]}" if r["near_line"] else ""
        print(f"  {r['minutes']:4d} min  {(r['name_a'] or r['mmsi_a'])[:18]:18s} + "
              f"{(r['name_b'] or r['mmsi_b'])[:18]:18s} {r['min_km'] * 1000:4.0f} m  "
              f"dryf {r['drift_km']:5.2f} km  {r['lat']:.2f},{r['lon']:.2f}{kabel}{lista}")

    OUT.write_text(json.dumps({
        "day": day,
        "source": f"Danish Maritime Authority, aisdk-{day}",
        "note": ("Dwa statki blisko siebie i wolno to nie dowod przeladunku. Kotwicowiska sa "
                 "wyprowadzone z tego samego dnia ruchu i odsiane, ale poza nimi zostaja holowniki, "
                 "pilotaz, bunkrowanie i awarie - kazdy przypadek trzeba przeczytac osobno."),
        "rules": {"max_separation_m": rules.max_separation_km * 1000, "max_sog": rules.max_sog,
                  "min_minutes": rules.min_duration.total_seconds() / 60,
                  "anchorage_min_ships": rules.anchorage_min_ships},
        "anchorage_cells": len(parked),
        "total": len(encounters),
        "in_anchorage": len(encounters) - len(poza),
        "offshore_all": len(poza),
        "offshore": len(sea),
        "cargo_pairs": len(ladunek),
        "pair_types": rodzaje,
        "encounters": sorted(wynik, key=lambda x: -x["minutes"]),
    }), encoding="utf-8")
    print(f"\nzapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
