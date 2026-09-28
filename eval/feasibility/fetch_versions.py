"""Fetches GDELT events together with their mentions and shows where the coverage splits.

Answers one question per event: which sides wrote about it, how many articles each, and how far apart
their tone is. The tone gap is not a truth meter - it says the tellings differ, not who is right.

  python eval/feasibility/fetch_versions.py [ile_godzin]
"""
import io
import json
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.events import cluster_events, in_box, parse_rows  # noqa: E402
from wachta_detectors.versions import compare_sides, group_by_event, load_policy, parse_mentions  # noqa: E402

OUT = ROOT / "eval" / "fixtures" / "versions_snapshot.json"
BASE = "http://data.gdeltproject.org/gdeltv2/"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}
WORLD = (-90.0, 90.0, -180.0, 180.0)
MIN_SIDES = 2
MIN_ARTICLES_PER_SIDE = 1   # pomiar: przy 2 zostaja 3 wydarzenia na swiecie, przy 1 - 22


def stamps(hours: float) -> list[str]:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    now -= timedelta(minutes=now.minute % 15 + 30)
    return [(now - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S") for i in range(int(hours * 4))]


def download(stamp: str, kind: str) -> list[str] | None:
    """kind: 'export' / 'mentions' / 'translation.export' / 'translation.mentions'."""
    try:
        response = requests.get(f"{BASE}{stamp}.{kind}.CSV.zip", headers=HEADERS, timeout=120)
        if response.status_code != 200:
            return None
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            return z.read(z.namelist()[0]).decode("utf-8", "replace").splitlines()
    except Exception:
        return None


def download_both(stamp: str, kind: str) -> list[str]:
    """English stream plus the translingual one.

    Measured 2026-09-27: in the English stream only 9% of mentions come from an outlet we can place
    on a side, and Russian or Ukrainian media barely appear. In the translation stream it is 35%,
    with real RU, UA and PL coverage - that is where the second version of a story lives.
    """
    rows = download(stamp, kind) or []
    rows += download(stamp, f"translation.{kind}") or []
    return rows


def main() -> int:
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    events: dict[str, object] = {}
    mentions = []

    for i, stamp in enumerate(stamps(hours), start=1):
        for event in in_box(parse_rows(download_both(stamp, "export")), *WORLD):
            events[event.id] = event
        mentions.extend(parse_mentions(download_both(stamp, "mentions")))
        if i % 4 == 0:
            print(f"  {i} paczek: zdarzen {len(events)}, wzmianek {len(mentions)}", flush=True)
        time.sleep(0.4)

    by_event = group_by_event(mentions)
    print(f"\nzdarzen: {len(events)}, wzmianek: {len(mentions)}, zdarzen ze wzmiankami: "
          f"{sum(1 for e in events if e in by_event)}")

    rozbieznosci = []
    for event_id, group in by_event.items():
        event = events.get(event_id)
        if event is None:
            continue
        versions = compare_sides(group, min_articles=MIN_ARTICLES_PER_SIDE)
        if versions is None or len(versions.sides) < MIN_SIDES:
            continue
        rozbieznosci.append((versions, event))

    rozbieznosci.sort(key=lambda pair: -pair[0].tone_gap)
    print(f"zdarzen opisanych przez co najmniej {MIN_SIDES} strony (po {MIN_ARTICLES_PER_SIDE}+ artykulow): "
          f"{len(rozbieznosci)}")

    print("\nnajwieksze roznice w wydzwieku relacji:")
    for versions, event in rozbieznosci[:10]:
        opis = " | ".join(f"{s.side}: {s.articles} art., ton {s.mean_tone:+.1f}" for s in versions.sides)
        slabo = " (cienka podstawa)" if versions.is_weak else ""
        print(f"  roznica {versions.tone_gap:5.1f}  {event.summary[:42]:42s} {(event.place or '?')[:22]:22s}  {opis}{slabo}")

    OUT.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "hours": hours,
        "source": "GDELT 2.0 export + mentions",
        # Bez tego snapshot nie da sie odtworzyc: ten sam material pod inna polityka przypisan daje
        # inne strony, inne srednie i inna liczbe wydarzen z dwiema wersjami.
        "policy_version": load_policy().version,
        "policy_tld_fallback": load_policy().tld_fallback,
        "note": ("Roznica wydzwieku pokazuje, ze relacje sie roznia - nie kto ma racje. "
                 "Ton to cecha tekstu, nie swiata."),
        "events": [{
            "id": event.id, "summary": event.summary, "kind": event.kind, "place": event.place,
            "lat": event.lat, "lon": event.lon, "day": event.day.isoformat(),
            "conflict": event.is_conflict, "aid": event.is_aid,
            "tone_gap": versions.tone_gap, "articles": versions.total_articles, "weak": versions.is_weak,
            "sides": [{"side": s.side, "articles": s.articles, "tone": s.mean_tone,
                       "languages": list(s.languages), "examples": list(s.examples)} for s in versions.sides],
        } for versions, event in rozbieznosci],
    }), encoding="utf-8")
    print(f"\nzapisano {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
