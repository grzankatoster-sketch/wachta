"""Downloads the OpenSanctions maritime dataset (one CSV, about 5 MB) and reports what is in it.

Licence: free for non-commercial use, which this project is. The file is not committed - it changes
constantly and is one command away.

  python eval/feasibility/fetch_sanctions.py
"""
import sys
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.sanctions import SanctionIndex  # noqa: E402

URL = "https://data.opensanctions.org/datasets/latest/maritime/maritime.csv"
OUT = ROOT / "data" / "sanctions" / "maritime.csv"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}


def main() -> int:
    print(f"pobieram {URL}")
    response = requests.get(URL, headers=HEADERS, timeout=300)
    response.raise_for_status()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(response.content)
    print(f"zapisano {OUT.stat().st_size // 1024} KB -> {OUT}")

    index = SanctionIndex.from_csv(OUT)
    risks: Counter[str] = Counter()
    for match in index._by_imo.values():  # noqa: SLF001 - skrypt diagnostyczny
        risks.update(match.risk or ("(brak etykiety)",))
    print(f"statkow z numerem IMO: {len(index)}")
    for risk, n in risks.most_common(8):
        print(f"  {risk:16s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
