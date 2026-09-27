"""Front line in Ukraine from DeepStateMap, normalised to three categories.

DeepStateMap is a Ukrainian volunteer project; its "last map" endpoint is public and widely reused.
The response carries no licence statement, so: local use with attribution, and **before any public
demo we ask them for permission**. That caveat lives in docs/SOURCES.md, not only in this comment.

Their polygons are labelled in three languages in one string, e.g.
    "Окуповано /// Occupied /// geoJSON.status.occupied"
which is what the status marker at the end is for.

  python eval/feasibility/fetch_frontline.py
"""
import json
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "frontline" / "ukraine.geojson"
URL = "https://deepstatemap.live/api/history/last"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}

# Kolory rozne od naszych warstw morskich, zeby mapa pozostala czytelna.
# Znaczniki uzywane przez zrodlo (sprawdzone 2026-09-27): status.occupied, status.dismissed (wyzwolone),
# status.dismissed_at {{at:DD.MM}}, status.unknown oraz territories.* dla obszarow spornych sprzed 2022.
CATEGORIES = {
    "occupied": ("okupowane", "#7f1d1d"),
    "liberated": ("wyzwolone", "#166534"),
    "unknown": ("status nieznany", "#78716c"),
    "territory": ("obszar sporny sprzed 2022", "#92400e"),
    "other": ("inne", "#57534e"),
}


def classify(name: str) -> str:
    marker = name.rsplit("///", 1)[-1].strip().lower()
    if "status.occupied" in marker:
        return "occupied"
    if "status.dismissed" in marker:      # zrodlo nazywa tak obszary wyzwolone
        return "liberated"
    if "status.unknown" in marker:
        return "unknown"
    if "territories." in marker:
        return "territory"
    return "other"


def english_name(name: str) -> str:
    parts = [p.strip() for p in name.split("///")]
    return parts[1] if len(parts) > 1 else parts[0]


def main() -> int:
    print(f"pobieram {URL}")
    response = requests.get(URL, headers=HEADERS, timeout=180)
    response.raise_for_status()
    payload = response.json()

    features, counts = [], {}
    for f in payload["map"]["features"]:
        if f["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            continue
        name = (f["properties"].get("name") or "").strip()
        category = classify(name)
        counts[category] = counts.get(category, 0) + 1
        label, colour = CATEGORIES[category]
        features.append({
            "type": "Feature",
            "properties": {"category": category, "label": label, "colour": colour, "name": english_name(name)},
            "geometry": f["geometry"],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "source": "DeepStateMap (deepstatemap.live) - projekt wolontariuszy, uzycie niekomercyjne z atrybucja",
        "map_datetime": payload.get("datetime"),
        "fetched_from": URL,
        "features": features,
    }), encoding="utf-8")

    print(f"stan mapy wg zrodla: {payload.get('datetime')}")
    print(f"obszarow: {len(features)} -> " + ", ".join(f"{CATEGORIES[k][0]}: {v}" for k, v in sorted(counts.items())))
    print(f"zapisano {OUT} ({OUT.stat().st_size // 1024} KB)")
    print("\nUWAGA: zrodlo bez podanej licencji. Przed publicznym demem trzeba zapytac autorow o zgode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
