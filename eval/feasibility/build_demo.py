"""Builds a self-contained demo page: military aircraft, GPS interference and Baltic cables on one map.

No database, no Docker, no API keys. Aircraft come from one live read of adsb.lol, interference from
the frozen hour in eval/fixtures/d3_hour.json, cables from data/infrastructure/baltic_cables.geojson.
The data is embedded in the HTML, so the file works offline and can be sent to someone as is.

  python eval/feasibility/build_demo.py
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

import h3  # noqa: E402

from wachta_detectors.jamming import aggregate_jamming  # noqa: E402
from wachta_detectors.models import Position  # noqa: E402
from wachta_detectors.ais import decode_eta  # noqa: E402
from wachta_detectors.sanctions import SanctionIndex  # noqa: E402

OUT = ROOT / "docs" / "demo" / "index.html"
SHOT = ROOT / "docs" / "screenshots" / "demo.png"
CABLES = ROOT / "data" / "infrastructure" / "baltic_cables.geojson"
HOUR = ROOT / "eval" / "fixtures" / "d3_hour.json"
SHIPS = ROOT / "eval" / "fixtures" / "ships_snapshot.json"
SANCTIONS = ROOT / "data" / "sanctions" / "maritime.csv"
EVENTS = ROOT / "eval" / "fixtures" / "events_snapshot.json"
AID = ROOT / "eval" / "fixtures" / "aid_snapshot.json"
VERSIONS = ROOT / "eval" / "fixtures" / "versions_snapshot.json"
FRONTLINE = ROOT / "data" / "frontline" / "ukraine.geojson"
ANOMALIES = ROOT / "eval" / "fixtures" / "anomalies_snapshot.json"
LOITERS = ROOT / "eval" / "fixtures" / "loiters_snapshot.json"
GAPS = ROOT / "eval" / "fixtures" / "gaps_snapshot.json"
STS = ROOT / "eval" / "fixtures" / "sts_snapshot.json"
IDENTITY = ROOT / "eval" / "fixtures" / "identity_snapshot.json"
TRACKS = ROOT / "eval" / "fixtures" / "ship_tracks.json"
ANALYST = ROOT / "eval" / "fixtures" / "analyst_answers.json"
HEADERS = {"User-Agent": "wachta-demo/0.1 (non-commercial portfolio project)"}

SOURCES = [
    ("https://api.adsb.lol/v2/mil", True),
    ("https://api.adsb.lol/v2/point/55.0/20.0/250", False),
    ("https://api.adsb.lol/v2/point/60.0/24.0/250", False),
]
BALTIC = (53.0, 66.5, 8.0, 31.0)  # lat_min, lat_max, lon_min, lon_max
CABLE_COLOURS = {"power": "#7dd3fc", "telecom": "#c4b5fd", "pipeline": "#fbbf24"}


def fetch_aircraft() -> list[dict]:
    """One read per endpoint, ten seconds apart: simultaneous bursts are what adsb.lol answers with 429."""
    seen, out = set(), []
    for url, force_military in SOURCES:
        for attempt in range(3):
            response = requests.get(url, headers=HEADERS, timeout=60)
            if response.status_code == 200:
                break
            print(f"  HTTP {response.status_code}, czekam")
            time.sleep(30)
        else:
            print(f"  pomijam {url}")
            continue

        body = response.json()
        for a in body.get("ac", []):
            hex_id = a.get("hex")
            if not hex_id or hex_id in seen or "lat" not in a or "lon" not in a:
                continue
            military = force_military or bool(int(a.get("dbFlags", 0)) & 1)
            if not (BALTIC[0] <= a["lat"] <= BALTIC[1] and BALTIC[2] <= a["lon"] <= BALTIC[3]):
                continue
            seen.add(hex_id)
            alt = a.get("alt_baro")
            out.append({
                "hex": hex_id,
                "flight": (a.get("flight") or "").strip() or None,
                "type": a.get("t"),
                "military": military,
                "lat": a["lat"],
                "lon": a["lon"],
                "alt": alt if isinstance(alt, (int, float)) else None,
                "track": a.get("track"),
                "nac_p": a.get("nac_p"),
            })
        print(f"  {url.rsplit('/', 3)[-1]}: lacznie {len(out)} samolotow w AOI")
        time.sleep(10)
    return out


def jamming_features() -> list[dict]:
    raw = json.loads(HOUR.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    positions = [Position(p["hex"], p["lat"], p["lon"], p["alt_ft"], p["on_ground"], p["nac_p"], now)
                 for p in raw["positions"]]
    features = []
    for cell in aggregate_jamming(positions):
        if cell.level == "low":
            continue
        boundary = [[lon, lat] for lat, lon in h3.cell_to_boundary(cell.h3)]
        features.append({
            "type": "Feature",
            "properties": {"level": cell.level, "pct": round(cell.pct, 3),
                           "aircraft": cell.n_aircraft, "degraded": cell.n_degraded,
                           "colour": "#e63946" if cell.level == "high" else "#ffbe00"},
            "geometry": {"type": "Polygon", "coordinates": [boundary + [boundary[0]]]},
        })
    return features


def cable_features() -> list[dict]:
    data = json.loads(CABLES.read_text(encoding="utf-8"))
    for f in data["features"]:
        f["properties"]["colour"] = CABLE_COLOURS.get(f["properties"].get("kind"), "#94a3b8")
    return data["features"]


def ship_tracks() -> tuple[dict[str, list], dict]:
    """Observed tracks per ship: where it came from during our watch, not where the voyage began."""
    if not TRACKS.exists():
        return {}, {}
    data = json.loads(TRACKS.read_text(encoding="utf-8"))
    tracks = {}
    for t in data["tracks"]:
        points = [[f["lon"], f["lat"]] for f in t["fixes"]]
        if len(points) >= 3:
            tracks[str(t["mmsi"])] = {"path": points, "from": t["fixes"][0]["ts"], "to": t["fixes"][-1]["ts"]}
    return tracks, {"from": data.get("collected_from"), "to": data.get("collected_to")}


def ships_with_sanctions() -> tuple[list[dict], int, int]:
    """Live ships joined with the sanctions list. A match is a reason to look, not a verdict."""
    if not SHIPS.exists():
        print("  brak ships_snapshot.json - pomijam statki")
        return [], 0, 0
    ships = json.loads(SHIPS.read_text(encoding="utf-8"))["ships"]
    index = SanctionIndex.from_csv(SANCTIONS) if SANCTIONS.exists() else None

    out, flagged, shadow, sanctioned = [], 0, 0, 0
    for s in ships:
        match = index.match(imo=s.get("imo"), mmsi=s.get("mmsi")) if index else None
        if match:
            flagged += 1
            shadow += match.is_shadow_fleet
            sanctioned += match.is_sanctions_list
        eta = decode_eta(s.get("eta"))
        out.append({
            **{k: s[k] for k in ("mmsi", "imo", "name", "class", "destination", "lat", "lon", "sog", "nav_status")},
            "cog": s.get("cog"),
            "callsign": s.get("callsign"),
            "draught": s.get("draught_m"),
            "eta": str(eta) if eta else None,
            "risk": "; ".join(match.risk) if match else None,
            "kategoria": match.category if match else None,
            "shadow": bool(match and match.is_shadow_fleet),
            "sankcje": bool(match and match.is_sanctions_list),
            "flagged": bool(match),
        })
    return out, flagged, shadow, sanctioned


def land_events() -> tuple[list[dict], int]:
    """Events from GDELT: who did what to whom. Conflict and aid only - the rest is diplomatic noise."""
    if not EVENTS.exists():
        print("  brak events_snapshot.json - pomijam zdarzenia")
        return [], 0
    data = json.loads(EVENTS.read_text(encoding="utf-8"))
    wanted = [e for e in data["events"] if e["conflict"] or e["aid"]]
    return wanted, data.get("hours", 0)


def aid_donors() -> tuple[list[dict], float, float]:
    """Who gave how much (Kiel tracker): allocations, not promises."""
    if not AID.exists():
        print("  brak aid_snapshot.json - pomijam wsparcie")
        return [], 0.0, 0.0
    data = json.loads(AID.read_text(encoding="utf-8"))
    donors = [d for d in data["donors"] if d.get("lat") is not None]
    return donors, data.get("total_bn", 0.0), data.get("military_bn", 0.0)


def two_versions() -> list[dict]:
    """Events told by at least two sides, with how far apart the telling is."""
    if not VERSIONS.exists():
        print("  brak versions_snapshot.json - pomijam dwie wersje")
        return []
    data = json.loads(VERSIONS.read_text(encoding="utf-8"))
    return [e for e in data["events"] if e["tone_gap"] > 0][:120]


def frontline() -> dict:
    if not FRONTLINE.exists():
        print("  brak ukraine.geojson - pomijam linie frontu")
        return {"type": "FeatureCollection", "features": []}
    data = json.loads(FRONTLINE.read_text(encoding="utf-8"))
    # Obszary sporne sprzed 2022 zaciemniaja obraz biezacej wojny - zostawiamy tylko biezace kategorie.
    data["features"] = [f for f in data["features"] if f["properties"]["category"] in ("occupied", "liberated", "unknown")]
    return data


def anomalies() -> tuple[list[dict], float, float]:
    """Places whose report count broke their own rhythm."""
    if not ANOMALIES.exists():
        print("  brak anomalies_snapshot.json - pomijam anomalie")
        return [], 0.0, 0.0
    data = json.loads(ANOMALIES.read_text(encoding="utf-8"))
    return data["spikes"], data.get("window_hours", 0), data.get("baseline_hours", 0)


def loiters() -> list[dict]:
    """D2: aircraft that stopped travelling and started holding a station."""
    if not LOITERS.exists():
        print("  brak loiters_snapshot.json - pomijam tory dyzurne")
        return []
    return json.loads(LOITERS.read_text(encoding="utf-8"))["loiters"]


def gaps() -> tuple[list[dict], str]:
    """D4: ships that went quiet while sailing, in water where other ships were being heard."""
    if not GAPS.exists():
        print("  brak gaps_snapshot.json - pomijam ciche statki")
        return [], ""
    data = json.loads(GAPS.read_text(encoding="utf-8"))
    return data["gaps"], data.get("day", "")


def transfers() -> tuple[list[dict], str]:
    """D5: two cargo ships or tankers side by side away from any anchorage."""
    if not STS.exists():
        print("  brak sts_snapshot.json - pomijam przeladunki")
        return [], ""
    data = json.loads(STS.read_text(encoding="utf-8"))
    return [e for e in data["encounters"] if e["cargo_pair"]], data.get("day", "")


def identities() -> tuple[list[dict], str]:
    """D7: numbers whose track puts them in two places no hull could cover."""
    if not IDENTITY.exists():
        print("  brak identity_snapshot.json - pomijam tozsamosc")
        return [], ""
    data = json.loads(IDENTITY.read_text(encoding="utf-8"))
    return data["cases"], data.get("day", "")


def analyst_note() -> dict:
    """Zapisany przebieg analityka RAG: pytania, zdania przyjete i te, ktore odsialy bramki.

    Odrzucone nie sa bledem do ukrycia - to jedyny widoczny dowod, ze bramki cytowan i liczb
    w ogole dzialaja, wiec ida na strone razem z przyjetymi.
    """
    if not ANALYST.exists():
        print("  brak analyst_answers.json - pomijam notatke analityka")
        return {"model": "?", "embedder": "?", "documents": 0, "answers": []}
    return json.loads(ANALYST.read_text(encoding="utf-8"))


def main() -> int:
    print("pobieram samoloty (3 odczyty, 10 s odstepu)")
    aircraft = fetch_aircraft()
    jamming = jamming_features()
    cables = cable_features()
    ships, flagged, shadow, sanctioned = ships_with_sanctions()
    tracks, track_window = ship_tracks()
    events, event_hours = land_events()
    donors, aid_total, aid_military = aid_donors()
    versions = two_versions()
    spikes, spike_window, spike_baseline = anomalies()
    front = frontline()
    stations = loiters()
    silences, gap_day = gaps()
    meetings, sts_day = transfers()
    doubles, id_day = identities()
    rag = analyst_note()
    rag_accepted = sum(len(a["accepted"]) for a in rag["answers"])
    rag_rejected = sum(len(a["rejected"]) for a in rag["answers"])
    rag_empty = sum(1 for a in rag["answers"] if not a["accepted"])
    military = sum(1 for a in aircraft if a["military"])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"samolotow {len(aircraft)} (wojskowych {military}), heksow zaklocen {len(jamming)}, "
          f"odcinkow kabli {len(cables)}, statkow {len(ships)} (dopasowanych {flagged}, w tym sankcje {sanctioned}, flota cieni {shadow}), "
          f"tras statkow {len(tracks)}, zdarzen ladowych {len(events)} z {event_hours:.0f} h, darczyncow {len(donors)}, "
          f"dwie wersje {len(versions)}, obszarow frontu {len(front['features'])}, anomalii {len(spikes)}, "
          f"torow dyzurnych {len(stations)}, cichych statkow {len(silences)}, przeladunkow {len(meetings)}, tozsamosci {len(doubles)}")
    print(f"notatka analityka: pytan {len(rag['answers'])} (w tym 'brak danych' {rag_empty}), "
          f"zdan przyjetych {rag_accepted}, odrzuconych przez bramki {rag_rejected}")

    page = (ROOT / "eval" / "feasibility" / "demo_template.html").read_text(encoding="utf-8")
    page = (page
            .replace("__AIRCRAFT__", json.dumps(aircraft))
            .replace("__JAMMING__", json.dumps({"type": "FeatureCollection", "features": jamming}))
            .replace("__CABLES__", json.dumps({"type": "FeatureCollection", "features": cables}))
            .replace("__STAMP__", stamp)
            .replace("__N_AIRCRAFT__", str(len(aircraft)))
            .replace("__N_MILITARY__", str(military))
            .replace("__N_JAMMING__", str(len(jamming)))
            .replace("__N_CABLES__", str(len(cables)))
            .replace("__SHIPS__", json.dumps(ships))
            .replace("__N_SHIPS__", str(len(ships)))
            .replace("__N_FLAGGED__", str(flagged))
            .replace("__N_SANCTIONED__", str(sanctioned))
            .replace("__N_INSPECTED__", str(flagged - sanctioned))
            .replace("__N_SHADOW__", str(shadow))
            .replace("__EVENTS__", json.dumps(events))
            .replace("__N_EVENTS__", str(len(events)))
            .replace("__N_CONFLICT__", str(sum(1 for e in events if e["conflict"])))
            .replace("__N_AID__", str(sum(1 for e in events if e["aid"])))
            .replace("__EVENT_HOURS__", f"{event_hours:.0f}")
            .replace("__AID__", json.dumps(donors))
            .replace("__AID_TOTAL__", f"{aid_total:.0f}")
            .replace("__AID_MILITARY__", f"{aid_military:.0f}")
            .replace("__VERSIONS__", json.dumps(versions))
            .replace("__N_VERSIONS__", str(len(versions)))
            .replace("__FRONTLINE__", json.dumps(front))
            .replace("__N_FRONT__", str(len(front["features"])))
            .replace("__ANOMALIES__", json.dumps(spikes))
            .replace("__IDENTITY__", json.dumps(doubles))
            .replace("__N_IDENTITY__", str(len(doubles)))
            .replace("__ID_DAY__", id_day)
            .replace("__STS__", json.dumps(meetings))
            .replace("__N_STS__", str(len(meetings)))
            .replace("__STS_DAY__", sts_day)
            .replace("__GAPS__", json.dumps(silences))
            .replace("__N_GAPS__", str(len(silences)))
            .replace("__GAP_DAY__", gap_day)
            .replace("__LOITERS__", json.dumps(stations))
            .replace("__N_LOITERS__", str(len(stations)))
            .replace("__N_TANKERS__", str(sum(1 for s in stations if s["kind"] == "tankowiec")))
            .replace("__N_ANOMALIES__", str(len(spikes)))
            .replace("__SPIKE_WINDOW__", f"{spike_window:.0f}")
            .replace("__TRACKS__", json.dumps(tracks))
            .replace("__N_TRACKS__", str(len(tracks)))
            .replace("__TRACK_FROM__", (track_window.get("from") or "")[11:16])
            .replace("__TRACK_TO__", (track_window.get("to") or "")[11:16])
            .replace("__ANALYST__", json.dumps(rag))
            .replace("__RAG_MODEL__", str(rag.get("model", "?")))
            .replace("__RAG_EMBEDDER__", str(rag.get("embedder", "?")))
            .replace("__RAG_DOCS__", str(rag.get("documents", 0)))
            .replace("__N_RAG_Q__", str(len(rag["answers"])))
            .replace("__N_RAG_ACCEPTED__", str(rag_accepted))
            .replace("__N_RAG_REJECTED__", str(rag_rejected)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"strona: {OUT} ({OUT.stat().st_size // 1024} KB)")

    shot = ROOT / "web" / "demo_shot.mjs"
    shot.write_text(
        'import { chromium } from "playwright";\n'
        "const browser = await chromium.launch();\n"
        'const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });\n'
        f'await page.goto("file:///{OUT.as_posix()}");\n'
        # Sygnatura to waitForFunction(fn, arg, options). Opcje podane jako drugi argument trafialy
        # do funkcji jako jej parametr, a limit czasu zostawal domyslny - przez co "timeout: 90000"
        # nigdy nie dzialal i przy kilkunastu warstwach zrzut wywalal sie po 30 sekundach.
        "await page.waitForFunction(() => window.mapReady === true, null, "
        "{ timeout: 180000, polling: 500 });\n"
        "await page.waitForTimeout(3000);\n"
        "const counts = await page.evaluate(() => window.__counts);\n"
        "console.log('WARSTWY ' + JSON.stringify(counts));\n"
        "const dead = Object.entries(counts).filter(([, n]) => n <= 0);\n"
        "if (dead.length) { console.error('PUSTE WARSTWY ' + JSON.stringify(dead)); process.exit(2); }\n"
        # Panel analityka nie jest warstwa mapy, wiec ma wlasna kontrole: brak pytan = blad budowania.
        "const rag = await page.evaluate(() => ({ pytania: window.__ragCount || 0, "
        "zdania: document.querySelectorAll('#rag-body .rag-sent, #rag-body .rag-empty').length }));\n"
        "console.log('ANALITYK ' + JSON.stringify(rag));\n"
        "if (!rag.pytania || !rag.zdania) { console.error('PUSTY PANEL ANALITYKA'); process.exit(3); }\n"
        f'await page.screenshot({{ path: "{SHOT.as_posix()}" }});\n'
        "await browser.close();\n", encoding="utf-8")
    try:
        result = subprocess.run(["node", "demo_shot.mjs"], cwd=ROOT / "web", capture_output=True, text=True, timeout=180)
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            print("zrzut nieudany:", (result.stderr or "")[-400:])
            return 1
    finally:
        shot.unlink(missing_ok=True)
    print(f"zrzut: {SHOT} ({SHOT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
