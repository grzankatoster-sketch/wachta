"""Which sanctioned or shadow-fleet ships are near a cable or pipeline right now.

Not a detector - no behaviour is judged here. It answers a question an analyst asks first: of the
ships on the lists, which ones are currently over infrastructure, and how close. Anchor dragging (D6)
is the behaviour on top of this; presence alone is context, not an accusation.

  python eval/feasibility/shadow_near_cables.py [promien_km]
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.infrastructure import load_lines  # noqa: E402
from wachta_detectors.sanctions import SanctionIndex  # noqa: E402
from wachta_detectors.spatial_index import LineIndex  # noqa: E402

SHIPS = ROOT / "eval" / "fixtures" / "ships_snapshot.json"
CABLES = ROOT / "data" / "infrastructure" / "baltic_cables.geojson"
SANCTIONS = ROOT / "data" / "sanctions" / "maritime.csv"


def main() -> int:
    radius = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    for path in (SHIPS, CABLES, SANCTIONS):
        if not path.exists():
            print(f"brak {path}")
            return 1

    snapshot = json.loads(SHIPS.read_text(encoding="utf-8"))
    index = LineIndex(load_lines(CABLES))
    sanctions = SanctionIndex.from_csv(SANCTIONS)
    print(f"odczyt z {snapshot['fetched_at'][:16]} · statkow {len(snapshot['ships'])} · "
          f"odcinkow {len(index)} · lista {len(sanctions)} statkow")

    rows = []
    for ship in snapshot["ships"]:
        match = sanctions.match(imo=ship.get("imo"), mmsi=ship.get("mmsi"))
        if not match:
            continue
        near = index.nearest(ship["lat"], ship["lon"], max_km=radius)
        if not near:
            continue
        line, km = near
        rows.append((km, ship, match, line))

    rows.sort(key=lambda r: r[0])
    shadow = sum(1 for _, _, m, _ in rows if m.is_shadow_fleet)
    print(f"\nstatkow z list w promieniu {radius:.0f} km od infrastruktury: {len(rows)} (w tym flota cieni: {shadow})\n")
    for km, ship, match, line in rows:
        tag = "FLOTA CIENI" if match.is_shadow_fleet else "; ".join(match.risk) or "wpis na liscie"
        print(f"  {km:5.2f} km  {(ship['name'] or ship['mmsi'])[:24]:24s} {ship['class']:11s} "
              f"{ship['sog'] or 0:4.1f} w.  {line.name[:28]:28s}  [{tag}]")

    if rows:
        print("\nTo jest kontekst, nie zarzut: przejscie nad kablem jest normalne, wiekszosc tras")
        print("na Baltyku przecina jakas linie. Dopiero zachowanie (D6) jest sygnalem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
