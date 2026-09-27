"""D4: a ship that went silent on AIS while under way, in a place where the receivers were working.

A gap in AIS says nothing by itself. Most gaps are the receiver's fault, not the ship's: coastal
stations reach 40-60 km, satellites pass over, message collisions drop reports in crowded water. The
transponder being switched off looks exactly the same in the data as sailing out of range.

So the gap alone is never the finding. Two questions are asked of every gap, and both are answered
from the same data, not from an assumption:

  * were other ships heard in that square while this one was quiet? If yes, the receiver was awake
    and the silence belongs to the ship.
  * did other ships go quiet in that square at the same moment? If yes, the station probably dropped
    out, and the ship is a bystander, not a suspect.

What comes out is a candidate with its own numbers attached - how long, how far, how fast it must
have sailed while invisible, how many witnesses there were - so the reader can disagree with it.
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .anchor import ShipFix
from .geo import haversine_km


@dataclass(frozen=True)
class GapRules:
    min_gap: timedelta = timedelta(minutes=45)
    max_gap: timedelta = timedelta(hours=12)   # dluzsza cisza to zwykle koniec rejsu, nie epizod
    min_sog_before: float = 3.0                # statek mial byc w ruchu, a nie stac przy nabrzezu
    cell_deg: float = 0.25                     # ok. 28 km na poludnik - zasieg jednej stacji brzegowej
    bucket: timedelta = timedelta(minutes=15)
    min_listeners: int = 3                     # ile innych statkow slychac, zeby uznac odbior za czynny
    max_simultaneous: int = 2                  # wiecej rownoczesnych zaniku w tej kratce = awaria stacji
    min_shift_km: float = 1.0                  # statek ma sie pojawic gdzie indziej, nie w tym samym punkcie
    # Predkosc wyliczona z luki rozdziela trzy zupelnie rozne sytuacje. Ponizej dolnego progu statek
    # po prostu stal (port, kotwicowisko) - cisza nic nie kryje. Powyzej gornego zaden statek nie
    # plynie, wiec to nie jest rejs, tylko blad pozycji albo dwa statki pod jednym numerem.
    min_implied_kt: float = 2.0
    max_implied_kt: float = 30.0


@dataclass(frozen=True)
class GapAlert:
    mmsi: str
    name: str | None
    vanished_at: datetime
    resumed_at: datetime
    vanish_lat: float
    vanish_lon: float
    resume_lat: float
    resume_lon: float
    sog_before: float | None
    shift_km: float
    implied_kt: float                # ile musial plynac, zeby pokonac te droge niewidziany
    listeners: int                   # inne statki slyszane w tej kratce w czasie ciszy
    simultaneous: int                # inne statki, ktore zamilkly tam w tym samym czasie
    verdict: str                     # co z odbiorem: czy cisza w ogole nalezy do statku
    motion: str                      # co ze statkiem: plynal, stal, czy dane sa niemozliwe

    @property
    def duration(self) -> timedelta:
        return self.resumed_at - self.vanished_at


def _cell(lat: float, lon: float, size: float) -> tuple[int, int]:
    return int(lat // size), int(lon // size)


def _buckets(start: datetime, end: datetime, step: timedelta) -> list[int]:
    """Whole time buckets strictly inside the gap - the moments the ship should have been heard."""
    first = int(start.timestamp() // step.total_seconds()) + 1
    last = int(end.timestamp() // step.total_seconds())
    return list(range(first, last))


def by_ship(fixes: Iterable[ShipFix]) -> dict[str, list[ShipFix]]:
    tracks: dict[str, list[ShipFix]] = {}
    for fix in fixes:
        tracks.setdefault(fix.mmsi, []).append(fix)
    for track in tracks.values():
        track.sort(key=lambda f: f.ts)
    return tracks


def _heard(fixes: Iterable[ShipFix], rules: GapRules) -> dict[tuple[int, int, int], set[str]]:
    """Who was heard in which square in which quarter of an hour - the witnesses for every gap."""
    index: dict[tuple[int, int, int], set[str]] = {}
    step = rules.bucket.total_seconds()
    for fix in fixes:
        row, col = _cell(fix.lat, fix.lon, rules.cell_deg)
        key = (row, col, int(fix.ts.timestamp() // step))
        index.setdefault(key, set()).add(fix.mmsi)
    return index


def find_gaps(fixes: Sequence[ShipFix], rules: GapRules = GapRules()) -> list[GapAlert]:
    """Every silence worth a second look, newest measurement attached to each one."""
    tracks = by_ship(fixes)
    heard = _heard(fixes, rules)

    # Najpierw wszystkie zaniki, potem dopiero werdykt: zeby stwierdzic awarie stacji, trzeba wiedziec,
    # czy w tej samej kratce i tej samej chwili zamilkl ktos jeszcze.
    raw: list[tuple[ShipFix, ShipFix]] = []
    for track in tracks.values():
        for before, after in zip(track, track[1:]):
            span = after.ts - before.ts
            if not (rules.min_gap <= span <= rules.max_gap):
                continue
            if before.sog is not None and before.sog < rules.min_sog_before:
                continue
            if haversine_km(before.lat, before.lon, after.lat, after.lon) < rules.min_shift_km:
                continue
            raw.append((before, after))

    silenced: dict[tuple[int, int, int], set[str]] = {}
    step = rules.bucket.total_seconds()
    for before, _ in raw:
        row, col = _cell(before.lat, before.lon, rules.cell_deg)
        silenced.setdefault((row, col, int(before.ts.timestamp() // step)), set()).add(before.mmsi)

    alerts: list[GapAlert] = []
    for before, after in raw:
        row, col = _cell(before.lat, before.lon, rules.cell_deg)
        witnesses: set[str] = set()
        for bucket in _buckets(before.ts, after.ts, rules.bucket):
            witnesses |= heard.get((row, col, bucket), set())
        witnesses.discard(before.mmsi)

        key = (row, col, int(before.ts.timestamp() // step))
        together = len(silenced.get(key, set()) - {before.mmsi})

        hours = (after.ts - before.ts).total_seconds() / 3600
        km = haversine_km(before.lat, before.lon, after.lat, after.lon)

        implied = km / 1.852 / hours if hours else 0.0
        if implied > rules.max_implied_kt:
            motion = "predkosc niemozliwa - dane do sprawdzenia"
        elif implied < rules.min_implied_kt:
            motion = "statek praktycznie stal"
        else:
            motion = "plynal w czasie ciszy"

        if together > rules.max_simultaneous:
            verdict = "prawdopodobna awaria odbioru"
        elif len(witnesses) >= rules.min_listeners:
            verdict = "cisza przy dzialajacym odbiorze"
        else:
            verdict = "brak swiadkow - luka w zasiegu"

        alerts.append(GapAlert(
            mmsi=before.mmsi, name=before.name or after.name,
            vanished_at=before.ts, resumed_at=after.ts,
            vanish_lat=round(before.lat, 4), vanish_lon=round(before.lon, 4),
            resume_lat=round(after.lat, 4), resume_lon=round(after.lon, 4),
            sog_before=before.sog, shift_km=round(km, 1),
            implied_kt=round(implied, 1),
            listeners=len(witnesses), simultaneous=together, verdict=verdict, motion=motion,
        ))

    alerts.sort(key=lambda a: (a.verdict != "cisza przy dzialajacym odbiorze", -a.listeners))
    return alerts


def suspicious(alerts: Iterable[GapAlert]) -> list[GapAlert]:
    """Only the silences the data itself cannot explain away: heard-from area, and the ship sailing.

    Both conditions have to hold. A ship quiet at a berth explains itself, and so does one whose
    apparent speed is impossible - that is a data problem, worth reading, but it is not a ship going
    dark on purpose.
    """
    return [a for a in alerts
            if a.verdict == "cisza przy dzialajacym odbiorze" and a.motion == "plynal w czasie ciszy"]


def impossible(alerts: Iterable[GapAlert]) -> list[GapAlert]:
    """Gaps whose arithmetic does not close - one hull cannot have done this."""
    return [a for a in alerts if a.motion == "predkosc niemozliwa - dane do sprawdzenia"]
