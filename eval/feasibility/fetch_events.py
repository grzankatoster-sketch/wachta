"""Downloads the last N GDELT packages and keeps the events inside a region.

GDELT publishes one package every fifteen minutes - about 40 KB each, no key needed. A whole day is
96 files and a few megabytes, so a day of world events costs less bandwidth than one satellite tile.

  python eval/feasibility/fetch_events.py [ile_godzin]
"""
import io
import json
import sys
import time
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.events import group_repeats, in_box, parse_rows  # noqa: E402

OUT = ROOT / "eval" / "fixtures" / "events_snapshot.json"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}
BASE = "http://data.gdeltproject.org/gdeltv2/"

# Caly swiat: detektor anomalii i porownanie wersji nie maja powodu zatrzymywac sie na Europie.
REGION = (-90.0, 90.0, -180.0, 180.0)  # lat_min, lat_max, lon_min, lon_max


def package_names(hours: float) -> list[str]:
    """GDELT names files by UTC timestamp rounded down to fifteen minutes."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    now -= timedelta(minutes=now.minute % 15 + 30)  # ostatnie paczki bywaja jeszcze niegotowe
    return [(now - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S") for i in range(int(hours * 4))]


def main() -> int:
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    events, missing = [], 0

    for i, stamp in enumerate(package_names(hours), start=1):
        for kind in ("export", "translation.export"):
            try:
                response = requests.get(f"{BASE}{stamp}.{kind}.CSV.zip", headers=HEADERS, timeout=120)
                if response.status_code != 200:
                    missing += 1
                    continue
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    rows = z.read(z.namelist()[0]).decode("utf-8", "replace").splitlines()
                events.extend(in_box(parse_rows(rows), *REGION))
            except Exception as e:
                missing += 1
                print(f"  {stamp} {kind}: {type(e).__name__}")
        if i % 8 == 0:
            print(f"  {i} paczek, zdarzen w regionie: {len(events)}", flush=True)
        time.sleep(0.5)

    grouped = group_repeats(events)
    conflict = [e for e, _ in grouped if e.is_conflict]
    aid = [e for e, _ in grouped if e.is_aid]
    print(f"\npaczek pobranych: {int(hours * 4) - missing}, brakujacych: {missing}")
    print(f"zdarzen w regionie: {len(events)} -> po zgrupowaniu powtorzen: {len(grouped)}")
    print(f"  w tym konfliktowych: {len(conflict)}, dotyczacych pomocy: {len(aid)}")

    rodzaje = Counter(e.kind for e, _ in grouped)
    print("\nnajczestsze rodzaje zdarzen:")
    for kind, n in rodzaje.most_common(8):
        print(f"  {kind:26s} {n}")

    print("\nnajszerzej opisywane zdarzenia:")
    for event, count in grouped[:10]:
        print(f"  [{count:3d} zrodel] {event.summary[:58]:58s} {event.place or '?':26s} {event.url[:40]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "hours": hours,
        "source": "GDELT 2.0 event export (co 15 minut, bez klucza)",
        "region": REGION,
        "events": [{
            "id": e.id, "day": e.day.isoformat(), "actor1": e.actor1, "actor2": e.actor2,
            "actor1_country": e.actor1_country, "actor2_country": e.actor2_country,
            "kind": e.kind, "quad": e.quad, "root": e.root_code, "conflict": e.is_conflict, "aid": e.is_aid,
            "goldstein": e.goldstein, "mentions": e.mentions, "sources": count,
            "place": e.place, "lat": e.lat, "lon": e.lon, "url": e.url,
        } for e, count in grouped],
    }), encoding="utf-8")
    print(f"\nzapisano {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
