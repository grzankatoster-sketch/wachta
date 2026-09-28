"""Dark STS: one ship stopped in open water while another ship's transponder was off beside it.

D5 can only see a transfer when both hulls are transmitting. The case worth finding is the one where
they are not - and then the data holds two halves that mean nothing apart:

  * a ship that stopped in open water on its own, for no reason it declares (D5's loiter);
  * a gap in someone else's track, starting nearby and overlapping in time (D4's silence).

Put together they describe a meeting that was never broadcast. Put together they are also still not
proof: a ship can stop for weather or repairs while an unrelated transponder fails a few kilometres
away. The join narrows the sea down to a handful of places to look, which is the whole job.
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .anchor import ShipFix
from .gaps import GapAlert, GapRules, find_gaps, suspicious
from .geo import KM_PER_NM, haversine_km
from .sts import Loiter, StsRules, find_encounters, stationary_periods


@dataclass(frozen=True)
class DarkStsRules:
    max_km: float = 25.0                          # zgrubny odsiew, zanim policzymy droge naprawde
    min_overlap: timedelta = timedelta(minutes=20)
    # Sama bliskosc niczego nie znaczy: statek stojacy w ruchliwej ciesninie ma obok siebie czyjas
    # cisze co chwile. Pytanie brzmi, czy zgaszony statek MOGL do niego podejsc, postac i wrocic na
    # trase w czasie, w ktorym go nie bylo. To jest arytmetyka, nie przeczucie.
    speed_kt: float = 12.0                        # tempo podejscia i odejscia
    min_stop: timedelta = timedelta(minutes=30)   # ile czasu musi zostac na sam przeladunek


@dataclass(frozen=True)
class DarkSts:
    visible_mmsi: str
    visible_name: str | None
    dark_mmsi: str
    dark_name: str | None
    start: datetime                               # poczatek wspolnego okna
    end: datetime
    lat: float
    lon: float
    distance_km: float                            # od stojacego statku do miejsca zanikniecia
    detour_km: float                              # cala droga: zanikniecie -> postoj -> powrot
    spare_min: int                                # ile minut zostalo na postoj po odjeciu drogi
    overlap_min: int
    gap_min: int
    listeners: int                                # ilu swiadkow slychac bylo w kratce ciszy

    @property
    def overlap(self) -> timedelta:
        return self.end - self.start


def _overlap(a_start: datetime, a_end: datetime,
             b_start: datetime, b_end: datetime) -> tuple[datetime, datetime] | None:
    start, end = max(a_start, b_start), min(a_end, b_end)
    return (start, end) if start < end else None


def pair_up(loiters: Iterable[Loiter], gaps: Iterable[GapAlert],
            rules: DarkStsRules = DarkStsRules()) -> list[DarkSts]:
    """Join the two halves: a ship standing still, and a silence that began next to it."""
    found: list[DarkSts] = []
    gaps = list(gaps)
    for loiter in loiters:
        if loiter.in_anchorage or not loiter.sailed_in:
            continue
        for gap in gaps:
            if gap.mmsi == loiter.mmsi:
                continue
            km = haversine_km(loiter.lat, loiter.lon, gap.vanish_lat, gap.vanish_lon)
            if km > rules.max_km:
                continue
            back_km = haversine_km(loiter.lat, loiter.lon, gap.resume_lat, gap.resume_lon)
            detour = km + back_km

            # Okno liczone od chwili, w ktorej zgaszony statek MOGL tu dotrzec, do chwili, w ktorej
            # musial juz ruszyc, zeby zdazyc na swoja pozycje powrotu. Pierwsza wersja brala cala
            # cisze i osobno sprawdzala, czy droga sie miesci - przez co zglaszala spotkania, na
            # ktore drugi statek zdazylby dopiero po koncu postoju widocznego.
            arrives = gap.vanished_at + timedelta(hours=km / KM_PER_NM / rules.speed_kt)
            must_leave = gap.resumed_at - timedelta(hours=back_km / KM_PER_NM / rules.speed_kt)
            window = _overlap(loiter.start, loiter.end, arrives, must_leave)
            if window is None or window[1] - window[0] < rules.min_overlap:
                continue

            spare = gap.duration - timedelta(hours=detour / KM_PER_NM / rules.speed_kt)
            if spare < rules.min_stop:
                continue        # nie zdazylby podejsc, postac i wrocic - to nie bylo spotkanie
            found.append(DarkSts(
                visible_mmsi=loiter.mmsi, visible_name=loiter.name,
                dark_mmsi=gap.mmsi, dark_name=gap.name,
                start=window[0], end=window[1],
                lat=loiter.lat, lon=loiter.lon, distance_km=round(km, 1),
                detour_km=round(detour, 1),
                spare_min=round(spare.total_seconds() / 60),
                overlap_min=round((window[1] - window[0]).total_seconds() / 60),
                gap_min=round(gap.duration.total_seconds() / 60),
                listeners=gap.listeners,
            ))
    found.sort(key=lambda d: (d.distance_km, -d.spare_min))
    return found


def find_dark_sts(fixes: Sequence[ShipFix], sts_rules: StsRules = StsRules(),
                  gap_rules: GapRules = GapRules(),
                  rules: DarkStsRules = DarkStsRules()) -> list[DarkSts]:
    """The whole join from raw positions: loiters without a visible partner, next to a silence."""
    # Wykluczamy POSTOJE nakladajace sie na widoczne spotkanie, a nie caly numer MMSI. Pierwsza
    # wersja skreslala statek na cala dobe, wiec jedno bunkrowanie rano potrafilo ukryc niezalezny
    # ciemny przeladunek wieczorem.
    seen: dict[str, list[tuple[datetime, datetime]]] = {}
    for e in find_encounters(fixes, sts_rules):
        for mmsi in (e.mmsi_a, e.mmsi_b):
            seen.setdefault(mmsi, []).append((e.start, e.end))

    alone = [p for p in stationary_periods(fixes, sts_rules)
             if not any(_overlap(p.start, p.end, start, end)
                        for start, end in seen.get(p.mmsi, ()))]
    return pair_up(alone, suspicious(find_gaps(fixes, gap_rules)), rules)
