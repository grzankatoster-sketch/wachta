"""D5: two ships side by side for long enough to move cargo between them.

Ship-to-ship transfer is how oil changes hands away from a port and away from the paperwork. The
shape in the data is simple - two hulls within a few hundred metres, barely moving, for half an hour
or more - and it is also the shape of two ships waiting at anchor next to each other, which happens
thousands of times a day and means nothing.

So the anchorages have to be removed, and this module derives them from the traffic itself rather
than from a harbour database that would have to be found, licensed and kept current: a square where
many different ships sit still over the course of a day is an anchorage, whatever a chart calls it.
That keeps the detector honest in waters nobody has mapped for us, which is most of them.

What it cannot see is the other half of the problem. If one of the two ships has its transponder off,
only one hull appears and no pair is formed. That case is "dark STS" and needs D4 alongside this -
a lone ship loitering where nobody else is, with a gap in someone else's track nearby.
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil

from .anchor import ShipFix, by_ship
from .geo import KM_PER_DEG_LAT
from .geo import cell_of as _cell
from .geo import haversine_km, implied_kt, km_per_deg_lon


@dataclass(frozen=True)
class StsRules:
    max_separation_km: float = 0.8     # burta w burte to setki metrow, nie kilometry
    max_sog: float = 3.0               # przeladunek idzie na postoju albo w powolnym dryfie
    min_duration: timedelta = timedelta(minutes=30)
    max_duration: timedelta = timedelta(hours=12)  # dluzej to nie epizod, tylko nabrzeze
    # Przeladunek to zdarzenie: statki przyplywaja, stoja przy sobie i odplywaja. Kuter przywiazany
    # do kei przez cala dobe nigdzie nie plynal, i to jest jedyna rzecz, ktora go od tego odroznia.
    transit_sog: float = 4.0
    approach: timedelta = timedelta(hours=6)
    max_gap: timedelta = timedelta(minutes=12)   # przerwa dluzsza niz ta konczy spotkanie
    # Postoj jest MIEJSCEM. Statek na kotwicy zatacza luk na lancuchu, ale nie przenosi sie o
    # kilometry - a przy max_sog 3 wezly i przerwie 12 minut zmiescilby sie w tym 1,1 km.
    max_spread_km: float = 2.0
    cell_deg: float = 0.02             # ok. 2,2 km - siatka do szukania sasiadow
    # Kotwicowisko wyprowadzone z danych: kratka, w ktorej przez dobe stalo wiele roznych statkow.
    anchorage_cell_deg: float = 0.05
    anchorage_min_ships: int = 12
    anchorage_sog: float = 0.5


@dataclass(frozen=True)
class Encounter:
    mmsi_a: str
    mmsi_b: str
    name_a: str | None
    name_b: str | None
    start: datetime
    end: datetime
    lat: float
    lon: float
    min_separation_km: float
    mean_separation_km: float
    mean_sog: float | None
    samples: int
    drift_km: float                    # ile para przesunela sie w trakcie: 0 = staly postoj
    in_anchorage: bool
    both_under_way: bool               # czy oba statki plynely w okolicach tego spotkania

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def anchorages(fixes: Iterable[ShipFix], rules: StsRules = StsRules()) -> set[tuple[int, int]]:
    """Squares where many different ships sat still - read off the traffic, not off a chart."""
    still: dict[tuple[int, int], set[str]] = {}
    for fix in fixes:
        if fix.sog is not None and fix.sog <= rules.anchorage_sog:
            still.setdefault(_cell(fix.lat, fix.lon, rules.anchorage_cell_deg), set()).add(fix.mmsi)
    return {cell for cell, ships in still.items() if len(ships) >= rules.anchorage_min_ships}


def _under_way(fixes: Iterable[ShipFix], rules: StsRules) -> dict[str, list[datetime]]:
    """When was each ship actually sailing - the evidence that it came and left under its own power.

    Speed is taken from the report when the ship sends one, and worked out from two positions when it
    does not. A missing speed field must not silently turn a sailing ship into a moored one.
    """
    moving: dict[str, list[datetime]] = {}
    for mmsi, track in by_ship(fixes).items():
        stamps = []
        for i, fix in enumerate(track):
            fast = fix.sog is not None and fix.sog >= rules.transit_sog
            if not fast and i:
                hours = (fix.ts - track[i - 1].ts).total_seconds() / 3600
                if 0 < hours <= 1:
                    km = haversine_km(track[i - 1].lat, track[i - 1].lon, fix.lat, fix.lon)
                    fast = implied_kt(km, hours) >= rules.transit_sog
            if fast:
                stamps.append(fix.ts)
        if stamps:
            moving[mmsi] = stamps
    return moving


def _sailed_near(stamps: Sequence[datetime], start: datetime, end: datetime,
                 window: timedelta) -> bool:
    lo, hi = start - window, end + window
    left, right = 0, len(stamps)
    while left < right:                       # bisect na posortowanej liscie chwil
        mid = (left + right) // 2
        if stamps[mid] < lo:
            left = mid + 1
        else:
            right = mid
    return left < len(stamps) and stamps[left] <= hi


def slow_fixes(fixes: Iterable[ShipFix], rules: StsRules) -> list[ShipFix]:
    """Fixes at which a transfer could be happening - slow by the ship's own account, or by ours.

    A missing speed field used to mean "slow", which let a ship crossing the strait at twenty knots
    count as standing still for over an hour. Where the field is absent the speed is worked out from
    the neighbouring positions instead, and only then judged.
    """
    out: list[ShipFix] = []
    for track in by_ship(fixes).values():
        for i, fix in enumerate(track):
            if fix.sog is not None:
                if fix.sog <= rules.max_sog:
                    out.append(fix)
                continue
            speeds = []
            for other in (track[i - 1] if i else None, track[i + 1] if i + 1 < len(track) else None):
                if other is None:
                    continue
                hours = abs((fix.ts - other.ts).total_seconds()) / 3600
                if 0 < hours <= 1:
                    speeds.append(implied_kt(haversine_km(fix.lat, fix.lon, other.lat, other.lon), hours))
            # Brak sasiada w zasiegu godziny: nie ma jak ocenic, wiec nie zgadujemy na korzysc alarmu.
            if speeds and min(speeds) <= rules.max_sog:
                out.append(fix)
    return out


def _slow_by_minute(fixes: Iterable[ShipFix], rules: StsRules) -> dict[datetime, list[ShipFix]]:
    """The same fixes, grouped by the minute they belong to."""
    frames: dict[datetime, list[ShipFix]] = {}
    for fix in slow_fixes(fixes, rules):
        frames.setdefault(fix.ts.replace(second=0, microsecond=0), []).append(fix)
    return frames


def _pairs_in_frame(frame: Sequence[ShipFix], rules: StsRules):
    """Ships close enough to touch, found through a grid so the day does not take an hour."""
    grid: dict[tuple[int, int], list[ShipFix]] = {}
    for fix in frame:
        grid.setdefault(_cell(fix.lat, fix.lon, rules.cell_deg), []).append(fix)

    # Pelne sasiedztwo, a nie polowa: przy polowie para lezaca w dwoch kratkach wypadalaby wtedy,
    # gdy porzadek numerow MMSI i porzadek kratek sa przeciwne. Duplikaty odsiewa warunek nizej.
    #
    # Zasieg liczony osobno dla obu osi, bo stopien dlugosci kurczy sie z szerokoscia: na 75 stopniu
    # kratka 0,02 stopnia ma w poziomie 0,57 km, wiec jeden pierscien sasiadow nie siega nawet
    # dopuszczalnych 0,8 km i para po prostu znika. Ten sam blad byl juz raz w spatial_index.py.
    rows = ceil(rules.max_separation_km / (rules.cell_deg * KM_PER_DEG_LAT))
    for (row, col), here in grid.items():
        lat = here[0].lat
        cols = ceil(rules.max_separation_km / (rules.cell_deg * km_per_deg_lon(lat)))
        neighbours = [f
                      for dr in range(-rows, rows + 1)
                      for dc in range(-cols, cols + 1)
                      for f in grid.get((row + dr, col + dc), ())]
        for a in here:
            for b in neighbours:
                if b.mmsi <= a.mmsi:
                    continue        # kazda para raz, w stalej kolejnosci
                km = haversine_km(a.lat, a.lon, b.lat, b.lon)
                if km <= rules.max_separation_km:
                    yield (a.mmsi, b.mmsi), a, b, km


def find_encounters(fixes: Sequence[ShipFix], rules: StsRules = StsRules()) -> list[Encounter]:
    """Every sustained side-by-side meeting, with the anchorage ones marked rather than hidden."""
    parked = anchorages(fixes, rules)
    moving = _under_way(fixes, rules)
    frames = _slow_by_minute(fixes, rules)

    # Kazda para zbiera kolejne minuty kontaktu; przerwa dluzsza niz max_gap zamyka spotkanie.
    open_now: dict[tuple[str, str], dict] = {}
    done: list[dict] = []

    for minute in sorted(frames):
        seen: set[tuple[str, str]] = set()
        for key, a, b, km in _pairs_in_frame(frames[minute], rules):
            if key in seen:
                continue        # ta sama para widziana dwa razy w jednej minucie liczy sie raz
            seen.add(key)
            state = open_now.get(key)
            if state is not None and minute - state["last"] <= rules.max_gap:
                state["last"] = minute
                state["samples"] += 1
                state["sum_km"] += km
                state["min_km"] = min(state["min_km"], km)
                state["lats"].append((a.lat + b.lat) / 2)
                state["lons"].append((a.lon + b.lon) / 2)
                state["sogs"] += [s for s in (a.sog, b.sog) if s is not None]
                state["name_a"] = state["name_a"] or a.name
                state["name_b"] = state["name_b"] or b.name
                continue
            if state is not None:
                done.append(state)
            open_now[key] = {
                "key": key, "start": minute, "last": minute, "samples": 1,
                "sum_km": km, "min_km": km, "lats": [(a.lat + b.lat) / 2],
                "lons": [(a.lon + b.lon) / 2],
                "sogs": [s for s in (a.sog, b.sog) if s is not None],
                "name_a": a.name, "name_b": b.name,
            }

        for key, state in list(open_now.items()):
            if key not in seen and minute - state["last"] > rules.max_gap:
                done.append(state)
                del open_now[key]

    done.extend(open_now.values())

    encounters = []
    for state in done:
        span = state["last"] - state["start"]
        if not (rules.min_duration <= span <= rules.max_duration):
            continue
        lat = sum(state["lats"]) / len(state["lats"])
        lon = sum(state["lons"]) / len(state["lons"])
        drift = haversine_km(state["lats"][0], state["lons"][0], state["lats"][-1], state["lons"][-1])
        encounters.append(Encounter(
            mmsi_a=state["key"][0], mmsi_b=state["key"][1],
            name_a=state["name_a"], name_b=state["name_b"],
            start=state["start"], end=state["last"],
            lat=round(lat, 4), lon=round(lon, 4),
            min_separation_km=round(state["min_km"], 3),
            mean_separation_km=round(state["sum_km"] / state["samples"], 3),
            mean_sog=round(sum(state["sogs"]) / len(state["sogs"]), 2) if state["sogs"] else None,
            samples=state["samples"], drift_km=round(drift, 2),
            in_anchorage=_cell(lat, lon, rules.anchorage_cell_deg) in parked,
            both_under_way=all(
                _sailed_near(moving.get(mmsi, ()), state["start"], state["last"], rules.approach)
                for mmsi in state["key"]),
        ))

    encounters.sort(key=lambda e: (e.in_anchorage, not e.both_under_way, -e.duration.total_seconds()))
    return encounters


def offshore(encounters: Iterable[Encounter]) -> list[Encounter]:
    """Meetings worth reading: away from anchorages, and between ships that sailed to get there.

    The second condition does most of the work. Without it the detector returns every fishing boat
    tied to a quay next to another fishing boat, which is thousands of pairs and no information.
    """
    return [e for e in encounters if not e.in_anchorage and e.both_under_way]


@dataclass(frozen=True)
class Loiter:
    """A ship holding position on its own - one half of a transfer whose other half may be dark."""
    mmsi: str
    name: str | None
    start: datetime
    end: datetime
    lat: float
    lon: float
    in_anchorage: bool
    sailed_in: bool

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def stationary_periods(fixes: Sequence[ShipFix], rules: StsRules = StsRules()) -> list[Loiter]:
    """Stretches where one ship sat still, whether or not anything was next to it.

    D5 needs two hulls to see a meeting. When the second transponder is off there is only one, and
    then this is all that remains visible: a ship that stopped in open water for no stated reason.

    Segments are cut on the full track and only then reduced to the slow parts, never the other way
    round. Dropping the fast positions first hides the proof that the ship left: a 40-minute stop, a
    6 km passage and a second 40-minute stop came back as one 92-minute loiter centred on a point
    the ship never sat at. A stop ends on confirmed movement, on too large a displacement, or on a
    gap in the reports - the three ways the data can say "this is no longer the same standstill".
    """
    parked = anchorages(fixes, rules)
    moving = _under_way(fixes, rules)
    wolne = {id(f) for f in slow_fixes(fixes, rules)}

    runs: list[list[ShipFix]] = []
    for track in by_ship(fixes).values():
        run: list[ShipFix] = []
        for fix in track:
            if id(fix) not in wolne:
                # Potwierdzony ruch konczy postoj. To nie jest przerwa w danych, tylko dowod, ze
                # statek juz nie stal - i wlasnie ten dowod znikal, gdy szybkie pozycje odrzucano
                # przed segmentacja zamiast po niej.
                if run:
                    runs.append(run)
                run = []
                continue
            if run and (fix.ts - run[-1].ts > rules.max_gap
                        or haversine_km(run[0].lat, run[0].lon, fix.lat, fix.lon) > rules.max_spread_km):
                runs.append(run)
                run = []
            run.append(fix)
        if run:
            runs.append(run)

    out: list[Loiter] = []
    for run in runs:
        span = run[-1].ts - run[0].ts
        if not (rules.min_duration <= span <= rules.max_duration):
            continue
        lat = sum(f.lat for f in run) / len(run)
        lon = sum(f.lon for f in run) / len(run)
        out.append(Loiter(
            mmsi=run[0].mmsi, name=next((f.name for f in run if f.name), None),
            start=run[0].ts, end=run[-1].ts, lat=round(lat, 4), lon=round(lon, 4),
            in_anchorage=_cell(lat, lon, rules.anchorage_cell_deg) in parked,
            sailed_in=_sailed_near(moving.get(run[0].mmsi, ()), run[0].ts, run[-1].ts, rules.approach),
        ))
    out.sort(key=lambda p: (p.in_anchorage, -p.duration.total_seconds()))
    return out
