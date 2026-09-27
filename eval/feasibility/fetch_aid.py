"""Who gave Ukraine how much: the Kiel Institute's Ukraine Support Tracker.

GDELT tells us that aid was reported; it does not say how much. The Kiel tracker does - one row per
donor country, split into financial, humanitarian and military, in billions of dollars, with a
distinction that matters and is usually lost in headlines:

  commitments  - what was promised
  allocations  - what was actually allocated

We read the allocations, because that is the number that reflects what has really moved, and we say
so on the map. Licence: free for research and non-commercial use, with attribution.

  python eval/feasibility/fetch_aid.py
"""
import json
import sys
from pathlib import Path

import openpyxl
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
XLSX = ROOT / "data" / "aid" / "ukraine_support_tracker.xlsx"
OUT = ROOT / "eval" / "fixtures" / "aid_snapshot.json"
URL = ("https://www.ifw-kiel.de/fileadmin/Dateiverwaltung/IfW-Publications/fis-import/"
       "fa51af99-bb76-4982-a39e-734c08b6467a-Ukraine_Support_Tracker_Release_30v2.xlsx")
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}

# Stolice, zeby dalo sie pokazac darczyncow na mapie (tylko ci, ktorzy cokolwiek przekazali).
CAPITALS = {
    "United States": (38.90, -77.04), "Germany": (52.52, 13.40), "United Kingdom": (51.51, -0.13),
    "Japan": (35.68, 139.69), "Canada": (45.42, -75.70), "Norway": (59.91, 10.75),
    "Netherlands": (52.37, 4.90), "Denmark": (55.68, 12.57), "Sweden": (59.33, 18.07),
    "Poland": (52.23, 21.01), "France": (48.86, 2.35), "Italy": (41.90, 12.50),
    "Finland": (60.17, 24.94), "Spain": (40.42, -3.70), "Belgium": (50.85, 4.35),
    "Czech Republic": (50.09, 14.42), "Czechia": (50.09, 14.42), "Austria": (48.21, 16.37),
    "Lithuania": (54.69, 25.28), "Latvia": (56.95, 24.11), "Estonia": (59.44, 24.75),
    "Ireland": (53.35, -6.26), "Portugal": (38.72, -9.14), "Greece": (37.98, 23.73),
    "Switzerland": (46.95, 7.45), "Australia": (-35.28, 149.13), "South Korea": (37.57, 126.98),
    "Korea": (37.57, 126.98), "Slovakia": (48.15, 17.11), "Slovenia": (46.06, 14.51),
    "Croatia": (45.81, 15.98), "Romania": (44.43, 26.10), "Bulgaria": (42.70, 23.32),
    "Hungary": (47.50, 19.04), "Luxembourg": (49.61, 6.13), "Iceland": (64.15, -21.94),
    "New Zealand": (-41.29, 174.78), "Turkey": (39.93, 32.87), "Cyprus": (35.19, 33.38),
    "Malta": (35.90, 14.51), "Taiwan": (25.03, 121.57), "China": (39.91, 116.39), "India": (28.61, 77.21),
}


def main() -> int:
    if not XLSX.exists():
        XLSX.parent.mkdir(parents=True, exist_ok=True)
        print("pobieram dane Instytutu Kilonskiego")
        response = requests.get(URL, headers=HEADERS, timeout=600)
        response.raise_for_status()
        XLSX.write_bytes(response.content)
        print(f"  {XLSX.stat().st_size // 1024} KB")

    workbook = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    sheet = workbook["Country Summary ($)"]
    rows = list(sheet.iter_rows(min_row=10, max_col=9, values_only=True))

    donors = []
    for row in rows:
        country = (row[1] or "").strip() if isinstance(row[1], str) else None
        if not country or country.lower().startswith(("total", "sum", "note")):
            continue
        financial, humanitarian, military, total = (row[4], row[5], row[6], row[7])
        if not isinstance(total, (int, float)) or total <= 0:
            continue
        lat_lon = CAPITALS.get(country)
        donors.append({
            "country": country,
            "eu": bool(row[2]),
            "financial_bn": round(float(financial or 0), 3),
            "humanitarian_bn": round(float(humanitarian or 0), 3),
            "military_bn": round(float(military or 0), 3),
            "total_bn": round(float(total), 3),
            "lat": lat_lon[0] if lat_lon else None,
            "lon": lat_lon[1] if lat_lon else None,
        })

    donors.sort(key=lambda d: -d["total_bn"])
    suma = sum(d["total_bn"] for d in donors)
    wojskowe = sum(d["military_bn"] for d in donors)
    na_mapie = sum(1 for d in donors if d["lat"] is not None)

    OUT.write_text(json.dumps({
        "source": "Kiel Institute, Ukraine Support Tracker (Release 30v2)",
        "note": "Wartosci przekazane (allocations), nie obiecane (commitments). Miliardy dolarow.",
        "url": "https://www.ifw-kiel.de/topics/war-against-ukraine/ukraine-support-tracker/",
        "total_bn": round(suma, 1),
        "military_bn": round(wojskowe, 1),
        "donors": donors,
    }), encoding="utf-8")

    print(f"darczyncow: {len(donors)} (na mapie {na_mapie}) | razem przekazane: {suma:.1f} mld $ "
          f"(w tym wojskowe {wojskowe:.1f} mld $)")
    print("\nnajwieksi:")
    for d in donors[:12]:
        print(f"  {d['country']:18s} razem {d['total_bn']:7.1f} mld $  "
              f"(wojskowe {d['military_bn']:6.1f} | finansowe {d['financial_bn']:6.1f} | humanitarne {d['humanitarian_bn']:5.1f})")
    print(f"\nzapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
