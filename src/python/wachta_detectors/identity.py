"""D7: one identity, two hulls - or one hull whose identity keeps changing.

An MMSI is not a ship. It is a number typed into a radio, reassigned when a vessel changes flag, and
occasionally copied onto a second vessel on purpose. The data shows the difference plainly once the
right question is asked: a single hull cannot be in two places at once, so a track that jumps back
and forth between two areas faster than any ship can sail is not one ship.

Two things are told apart here, because they call for different reactions:

  * a bad fix - one position out of line between two consistent ones. A decoding error or a moment
    of nonsense from the receiver. Common, boring, and it must not be reported as fraud.
  * two hulls - the track keeps alternating between separated areas, with real runs of consistent
    movement on each side. One number, two ships.

The static side is checked too: a name or a ship type that changes under one number. That alone is
weak evidence, because crews mistype and registries lag, so it is reported as a separate fact rather
than folded into the verdict.
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .anchor import ShipFix
from .geo import haversine_km

MAX_HULL_KT = 40.0          # szybciej nie plynie nic, co wozi ladunek; kutry i wodoloty tez nie

# Nie kazdy numer MMSI nalezy do statku. Standard ITU rezerwuje calE prefiksy na co innego, a
# smiglowiec ratowniczy pod numerem 111xxxxxx robi 160 wezlow zgodnie z przeznaczeniem. Bez tej
# tabeli detektor oglaszal cztery smiglowce Duńskiej sluzby SAR jako podszywanie sie pod statki.
PREFIKSY = (
    ("111", "statek powietrzny SAR"),
    ("970", "nadajnik ratunkowy AIS-SART"),
    ("972", "nadajnik czlowieka za burta"),
    ("974", "radiopława EPIRB"),
    ("99", "znak nawigacyjny"),
    ("98", "jednostka pomocnicza"),
    ("00", "stacja brzegowa"),
    ("0", "grupa stacji"),
)


def mmsi_kind(mmsi: str) -> str:
    """What the number is reserved for, per the ITU numbering plan."""
    number = str(mmsi or "").strip()
    for prefix, kind in PREFIKSY:
        if number.startswith(prefix):
            return kind
    return "statek"


@dataclass(frozen=True)
class IdentityRules:
    max_hull_kt: float = MAX_HULL_KT
    min_segment_fixes: int = 3         # tyle spojnych pozycji pod rzad, zeby uznac odcinek za realny
    min_separation_km: float = 20.0    # jak daleko od siebie musza lezec skupiska, by byly osobne
    min_alternations: int = 2          # ile razy tor musi przeskoczyc tam i z powrotem


@dataclass(frozen=True)
class Jump:
    mmsi: str
    at: datetime
    km: float
    minutes: float
    implied_kt: float
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float


@dataclass
class IdentityReport:
    mmsi: str
    verdict: str                       # "dwa kadluby", "bledny punkt" albo "spojny"
    jumps: list[Jump] = field(default_factory=list)
    clusters: list[tuple[float, float, int]] = field(default_factory=list)   # lat, lon, ile odcinkow
    alternations: int = 0
    names: tuple[str, ...] = ()
    fixes: int = 0

    @property
    def max_implied_kt(self) -> float:
        return max((j.implied_kt for j in self.jumps), default=0.0)


def implied_kt(a: ShipFix, b: ShipFix) -> float:
    hours = (b.ts - a.ts).total_seconds() / 3600
    if hours <= 0:
        return 0.0
    return haversine_km(a.lat, a.lon, b.lat, b.lon) / 1.852 / hours


def find_jumps(track: Sequence[ShipFix], rules: IdentityRules = IdentityRules()) -> list[Jump]:
    """Transitions no single hull could have made."""
    out = []
    for a, b in zip(track, track[1:]):
        kt = implied_kt(a, b)
        if kt > rules.max_hull_kt:
            out.append(Jump(mmsi=a.mmsi, at=b.ts,
                            km=round(haversine_km(a.lat, a.lon, b.lat, b.lon), 1),
                            minutes=round((b.ts - a.ts).total_seconds() / 60, 1),
                            implied_kt=round(kt, 1),
                            from_lat=a.lat, from_lon=a.lon, to_lat=b.lat, to_lon=b.lon))
    return out


def _segments(track: Sequence[ShipFix], rules: IdentityRules) -> list[list[ShipFix]]:
    """The track cut at every impossible transition - each piece is one hull's plausible movement."""
    runs: list[list[ShipFix]] = [[track[0]]] if track else []
    for a, b in zip(track, track[1:]):
        if implied_kt(a, b) > rules.max_hull_kt:
            runs.append([b])
        else:
            runs[-1].append(b)
    return runs


def _centroid(run: Sequence[ShipFix]) -> tuple[float, float]:
    return sum(f.lat for f in run) / len(run), sum(f.lon for f in run) / len(run)


def examine(track: Sequence[ShipFix], rules: IdentityRules = IdentityRules()) -> IdentityReport:
    """What one MMSI's whole track says about how many ships are wearing that number."""
    ordered = sorted(track, key=lambda f: f.ts)
    names = tuple(sorted({f.name for f in ordered if f.name}))
    report = IdentityReport(mmsi=ordered[0].mmsi if ordered else "", verdict="spojny",
                            names=names, fixes=len(ordered))
    if len(ordered) < 2:
        return report

    report.jumps = find_jumps(ordered, rules)
    if not report.jumps:
        return report

    # Tylko odcinki dostatecznie dlugie sa dowodem na cokolwiek; pojedynczy punkt to blad odczytu.
    solid = [run for run in _segments(ordered, rules) if len(run) >= rules.min_segment_fixes]
    groups: list[list[tuple[float, float]]] = []
    labels: list[int] = []
    for run in solid:
        point = _centroid(run)
        for i, group in enumerate(groups):
            if any(haversine_km(*point, *other) <= rules.min_separation_km for other in group):
                group.append(point)
                labels.append(i)
                break
        else:
            groups.append([point])
            labels.append(len(groups) - 1)

    report.clusters = [(round(sum(p[0] for p in g) / len(g), 3),
                        round(sum(p[1] for p in g) / len(g), 3), len(g)) for g in groups]
    report.alternations = sum(1 for x, y in zip(labels, labels[1:]) if x != y)

    if len(groups) >= 2 and report.alternations >= rules.min_alternations:
        report.verdict = "dwa kadluby"
    else:
        report.verdict = "bledny punkt"
    return report


def by_ship(fixes: Iterable[ShipFix]) -> dict[str, list[ShipFix]]:
    tracks: dict[str, list[ShipFix]] = {}
    for fix in fixes:
        tracks.setdefault(fix.mmsi, []).append(fix)
    for track in tracks.values():
        track.sort(key=lambda f: f.ts)
    return tracks


def scan(fixes: Iterable[ShipFix], rules: IdentityRules = IdentityRules()) -> list[IdentityReport]:
    """Every ship MMSI whose own track contradicts itself, worst first.

    Numbers reserved for something other than a ship are left out entirely rather than judged by a
    ship's speed limit - a rescue helicopter is not an impostor for flying.
    """
    reports = [examine(track, rules) for mmsi, track in by_ship(fixes).items()
               if mmsi_kind(mmsi) == "statek"]
    flagged = [r for r in reports if r.verdict != "spojny"]
    flagged.sort(key=lambda r: (r.verdict != "dwa kadluby", -r.alternations, -r.max_implied_kt))
    return flagged


def renamed(fixes: Iterable[ShipFix]) -> list[IdentityReport]:
    """Numbers that broadcast more than one name - weak on its own, worth listing beside the rest."""
    out = []
    for track in by_ship(fixes).values():
        report = examine(track)
        if len(report.names) > 1:
            out.append(report)
    return out
