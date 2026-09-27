"""Evaluates D1 and D3 on frozen fixtures. --check <baseline.json> fails (exit 1) on a drop > TOLERANCE."""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python"))

import h3  # noqa: E402

from wachta_detectors.anchor import ShipFix  # noqa: E402
from wachta_detectors.dark import LastSeen, find_dark_candidates  # noqa: E402
from wachta_detectors.gaps import find_gaps, suspicious  # noqa: E402
from wachta_detectors.identity import scan as scan_identity  # noqa: E402
from wachta_detectors.racetrack import TracePoint, find_loiters  # noqa: E402
from wachta_detectors.sts import find_encounters, offshore  # noqa: E402
from wachta_detectors.geo import haversine_km  # noqa: E402
from wachta_detectors.jamming import aggregate_jamming  # noqa: E402
from wachta_detectors.models import Position  # noqa: E402

TOLERANCE = 0.05
FIX = Path(__file__).parent / "fixtures"
KALININGRAD = (54.71, 20.51)


def prf(tp: int, fp: int, fn: int) -> dict:
    return {"precision": round(tp / (tp + fp), 3) if tp + fp else 1.0, "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0}


def load_snapshot_positions() -> list[Position]:
    """One frozen hour of positions (a single snapshot is too sparse: res-4 cells need ~5 aircraft each)."""
    raw = json.loads((FIX / "d3_hour.json").read_text(encoding="utf-8"))["positions"]
    now = datetime.now(timezone.utc)
    return [Position(p["hex"], p["lat"], p["lon"], p["alt_ft"], p["on_ground"], p["nac_p"], now) for p in raw]


def eval_d3() -> dict:
    """Labels are frozen in d3_labels.json. A detector returning nothing must score recall 0, not 1."""
    labels = json.loads((FIX / "d3_labels.json").read_text(encoding="utf-8"))
    flagged = {c.h3 for c in aggregate_jamming(load_snapshot_positions()) if c.level != "low"}
    tp = sum(cell in flagged for cell in labels["positive"])
    fn = len(labels["positive"]) - tp
    fp = sum(cell in flagged for cell in labels["negative"])
    return {**prf(tp, fp, fn), "n_positive": len(labels["positive"]), "n_negative": len(labels["negative"])}


def eval_d1(path: Path) -> dict:
    if not path.exists():
        return {"precision": None, "recall": None, "n_cases": 0}
    tp = fp = fn = n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        s = dict(c["last_seen"])
        s["ts"] = datetime.fromisoformat(s["ts"])
        s["last_message_at"] = datetime.fromisoformat(s["last_message_at"])
        got = bool(find_dark_candidates([LastSeen(**s)], c["coverage"], set(c["alive"]),
                                        [tuple(a) for a in c["airports"]], datetime.fromisoformat(c["now"])))
        tp += got and c["expected"]
        fp += got and not c["expected"]
        fn += (not got) and c["expected"]
        n += 1
    return {**prf(tp, fp, fn), "n_cases": n}


CARGO = {"Cargo", "Tanker"}


def load_slice(name: str) -> list[ShipFix]:
    data = json.loads((FIX / name).read_text(encoding="utf-8"))["fixes"]
    return [ShipFix(mmsi=f["mmsi"], ts=datetime.fromisoformat(f["ts"]), lat=f["lat"],
                    lon=f["lon"], sog=f["sog"], name=f.get("name")) for f in data]


def synthetic_racetrack() -> list[TracePoint]:
    """A deterministic tanker pattern - the D2 rule has no real frozen trace to run against."""
    base = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    points, minute, lat = [], 0.0, 57.0
    for leg in range(6):
        direction = 1 if leg % 2 == 0 else -1
        for step in range(12):
            frac = step / 12
            points.append(TracePoint(t=base + timedelta(minutes=minute + 12 * frac),
                                     lat=lat + direction * frac * 60 / 111.0, lon=21.0, alt_ft=25000.0))
        lat += direction * 60 / 111.0
        minute += 12.0
    return points


def eval_regression() -> dict:
    """Counts on frozen slices of one real day.

    This is a REGRESSION gate, not a quality one. The cases in it were read by hand and understood,
    but there is no independent source saying which ships really switched their transponders off, so
    these numbers say "the behaviour did not change", never "the detector is right". Only D3 has
    labels from outside the project (gpsjam), and only D3 may be read as quality.
    """
    out: dict = {}

    if (FIX / "d4_slice.json").exists():
        hits = suspicious(find_gaps(load_slice("d4_slice.json")))
        out["d4_gaps"] = {"found": len(hits), "mmsi": sorted(a.mmsi for a in hits)}

    if (FIX / "d5_slice.json").exists() and (FIX / "slice_types.json").exists():
        types = json.loads((FIX / "slice_types.json").read_text(encoding="utf-8"))
        sea = offshore(find_encounters(load_slice("d5_slice.json")))
        cargo = [e for e in sea if types.get(e.mmsi_a) in CARGO and types.get(e.mmsi_b) in CARGO]
        out["d5_sts"] = {"offshore": len(sea), "cargo_pairs": len(cargo),
                         "pairs": sorted("+".join(sorted((e.mmsi_a, e.mmsi_b))) for e in cargo)}

    if (FIX / "d7_slice.json").exists():
        flagged = scan_identity(load_slice("d7_slice.json"))
        out["d7_identity"] = {"two_hulls": sum(r.verdict == "dwa kadluby" for r in flagged),
                              "mmsi": sorted(r.mmsi for r in flagged if r.verdict == "dwa kadluby")}

    loiters = find_loiters(synthetic_racetrack())
    out["d2_synthetic"] = {"patterns": len(loiters),
                           "kinds": sorted(loiter.kind for loiter in loiters)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", type=Path)
    args = ap.parse_args()
    results = {
        "d3": eval_d3(),
        # Synthetic = regression test of the rule. Real = quality, from hand-labelled silent aircraft (T1.15 Step 10).
        "d1_synthetic": eval_d1(FIX / "d1_cases.jsonl"),
        "d1_real": eval_d1(FIX / "d1_real_cases.jsonl"),
        "regresja": eval_regression(),
    }
    out = Path(__file__).parent / "results" / "latest.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    if args.check:
        base = json.loads(args.check.read_text(encoding="utf-8"))
        drops = [f"{d}.{m}: {base[d][m]} -> {results[d][m]}"
                 for d in base if d != "regresja" for m in ("precision", "recall")
                 if base[d].get(m) is not None
                 and (results[d][m] is None or results[d][m] < base[d][m] - TOLERANCE)]
        # Regresja porownuje sie doslownie. Nie ma tu tolerancji, bo nie ma metryki, ktora moglaby
        # "troche spasc": albo detektor widzi na zamrozonych danych to samo, albo cos sie zmienilo.
        zmiany = []
        for nazwa, oczekiwane in base.get("regresja", {}).items():
            teraz = results.get("regresja", {}).get(nazwa)
            if teraz != oczekiwane:
                zmiany.append(f"{nazwa}: {json.dumps(oczekiwane, ensure_ascii=False)}"
                              f" -> {json.dumps(teraz, ensure_ascii=False)}")
        if drops:
            print("METRIC DROP:\n  " + "\n  ".join(drops))
        if zmiany:
            print("ZMIANA ZACHOWANIA NA ZAMROZONYCH DANYCH:\n  " + "\n  ".join(zmiany))
        if drops or zmiany:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
