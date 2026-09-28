"""Collects one wide ADS-B reading across the regions where GPS jamming actually happens.

The D3 evaluation so far used one hour over the Baltic, which intersects only 30 of the cells
gpsjam labels - eight positive. Thirty examples cannot train anything; a model fitted to them would
be fitting noise, and any score it produced would say more about the split than about the model.

gpsjam labels the whole world: 356 positive cells and 21835 negative on 2026-09-26. The shortage was
never the labels, it was our own coverage. So this sweeps circles over the places that carry both -
the Baltic, the Black Sea, the eastern Mediterranean, the Caucasus and the Gulf for positives,
western Europe and the Atlantic approaches for honest negatives.

Jeden przelot to okolo dwoch samolotow na komorke H3 - za malo, zeby udzial zakloconych cokolwiek
znaczyl. Dlatego skrypt krazy po tych samych okregach przez zadany czas i sumuje obserwacje: ten sam
samolot w tej samej komorce liczy sie raz, ale kolejne minuty dokladaja nowe.

Zmierzone 2026-09-27: adsb.lol odmawia (429) takze przy odstepie 2,5 s, wiec ogranicza rowniez
CZESTOTLIWOSC, nie tylko rownoczesnosc - wczesniejsza notatka w SOURCES.md byla niepelna. Skrypt
wydluza odstep po kazdej odmowie i skraca go po serii udanych zapytan.

  python eval/feasibility/collect_wide.py [minut] [promien_nm]
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "fixtures" / "adsb_wide.json"
POINT = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"
HEADERS = {"User-Agent": "wachta-research/0.1 (non-commercial portfolio project)"}

# Srodki okregow. Pierwsza grupa to rejony, w ktorych zaklocenia sa zjawiskiem codziennym; druga to
# ruch spokojny, potrzebny tak samo - model uczony na samych pozytywach nauczy sie mowic "tak".
SRODKI = [
    # Baltyk i Europa Wschodnia
    (57.0, 21.0), (59.5, 24.5), (54.5, 19.0), (52.0, 24.0), (60.5, 29.0),
    # Morze Czarne, Kaukaz, Turcja
    (44.5, 33.5), (41.0, 29.0), (41.5, 44.0), (40.0, 38.0), (46.5, 31.0),
    # Wschodnia czesc Morza Srodziemnego i Bliski Wschod
    (34.0, 34.0), (32.0, 36.0), (30.0, 31.5), (36.0, 28.0), (33.5, 44.0),
    # Zatoka Perska
    (26.0, 52.0), (25.0, 56.5), (29.0, 48.0),
    # Ruch spokojny: Europa Zachodnia i Atlantyk
    (48.5, 2.5), (51.5, 0.0), (50.0, 8.5), (41.5, 2.0), (55.0, -4.0),
    (45.0, 9.0), (40.0, -3.5), (52.5, 13.5), (47.5, 19.0), (59.0, 18.0),
]


def main() -> int:
    minuty = float(sys.argv[1]) if len(sys.argv) > 1 else 50.0
    radius = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    seen: dict[str, dict] = {}
    udane = odmowy = przeloty = 0
    odstep = 6.0
    koniec = time.time() + minuty * 60

    print(f"kraze po {len(SRODKI)} okregach przez {minuty:.0f} min")
    while time.time() < koniec:
        przeloty += 1
        przed = len(seen)
        for lat, lon in SRODKI:
            if time.time() >= koniec:
                break
            try:
                response = requests.get(POINT.format(lat=lat, lon=lon, radius=radius),
                                        headers=HEADERS, timeout=90)
            except requests.RequestException:
                odmowy += 1
                time.sleep(odstep)
                continue
            if response.status_code == 429:
                odmowy += 1
                odstep = min(30.0, odstep * 1.5)    # serwer mowi "wolniej" - sluchamy go
                time.sleep(odstep)
                continue
            if response.status_code != 200:
                odmowy += 1
                time.sleep(odstep)
                continue

            for a in response.json().get("ac", []):
                hex_id = (a.get("hex") or "").strip().lower()
                if not hex_id or a.get("lat") is None or a.get("lon") is None:
                    continue
                alt = a.get("alt_baro")
                klucz = f"{hex_id}:{round(a['lat'], 1)}:{round(a['lon'], 1)}"
                if klucz in seen:
                    continue    # ten sam samolot w tym samym miejscu nie liczy sie dwa razy
                seen[klucz] = {
                    "hex": hex_id, "lat": a["lat"], "lon": a["lon"],
                    "alt_ft": alt if isinstance(alt, (int, float)) else None,
                    "on_ground": alt == "ground",
                    "nic": a.get("nic"), "nac_p": a.get("nac_p"),
                    "gs": a.get("gs"), "seen_pos": a.get("seen_pos"),
                }
            udane += 1
            odstep = max(4.0, odstep * 0.92)        # po serii udanych mozna troche przyspieszyc
            time.sleep(odstep)

        zostalo = max(0, koniec - time.time()) / 60
        print(f"  przelot {przeloty}: +{len(seen) - przed} obserwacji, lacznie {len(seen)}, "
              f"udanych {udane}, odmow {odmowy}, odstep {odstep:.1f} s, zostalo {zostalo:.0f} min",
              flush=True)

    z_nacp = sum(1 for p in seen.values() if p["nac_p"] is not None)
    OUT.write_text(json.dumps({
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "adsb.lol /v2/point (ODbL)",
        "circles": len(SRODKI), "calls_ok": udane, "calls_refused": odmowy,
        "sweeps": przeloty, "radius_nm": radius,
        "note": ("Obserwacje sumowane przez cala sesje: ten sam samolot w tym samym miejscu liczy "
                 "sie raz, ale przemieszczajac sie dokłada kolejne. To nie jest liczba samolotow, "
                 "tylko liczba obserwacji - i tak samo liczy je referencja gpsjam."),
        "positions": list(seen.values()),
    }), encoding="utf-8")

    print("")
    print(f"przelotow: {przeloty}, zapytan udanych: {udane}, odmow: {odmowy}")
    print(f"obserwacji: {len(seen)}, z polem nac_p: {z_nacp}")
    print(f"zapisano {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
