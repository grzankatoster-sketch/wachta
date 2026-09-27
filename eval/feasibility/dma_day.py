"""Downloads one day of Danish AIS data and keeps only what happened near a cable or pipeline.

Coverage note: the Danish dataset covers Danish waters and the approaches, not the Gulf of Finland,
so the Eagle S episode over Estlink 2 is NOT in it. What it does give is a full day of real traffic
over real infrastructure (Nord Stream, Baltic Pipe, the power links through the straits), which is
exactly what is needed to answer the question that decides whether D6 is usable at all: how often
does it fire on ships that are simply going about their business.

  python eval/feasibility/dma_day.py 2024-12-25
"""
import io
import json
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.infrastructure import load_lines  # noqa: E402

BUCKET = "http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/"
CABLES = ROOT / "data" / "infrastructure" / "baltic_cables.geojson"
CACHE = ROOT / "data" / "dma"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}

GRID = 0.05          # ~5,5 km w pionie; komorka siatki do szybkiego odsiewu
NEAR_CELLS = 2       # ile komorek dookola trasy kabla uznajemy za "blisko"
MIN_FIXES = 5


def download(day: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"aisdk-{day}.zip"
    if target.exists():
        print(f"mam juz {target.name} ({target.stat().st_size // 1_048_576} MB)")
        return target

    url = f"{BUCKET}{day[:4]}/aisdk-{day}.zip"
    print(f"pobieram {url}")
    with requests.get(url, headers=HEADERS, stream=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with target.open("wb") as f:
            for chunk in r.iter_content(chunk_size=4 * 1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1_048_576:6.0f} / {total / 1_048_576:.0f} MB", end="", flush=True)
    print(f"\nzapisano {target}")
    return target


def cable_cells() -> set[tuple[int, int]]:
    """Coarse grid cells covering the cable routes - a cheap first filter before any real distance."""
    cells: set[tuple[int, int]] = set()
    for line in load_lines(CABLES):
        for lat, lon in line.coords:
            base_lat, base_lon = int(lat / GRID), int(lon / GRID)
            for d_lat in range(-NEAR_CELLS, NEAR_CELLS + 1):
                for d_lon in range(-NEAR_CELLS, NEAR_CELLS + 1):
                    cells.add((base_lat + d_lat, base_lon + d_lon))
    return cells


def parse_day(zip_path: Path, day: str) -> dict:
    cells = cable_cells()
    print(f"komorek siatki wokol kabli: {len(cells)}")

    fixes: dict[str, list[dict]] = defaultdict(list)
    names: dict[str, dict] = {}
    rows = kept = 0

    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        print(f"czytam {name}")
        with z.open(name) as raw, io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="") as text:
            header = text.readline().split(",")
            # naglowek zaczyna sie od "# Timestamp" - stad obcinanie krat i cudzyslowow
            idx = {h.strip().strip('"#').strip().lower(): i for i, h in enumerate(header)}
            col = {k: idx.get(k) for k in ("timestamp", "mmsi", "latitude", "longitude", "sog", "cog", "imo", "name", "ship type")}
            brakuje = [k for k, v in col.items() if v is None]
            if brakuje:
                raise SystemExit(f"brak kolumn w pliku: {brakuje}; naglowek: {[h.strip() for h in header]}")

            for line in text:
                rows += 1
                if rows % 5_000_000 == 0:
                    print(f"  {rows / 1e6:.0f} mln wierszy, zachowanych {kept}", flush=True)
                parts = line.split(",")
                if len(parts) <= (col["longitude"] or 0):
                    continue
                try:
                    lat = float(parts[col["latitude"]])
                    lon = float(parts[col["longitude"]])
                except ValueError:
                    continue
                if (int(lat / GRID), int(lon / GRID)) not in cells:
                    continue

                mmsi = parts[col["mmsi"]].strip()
                try:
                    sog = float(parts[col["sog"]]) if parts[col["sog"]].strip() else None
                    cog = float(parts[col["cog"]]) if parts[col["cog"]].strip() else None
                except ValueError:
                    sog = cog = None
                stamp = parts[col["timestamp"]].strip()
                try:
                    ts = datetime.strptime(stamp, "%d/%m/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

                kept += 1
                fixes[mmsi].append({"ts": ts.isoformat(), "lat": lat, "lon": lon, "sog": sog, "cog": cog})
                if mmsi not in names and col["name"] is not None and len(parts) > col["name"]:
                    names[mmsi] = {"name": parts[col["name"]].strip() or None,
                                   "imo": parts[col["imo"]].strip() if col["imo"] is not None else None,
                                   "ship_type": parts[col["ship type"]].strip() if col["ship type"] is not None else None}

    tracks = []
    for mmsi, points in fixes.items():
        if len(points) < MIN_FIXES:
            continue
        meta = names.get(mmsi, {})
        # jedna pozycja na minute wystarcza detektorowi i skraca plik kilkudziesieciokrotnie
        thinned, last_minute = [], None
        for p in sorted(points, key=lambda x: x["ts"]):
            minute = p["ts"][:16]
            if minute != last_minute:
                thinned.append(p)
                last_minute = minute
        tracks.append({"mmsi": mmsi, **meta, "fixes": thinned})

    print(f"wierszy w pliku: {rows}, blisko kabli: {kept}, statkow z trasa: {len(tracks)}")
    return {
        "collected_from": f"{day}T00:00:00+00:00",
        "collected_to": f"{day}T23:59:59+00:00",
        "source": f"Danish Maritime Authority, aisdk-{day} (wody dunskie; NIE obejmuje Zatoki Finskiej)",
        "interval_seconds": 60,
        "tracks": tracks,
    }


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else "2024-12-25"
    out = ROOT / "eval" / "fixtures" / f"dma_tracks_{day}.json"
    data = parse_day(download(day), day)
    out.write_text(json.dumps(data), encoding="utf-8")
    print(f"zapisano {out} ({out.stat().st_size // 1_048_576} MB)")
    print(f"teraz: python eval/feasibility/run_d6.py {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
