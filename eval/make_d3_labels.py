"""Builds frozen D3 labels from an independent reference: the daily H3 files published by gpsjam.org.

The first version labelled cells by distance from Kaliningrad. On real data that turned out to be
wrong — the hour collected on 2026-09-26 has its affected aircraft centred near 56.2N 21.3E, over
200 km north of Kaliningrad, so the rule produced zero positive labels.

gpsjam.org publishes, per day and per H3 res-4 cell, how many aircraft reported good and bad
navigation accuracy — the same quantity this detector computes, from a separate implementation and a
different data pipeline. That makes it a reference, not a mirror of our own thresholds.

Caveats, and they go in the README:
  * gpsjam publishes with a delay, so the reference is normally the previous day;
  * it aggregates a whole day, we aggregate one hour — agreement is expected to be partial,
    which makes recall measured this way pessimistic rather than flattering.

  python eval/make_d3_labels.py [YYYY-MM-DD]
"""
import csv
import io
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.jamming import aggregate_jamming  # noqa: E402
from wachta_detectors.models import Position  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
REFERENCE_URL = "https://gpsjam.org/data/{day}-h3_4.csv"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}

MIN_REFERENCE_AIRCRAFT = 20  # a reference cell has to be busy enough to mean anything
POSITIVE_SHARE = 0.10        # gpsjam calls this "high"
NEGATIVE_SHARE = 0.01        # quiet by the reference's own numbers


def fetch_reference(day: date) -> dict[str, tuple[int, int]]:
    url = REFERENCE_URL.format(day=day.isoformat())
    response = requests.get(url, headers=HEADERS, timeout=120)
    if response.status_code == 404:
        raise SystemExit(f"gpsjam nie ma jeszcze pliku za {day} ({url}) - sprobuj z data wczesniejsza")
    response.raise_for_status()
    rows = csv.DictReader(io.StringIO(response.text))
    return {r["hex"]: (int(r["count_good_aircraft"]), int(r["count_bad_aircraft"])) for r in rows}


def our_cells() -> dict[str, object]:
    raw = json.loads((FIX / "d3_hour.json").read_text(encoding="utf-8"))["positions"]
    now = datetime.now(timezone.utc)
    positions = [Position(p["hex"], p["lat"], p["lon"], p["alt_ft"], p["on_ground"], p["nac_p"], now) for p in raw]
    return {c.h3: c for c in aggregate_jamming(positions)}


def main() -> int:
    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=1)
    reference = fetch_reference(day)
    ours = our_cells()
    print(f"referencja gpsjam {day}: {len(reference)} komorek na swiecie")
    print(f"nasza godzina: {len(ours)} komorek")

    positive, negative, ignored = [], [], 0
    for cell in ours:
        if cell not in reference:
            ignored += 1
            continue
        good, bad = reference[cell]
        total = good + bad
        if total < MIN_REFERENCE_AIRCRAFT:
            ignored += 1
            continue
        share = bad / total
        if share >= POSITIVE_SHARE:
            positive.append(cell)
        elif share <= NEGATIVE_SHARE:
            negative.append(cell)
        else:
            ignored += 1

    labels = {
        "source": f"gpsjam.org {day} (H3 res 4, count_good_aircraft / count_bad_aircraft)",
        "note": ("Referencja z dnia poprzedniego i z calej doby, nasz pomiar to jedna godzina - "
                 "zgodnosc jest z natury czesciowa, wiec recall liczony w ten sposob jest zanizony."),
        "thresholds": {"min_reference_aircraft": MIN_REFERENCE_AIRCRAFT,
                       "positive_share": POSITIVE_SHARE, "negative_share": NEGATIVE_SHARE},
        "positive": sorted(positive),
        "negative": sorted(negative),
    }
    (FIX / "d3_labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")

    print(f"\netykiety: {len(positive)} positive, {len(negative)} negative, {ignored} pominietych")
    for cell in positive:
        good, bad = reference[cell]
        c = ours[cell]
        print(f"  + {cell}  gpsjam {bad}/{good + bad} = {bad / (good + bad):.0%}  |  nasze {c.n_degraded}/{c.n_aircraft} -> {c.level}")

    if len(positive) < 3 or len(negative) < 10:
        print("\nZA MALO ETYKIET - zbierz dluzsze okno albo wybierz dzien z wieksza aktywnoscia")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
