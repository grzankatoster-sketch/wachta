"""Downloads a couple of days of world events and looks for places breaking their own rhythm.

Window and baseline are deliberately explicit: the last N hours against the preceding M, per grid
cell, judged by a Poisson tail rather than a ratio. A place that always makes the news does not
become an anomaly by making it again.

  python eval/feasibility/run_anomalies.py [godzin_lacznie] [godzin_okna]
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

from wachta_detectors.anomalies import detect_spikes  # noqa: E402
from wachta_detectors.events import parse_rows  # noqa: E402

OUT = ROOT / "eval" / "fixtures" / "anomalies_snapshot.json"
BASE = "http://data.gdeltproject.org/gdeltv2/"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}


def fetch(hours: float) -> list:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    now -= timedelta(minutes=now.minute % 15 + 30)
    events, missing = [], 0
    for i in range(int(hours * 4)):
        stamp = (now - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S")
        for kind in ("export", "translation.export"):
            try:
                response = requests.get(f"{BASE}{stamp}.{kind}.CSV.zip", headers=HEADERS, timeout=120)
                if response.status_code != 200:
                    missing += 1
                    continue
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    rows = z.read(z.namelist()[0]).decode("utf-8", "replace").splitlines()
                events.extend(parse_rows(rows))
            except Exception:
                missing += 1
        if (i + 1) % 16 == 0:
            print(f"  {i + 1} okien, zdarzen {len(events)}", flush=True)
        time.sleep(0.25)
    print(f"pobrano {len(events)} zdarzen, brakujacych plikow: {missing}")
    return events


def main() -> int:
    total_hours = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
    window_hours = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0

    events = fetch(total_hours)
    now = datetime.now(timezone.utc)
    spikes = detect_spikes(events, now,
                           window=timedelta(hours=window_hours),
                           baseline=timedelta(hours=total_hours - window_hours))

    print(f"\nokno: ostatnie {window_hours:.0f} h, tlo: poprzednie {total_hours - window_hours:.0f} h")
    print(f"miejsc z nietypowym skupiskiem: {len(spikes)}\n")
    for s in spikes[:20]:
        print(f"  p={s.p_value:.1e}  {s.recent:3d} zdarzen (spodziewane {s.expected:5.2f}, "
              f"x{s.times_over:5.1f})  {(s.place or '?')[:34]:34s} {', '.join(s.kinds)[:40]}")

    OUT.write_text(json.dumps({
        "fetched_at": now.isoformat(),
        "window_hours": window_hours,
        "baseline_hours": total_hours - window_hours,
        "source": "GDELT 2.0 export + translation.export",
        "note": ("Skupisko DONIESIEN, nie potwierdzonych zdarzen. Nagly wzrost moze oznaczac walki, "
                 "ale rownie dobrze jedna konferencje prasowa podchwycona przez wiele redakcji."),
        "spikes": [{
            "lat": s.lat, "lon": s.lon, "place": s.place, "recent": s.recent,
            "expected": s.expected, "p_value": s.p_value, "times_over": s.times_over,
            "kinds": list(s.kinds), "examples": list(s.examples),
        } for s in spikes],
    }), encoding="utf-8")
    print(f"\nzapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
