"""Land events from GDELT: who did what to whom, where, when, and which article says so.

GDELT publishes a package of events every fifteen minutes, free and without a key. One row is one
event extracted from one article: two actors, a CAMEO action code, coordinates and the source URL.

Two things this module refuses to do, because both would turn a noisy feed into false certainty:
  * treat one row as one fact - the same event appears in many articles, each as its own row;
  * translate a CAMEO code into a claim about what happened. The code says what the article reported.
"""
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone

# CAMEO root codes, grouped the way an analyst reads them.
ROOT_CODES = {
    "01": "wypowiedz publiczna", "02": "apel", "03": "deklaracja wspolpracy", "04": "konsultacje",
    "05": "wspolpraca dyplomatyczna", "06": "wspolpraca materialna", "07": "pomoc",
    "08": "ustepstwo", "09": "sledztwo", "10": "zadanie", "11": "dezaprobata", "12": "odrzucenie",
    "13": "grozba", "14": "protest", "15": "demonstracja sily", "16": "zerwanie relacji",
    "17": "przymus", "18": "napasc", "19": "walka", "20": "przemoc masowa",
}

# GDELT's own four-way split: 1-2 cooperation, 3-4 conflict; material outranks verbal.
QUAD_CLASS = {1: "wspolpraca slowna", 2: "wspolpraca materialna", 3: "konflikt slowny", 4: "konflikt zbrojny"}

CONFLICT_ROOTS = frozenset({"13", "14", "15", "17", "18", "19", "20"})
AID_ROOTS = frozenset({"07"})

# Column positions in the GDELT 2.0 export file (61 tab-separated columns, no header).
COL = {
    "id": 0, "day": 1, "actor1": 6, "actor1_country": 7, "actor2": 16, "actor2_country": 17,
    "event_code": 26, "root_code": 28, "quad_class": 29, "goldstein": 30, "mentions": 31,
    "avg_tone": 34, "geo_name": 52, "geo_country": 53, "lat": 56, "lon": 57,
    "added": 59, "url": 60,
}


@dataclass(frozen=True)
class Event:
    id: str
    day: date
    added: datetime | None      # DATEADDED - kiedy GDELT dodal wiersz; jedyny czas z dokladnoscia do sekund
    actor1: str | None
    actor1_country: str | None
    actor2: str | None
    actor2_country: str | None
    root_code: str
    event_code: str
    quad_class: int
    goldstein: float | None      # -10 (najgorsze) .. +10 (najlepsze), skala CAMEO
    mentions: int
    place: str | None
    country: str | None
    lat: float
    lon: float
    url: str

    @property
    def kind(self) -> str:
        return ROOT_CODES.get(self.root_code, f"kod {self.root_code}")

    @property
    def quad(self) -> str:
        return QUAD_CLASS.get(self.quad_class, "?")

    @property
    def is_conflict(self) -> bool:
        return self.root_code in CONFLICT_ROOTS

    @property
    def is_aid(self) -> bool:
        return self.root_code in AID_ROOTS

    @property
    def summary(self) -> str:
        """Plain reading: who, what, to whom - deliberately without adding any interpretation."""
        who = self.actor1 or "?"
        whom = f" -> {self.actor2}" if self.actor2 else ""
        return f"{who}{whom}: {self.kind}"


def _text(parts: list[str], key: str) -> str | None:
    value = parts[COL[key]].strip() if COL[key] < len(parts) else ""
    return value or None


def parse_rows(rows: Iterable[str]) -> Iterator[Event]:
    """Parses GDELT export lines, skipping anything without usable coordinates."""
    for row in rows:
        parts = row.split("\t")
        if len(parts) < 61:
            continue
        try:
            lat = float(parts[COL["lat"]])
            lon = float(parts[COL["lon"]])
            day = datetime.strptime(parts[COL["day"]], "%Y%m%d").date()
        except ValueError:
            continue

        try:
            added = datetime.strptime(parts[COL["added"]], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            added = None

        root = (parts[COL["root_code"]] or "").strip().zfill(2)
        try:
            quad = int(parts[COL["quad_class"]])
        except ValueError:
            quad = 0
        try:
            goldstein = float(parts[COL["goldstein"]])
        except ValueError:
            goldstein = None
        try:
            mentions = int(parts[COL["mentions"]])
        except ValueError:
            mentions = 1

        yield Event(
            id=parts[COL["id"]].strip(), day=day, added=added,
            actor1=_text(parts, "actor1"), actor1_country=_text(parts, "actor1_country"),
            actor2=_text(parts, "actor2"), actor2_country=_text(parts, "actor2_country"),
            root_code=root, event_code=(parts[COL["event_code"]] or "").strip(),
            quad_class=quad, goldstein=goldstein, mentions=mentions,
            place=_text(parts, "geo_name"), country=_text(parts, "geo_country"),
            lat=lat, lon=lon, url=_text(parts, "url") or "",
        )


def in_box(events: Iterable[Event], lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> list[Event]:
    return [e for e in events if lat_min <= e.lat <= lat_max and lon_min <= e.lon <= lon_max]


def cluster_events(events: Iterable[Event], round_to: int = 2) -> list[list[Event]]:
    """The same happening arrives as many rows. Cluster by day, action, rounded position and actors.

    GDELT emits a separate row per article pair, so one happening is routinely a dozen event ids.
    Anything that wants all the coverage of one happening - the two-versions comparison above all -
    has to work on clusters, not on single ids.
    """
    buckets: dict[tuple, list[Event]] = {}
    for e in events:
        key = (e.day, e.root_code, round(e.lat, round_to), round(e.lon, round_to),
               (e.actor1_country or e.actor1 or ""), (e.actor2_country or e.actor2 or ""))
        buckets.setdefault(key, []).append(e)
    return sorted(buckets.values(), key=lambda group: -len(group))


def group_repeats(events: Iterable[Event], round_to: int = 2) -> list[tuple[Event, int]]:
    """Representative row of each cluster with the number of rows behind it.

    That count measures how widely something was written up, not how certain it is: a hundred
    articles repeating one agency dispatch are still one source.
    """
    return [(max(group, key=lambda x: x.mentions), len(group)) for group in cluster_events(events, round_to)]
