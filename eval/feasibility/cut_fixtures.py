"""Cuts three small frozen slices out of the Danish day, so the gate can run without the 500 MB file.

Each slice is chosen around a case that was read by hand and understood, together with enough of the
surrounding traffic for the detector to reach the same conclusion it reached on the whole day. A
slice that contained only the suspect would prove nothing: D4 needs witnesses, D5 needs the quays it
must ignore, D7 needs the rescue helicopters it must not accuse.

  python eval/feasibility/cut_fixtures.py [2024-12-25]
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))
sys.path.insert(0, str(ROOT / "eval" / "feasibility"))

from run_d4 import read_day  # noqa: E402

FIX = ROOT / "eval" / "fixtures"

# Bornholm: cisza STANISLAV GOVORUKHIN o 15:55-16:41 i ruch, ktory ja obala albo potwierdza.
D4_BOX = (54.6, 55.4, 13.0, 14.0)
D4_FROM, D4_TO = 13, 19

# Skagen: najwieksze miejsce bunkrowania w Europie, razem z kejami, ktore detektor ma pominac.
D5_BOX = (57.4, 57.85, 10.3, 11.0)
D5_FROM, D5_TO = 6, 14

# D7 nie potrzebuje sasiadow, tylko wlasciwych numerow: podejrzany i smiglowce, ktore nim nie sa.
D7_MMSI = {"219006091", "111219515", "111219513", "111219516", "111219504", "219016938"}


def dump(name: str, fixes: list, note: str) -> None:
    path = FIX / name
    path.write_text(json.dumps({
        "source": "Danish Maritime Authority, aisdk-2024-12-25 (wyciety fragment)",
        "note": note,
        "fixes": [{"mmsi": f.mmsi, "ts": f.ts.isoformat(), "lat": round(f.lat, 5),
                   "lon": round(f.lon, 5), "sog": f.sog, "name": f.name} for f in fixes],
    }), encoding="utf-8")
    ships = len({f.mmsi for f in fixes})
    print(f"  {name}: {len(fixes)} pozycji, {ships} statkow, {path.stat().st_size // 1024} KB")


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else "2024-12-25"
    fixes, types, _names = read_day(day)
    base = datetime.fromisoformat(f"{day}T00:00:00+00:00").replace(tzinfo=timezone.utc)

    def slice_box(box, hour_from, hour_to):
        lat_min, lat_max, lon_min, lon_max = box
        start, end = base + timedelta(hours=hour_from), base + timedelta(hours=hour_to)
        return [f for f in fixes
                if lat_min <= f.lat <= lat_max and lon_min <= f.lon <= lon_max
                and start <= f.ts <= end]

    print("wycinam:")
    dump("d4_slice.json", slice_box(D4_BOX, D4_FROM, D4_TO),
         "Bornholm, 13-19 UTC. Zawiera cisze STANISLAV GOVORUKHIN i ruch, ktory ja czyni wyjatkowa.")
    dump("d5_slice.json", slice_box(D5_BOX, D5_FROM, D5_TO),
         "Skagen, 6-14 UTC. Zawiera bunkrowania i keje, ktore detektor ma pominac.")
    dump("d7_slice.json", [f for f in fixes if f.mmsi in D7_MMSI],
         "RAGNA (dwa kadluby) oraz numery 111xxxxxx, ktore sa smiglowcami SAR, a nie oszustwem.")

    typy = {m: t for m, t in types.items()}
    (FIX / "slice_types.json").write_text(json.dumps(typy), encoding="utf-8")
    print(f"  slice_types.json: {len(typy)} typow statkow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
