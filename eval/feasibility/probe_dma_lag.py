"""How stale is the Danish AIS archive? HEAD one file per day, newest first.

The answer decides whether DMA can ever be a live source (it cannot) or only a backtest corpus.

  py eval/feasibility/probe_dma_lag.py [ile_dni]
"""
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")
UA = "wachta-project/0.1 (situational awareness, non-commercial)"
BUCKET = "http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/"

days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
for back in range(1, days + 1):
    day = (datetime.now(timezone.utc) - timedelta(days=back)).strftime("%Y-%m-%d")
    url = f"{BUCKET}{day[:4]}/aisdk-{day}.zip"
    request = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            size = int(response.headers.get("Content-Length", 0))
        print(f"OK  {day} (-{back} d): {size / 1_048_576:.0f} MB")
    except urllib.error.HTTPError as exc:
        print(f"ERR {day} (-{back} d): HTTP {exc.code}")
    except Exception as exc:
        print(f"ERR {day} (-{back} d): {exc!r}"[:120])
