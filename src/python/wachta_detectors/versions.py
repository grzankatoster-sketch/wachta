"""Two versions of the same event: who reported it, in what language, with what tone.

GDELT publishes, next to the events, a file of mentions: one row per article that reported a given
event, with the outlet's domain, the document tone and - for translated articles - the source
language. Joined on the event id, that is enough to ask the question this project cares about:

    the same happening, as told by which side, and does the telling differ?

What this does NOT do, on purpose:
  * it does not say who is lying. It shows that coverage differs, and by how much;
  * it does not treat tone as truth. Tone is a property of the text, not of the world;
  * a side with one article is not "a side". Comparisons need a minimum number of articles.
"""
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from statistics import mean

# Kto po ktorej stronie - i czy domena krajowa sama wystarczy - to decyzja ANALITYCZNA, nie
# techniczna. Dlatego mieszka w wersjonowanym pliku danych, nie w kodzie: zmiane przypisania widac
# w historii repozytorium jako zmiane polityki, a nie jako poprawke w module.
POLICY_PATH = Path(__file__).resolve().parents[3] / "data" / "analysis" / "outlet_sides.json"


@dataclass(frozen=True)
class SidePolicy:
    """Which outlet speaks for which side, and whether a country domain may stand in for that.

    Deliberately narrow: the point is to compare how THIS conflict is told, not to classify the
    world's press. An outlet nobody assigned belongs to no side at all - better a missing voice than
    a wrongly labelled one.

    tld_fallback is kept apart from the assignments because it is a different claim. An assignment
    says "we read this outlet and placed it"; the fallback says "a country domain is enough". With
    the fallback on, the promise above does not hold: any blog under .ru joins the RU side and drags
    its mean tone. Which is why it is a switch in the configuration, off by default, and not a line
    of code.
    """
    outlets: Mapping[str, str]
    tld_sides: Mapping[str, str]
    tld_fallback: bool
    version: str = ""

    def side(self, source: str) -> str | None:
        """Side of the telling for one outlet domain, or None when it is not assigned."""
        assigned, _ = self.side_with_origin(source)
        return assigned

    def side_with_origin(self, source: str) -> tuple[str | None, str]:
        """The side, and whether it was NAMED in the list or GUESSED from the country domain.

        The difference matters enough to travel with the value. A named outlet is an editorial
        decision somebody made and can be argued with; a side taken from the top level domain is an
        assumption that everything published under `.lv` speaks with one voice, which is false for
        any country with a Russian-language press - and which would give a bicycle shop a position
        on the war. Measured on three hours of GDELT: without the fallback the layer finds 4 events
        with two sides, with it 18. Dropping three quarters of the output is too high a price for
        purity, so the guess stays and is labelled instead.
        """
        domain = source.lower().strip()
        if domain in self.outlets:
            return self.outlets[domain], "lista"
        parts = domain.split(".")
        if len(parts) >= 2 and ".".join(parts[-2:]) in self.outlets:
            return self.outlets[".".join(parts[-2:])], "lista"
        if not self.tld_fallback:
            return None, "brak"
        guessed = self.tld_sides.get(parts[-1] if parts else "")
        return guessed, ("domena" if guessed else "brak")

    @classmethod
    def from_file(cls, path: Path) -> "SidePolicy":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            outlets={k.lower(): v for k, v in raw["outlets"].items()},
            tld_sides={k.lower(): v for k, v in raw.get("tld_sides", {}).items()},
            tld_fallback=bool(raw.get("tld_fallback", False)),
            version=str(raw.get("wersja", "")),
        )


@lru_cache(maxsize=None)
def load_policy(path: Path | str | None = None) -> SidePolicy:
    return SidePolicy.from_file(Path(path) if path else POLICY_PATH)


COL = {
    "event_id": 0, "event_time": 1, "mention_time": 2, "type": 3, "source": 4, "url": 5,
    "confidence": 11, "doc_len": 12, "tone": 13, "translation": 14,
}


@dataclass(frozen=True)
class Mention:
    event_id: str
    source: str            # domena
    url: str
    tone: float | None     # wydzwiek dokumentu wg GDELT: ujemny = negatywny
    language: str | None   # jezyk oryginalu, gdy artykul byl tlumaczony
    confidence: int

    @property
    def side(self) -> str | None:
        """Side of the telling under the configured policy, or None when the outlet is unassigned."""
        return load_policy().side(self.source)


@dataclass(frozen=True)
class SideView:
    side: str
    articles: int
    mean_tone: float
    languages: tuple[str, ...]
    examples: tuple[str, ...] = field(default=())
    from_tld: int = 0            # ile z tych artykulow dostalo strone z domeny, a nie z listy

    @property
    def only_guessed(self) -> bool:
        """True when nothing on this side was a named outlet - the whole voice is an assumption."""
        return self.articles > 0 and self.from_tld == self.articles


@dataclass(frozen=True)
class Versions:
    event_id: str
    sides: tuple[SideView, ...]

    @property
    def total_articles(self) -> int:
        return sum(s.articles for s in self.sides)

    @property
    def is_weak(self) -> bool:
        """True when the comparison rests on thin ground: one article, or only guessed outlets.

        Both cases look identical in the output - two sides, two numbers, a tone gap - and both
        deserve the same warning. A side built entirely from country-domain guesses is not a side
        that anyone edited; it is a bucket.
        """
        return any(s.articles < 2 or s.only_guessed for s in self.sides)

    @property
    def tone_gap(self) -> float:
        """Difference between the most and least negative side. Zero when there is nothing to compare."""
        if len(self.sides) < 2:
            return 0.0
        tones = [s.mean_tone for s in self.sides]
        return round(max(tones) - min(tones), 2)


def parse_mentions(rows: Iterable[str]) -> Iterator[Mention]:
    for raw in rows:
        parts = raw.split("\t")
        if len(parts) < 15:
            continue
        try:
            tone = float(parts[COL["tone"]])
        except ValueError:
            tone = None
        try:
            confidence = int(parts[COL["confidence"]])
        except ValueError:
            confidence = 0

        translation = parts[COL["translation"]] or ""
        language = None
        if "srclc:" in translation:
            language = translation.split("srclc:", 1)[1].split(";")[0].strip() or None

        yield Mention(
            event_id=parts[COL["event_id"]].strip(),
            source=parts[COL["source"]].strip(),
            url=parts[COL["url"]].strip(),
            tone=tone,
            language=language,
            confidence=confidence,
        )


def compare_sides(mentions: Iterable[Mention], min_articles: int = 1,
                  policy: SidePolicy | None = None) -> Versions | None:
    """Groups one event's mentions by side. Sides below `min_articles` are dropped, not averaged in.

    The default of one article is deliberate: measured on four hours of GDELT, requiring two articles
    per side left three comparable events in the whole world, while one article left twenty-two. A
    thin comparison flagged as thin (see `is_weak`) beats no comparison at all.
    """
    polityka = policy or load_policy()
    by_side: dict[str, list[Mention]] = {}
    event_id = None
    zgadniete: set[str] = set()          # adresy, ktorych strona wzieła sie z domeny, nie z listy
    for m in mentions:
        event_id = event_id or m.event_id
        side, skad = polityka.side_with_origin(m.source)
        if m.tone is None or side is None:   # nieprzypisana redakcja nie jest zadna strona
            continue
        if skad == "domena":
            zgadniete.add(m.url)
        by_side.setdefault(side, []).append(m)

    sides = []
    for side, group in by_side.items():
        # Jeden artykul to jeden glos. GDELT wystawia wiersz na kazda WZMIANKE, wiec ten sam tekst
        # potrafi wrocic kilka razy - a wtedy podwaja swoj wplyw na srednia, przepycha strone przez
        # min_articles i kasuje ostrzezenie o cienkiej podstawie. Zostaje wzmianka najpewniejsza.
        najlepsze: dict[str, Mention] = {}
        for m in sorted(group, key=lambda x: -x.confidence):
            najlepsze.setdefault(m.url, m)
        group = list(najlepsze.values())

        if len(group) < min_articles:
            continue
        sides.append(SideView(
            side=side,
            articles=len(group),
            mean_tone=round(mean(m.tone for m in group), 2),
            languages=tuple(sorted({m.language for m in group if m.language})),
            examples=tuple(m.url for m in sorted(group, key=lambda x: -x.confidence)[:2]),
            from_tld=sum(1 for m in group if m.url in zgadniete),
        ))

    if not sides or event_id is None:
        return None
    return Versions(event_id=event_id, sides=tuple(sorted(sides, key=lambda s: -s.articles)))


def group_by_event(mentions: Iterable[Mention]) -> dict[str, list[Mention]]:
    grouped: dict[str, list[Mention]] = {}
    for m in mentions:
        grouped.setdefault(m.event_id, []).append(m)
    return grouped
