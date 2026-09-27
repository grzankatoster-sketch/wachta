"""Freezes Baltic submarine cables and pipelines from OpenStreetMap into a GeoJSON file.

EMODnet has the pipelines but no cables for the Gulf of Finland (checked 2026-09-22), so OSM is the
source for D6 (a ship dragging its anchor over a cable). Only named lines are kept — unnamed
fragments are mostly shore connections and would drown the map.

Whole-Baltic queries time out (504) and so do six-clause ones, so the work is split by area and by
category, and the mirrors are tried in turn.

  python eval/feasibility/fetch_cables.py
"""
import json
import sys
import time
from pathlib import Path

import requests

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Smaller tiles: a 3x7 degree box with "out geom" is already too heavy for Overpass (504).
CHUNKS = {
    "ciesniny dunskie": "53.5,9.0,56.5,13.0",
    "poludniowy Baltyk zachod": "53.5,13.0,56.5,17.5",
    "poludniowy Baltyk wschod": "53.5,17.5,56.5,22.0",
    "srodkowy Baltyk zachod": "56.5,15.0,59.0,19.5",
    "srodkowy Baltyk wschod": "56.5,19.5,59.0,24.0",
    "Zatoka Finska zachod": "58.5,21.0,60.5,25.5",
    "Zatoka Finska wschod": "58.5,25.5,61.0,30.5",
    "Zatoka Botnicka poludnie": "59.0,16.0,62.5,23.0",
    "Zatoka Botnicka polnoc": "62.5,16.0,66.0,26.0",
}

# One clause per request: two clauses with "out geom" over a large bbox already give 504.
CLAUSES = [
    ("kabel energetyczny (underwater)", 'way["location"="underwater"]["power"="cable"]({bbox});'),
    ("kabel energetyczny (submarine)", 'way["submarine"="yes"]["power"="cable"]({bbox});'),
    ("kabel telekom (communication)", 'way["location"="underwater"]["communication"="line"]({bbox});'),
    ("kabel telekom (telecom)", 'way["location"="underwater"]["telecom"="line"]({bbox});'),
    ("rurociag (submarine)", 'way["submarine"="yes"]["man_made"="pipeline"]({bbox});'),
    ("rurociag (underwater)", 'way["location"="underwater"]["man_made"="pipeline"]({bbox});'),
]

OUT = Path(__file__).resolve().parents[2] / "data" / "infrastructure" / "baltic_cables.geojson"
HEADERS = {"User-Agent": "wachta-infrastructure/0.1 (non-commercial portfolio project)"}

# Cables and pipelines damaged in the incidents that D6 is evaluated against.
# OSM nazywa te same linie roznie ("Baltic Connector" na morzu, "Balticconnector" na ladzie),
# wiec porownanie ignoruje spacje i myslniki.
INCIDENT_LINES = ["estlink2", "clion1", "bcsnorth", "balticconnector"]


def build_query(bbox: str, clauses: list[str]) -> str:
    lines = ["[out:json][timeout:90];", "("]
    lines += [c.format(bbox=bbox) for c in clauses]
    lines += [");", "out geom;"]
    return "\n".join(lines)


def ask_overpass(bbox: str, clauses: list[str]) -> list:
    query = build_query(bbox, clauses)
    last = None
    for attempt, server in enumerate(OVERPASS_SERVERS * 2, start=1):
        try:
            response = requests.post(server, data={"data": query}, headers=HEADERS, timeout=180)
            response.raise_for_status()
            return response.json()["elements"]
        except requests.HTTPError as e:
            code = e.response.status_code
            last = f"{server.split('/')[2]}: HTTP {code}"
            print(f"    nieudane ({attempt}/4) - {last}")
            # 429 = limit slotow Overpass, 504 = zapytanie za ciezkie dla serwera
            time.sleep(90 if code == 429 else 15)
        except Exception as e:
            last = f"{server.split('/')[2]}: {type(e).__name__}"
            print(f"    nieudane ({attempt}/4) - {last}")
            time.sleep(15)
    print(f"    POMIJAM ten fragment - Overpass odmowil ({last})")
    return []


def kind(tags: dict) -> str:
    if tags.get("man_made") == "pipeline":
        return "pipeline"
    if tags.get("power") == "cable":
        return "power"
    return "telecom"


def main() -> int:
    elements, skipped = [], []
    for label, bbox in CHUNKS.items():
        print(f"pytam Overpass: {label}")
        for label_clause, clause in CLAUSES:
            got = ask_overpass(bbox, [clause])
            if got is None:
                got = []
            if not got:
                skipped.append(f"{label} / {label_clause}")
            print(f"  {label_clause}: {len(got)}")
            elements.extend(got)
            time.sleep(8)

    # Repeated runs accumulate: a fragment that fell over with 504 last time can be filled in later.
    features, seen_ids = [], set()
    if OUT.exists():
        previous = json.loads(OUT.read_text(encoding="utf-8")).get("features", [])
        features.extend(previous)
        seen_ids.update(f["properties"]["osm_id"] for f in previous)
        print(f"wczytano {len(previous)} odcinkow z poprzedniego przebiegu")
    for e in elements:
        tags = e.get("tags") or {}
        name, geometry = tags.get("name"), e.get("geometry")
        if not name or not geometry or len(geometry) < 2 or e["id"] in seen_ids:
            continue
        seen_ids.add(e["id"])
        features.append({
            "type": "Feature",
            "properties": {"osm_id": e["id"], "name": name, "kind": kind(tags), "operator": tags.get("operator")},
            "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in geometry]},
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "source": "OpenStreetMap contributors, ODbL - Overpass API",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chunks": CHUNKS,
        "features": features,
    }), encoding="utf-8")

    names = sorted({f["properties"]["name"] for f in features})
    if skipped:
        print(f"fragmenty bez wyniku ({len(skipped)}): " + "; ".join(skipped[:8]))
    print(f"\nzapisano {len(features)} odcinkow ({len(names)} nazw), {OUT.stat().st_size // 1024} KB -> {OUT}")

    flat = [n.lower().replace(" ", "").replace("-", "") for n in names]
    missing = [c for c in INCIDENT_LINES if not any(c in n for n in flat)]
    if missing:
        print("UWAGA, brak linii z incydentow:", missing)
        return 1
    print("linie z incydentow obecne:", ", ".join(INCIDENT_LINES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
