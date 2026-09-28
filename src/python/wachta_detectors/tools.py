"""The detectors as callable tools, for a model that has to decide which question to ask.

Everything a tool returns carries two things besides the answer: where it came from, and what it
does not prove. That is not politeness. A language model handed a bare list of "suspicious ships"
will describe them as suspicious ships; handed the same list with the sentence that says a transponder
failure looks identical, it tends to repeat that too. The caveat travels with the data because the
model will only be as careful as its input.

Two families of tools live here. The snapshot ones read the frozen fixtures this project produced
rather than recomputing from raw feeds: a call stays cheap and repeatable, and the freshness of each
answer is visible instead of implied. The live ones read the database the ingestion is filling right
now, and they carry one extra obligation - saying when the data is from and how much of it there is.
A stack started ten minutes ago returns almost nothing, which reads exactly like a quiet sky unless
the answer says otherwise.
"""
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MAX_WIERSZY = 100
MAX_PUNKTOW_TORU = 500
MAX_OKNO_MINUT = 7 * 24 * 60      # dluzej nie ma sensu pytac: retencja aircraft_position to 7 dni


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    run: Callable[[dict[str, Any]], dict[str, Any]]


class Toolbox:
    """A registry. Nothing here knows about JSON-RPC; that lives in the server."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"narzedzie {tool.name} juz istnieje")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description, "inputSchema": t.schema}
                for t in (self._tools[n] for n in self.names())]

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name].run(arguments or {})


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"brak danych: {path.name} - uruchom odpowiedni skrypt w eval/feasibility")
    return json.loads(path.read_text(encoding="utf-8"))


def _ile(arguments: dict[str, Any], default: int = 10, maximum: int = MAX_WIERSZY) -> int:
    """How many rows the caller asked for, clamped. Nonsense falls back instead of raising.

    The model writes this argument, so it is treated as a suggestion: the ceiling is ours, not its.
    """
    try:
        n = int(arguments.get("ile", default))
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, maximum))


def _limit(rows: Sequence[dict], arguments: dict[str, Any], default: int = 10) -> list[dict]:
    return list(rows[:_ile(arguments, default)])


def _okno_minut(arguments: dict[str, Any], default: int) -> int:
    try:
        n = int(arguments.get("minuty", default))
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_OKNO_MINUT))


def _iso(wartosc: Any) -> Any:
    return wartosc.isoformat() if isinstance(wartosc, datetime) else wartosc


def _plain(rows: Sequence[dict]) -> list[dict]:
    """JSON does not carry datetimes; the tool layer owns that, not the repository."""
    return [{k: _iso(v) for k, v in row.items()} for row in rows]


def _swiezosc(teraz: datetime, okno_minut: int, ile: int, najstarszy: Any, najnowszy: Any) -> str:
    """The sentence every live answer starts with: when the data is from, and how much of it there is.

    A stack started ten minutes ago and a quiet sky produce the same short list. The model cannot tell
    them apart from the rows, so the row count and the timestamps travel with the answer and say it.
    """
    zakres = (f"od {_iso(najstarszy)} do {_iso(najnowszy)}" if najstarszy and najnowszy
              else "w oknie nie ma ani jednego rekordu")
    return (f"Dane z zywej bazy, odczyt {_iso(teraz)}; okno {okno_minut} min, rekordow {ile} "
            f"({zakres}). Swiezo uruchomiony stos ma pusta historie - brak wynikow albo ich mala "
            f"liczba znaczy, ze baza dopiero sie zapelnia, a NIE ze nic sie nie dzieje.")


def build_toolbox(fixtures: Path, search=None, db=None) -> Toolbox:
    """Every tool the model may call.

    `search` and `db` are optional, and each one only costs its own tools. `db` is a factory of fresh
    connections (a callable used as a context manager), so a database that went away between two
    calls costs one answer instead of poisoning the server for the rest of its life.
    """
    box = Toolbox()

    def ciche_statki(args):
        data = _load(fixtures / "gaps_snapshot.json")
        return {
            "doba": data.get("day"),
            "zrodlo": data.get("source"),
            "znalezione": data.get("confirmed"),
            "sprawdzonych_luk": data.get("total"),
            "statki": _limit(data.get("gaps", []), args),
            "zastrzezenie": ("Luka w AIS nie jest dowodem wylaczenia nadajnika. Awaria transpondera "
                             "wyglada w danych identycznie. Zachowane sa tylko te ciszy, w ktorych "
                             "slychac bylo inne statki i statek naprawde plynal."),
        }

    def przeladunki(args):
        data = _load(fixtures / "sts_snapshot.json")
        pary = [e for e in data.get("encounters", []) if e.get("cargo_pair")]
        return {
            "doba": data.get("day"),
            "spotkan_lacznie": data.get("total"),
            "poza_kotwicowiskiem": data.get("offshore"),
            "par_ladunkowych": data.get("cargo_pairs"),
            "pary": _limit(pary, args),
            "zastrzezenie": ("Wiekszosc spotkan burta w burte to legalne bunkrowanie paliwa - Skagen "
                             "jest najwiekszym takim miejscem w Europie. Ksztalt zdarzenia nie "
                             "odroznia bunkrowania od przeladunku poza rejestrem."),
        }

    def tozsamosc(args):
        data = _load(fixtures / "identity_snapshot.json")
        return {
            "doba": data.get("day"),
            "numerow_sprawdzonych": data.get("mmsi_total"),
            "dwa_kadluby": data.get("two_hulls"),
            "bledne_punkty": data.get("bad_fix"),
            "przypadki": _limit(data.get("cases", []), args),
            "zastrzezenie": ("Numer MMSI to liczba wpisana do radia, nie statek. Odbiornik, ktory "
                             "pomyli bity w czyjejs wiadomosci, przypisze ja do sasiedniego numeru "
                             "i wyglada to identycznie jak podszywanie sie."),
        }

    def tory_dyzurne(args):
        data = _load(fixtures / "loiters_snapshot.json")
        return {
            "odczyt": data.get("fetched_at"),
            "torow_sprawdzonych": data.get("checked"),
            "wzorcow": len(data.get("loiters", [])),
            "samoloty": _limit(data.get("loiters", []), args),
            "zastrzezenie": ("To ksztalt toru, nie misja. Tak lata tankowiec na dyzurze, ale tak "
                             "samo rozpoznanie i samolot czekajacy na lotnisko."),
        }

    def wsparcie(args):
        data = _load(fixtures / "aid_snapshot.json")
        return {
            "lacznie_mld_usd": data.get("total_bn"),
            "wojskowe_mld_usd": data.get("military_bn"),
            "darczyncy": _limit(data.get("donors", []), args),
            "zastrzezenie": "Kwoty PRZEKAZANE, nie obiecane. Zrodlo: Kiel Institute Ukraine Support Tracker.",
        }

    def anomalie(args):
        data = _load(fixtures / "anomalies_snapshot.json")
        return {
            "okno_godzin": data.get("window_hours"),
            "tlo_godzin": data.get("baseline_hours"),
            "miejsc": len(data.get("spikes", [])),
            "skupiska": _limit(data.get("spikes", []), args),
            "zastrzezenie": ("Skupisko DONIESIEN, nie potwierdzonych zdarzen. Nagly wzrost moze "
                             "oznaczac walki, ale rownie dobrze jedna konferencje prasowa "
                             "podchwycona przez wiele redakcji."),
        }

    def dwie_wersje(args):
        data = _load(fixtures / "versions_snapshot.json")
        return {
            "wydarzen": len(data.get("events", [])),
            "wydarzenia": _limit(data.get("events", []), args),
            "zastrzezenie": ("Porownanie dotyczy WYDZWIEKU tekstow, nie prawdziwosci relacji. Ton "
                             "jest cecha tekstu, nie dowodem, kto ma racje."),
        }

    prosty = {"type": "object",
              "properties": {"ile": {"type": "integer", "minimum": 1, "maximum": 100,
                                     "description": "ile pozycji zwrocic (domyslnie 10)"}}}

    box.add(Tool("ciche_statki", "Statki, ktore przestaly nadawac AIS w ruchu tam, gdzie odbiorniki "
                                 "dzialaly (detektor D4).", prosty, ciche_statki))
    box.add(Tool("przeladunki", "Pary statkow stojace burta w burte poza kotwicowiskiem, oba "
                                "ladunkowce lub tankowce (detektor D5).", prosty, przeladunki))
    box.add(Tool("tozsamosc_statkow", "Numery MMSI, ktorych tor stawia je w dwoch miejscach naraz "
                                      "(detektor D7).", prosty, tozsamosc))
    box.add(Tool("tory_dyzurne", "Samoloty, ktore przestaly leciec z A do B i chodza po jednej linii "
                                 "(detektor D2).", prosty, tory_dyzurne))
    box.add(Tool("wsparcie_ukrainy", "Kto ile przekazal Ukrainie, w miliardach dolarow.", prosty, wsparcie))
    box.add(Tool("nietypowe_skupiska", "Miejsca, w ktorych liczba doniesien zlamala wlasny rytm "
                                       "(detektor D8).", prosty, anomalie))
    box.add(Tool("dwie_wersje", "Wydarzenia opisane inaczej przez rozne strony - porownanie "
                                "wydzwieku.", prosty, dwie_wersje))

    if search is not None:
        def szukaj(args):
            pytanie = (args.get("pytanie") or "").strip()
            if not pytanie:
                raise ValueError("wymagane pole 'pytanie'")
            hits = search(pytanie, int(args.get("ile", 8)))
            return {
                "pytanie": pytanie,
                "znalezione": len(hits),
                "wyniki": [{"wynik": h.score, "tekst": h.document.text,
                            "zrodlo": h.document.metadata.get("url")} for h in hits],
                "zastrzezenie": ("Wynik to podobienstwo, nie trafnosc. Pusta lista znaczy, ze nic w "
                                 "korpusie nie przekroczylo progu - i to jest odpowiedz, a nie blad."),
            }

        box.add(Tool("szukaj_zdarzen",
                     "Szuka zdarzen po ZNACZENIU, nie po slowach. Pytanie moze byc po polsku, "
                     "a zdarzenia sa po angielsku.",
                     {"type": "object",
                      "properties": {"pytanie": {"type": "string", "description": "pytanie w dowolnym jezyku"},
                                     "ile": {"type": "integer", "minimum": 1, "maximum": 50}},
                      "required": ["pytanie"]},
                     szukaj))

    if db is not None:
        # Import dopiero tutaj: repository ciagnie psycopg i h3. Bez bazy serwer ma wstac nawet wtedy,
        # gdy tych pakietow nie da sie zaimportowac, a tryb na migawkach ich nie potrzebuje.
        import h3

        from . import repository as repo
        from .jamming import JammingCell

        def _teraz() -> datetime:
            return datetime.now(timezone.utc)

        def samoloty_na_zywo(args):
            minuty = _okno_minut(args, 15)
            ile = _ile(args)
            teraz = _teraz()
            od = teraz - timedelta(minutes=minuty)
            with db() as conn:
                stan = repo.position_window(conn, od)
                wiersze = repo.live_aircraft(conn, od, ile)
            return {
                "odczyt": _iso(teraz),
                "okno_minut": minuty,
                "samolotow_w_oknie": stan["n_aircraft"],
                "pozycji_w_oknie": stan["n_positions"],
                "najstarszy_punkt": _iso(stan["oldest"]),
                "najnowszy_punkt": _iso(stan["newest"]),
                "pokazano": len(wiersze),
                "samoloty": _plain(wiersze),
                "zastrzezenie": _swiezosc(teraz, minuty, stan["n_positions"],
                                          stan["oldest"], stan["newest"])
                + (" Kazdy wiersz to OSTATNI odebrany raport ADS-B, nie biezace polozenie - maszyna "
                   "jest juz gdzie indziej. Widac tylko to, co slysza odbiorniki karmiace feed, wiec "
                   "nieobecnosc samolotu nie znaczy, ze go nie ma."),
            }

        def zaklocenia_gps(args):
            minuty = _okno_minut(args, 60)
            ile = _ile(args)
            teraz = _teraz()
            od = teraz - timedelta(minutes=minuty)
            with db() as conn:
                stan = repo.jamming_window(conn, od)
                wiersze = repo.jamming_cells_since(conn, od, ile)
            komorki = []
            for w in wiersze:
                cell = JammingCell(w["h3"], w["n_aircraft"], w["n_degraded"])
                lat, lon = h3.cell_to_latlng(w["h3"])
                komorki.append({"godzina": _iso(w["hour"]), "h3": w["h3"], "lat": lat, "lon": lon,
                                "samolotow": w["n_aircraft"], "z_gorszym_gps": w["n_degraded"],
                                "udzial": round(cell.pct, 3),
                                "dolna_granica_ufnosci": round(cell.confidence_floor, 3),
                                "poziom": cell.level})
            return {
                "odczyt": _iso(teraz),
                "okno_minut": minuty,
                "komorek_w_oknie": stan["n_cells"],
                "najstarsza_godzina": _iso(stan["oldest"]),
                "najnowsza_godzina": _iso(stan["newest"]),
                "pokazano": len(komorki),
                "komorki": komorki,
                "zastrzezenie": _swiezosc(teraz, minuty, stan["n_cells"],
                                          stan["oldest"], stan["newest"])
                + (" Poziom liczy dolna granica przedzialu Wilsona, nie surowy udzial (detektor D3). "
                   "Gorszy NACp to slad zaklocania GPS, ale tak samo wyglada grupa maszyn ze slabszym "
                   "wyposazeniem - to przeslanka, nie dowod zaklocania."),
            }

        def alerty_detektorow(args):
            minuty = _okno_minut(args, 24 * 60)
            ile = _ile(args)
            detektor = (args.get("detektor") or "").strip() or None
            teraz = _teraz()
            od = teraz - timedelta(minutes=minuty)
            with db() as conn:
                stan = repo.alert_window(conn, od, detektor)
                wiersze = repo.recent_alerts(conn, od, ile, detektor)
            return {
                "odczyt": _iso(teraz),
                "okno_minut": minuty,
                "detektor": detektor,
                "alertow_w_oknie": stan["n_alerts"],
                "najstarszy_alert": _iso(stan["oldest"]),
                "najnowszy_alert": _iso(stan["newest"]),
                "pokazano": len(wiersze),
                "alerty": _plain(wiersze),
                "zastrzezenie": _swiezosc(teraz, minuty, stan["n_alerts"],
                                          stan["oldest"], stan["newest"])
                + (" Alert to powod, zeby sprawdzic, nie ustalenie faktu. D1 zglasza cisze ADS-B, a "
                   "wylaczony transponder wyglada w danych tak samo jak wyjscie poza zasieg "
                   "odbiornika. Pusta lista to rowniez odpowiedz, nie blad."),
            }

        def tor_samolotu(args):
            hex_ = (args.get("hex") or "").strip().lower()
            if not hex_:
                raise ValueError("wymagane pole 'hex' - adres ICAO samolotu, np. 4b1815")
            minuty = _okno_minut(args, 6 * 60)
            ile = _ile(args, default=100, maximum=MAX_PUNKTOW_TORU)
            teraz = _teraz()
            od = teraz - timedelta(minutes=minuty)
            with db() as conn:
                stan = repo.aircraft_summary(conn, hex_, od)
                punkty = repo.aircraft_track(conn, hex_, od, ile)
            return {
                "odczyt": _iso(teraz),
                "hex": hex_,
                "okno_minut": minuty,
                "znak_wywolawczy": stan["flight"],
                "typ": stan["type_code"],
                "wojskowy": stan["is_military"],
                "punktow_w_oknie": stan["n_points"],
                "pierwszy_punkt": _iso(stan["oldest"]),
                "ostatni_punkt": _iso(stan["newest"]),
                "pokazano": len(punkty),
                "tor": _plain(punkty),
                "zastrzezenie": _swiezosc(teraz, minuty, stan["n_points"],
                                          stan["oldest"], stan["newest"])
                + (" Tor to punkty, ktore dotarly do odbiornikow. Przerwa w nim nie dowodzi, ze "
                   "samolot zniknal - rownie dobrze moze byc dziura w pokryciu. Pozycje starsze niz "
                   "7 dni kasuje polityka retencji, wiec dluzsze okno i tak ich nie pokaze."),
            }

        okno = {"minuty": {"type": "integer", "minimum": 1, "maximum": MAX_OKNO_MINUT,
                           "description": "jak daleko wstecz siegnac (minuty)"}}
        ile_pole = {"ile": {"type": "integer", "minimum": 1, "maximum": MAX_WIERSZY,
                            "description": "ile pozycji zwrocic (domyslnie 10)"}}

        box.add(Tool("samoloty_na_zywo",
                     "ZYWA BAZA: samoloty widziane w ostatnich minutach - ostatnia pozycja kazdego "
                     "z nich. Domyslne okno 15 minut.",
                     {"type": "object", "properties": {**okno, **ile_pole}}, samoloty_na_zywo))
        box.add(Tool("zaklocenia_gps",
                     "ZYWA BAZA: komorki zaklocen GPS z ostatniej godziny, policzone z jakosci "
                     "pozycji ADS-B (detektor D3). Najgorsze pierwsze.",
                     {"type": "object", "properties": {**okno, **ile_pole}}, zaklocenia_gps))
        box.add(Tool("alerty_detektorow",
                     "ZYWA BAZA: alerty zgloszone przez detektory, najnowsze pierwsze. Mozna zawezic "
                     "do jednego detektora (np. D1). Domyslne okno doba.",
                     {"type": "object",
                      "properties": {**okno, **ile_pole,
                                     "detektor": {"type": "string",
                                                  "description": "symbol detektora, np. D1; pusty = wszystkie"}}},
                     alerty_detektorow))
        box.add(Tool("tor_samolotu",
                     "ZYWA BAZA: tor jednego samolotu po adresie ICAO (hex), najnowszy punkt "
                     "pierwszy. Domyslne okno 6 godzin.",
                     {"type": "object",
                      "properties": {**okno,
                                     "hex": {"type": "string",
                                             "description": "adres ICAO 24-bit, np. 4b1815"},
                                     "ile": {"type": "integer", "minimum": 1,
                                             "maximum": MAX_PUNKTOW_TORU,
                                             "description": "ile punktow toru (domyslnie 100)"}},
                      "required": ["hex"]},
                     tor_samolotu))

    return box
