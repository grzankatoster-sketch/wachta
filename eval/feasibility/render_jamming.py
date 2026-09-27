"""Renders the D3 result for the frozen hour as a standalone map image.

Runs the production aggregation on eval/fixtures/d3_hour.json, writes the cells to GeoJSON, builds a
self-contained HTML map and screenshots it with Playwright. No database, no API — this is the proof
that the detector produces something real before the stack exists.

  python eval/feasibility/render_jamming.py
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

import h3  # noqa: E402

from wachta_detectors.jamming import aggregate_jamming  # noqa: E402
from wachta_detectors.models import Position  # noqa: E402

FIXTURE = ROOT / "eval" / "fixtures" / "d3_hour.json"
GEOJSON = ROOT / "eval" / "results" / "d3_cells.geojson"
HTML = ROOT / "eval" / "results" / "d3_map.html"
SHOT = ROOT / "docs" / "screenshots" / "zaklocenia-gps.png"

COLOURS = {"high": "#e63946", "medium": "#ffbe00", "low": "#4b5563"}

PAGE = """<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<title>WACHTA — zakłócenia GPS</title>
<link href="https://unpkg.com/maplibre-gl@5.9.0/dist/maplibre-gl.css" rel="stylesheet">
<style>
  body {{ margin: 0; background: #0d1117; color: #e6edf3; font-family: system-ui, sans-serif; }}
  #map {{ position: absolute; inset: 0; }}
  .box {{ position: absolute; z-index: 1; background: #0d1117e6; border-radius: 8px; padding: 10px 14px; font-size: 13px; }}
  #title {{ top: 12px; left: 12px; }}
  #legend {{ bottom: 12px; left: 12px; font-size: 12px; }}
  #legend i {{ display: inline-block; width: 11px; height: 11px; margin: 0 5px 0 10px; }}
  b {{ font-size: 15px; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="box" id="title"><b>Zakłócenia GPS nad Bałtykiem</b><br>{subtitle}</div>
<div class="box" id="legend">
  udział samolotów z osłabionym GPS:
  <i style="background:#ffbe00"></i> 2–10%
  <i style="background:#e63946"></i> ≥ 10%
  <br>dane: adsb.lol (ODbL) · podkład: OpenFreeMap, © OpenStreetMap contributors
</div>
<script src="https://unpkg.com/maplibre-gl@5.9.0/dist/maplibre-gl.js"></script>
<script>
const cells = {geojson};
const map = new maplibregl.Map({{
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  center: [20.5, 57.5], zoom: 4.7, attributionControl: false,
}});
map.on("load", () => {{
  map.addSource("cells", {{ type: "geojson", data: cells }});
  map.addLayer({{ id: "fill", type: "fill", source: "cells",
    paint: {{ "fill-color": ["get", "colour"], "fill-opacity": ["get", "opacity"] }} }});
  map.addLayer({{ id: "line", type: "line", source: "cells",
    paint: {{ "line-color": ["get", "colour"], "line-width": 1, "line-opacity": 0.8 }} }});
  window.mapReady = true;
}});
</script>
</body>
</html>
"""


def main() -> int:
    if not FIXTURE.exists():
        print(f"brak {FIXTURE} - najpierw zbierz dane (collect_hour.py albo export_d3_fixture.py)")
        return 1

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    positions = [Position(p["hex"], p["lat"], p["lon"], p["alt_ft"], p["on_ground"], p["nac_p"], now)
                 for p in raw["positions"]]
    from wachta_detectors.jamming import aggregate_jamming as _agg
    min_aircraft = _agg.__defaults__[2]  # produkcyjny prog, zeby podpis nie klamal
    cells = aggregate_jamming(positions)
    by_level = {level: sum(1 for c in cells if c.level == level) for level in ("low", "medium", "high")}
    print(f"pozycji: {len(positions)}, komorek: {len(cells)}, w tym {by_level['high']} wysokich i {by_level['medium']} srednich")

    features = []
    for c in cells:
        boundary = [[lon, lat] for lat, lon in h3.cell_to_boundary(c.h3)]
        features.append({
            "type": "Feature",
            "properties": {"h3": c.h3, "pct": round(c.pct, 3), "level": c.level,
                           "colour": COLOURS[c.level], "opacity": 0.15 if c.level == "low" else 0.55,
                           "aircraft": c.n_aircraft, "degraded": c.n_degraded},
            "geometry": {"type": "Polygon", "coordinates": [boundary + [boundary[0]]]},
        })
    geojson = {"type": "FeatureCollection", "features": features}
    GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON.write_text(json.dumps(geojson), encoding="utf-8")

    window = f"{raw.get('collected_from', '?')[11:16]}–{raw.get('collected_to', '?')[11:16]} UTC, {raw.get('collected_from', '?')[:10]}"
    subtitle = (f"{window} · {len(positions)} pozycji · {len(cells)} komórek H3 "
                f"(min. {min_aircraft} samolotów) · {by_level['high']} z dolną granicą udziału ≥ 10%")
    HTML.write_text(PAGE.format(geojson=json.dumps(geojson), subtitle=subtitle), encoding="utf-8")
    print(f"mapa: {HTML}")

    shot_script = f"""
import {{ chromium }} from "playwright";
const browser = await chromium.launch();
const page = await browser.newPage({{ viewport: {{ width: 1600, height: 1000 }} }});
await page.goto("file:///{HTML.as_posix()}");
await page.waitForFunction(() => window.mapReady === true, {{ timeout: 60000 }});
await page.waitForTimeout(6000);
await page.screenshot({{ path: "{SHOT.as_posix()}" }});
await browser.close();
"""
    script_path = ROOT / "web" / "render_shot.mjs"
    script_path.write_text(shot_script, encoding="utf-8")
    try:
        result = subprocess.run(["node", "render_shot.mjs"], cwd=ROOT / "web", capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            print("zrzut nieudany:", result.stderr[-400:])
            return 1
    finally:
        script_path.unlink(missing_ok=True)

    print(f"zrzut: {SHOT} ({SHOT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
