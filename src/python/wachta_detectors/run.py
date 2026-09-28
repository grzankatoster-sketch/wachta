"""Detector loop: D1 every tick, D3 on its own interval, coverage for every closed hour.

The schedule and the slack live in RunnerConfig instead of in literals spread through the functions.
The one number here that is not a scheduling choice - how far back D1 reads - is derived from D1's
own rules, so widening max_gap widens the query with it.
"""
import gzip
import json
import logging
import os
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from wachta_detectors import repository as repo
from wachta_detectors.airports import load_airports
from wachta_detectors.anchor import AnchorRules, by_ship, find_anchor_drag
from wachta_detectors.coverage import count_reports
from wachta_detectors.dark import DarkRules, find_dark_candidates, silent_aircraft, snapshot_inputs
from wachta_detectors.embeddings import embedder_from_env
from wachta_detectors.gaps import GapAlert, GapRules, find_gaps, suspicious
from wachta_detectors.identity import IdentityReport, IdentityRules
from wachta_detectors.identity import scan as scan_identity
from wachta_detectors.indexer import alert_documents, index
from wachta_detectors.infrastructure import load_lines
from wachta_detectors.jamming import aggregate_jamming
from wachta_detectors.spatial_index import LineIndex
from wachta_detectors.sts import Encounter, StsRules, find_encounters, offshore

log = logging.getLogger("wachta.detectors")
MAX_CATCHUP_HOURS = 48

# Digitraffic (Fintraffic) odmawia (403) bez User-Agent opisowego i bez Digitraffic-User - projekt
# przerabial dokladnie ten sam blad z adsb.lol, wiec naglowki sa tu od pierwszego wywolania, nie
# dopisane po pierwszej awarii. Uzywamy urllib zamiast requests: nowa zaleznosc wymagalaby zmiany
# pyproject.toml/uv.lock, ktorych to zadanie nie obejmuje.
DIGITRAFFIC_HEADERS = {
    "User-Agent": "wachta-project/0.1 (situational awareness, non-commercial)",
    "Digitraffic-User": "wachta/detectors",
    "Accept-Encoding": "gzip",
}
DIGITRAFFIC_LOCATIONS = "https://meri.digitraffic.fi/api/ais/v1/locations"
DIGITRAFFIC_VESSELS = "https://meri.digitraffic.fi/api/ais/v1/vessels"
SHIP_SOURCE_ID = "digitraffic-ais"
MAX_POSITION_AGE_MIN = 30.0   # stara pozycja nie ma wygladac jak biezaca


def _get_json(url: str, timeout: float):
    """GET as JSON, undoing gzip by hand.

    Znalezione na zywym Digitraffic: requests dekompresuje gzip samo, urllib nie - a serwer i tak
    odsyla gzip mimo naszego naglowka (widziane po magic bytes 0x1f 0x8b), wiec sprawdzamy tresc,
    nie tylko deklarowany Content-Encoding.
    """
    request = urllib.request.Request(url, headers=DIGITRAFFIC_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def fetch_ships(timeout: float = 60.0) -> list[dict]:
    """One read of Digitraffic AIS: positions joined with vessel metadata.

    Coverage is Finnish waters only (measured: nothing south of ~57.7N) - that is Digitraffic's
    limit, not this function's; the southern Baltic needs AISStream once a key exists.
    """
    locations = _get_json(DIGITRAFFIC_LOCATIONS, timeout)["features"]
    vessels = {v["mmsi"]: v for v in _get_json(DIGITRAFFIC_VESSELS, timeout)}

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    ships = []
    for f in locations:
        props, (lon, lat) = f["properties"], f["geometry"]["coordinates"]
        mmsi = str(props["mmsi"])
        stamp_ms = props.get("timestampExternal", now_ms)
        if (now_ms - stamp_ms) / 60000 > MAX_POSITION_AGE_MIN:
            continue
        meta = vessels.get(props["mmsi"], {})
        ships.append({
            "mmsi": mmsi,
            "ts": datetime.fromtimestamp(stamp_ms / 1000, tz=timezone.utc),
            "lat": lat,
            "lon": lon,
            "sog": props.get("sog"),
            "cog": props.get("cog"),
            "name": (meta.get("name") or "").strip() or None,
            "imo": str(meta["imo"]) if meta.get("imo") else None,
            "ship_type": str(meta["shipType"]) if meta.get("shipType") is not None else None,
            "nav_status": str(props["navStat"]) if props.get("navStat") is not None else None,
        })
    return ships


@dataclass(frozen=True)
class RunnerConfig:
    """How often the loop runs and how much slack it gives itself - nothing about what counts as a find.

    Thresholds belong to the detectors and the schedule belongs here; the two must not be confused.
    The one place they meet is the data window, and it is derived (see d1_window) rather than typed
    in. A window written out by hand stops matching the rules the moment someone widens max_gap, and
    then the detector is looking for silences the query never hands it.
    """
    tick: timedelta = timedelta(seconds=60)
    d3_every: timedelta = timedelta(minutes=10)
    receiver_fresh: timedelta = timedelta(minutes=2)   # jak swiezy ma byc odbior, zeby uznac go za zywy
    fetch_margin: timedelta = timedelta(minutes=5)     # zapas na opoznienie zapisu i dlugosc cyklu
    # Pierwsze uruchomienie z pustym magazynem: zakres jawny, zeby start nie zalezal od tego, co
    # akurat jest w bazie. Bez tego pierwszy przebieg liczyl wylacznie biezaca (niepelna) godzine.
    d3_first_run_hours: int = 3
    coverage_first_run_hours: int = 1
    max_catchup_hours: int = MAX_CATCHUP_HOURS
    # Warstwa morska: AIS pobierany czesto (Digitraffic odswieza co kilka minut), D4/D6 rzadziej, bo
    # obydwa potrzebuja okna GODZIN pozycji, nie pojedynczego zrzutu.
    ships_every: timedelta = timedelta(minutes=2)
    d4_every: timedelta = timedelta(minutes=10)
    d6_every: timedelta = timedelta(minutes=10)
    d4_window_hours: int = 24    # dluzej niz GapRules.max_gap (12h), zeby kazda luka miala "przed" i "po" w oknie
    d6_window_hours: int = 6     # AnchorRules.min_duration liczy sie w minutach, wiec kilka godzin wystarcza
    # D5 co kwadrans, D7 co pol godziny: obydwa czytaja to samo dwunastogodzinne okno, a ich werdykt
    # nie zmienia sie w tempie jednego cyklu. D7 rzadziej, bo sprzecznosc toru narasta godzinami -
    # przemielenie tych samych dwunastu godzin co dziesiec minut daje ten sam wynik za kazdym razem.
    d5_every: timedelta = timedelta(minutes=15)
    d7_every: timedelta = timedelta(minutes=30)
    # StsRules.max_duration to 12 h, a both_under_way zaglada 6 h przed spotkanie i 6 h za nie
    # (StsRules.approach). Okno krotsze niz to obcina dlugie spotkania w polowie i odbiera dowod, ze
    # statki w ogole gdzies plynely - a wtedy offshore() odsiewa prawdziwe spotkania jako "nabrzeze".
    d5_window_hours: int = 12
    d7_window_hours: int = 12    # to samo okno co D5: skok tam i z powrotem musi sie w nim zmiescic
    # Indeksowanie wektorowe: rzadko i tylko przyrostowo. Wyszukiwanie po znaczeniu bylo jednorazowa
    # migawka - nowe alarmy nigdy do niego nie trafialy, bo indekser uruchamialo sie z reki.
    index_every: timedelta = timedelta(minutes=15)
    # Pierwszy przebieg po restarcie: ile wstecz dobrac. Pelne nadrobienie (7 dni) zostaje przy
    # recznym `python -m wachta_detectors.indexer` - petla ma trzymac indeks biezacym, nie odbudowywac
    # go od zera przy kazdym restarcie kontenera.
    index_backfill_hours: int = 24

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RunnerConfig":
        """Schedule read from the environment, so a deployment can slow the loop without a rebuild."""
        env = os.environ if env is None else env
        pola = cls()

        def minuty(nazwa: str, domyslne: timedelta) -> timedelta:
            return timedelta(minutes=float(env[nazwa])) if nazwa in env else domyslne

        tick = timedelta(seconds=float(env["WACHTA_TICK_SECONDS"])) if "WACHTA_TICK_SECONDS" in env else pola.tick
        return cls(
            tick=tick,
            d3_every=minuty("WACHTA_D3_EVERY_MINUTES", pola.d3_every),
            receiver_fresh=minuty("WACHTA_RECEIVER_FRESH_MINUTES", pola.receiver_fresh),
            fetch_margin=minuty("WACHTA_FETCH_MARGIN_MINUTES", pola.fetch_margin),
            max_catchup_hours=int(env.get("WACHTA_MAX_CATCHUP_HOURS", pola.max_catchup_hours)),
        )


def d1_window(rules: DarkRules = DarkRules(), config: RunnerConfig = RunnerConfig()) -> timedelta:
    """How far back D1 has to read, taken from D1's own rules.

    Anything quiet for longer than max_gap is out of scope by definition, so that is the horizon; the
    margin covers the tick itself and the lag between a message arriving and being stored.
    """
    return rules.max_gap + config.fetch_margin


@dataclass
class Progress:
    """What the loop has already finished - deliberately kept apart from what it has written.

    Results are not a progress marker: an hour with no traffic writes no rows, so a max(hour) taken
    from the results never moves past it.
    """
    last_d3_run: datetime | None = None
    d3_done_through: datetime | None = None
    coverage_done_through: datetime | None = None
    last_ships_fetch: datetime | None = None
    last_d4_run: datetime | None = None
    last_d6_run: datetime | None = None
    last_d5_run: datetime | None = None
    last_d7_run: datetime | None = None
    # Indeksowanie ma DWA znaczniki, i to nie jest powtorzenie. "Kiedy probowalismy" trzyma tempo,
    # zeby padnieta Ollama nie zamienila zadania kwadransowego w probe co tick. "Co juz w indeksie"
    # przesuwa sie wylacznie po udanym zapisie, zeby alarmy z czasu awarii nie wypadly z okna.
    last_index_run: datetime | None = None
    indexed_through: datetime | None = None


def run_d1(conn, airports, now, rules: DarkRules = DarkRules(), config: RunnerConfig = RunnerConfig()):
    last_seen = repo.last_seen_since(conn, now - d1_window(rules, config))
    coverage = repo.coverage_last_days(conn)
    alive = repo.alive_cells(conn, now - config.receiver_fresh)
    candidates = find_dark_candidates(last_seen, coverage, alive, airports, now, rules)
    alerted = {c.hex for c in candidates}

    # Freeze inputs for every silent aircraft, alerted or not — this is what recall is measured on.
    samples = [(s.hex, now, s.hex in alerted, snapshot_inputs(s, coverage, alive, airports, now, rules))
               for s in silent_aircraft(last_seen, now, rules)]
    # Jedna transakcja: probka mowi "alerted=True", wiec alert bez swojej probki (albo probka bez
    # swojego alertu) to niespojny material do pomiaru recall, a nie brakujacy wiersz.
    with conn.transaction():
        repo.insert_d1_samples(conn, samples)
        n_alerts = repo.insert_alerts(conn, "D1", candidates)
    log.info("D1: %d aircraft checked, %d silent, %d new alerts", len(last_seen), len(samples), n_alerts)


def run_ship_ingest(conn, now) -> None:
    """One Digitraffic snapshot in, with provenance - same shape as the aircraft ingestion pattern."""
    ships = fetch_ships()
    n = repo.insert_ship_positions(conn, SHIP_SOURCE_ID, ships, now)
    log.info("statki: %d pozycji zapisanych (Digitraffic)", n)


def _gap_evidence(a: GapAlert) -> dict:
    return {
        **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(a).items()},
        "duration_minutes": round(a.duration.total_seconds() / 60, 1),
        "note": "Candidate to check, not a verdict.",
    }


def _gap_score(a: GapAlert) -> float:
    """find_gaps() carries no score - suspicious() only filters. Built here from what it already
    guarantees true: more witnesses and a longer proven silence both raise confidence, capped like
    every other detector's score.
    """
    hours = a.duration.total_seconds() / 3600
    return round(min(1.0, 0.4 + 0.05 * a.listeners + 0.1 * min(hours, 6)), 3)


def run_d4(conn, now, rules: GapRules = GapRules(), window_hours: int = 24) -> None:
    """D4: ships silent on AIS while under way, in a place where the receivers were working."""
    fixes = repo.recent_ship_fixes(conn, now - timedelta(hours=window_hours))
    alerts = suspicious(find_gaps(fixes, rules))
    rows = [("D4", a.mmsi, a.vanished_at, a.vanish_lat, a.vanish_lon, _gap_score(a), _gap_evidence(a))
            for a in alerts]
    n = repo.insert_alert_rows(conn, rows)
    log.info("D4: %d statkow w oknie, %d podejrzanych zanikow, %d nowych alarmow",
             len({f.mmsi for f in fixes}), len(alerts), n)


def run_d6(conn, now, cable_index: LineIndex, rules: AnchorRules = AnchorRules(), window_hours: int = 6) -> None:
    """D6: ships behaving as if dragging anchor across a cable or pipeline.

    find_anchor_drag() assumes every fix it receives belongs to one ship (see anchor.py) - the runs
    it builds would otherwise splice tracks from different vessels together, so tracks are split with
    by_ship() before the detector ever sees them, exactly like eval/feasibility/run_d6.py does.
    """
    fixes = repo.recent_ship_fixes(conn, now - timedelta(hours=window_hours))
    rows = []
    for track in by_ship(fixes).values():
        for a in find_anchor_drag(track, cable_index, rules):
            rows.append(("D6", a.mmsi, a.started_at, a.lat, a.lon, a.score, a.evidence))
    n = repo.insert_alert_rows(conn, rows)
    log.info("D6: %d statkow w oknie, %d alarmow wleczenia kotwicy, %d nowych",
             len({f.mmsi for f in fixes}), len(rows), n)


def _sts_score(e: Encounter, rules: StsRules) -> float:
    """find_encounters() carries no score - offshore() only filters, exactly like suspicious() in D4.

    Built from what the encounter already proves: how long the hulls stayed side by side, and how
    close they got. Both are capped, so one very long meeting cannot outrank everything else, and
    the floor is the same 0.4 D4 uses - a candidate to read, never a verdict.
    """
    hours = e.duration.total_seconds() / 3600
    bliskosc = 1.0 - min(1.0, e.min_separation_km / rules.max_separation_km)
    return round(min(1.0, 0.4 + 0.1 * min(hours, 3) + 0.3 * bliskosc), 3)


def _sts_evidence(e: Encounter) -> dict:
    return {
        "mmsi_a": e.mmsi_a, "mmsi_b": e.mmsi_b, "name_a": e.name_a, "name_b": e.name_b,
        "start": e.start.isoformat(), "end": e.end.isoformat(),
        "minutes": round(e.duration.total_seconds() / 60),
        "min_separation_m": round(e.min_separation_km * 1000),
        "mean_separation_m": round(e.mean_separation_km * 1000),
        "mean_sog": e.mean_sog, "drift_km": e.drift_km, "samples": e.samples,
        "note": "Candidate to check, not a verdict.",
    }


def run_d5(conn, now, rules: StsRules = StsRules(), window_hours: int = 12) -> None:
    """D5: two hulls side by side long enough to move cargo, away from any anchorage.

    Only offshore() encounters are written. The raw find_encounters() output is dominated by ships
    moored next to each other and by anchorages - hundreds of pairs a day that mean nothing - and
    offshore() is the module's own answer to which of them are worth reading. Writing the unfiltered
    list would bury the alert table, not fill it.
    """
    fixes = repo.recent_ship_fixes(conn, now - timedelta(hours=window_hours))
    sea = offshore(find_encounters(fixes, rules))
    # Para w stalej kolejnosci: entity_id wchodzi do UNIQUE (detector, entity_id, started_at), wiec
    # "A+B" i "B+A" byloby tym samym spotkaniem zapisanym dwa razy.
    rows = [("D5", "+".join(sorted((e.mmsi_a, e.mmsi_b))), e.start, e.lat, e.lon,
             _sts_score(e, rules), _sts_evidence(e)) for e in sea]
    n = repo.insert_alert_rows(conn, rows)
    log.info("D5: %d statkow w oknie, %d spotkan poza kotwicowiskiem, %d nowych alarmow",
             len({f.mmsi for f in fixes}), len(sea), n)


def _identity_score(r: IdentityReport, rules: IdentityRules) -> float:
    """How hard the track contradicts itself: how often it jumped sides, and over how many areas."""
    return round(min(1.0, 0.5 + 0.1 * min(r.alternations, 3) + 0.1 * min(len(r.clusters), 2)), 3)


def _identity_evidence(r: IdentityReport) -> dict:
    return {
        "mmsi": r.mmsi, "verdict": r.verdict, "alternations": r.alternations,
        "max_implied_kt": r.max_implied_kt, "names": list(r.names), "fixes": r.fixes,
        "clusters": [{"lat": lat, "lon": lon, "segments": ile} for lat, lon, ile in r.clusters],
        "jumps": [{"at": j.at.isoformat(), "km": j.km, "minutes": j.minutes,
                   "implied_kt": j.implied_kt} for j in r.jumps[:10]],
        "note": "Candidate to check, not a verdict.",
    }


def run_d7(conn, now, rules: IdentityRules = IdentityRules(), window_hours: int = 12) -> None:
    """D7: one MMSI whose own track says it is two hulls.

    scan() returns two kinds of finding and only one of them is a claim about a ship: "bledny punkt"
    is a decoding error - a single position out of line - and identity.py exists precisely to keep it
    apart from fraud. Alerting on it would report the receiver's hiccups as impersonation.
    """
    fixes = repo.recent_ship_fixes(conn, now - timedelta(hours=window_hours))
    flagged = [r for r in scan_identity(fixes, rules) if r.verdict == "dwa kadluby"]
    rows = []
    for r in flagged:
        # Pierwszy skok w oknie jako started_at: dopoki to samo okno go obejmuje, UNIQUE trzyma
        # jeden alarm na te sama sprzecznosc zamiast nowego przy kazdym przebiegu.
        first = min(j.at for j in r.jumps)
        lat, lon, _ = r.clusters[0] if r.clusters else (r.jumps[0].to_lat, r.jumps[0].to_lon, 0)
        rows.append(("D7", r.mmsi, first, lat, lon, _identity_score(r, rules), _identity_evidence(r)))
    n = repo.insert_alert_rows(conn, rows)
    log.info("D7: %d statkow w oknie, %d numerow wygladajacych na dwa kadluby, %d nowych alarmow",
             len({f.mmsi for f in fixes}), len(flagged), n)


def run_indexing(conn, now, progress, config: RunnerConfig = RunnerConfig(), embedder=None) -> None:
    """Puts new alerts into the vector store, so that searching by meaning sees today's findings.

    Incremental on purpose: only alerts created since the last successful pass. The manual
    `python -m wachta_detectors.indexer` re-reads a week and is the right tool for a backfill; doing
    that every quarter of an hour would spend minutes of Ollama time re-embedding text that has not
    changed. The marker moves only after the write, so a failed pass loses nothing.
    """
    since = progress.indexed_through or (now - timedelta(hours=config.index_backfill_hours))
    docs = alert_documents(conn, since)
    if not docs:
        # Pusty korpus to nie awaria - przesuwamy znacznik, bo tych alarmow po prostu nie ma.
        progress.indexed_through = now
        log.debug("indeks: brak nowych alarmow od %s", since)
        return
    written = index(conn, docs, embedder or embedder_from_env())
    progress.indexed_through = now
    log.info("indeks wektorowy: %d alarmow od %s, zapisanych %d", len(docs), since, written)


def hour_of(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def hours_to_finalise(current, done_through, stored_hour, first_run_hours, max_catchup_hours=MAX_CATCHUP_HOURS):
    """Closed hours still waiting to be computed, oldest first.

    done_through is the loop's own marker and advances over hours that produced nothing, which the
    stored results cannot do. stored_hour only seeds that marker after a restart, and is recomputed
    rather than skipped, because the newest stored hour may have been written while it was still
    partial. With neither, the first run covers an explicit window instead of nothing at all.
    """
    if done_through is not None:
        start = done_through + timedelta(hours=1)
    elif stored_hour is not None:
        start = stored_hour
    else:
        start = current - timedelta(hours=first_run_hours)
    start = max(start, current - timedelta(hours=max_catchup_hours))
    hours = []
    while start < current:
        hours.append(start)
        start += timedelta(hours=1)
    return hours


def run_d3(conn, now, progress, config: RunnerConfig = RunnerConfig()):
    """Finalise every closed hour we have not computed yet, then refresh the current (partial) hour."""
    current = hour_of(now)
    stored = repo.last_jamming_hour(conn) if progress.d3_done_through is None else None
    hours = hours_to_finalise(current, progress.d3_done_through, stored,
                              config.d3_first_run_hours, config.max_catchup_hours)
    for hour in hours:
        repo.replace_jamming(conn, hour, aggregate_jamming(repo.positions_between(conn, hour, hour + timedelta(hours=1))))
        # Znacznik po kazdej godzinie: przerwane nadrabianie nie zaczyna nastepnym razem od zera.
        progress.d3_done_through = hour
    cells = aggregate_jamming(repo.positions_between(conn, current, now))
    repo.replace_jamming(conn, current, cells)
    log.info("D3: %d closed hours recomputed, current hour %d cells, %d high",
             len(hours), len(cells), sum(c.level == "high" for c in cells))


def run_coverage(conn, now, progress, config: RunnerConfig = RunnerConfig()):
    current = hour_of(now)
    # Ten sam problem co w D3: upsert_coverage nic nie zapisuje dla pustej godziny, wiec max(hour)
    # z wynikow nigdy jej nie minie. Roznica wobec D3: pokrycie liczymy wylacznie dla godzin
    # zamknietych, wiec ostatnia zapisana godzina jest kompletna i nie ma jej po co przeliczac - stad
    # przesuniecie o godzine przed podaniem jej jako punktu startowego.
    stored = repo.last_coverage_hour(conn) if progress.coverage_done_through is None else None
    stored = stored + timedelta(hours=1) if stored is not None else None
    hours = hours_to_finalise(current, progress.coverage_done_through, stored,
                              config.coverage_first_run_hours, config.max_catchup_hours)
    for hour in hours:
        repo.upsert_coverage(conn, hour, count_reports(repo.positions_between(conn, hour, hour + timedelta(hours=1))))
        log.info("coverage: hour %s done", hour)
        progress.coverage_done_through = hour


def _guarded(name, detector, *args):
    """Run one detector and report whether it got through.

    A bad row in D1 must cost D1 this tick, not D3 and coverage as well. KeyboardInterrupt and
    SystemExit are BaseException, so they are not caught here and the process stays stoppable.
    """
    try:
        detector(*args)
        return True
    except Exception:
        log.exception("%s failed, skipping until the next tick", name)
        return False


def tick(conn, airports, now, progress, rules: DarkRules = DarkRules(), config: RunnerConfig = RunnerConfig(),
         cable_index: LineIndex | None = None):
    _guarded("D1", run_d1, conn, airports, now, rules, config)
    _guarded("coverage", run_coverage, conn, now, progress, config)

    if progress.last_ships_fetch is None or now - progress.last_ships_fetch >= config.ships_every:
        if _guarded("ships", run_ship_ingest, conn, now):
            progress.last_ships_fetch = now

    if progress.last_d4_run is None or now - progress.last_d4_run >= config.d4_every:
        if _guarded("D4", run_d4, conn, now, GapRules(), config.d4_window_hours):
            progress.last_d4_run = now

    if cable_index is None:
        log.debug("D6: brak indeksu kabli, pomijam")
    elif progress.last_d6_run is None or now - progress.last_d6_run >= config.d6_every:
        if _guarded("D6", run_d6, conn, now, cable_index, AnchorRules(), config.d6_window_hours):
            progress.last_d6_run = now

    if progress.last_d5_run is None or now - progress.last_d5_run >= config.d5_every:
        if _guarded("D5", run_d5, conn, now, StsRules(), config.d5_window_hours):
            progress.last_d5_run = now

    if progress.last_d7_run is None or now - progress.last_d7_run >= config.d7_every:
        if _guarded("D7", run_d7, conn, now, IdentityRules(), config.d7_window_hours):
            progress.last_d7_run = now

    if progress.last_index_run is None or now - progress.last_index_run >= config.index_every:
        # Znacznik proby przesuwa sie zawsze, takze po bledzie. Indeksowanie wisi na Ollamie, ktora
        # stoi poza tym stosem - jej brak ma kosztowac jedno podejscie na kwadrans i linijke w logu,
        # dokladnie tak jak brak pliku z kablami wylacza D6 zamiast wywracac petle.
        progress.last_index_run = now
        _guarded("indeks wektorowy", run_indexing, conn, now, progress, config)

    if progress.last_d3_run is None or now - progress.last_d3_run >= config.d3_every:
        # Znacznik przebiegu przesuwamy tylko po udanym D3, zeby awaria nie kasowala kolejnej proby.
        if _guarded("D3", run_d3, conn, now, progress, config):
            progress.last_d3_run = now


def load_cable_index() -> LineIndex | None:
    """Cables/pipelines for D6 - optional: the file is not baked into the detectors image, so a
    missing file degrades to "D6 off" instead of crashing the whole loop.
    """
    path = Path(os.environ.get("CABLES_GEOJSON", "data/infrastructure/baltic_cables.geojson"))
    if not path.exists():
        log.warning("D6: brak %s, detektor wleczenia kotwicy wylaczony", path)
        return None
    return LineIndex(load_lines(path))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    airports = load_airports(Path(os.environ.get("AIRPORTS_CSV", "data/airports.csv")))
    cable_index = load_cable_index()
    config = RunnerConfig.from_env()
    rules = DarkRules()
    log.info("runner: tick %ss, D3 co %s, okno danych D1 %s, kable dla D6: %s",
             config.tick.total_seconds(), config.d3_every, d1_window(rules, config),
             len(cable_index) if cable_index is not None else "brak")
    progress = Progress()
    while True:
        now = datetime.now(timezone.utc)
        try:
            # New connection each tick: a database restart must not silently kill the detectors forever.
            with psycopg.connect(os.environ["WACHTA_DB"], autocommit=True, connect_timeout=10) as conn:
                tick(conn, airports, now, progress, rules, config, cable_index)
        except Exception:
            # Nie tylko psycopg.Error: blad danych albo geometrii ma kosztowac jeden cykl, nie caly
            # proces. KeyboardInterrupt i SystemExit to BaseException, wiec nadal zatrzymuja petle.
            log.exception("detector tick failed, retrying next tick")
        time.sleep(config.tick.total_seconds())


if __name__ == "__main__":
    main()
