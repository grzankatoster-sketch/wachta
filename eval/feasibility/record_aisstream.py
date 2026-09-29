"""Records a real AISStream sample, so the offline test can stop running on a synthesised one.

The parser in wachta_detectors/aisstream.py was written and tested before this project had a key.
Its fixture (src/python/tests/tests fixtures, aisstream_sample.jsonl) was built field by field from
aisstream.io's own OpenAPI models - honest, but not the same thing as traffic. The moment a key
exists, run this and overwrite the fixture with what the socket actually sent:

  AISSTREAM_API_KEY=... py eval/feasibility/record_aisstream.py 60 > src/python/tests/fixtures/aisstream_sample.jsonl

The argument is how many seconds to listen. Nothing here writes to the database.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.aisstream import BALTIC_SOUTH, USER_AGENT, URL, subscription  # noqa: E402
from wachta_detectors.websocket import WebSocket  # noqa: E402

key = (os.environ.get("AISSTREAM_API_KEY") or "").strip()
if not key:
    sys.exit("brak AISSTREAM_API_KEY - instrukcja zdobycia klucza w docs/SOURCES.md")

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
deadline = datetime.now(timezone.utc) + timedelta(seconds=seconds)

socket = WebSocket.connect(URL, headers={"User-Agent": USER_AGENT})
socket.settimeout(seconds + 30)
try:
    socket.send_text(json.dumps(subscription(key)))
    count = 0
    while datetime.now(timezone.utc) < deadline:
        text = socket.recv_text()
        if text is None:
            break
        # Jedna wiadomosc na linie, bez formatowania: plik ma byc dokladnie tym, co przyszlo.
        print(text.replace("\n", " "))
        count += 1
finally:
    socket.close()
print(f"# {count} wiadomosci w {seconds:.0f} s, pudelko {BALTIC_SOUTH.as_pairs()}", file=sys.stderr)
