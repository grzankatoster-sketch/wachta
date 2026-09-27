"""Runs D7 over a day of Danish AIS: numbers whose own track contradicts itself.

  python eval/feasibility/run_d7.py [2024-12-25]
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.identity import IdentityRules, by_ship, examine, scan  # noqa: E402
from wachta_detectors.sanctions import SanctionIndex  # noqa: E402

sys.path.insert(0, str(ROOT / "eval" / "feasibility"))
from run_d4 import read_day  # noqa: E402

OUT = ROOT / "eval" / "fixtures" / "identity_snapshot.json"
SANCTIONS = ROOT / "data" / "sanctions" / "maritime.csv"


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else "2024-12-25"
    fixes, types, all_names = read_day(day)

    rules = IdentityRules()
    reports = scan(fixes, rules)
    dwa = [r for r in reports if r.verdict == "dwa kadluby"]
    blad = [r for r in reports if r.verdict == "bledny punkt"]

    print("")
    print(f"numerow MMSI w dobie: {len(by_ship(fixes))}")
    print(f"  z niemozliwym skokiem pozycji: {len(reports)}")
    print(f"    tor wraca miedzy dwoma obszarami (dwa kadluby): {len(dwa)}")
    print(f"    pojedynczy punkt poza torem (blad odczytu): {len(blad)}")

    wiele_nazw = {m: n for m, n in all_names.items() if len(n) > 1}
    print(f"  numerow nadajacych wiecej niz jedna nazwe: {len(wiele_nazw)}")

    sankcje = SanctionIndex.from_csv(SANCTIONS) if SANCTIONS.exists() else None

    print("")
    print("numery, ktore wygladaja na dwa kadluby:")
    for r in dwa[:15]:
        miejsca = " | ".join(f"{lat:.2f},{lon:.2f} ({ile} odc.)" for lat, lon, ile in r.clusters)
        print(f"  {r.mmsi} {(all_names.get(r.mmsi) or ['?'])[0][:18]:18s} "
              f"{r.alternations} przeskokow, max {r.max_implied_kt:6.1f} w.  {miejsca}")

    print("")
    print("numery nadajace wiecej niz jedna nazwe:")
    for mmsi, nazwy in sorted(wiele_nazw.items(), key=lambda kv: -len(kv[1]))[:15]:
        print(f"  {mmsi} ({types.get(mmsi) or '?'}): {', '.join(nazwy[:4])}")

    OUT.write_text(json.dumps({
        "day": day,
        "source": f"Danish Maritime Authority, aisdk-{day}",
        "note": ("Numer MMSI to nie statek, tylko liczba wpisana do radia. Skok pozycji szybszy niz "
                 "jakikolwiek kadlub oznacza, ze pod jednym numerem melduja sie dwa statki albo ze "
                 "odbiornik podal blad - i te dwie rzeczy sa tu rozdzielone."),
        "rules": {"max_hull_kt": rules.max_hull_kt, "min_segment_fixes": rules.min_segment_fixes,
                  "min_separation_km": rules.min_separation_km},
        "mmsi_total": len(by_ship(fixes)),
        "two_hulls": len(dwa), "bad_fix": len(blad), "many_names": len(wiele_nazw),
        "cases": [{
            "mmsi": r.mmsi, "verdict": r.verdict, "names": all_names.get(r.mmsi, []),
            "type": types.get(r.mmsi), "alternations": r.alternations,
            "max_kt": r.max_implied_kt, "fixes": r.fixes,
            "clusters": [{"lat": lat, "lon": lon, "segments": ile} for lat, lon, ile in r.clusters],
            "listed": bool(sankcje and sankcje.match(mmsi=r.mmsi)),
        } for r in dwa],
        "renamed": [{"mmsi": m, "names": n, "type": types.get(m)}
                    for m, n in sorted(wiele_nazw.items())],
    }), encoding="utf-8")
    print("")
    print(f"zapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
