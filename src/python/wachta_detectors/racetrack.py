"""D2 - loiter patterns in a flight track: the racetrack of an air tanker, and plain orbiting.

A transport aircraft flies from A to B. A tanker on station does something visibly different: it
walks the same line back and forth for an hour or two, at one altitude, inside a small box. The
same shape is flown by reconnaissance aircraft, so the shape alone names the behaviour, never the
mission - the caller adds the aircraft type and says "refuelling" only when the type says tanker.

Two loiter shapes are told apart here, because they mean different things:

  * racetrack - long legs on one axis with sharp reversals at the ends; what a tanker or an AWACS
    flies when it holds a station. Headings cluster around two opposite directions.
  * orbit - a continuous turn in one direction; a holding pattern, a circling reconnaissance run or
    an aircraft waiting for a slot. Headings are spread evenly.

Nothing here trusts the reported track angle: bearings are computed from consecutive positions, so
a trace without a track field works the same as one with it.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from heapq import heappop, heappush
from math import atan2, cos, degrees, radians, sin
from statistics import median

from .geo import bearing_deg, haversine_km

MIN_STEP_KM = 0.4       # ponizej tego dystansu kierunek miedzy punktami to juz tylko szum pomiaru
TURN_COS = 0.34         # ok. 70 stopni od osi - samolot jest w zakrecie, nie na nodze toru
STRAIGHT_DEG = 20.0     # ile kierunek moze odejsc od poczatku odcinka, zeby uznac go za prosty


@dataclass(frozen=True)
class TracePoint:
    t: datetime
    lat: float
    lon: float
    alt_ft: float | None = None
    gs_kt: float | None = None


@dataclass(frozen=True)
class LoiterRules:
    """Every threshold is a decision that can be argued with, so each one is named and visible."""
    min_duration: timedelta = timedelta(minutes=40)
    min_points: int = 20
    max_radius_km: float = 90.0        # wzorzec ma stac w miejscu, nie przesuwac sie przez kontynent
    max_alt_spread_ft: float = 2500.0  # tankowanie idzie na jednym poziomie lotu
    min_alt_ft: float = 10000.0        # nizej to krecenie sie nad lotniskiem, nie dyzur
    min_reversals: int = 3             # trzy zawroty = cztery nogi; jeden zawrot to jeszcze nie wzorzec
    min_leg_km: float = 25.0           # tor wyscigowy ma proste nogi; okrag nie ma zadnej
    min_orbit_turn_deg: float = 720.0  # dwa pelne okrazenia w te sama strone


@dataclass(frozen=True)
class Loiter:
    kind: str                # "tor wyscigowy" albo "krazenie"
    start: datetime
    end: datetime
    points: int
    centre_lat: float
    centre_lon: float
    radius_km: float
    alt_ft: float | None
    alt_spread_ft: float
    axis_deg: float | None   # os toru wyscigowego, None dla krazenia
    reversals: int
    longest_leg_km: float    # najdluzszy prosty odcinek: to odroznia tor od okregu
    straight_share: float    # jaka czesc drogi przebyta prosto, a nie w zakrecie
    turn_deg: float          # suma zmian kierunku ze znakiem: duza i jednostronna = krazenie

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def angle_diff(a: float, b: float) -> float:
    """Signed difference a -> b in degrees, always in (-180, 180]."""
    return (b - a + 180.0) % 360.0 - 180.0


def axis_deg(bearings: list[float]) -> float | None:
    """Dominant axis of a set of headings, treating a heading and its opposite as the same line.

    Doubling the angles folds 10 deg and 190 deg onto the same direction, so a mean over the doubled
    angles finds the line of the legs instead of cancelling them out.
    """
    if not bearings:
        return None
    x = sum(cos(radians(2 * b)) for b in bearings)
    y = sum(sin(radians(2 * b)) for b in bearings)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return None
    return (degrees(atan2(y, x)) / 2.0) % 180.0


def _legs(points: list[TracePoint]) -> list[tuple[float, float]]:
    """Bearing and length of each step long enough to mean something, in flight order."""
    legs: list[tuple[float, float]] = []
    anchor = 0
    for i in range(1, len(points)):
        km = haversine_km(points[anchor].lat, points[anchor].lon, points[i].lat, points[i].lon)
        if km >= MIN_STEP_KM:
            legs.append((bearing_deg(points[anchor].lat, points[anchor].lon, points[i].lat, points[i].lon), km))
            anchor = i
    return legs


def straight_runs(legs: list[tuple[float, float]]) -> list[float]:
    """Lengths in km of the stretches flown straight - the legs of a racetrack.

    A run ends when the heading has wandered more than STRAIGHT_DEG from where the run began. This is
    what separates the two shapes: a racetrack is mostly straight line with two turns, while a circle
    of any radius has no straight stretch at all, only a heading that keeps sliding away.
    """
    runs: list[float] = []
    start_bearing, run_km = None, 0.0
    for bearing, km in legs:
        if start_bearing is not None and abs(angle_diff(start_bearing, bearing)) <= STRAIGHT_DEG:
            run_km += km
            continue
        if start_bearing is not None:
            runs.append(run_km)
        start_bearing, run_km = bearing, km
    if start_bearing is not None:
        runs.append(run_km)
    return runs


def _centre(points: list[TracePoint]) -> tuple[float, float, float]:
    lat = sum(p.lat for p in points) / len(points)
    lon = sum(p.lon for p in points) / len(points)
    radius = max(haversine_km(lat, lon, p.lat, p.lon) for p in points)
    return lat, lon, radius


def _altitudes(points: list[TracePoint]) -> list[float]:
    return [p.alt_ft for p in points if p.alt_ft is not None]


class _GrowingBox:
    """Running centre, radius and altitude statistics for a segment that only ever gets longer.

    The mean centre and the altitude spread and median all update per added point, in constant or
    logarithmic time. The radius cannot: it is the largest distance from a centre that moves as
    points arrive, so no running total tracks it. It is bracketed instead, against a fixed anchor:

      * upper bound - the largest distance any point reaches from the anchor, plus the distance the
        mean centre has drifted away from that anchor. The triangle inequality makes this an honest
        ceiling on the true radius.
      * lower bound - the distance from the mean centre to the one point known to sit farthest from
        the anchor. Any single point is an honest floor on the true radius.

    When both brackets fall on the same side of the limit the verdict is settled without touching the
    other points. Only when the limit lands between them is every point measured again, and the
    anchor then moves to the current centre so the brackets reopen. Nothing here is approximated: the
    answer is always the one a full scan would give. A track whose radius sits exactly on the limit
    would rescan on every point and cost what the old code always cost - that is the worst case, not
    the normal one.
    """

    def __init__(self, anchor: TracePoint) -> None:
        self._anchor = (anchor.lat, anchor.lon)
        self._far = (anchor.lat, anchor.lon)   # punkt najdalszy od kotwicy...
        self._far_km = 0.0                     # ...i jego odleglosc, czyli gorna polowa widelek
        self._seen: list[TracePoint] = []
        self._lat_sum = 0.0
        self._lon_sum = 0.0
        self._alt_min: float | None = None
        self._alt_max: float | None = None
        # Dwa kopce trzymaja mediane wysokosci na szczytach: dolna polowa jako wartosci ujemne
        # (kopiec maksimow), gorna normalnie. Sortowanie calej listy przy kazdym punkcie bylo drugim,
        # obok promienia, zrodlem kwadratowej pracy.
        self._low: list[float] = []
        self._high: list[float] = []

    def add(self, point: TracePoint) -> None:
        self._seen.append(point)
        self._lat_sum += point.lat
        self._lon_sum += point.lon
        km = haversine_km(self._anchor[0], self._anchor[1], point.lat, point.lon)
        if km > self._far_km:
            self._far_km, self._far = km, (point.lat, point.lon)
        if point.alt_ft is not None:
            self._add_altitude(point.alt_ft)

    def fits(self, rules: LoiterRules) -> bool:
        """Same verdict as measuring the whole segment from scratch, at a fraction of the cost."""
        if self._radius_exceeds(rules.max_radius_km):
            return False
        if not self._low:
            return True
        return (self._alt_max - self._alt_min <= rules.max_alt_spread_ft
                and self._median_alt() >= rules.min_alt_ft)

    def _centre(self) -> tuple[float, float]:
        # Sumowanie w kolejnosci lotu, jak w sum() po wycinku - zeby wynik byl bit w bit ten sam.
        n = len(self._seen)
        return self._lat_sum / n, self._lon_sum / n

    def _radius_exceeds(self, limit_km: float) -> bool:
        lat, lon = self._centre()
        drift = haversine_km(lat, lon, self._anchor[0], self._anchor[1])
        if self._far_km + drift <= limit_km:
            return False
        if haversine_km(lat, lon, self._far[0], self._far[1]) > limit_km:
            return True
        return self._remeasure(lat, lon) > limit_km

    def _remeasure(self, lat: float, lon: float) -> float:
        """Exact radius around (lat, lon); the anchor moves here so the brackets open up again."""
        far_km, far = 0.0, (lat, lon)
        for p in self._seen:
            km = haversine_km(lat, lon, p.lat, p.lon)
            if km > far_km:
                far_km, far = km, (p.lat, p.lon)
        self._anchor, self._far, self._far_km = (lat, lon), far, far_km
        return far_km

    def _add_altitude(self, alt: float) -> None:
        self._alt_min = alt if self._alt_min is None else min(self._alt_min, alt)
        self._alt_max = alt if self._alt_max is None else max(self._alt_max, alt)
        if self._low and alt <= -self._low[0]:
            heappush(self._low, -alt)
        else:
            heappush(self._high, alt)
        if len(self._low) > len(self._high) + 1:
            heappush(self._high, -heappop(self._low))
        elif len(self._high) > len(self._low):
            heappush(self._low, -heappop(self._high))

    def _median_alt(self) -> float:
        if len(self._low) > len(self._high):
            return -self._low[0]
        return (-self._low[0] + self._high[0]) / 2


def _stable_segments(points: list[TracePoint], rules: LoiterRules) -> list[list[TracePoint]]:
    """Maximal runs that stay inside one box at one altitude - the candidates for a loiter.

    Grown greedily from each start; when a run ends, the next one starts where it ended, so a long
    flight is scanned once rather than once per point. The box measurements grow with the run in
    _GrowingBox instead of being taken again for every candidate end - remeasuring the prefix was
    what made a long stable track cost quadratic work despite the single sweep promised here.
    """
    segments: list[list[TracePoint]] = []
    start = 0
    while start < len(points):
        box = _GrowingBox(points[start])
        end = start
        for j in range(start, len(points)):
            box.add(points[j])
            if j + 1 - start < rules.min_points:
                continue
            if not box.fits(rules):
                break
            end = j + 1
        if end > start:
            segments.append(points[start:end])
            start = end
        else:
            start += 1
    return segments


def classify(points: list[TracePoint], rules: LoiterRules = LoiterRules()) -> Loiter | None:
    """Names the shape of one candidate segment, or returns None when it is neither shape."""
    if len(points) < rules.min_points or points[-1].t - points[0].t < rules.min_duration:
        return None

    legs = _legs(points)
    if len(legs) < 4:
        return None
    bearings = [b for b, _ in legs]

    turn = sum(angle_diff(bearings[i - 1], bearings[i]) for i in range(1, len(bearings)))
    runs = straight_runs(legs)
    total_km = sum(km for _, km in legs)
    longest_leg_km = max(runs) if runs else 0.0
    straight_share = sum(r for r in runs if r >= 0.5 * longest_leg_km) / total_km if total_km else 0.0

    axis = axis_deg(bearings)
    if axis is None:
        # Rownomierny rozklad kierunkow nie ma dominujacej osi - i wlasnie tak wyglada pelna orbita.
        # Pierwsza wersja wracala tutaj z niczym, wiec najczystszy okrag byl jedynym, ktorego
        # detektor nie widzial. Os jest potrzebna do toru wyscigowego, nie do krazenia.
        if abs(turn) < rules.min_orbit_turn_deg:
            return None
        lat, lon, radius = _centre(points)
        alts = _altitudes(points)
        return Loiter(
            kind="krazenie", start=points[0].t, end=points[-1].t, points=len(points),
            centre_lat=round(lat, 4), centre_lon=round(lon, 4), radius_km=round(radius, 1),
            alt_ft=round(median(alts)) if alts else None,
            alt_spread_ft=round(max(alts) - min(alts)) if alts else 0.0,
            axis_deg=None, reversals=0, longest_leg_km=round(longest_leg_km, 1),
            straight_share=round(straight_share, 2), turn_deg=round(turn),
        )
    # Skladowa kazdej nogi wzdluz osi: dodatnia w jedna strone, ujemna w druga.
    side = [cos(radians(b - axis)) for b in bearings]
    reversals, last = 0, 0.0
    for s in side:
        if abs(s) < TURN_COS:      # samolot jest w zakrecie na koncu toru, nie na nodze
            continue
        if last and (s > 0) != (last > 0):
            reversals += 1
        last = s

    lat, lon, radius = _centre(points)
    alts = _altitudes(points)

    if reversals >= rules.min_reversals and longest_leg_km >= rules.min_leg_km:
        kind = "tor wyscigowy"
    elif abs(turn) >= rules.min_orbit_turn_deg:
        # Nie ma prostych nog, a samolot obrocil sie kilka razy w te sama strone - to okrag.
        kind, axis = "krazenie", None
    else:
        return None

    return Loiter(
        kind=kind, start=points[0].t, end=points[-1].t, points=len(points),
        centre_lat=round(lat, 4), centre_lon=round(lon, 4), radius_km=round(radius, 1),
        alt_ft=round(median(alts)) if alts else None,
        alt_spread_ft=round(max(alts) - min(alts)) if alts else 0.0,
        axis_deg=round(axis, 1) if axis is not None else None,
        reversals=reversals, longest_leg_km=round(longest_leg_km, 1),
        straight_share=round(straight_share, 2), turn_deg=round(turn),
    )


def find_loiters(points: list[TracePoint], rules: LoiterRules = LoiterRules()) -> list[Loiter]:
    """All loiter patterns in one flight track, in the order they were flown."""
    ordered = sorted(points, key=lambda p: p.t)
    found = []
    for segment in _stable_segments(ordered, rules):
        loiter = classify(segment, rules)
        if loiter is not None:
            found.append(loiter)
    return found
