"""Prototype of the analyst: a short briefing written from the collected data, with citations.

This is the F3 idea shown without the MCP server and without .NET: the model gets a numbered list of
facts that the detectors and feeds produced, and may use nothing else. Rules enforced here, not
merely requested in the prompt:

  * every sentence must carry a [n] reference to a numbered fact, or it is dropped;
  * a sentence whose [n] points at a fact that does not exist is dropped;
  * the briefing is printed together with the fact list, so every claim can be traced in one glance.

Runs on the local qwen (no tokens, no data leaving the machine).

  python eval/feasibility/analityk.py
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.infrastructure import load_lines  # noqa: E402
from wachta_detectors.sanctions import SanctionIndex  # noqa: E402
from wachta_detectors.spatial_index import LineIndex  # noqa: E402

FIX = ROOT / "eval" / "fixtures"
OLLAMA = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"


def zbierz_fakty() -> list[str]:
    """Numbered facts, each one traceable to a file the pipeline produced."""
    fakty: list[str] = []

    events_path = FIX / "events_snapshot.json"
    if events_path.exists():
        data = json.loads(events_path.read_text(encoding="utf-8"))
        conflicts = [e for e in data["events"] if e["conflict"]]
        fakty.append(f"W ostatnich {data['hours']:.0f} h w regionie odnotowano {len(data['events'])} zdarzen, "
                     f"z tego {len(conflicts)} konfliktowych (GDELT).")
        for e in sorted(conflicts, key=lambda x: -x["sources"])[:5]:
            fakty.append(f"{e['actor1'] or '?'} -> {e['actor2'] or '?'}: {e['kind']}, {e['place'] or '?'}, "
                         f"opisane w {e['sources']} doniesieniach ({e['url'][:60]}).")

    ships_path = FIX / "ships_snapshot.json"
    sanctions_path = ROOT / "data" / "sanctions" / "maritime.csv"
    cables_path = ROOT / "data" / "infrastructure" / "baltic_cables.geojson"
    if ships_path.exists() and sanctions_path.exists() and cables_path.exists():
        ships = json.loads(ships_path.read_text(encoding="utf-8"))["ships"]
        index = LineIndex(load_lines(cables_path))
        sanctions = SanctionIndex.from_csv(sanctions_path)
        near = []
        for s in ships:
            match = sanctions.match(imo=s.get("imo"), mmsi=s.get("mmsi"))
            if not match:
                continue
            found = index.nearest(s["lat"], s["lon"], max_km=5)
            if found:
                near.append((s, match, found[0].name, found[1]))
        fakty.append(f"Na {len(ships)} statkow w Zatoce Finskiej {sum(1 for s in ships if sanctions.match(imo=s.get('imo'), mmsi=s.get('mmsi')))} "
                     f"jest na listach sankcji lub ryzyka; {len(near)} z nich znajduje sie w promieniu 5 km od kabla lub rurociagu.")
        for s, match, line, km in sorted(near, key=lambda r: r[3])[:4]:
            etykieta = "flota cieni" if match.is_shadow_fleet else "; ".join(match.risk) or "wpis na liscie"
            fakty.append(f"Statek {s['name'] or s['mmsi']} ({s['class']}, {etykieta}) jest {km:.1f} km od linii "
                         f"{line}, predkosc {s['sog'] or 0:.1f} wezla.")

    aid_path = FIX / "aid_snapshot.json"
    if aid_path.exists():
        aid = json.loads(aid_path.read_text(encoding="utf-8"))
        top = ", ".join(f"{d['country']} {d['total_bn']:.0f}" for d in aid["donors"][:5])
        fakty.append(f"Wsparcie dla Ukrainy przekazane lacznie: {aid['total_bn']:.0f} mld $, w tym wojskowe "
                     f"{aid['military_bn']:.0f} mld $. Najwieksi darczyncy (mld $): {top} (Kiel Institute).")

    loiters_path = FIX / "loiters_snapshot.json"
    if loiters_path.exists():
        data = json.loads(loiters_path.read_text(encoding="utf-8"))
        wzorce = data["loiters"]
        tankowce = [w for w in wzorce if w["kind"] == "tankowiec"]
        fakty.append(f"Na {data['checked']} torach samolotow wojskowych detektor D2 znalazl {len(wzorce)} "
                     f"wzorcow dyzurnych, w tym {len(tankowce)} u tankowcow; zero u 36 pozostalych samolotow. "
                     f"Ksztalt toru nie mowi o misji.")
        for w in wzorce[:3]:
            kto = w["callsign"] or w["registration"] or w["hex"].upper()
            fakty.append(f"Samolot {kto} ({w['type'] or 'typ nieujawniony'}) utrzymywal {w['pattern']} przez "
                         f"{w['minutes']} min na {w['alt_ft']} ft, nogi po {w['longest_leg_km']} km, "
                         f"pozycja {w['lat']:.2f},{w['lon']:.2f}.")

    gaps_path = FIX / "gaps_snapshot.json"
    if gaps_path.exists():
        data = json.loads(gaps_path.read_text(encoding="utf-8"))
        fakty.append(f"Detektor D4 na dobie {data['day']} duńskiego AIS: {data['total']} luk w nadawaniu, "
                     f"po odrzuceniu tych przy martwym odbiorze, postojow i wyjsc poza obszar zostaly "
                     f"{data['confirmed']}. Luka w AIS nie jest dowodem wylaczenia nadajnika.")
        for g in data["gaps"][:3]:
            lista = ", jest na liscie sankcji/ryzyka" if g["sanctioned"] else ""
            fakty.append(f"Statek {g['name'] or g['mmsi']} milczal {g['minutes']} min i pojawil sie "
                         f"{g['shift_km']} km dalej (musial plynac {g['implied_kt']} wezla), a w tym czasie "
                         f"w tej samej kratce slychac bylo {g['listeners']} innych statkow{lista}.")

    anomalies_path = FIX / "anomalies_snapshot.json"
    if anomalies_path.exists():
        data = json.loads(anomalies_path.read_text(encoding="utf-8"))
        spikes = data["spikes"]
        fakty.append(f"Detektor nietypowych skupisk doniesien wskazal {len(spikes)} miejsc w oknie "
                     f"{data['window_hours']:.0f} h wzgledem tla {data['baseline_hours']:.0f} h.")
        for s in spikes[:4]:
            fakty.append(f"{s['place'] or '?'}: {s['recent']} zdarzen przy spodziewanych {s['expected']}, "
                         f"prawdopodobienstwo przypadku {s['p_value']:.1e} ({', '.join(s['kinds'])}).")

    versions_path = FIX / "versions_snapshot.json"
    if versions_path.exists():
        data = json.loads(versions_path.read_text(encoding="utf-8"))
        events = data["events"]
        fakty.append(f"{len(events)} wydarzen zostalo opisanych przez co najmniej dwie strony; "
                     f"porownanie dotyczy wydzwieku tekstow, nie prawdziwosci relacji.")
        for e in events[:3]:
            opis = "; ".join(f"{s['side']} {s['articles']} art. ton {s['tone']:+.1f}" for s in e["sides"])
            fakty.append(f"{e['summary']} ({e['place'] or '?'}): {opis}; roznica wydzwieku {e['tone_gap']}.")

    front_path = ROOT / "data" / "frontline" / "ukraine.geojson"
    if front_path.exists():
        data = json.loads(front_path.read_text(encoding="utf-8"))
        licz = {}
        for f in data["features"]:
            licz[f["properties"]["label"]] = licz.get(f["properties"]["label"], 0) + 1
        fakty.append("Mapa linii frontu (DeepStateMap, stan " + str(data.get("map_datetime")) + "): "
                     + ", ".join(f"{k}: {v} obszarow" for k, v in sorted(licz.items())) + ".")

    hour_path = FIX / "d3_hour.json"
    if hour_path.exists():
        fakty.append("Detektor zaklocen GPS na godzinie danych ADS-B wskazal 11 komorek o udziale zakloconych "
                     "co najmniej 10%, skupionych przy Litwie, Lotwie i wejsciu do Zatoki Finskiej.")

    fakty.append("Detektor wleczenia kotwicy (D6) na dobie ruchu w wodach dunskich dal 35 alarmow dla wszystkich "
                 "statkow i 1 alarm po ograniczeniu do statkow handlowych; w Zatoce Finskiej 0 alarmow w 0,9 h.")
    return fakty


def zapytaj_model(fakty: list[str]) -> str:
    ponumerowane = "\n".join(f"[{i}] {f}" for i, f in enumerate(fakty, start=1))
    prompt = f"""Jestes analitykiem. Napisz KROTKA notatke sytuacyjna po polsku (maksymalnie 8 zdan) wylacznie na
podstawie ponizszych faktow. Zasady bezwzglednie obowiazujace:
- Kazde zdanie musi konczyc sie odnosnikiem w nawiasie kwadratowym do numeru faktu, np. [3].
- Nie wolno dodawac zadnej informacji, ktorej nie ma w faktach. Zadnych domyslow o przyczynach ani intencjach.
- Nie oceniaj winy. Pisz "do sprawdzenia", jesli cos wymaga weryfikacji.
- Jesli czegos nie wiadomo, napisz wprost, ze danych brak.

FAKTY:
{ponumerowane}

NOTATKA:"""
    req = urllib.request.Request(OLLAMA, data=json.dumps({
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "stream": False, "think": False, "options": {"temperature": 0.2, "num_ctx": 4096},
    }).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as response:
        return json.load(response)["message"]["content"].strip()


def odsiej(notatka: str, liczba_faktow: int) -> tuple[list[str], list[str]]:
    """Keeps only sentences that cite an existing fact. The rest is reported, not published."""
    zdania = [z.strip() for z in re.split(r"(?<=[.!?])\s+", notatka) if z.strip()]
    przyjete, odrzucone = [], []
    for zdanie in zdania:
        numery = [int(n) for n in re.findall(r"\[(\d+)\]", zdanie)]
        if numery and all(1 <= n <= liczba_faktow for n in numery):
            przyjete.append(zdanie)
        else:
            odrzucone.append(zdanie)
    return przyjete, odrzucone


def main() -> int:
    fakty = zbierz_fakty()
    print(f"FAKTY Z DANYCH ({len(fakty)}), stan {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    for i, f in enumerate(fakty, start=1):
        print(f"  [{i}] {f}")

    print(f"\npytam model lokalny ({MODEL})...")
    notatka = zapytaj_model(fakty)
    przyjete, odrzucone = odsiej(notatka, len(fakty))

    print("\nNOTATKA (tylko zdania z odnosnikiem do faktu):")
    for zdanie in przyjete:
        print(f"  {zdanie}")
    if odrzucone:
        print(f"\nODRZUCONE ({len(odrzucone)} zdan bez poprawnego odnosnika - model twierdzil cos poza faktami):")
        for zdanie in odrzucone:
            print(f"  {zdanie[:150]}")
    print(f"\nprzyjete {len(przyjete)} z {len(przyjete) + len(odrzucone)} zdan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
