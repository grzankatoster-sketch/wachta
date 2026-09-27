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
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from statistics import mean

# Which side of the telling an outlet belongs to. Deliberately narrow: the point is to compare how
# THIS conflict is told, not to classify the world's press. An outlet we have not assigned returns
# None and is counted in no side at all - better a missing voice than a wrongly labelled one.
OUTLET_SIDES = {
    # rosyjskie panstwowe i prorzadowe
    "rt.com": "RU", "tass.com": "RU", "tass.ru": "RU", "ria.ru": "RU", "sputnikglobe.com": "RU",
    "sputniknews.com": "RU", "iz.ru": "RU", "kp.ru": "RU", "gazeta.ru": "RU", "lenta.ru": "RU",
    "rg.ru": "RU", "vedomosti.ru": "RU", "kommersant.ru": "RU", "interfax.ru": "RU", "tvzvezda.ru": "RU",
    # rosyjskie niezalezne i na emigracji - osobna strona, bo to inna perspektywa niz panstwowa
    "meduza.io": "RU-niezalezne", "themoscowtimes.com": "RU-niezalezne", "novayagazeta.eu": "RU-niezalezne",
    "istories.media": "RU-niezalezne", "agents.media": "RU-niezalezne",
    # ukrainskie
    "kyivpost.com": "UA", "unian.info": "UA", "unian.ua": "UA", "ukrinform.net": "UA",
    "ukrinform.ua": "UA", "pravda.com.ua": "UA", "kyivindependent.com": "UA", "epravda.com.ua": "UA",
    "censor.net": "UA", "liga.net": "UA", "suspilne.media": "UA", "rbc.ua": "UA", "nv.ua": "UA",
    # bialoruskie
    "belta.by": "BY", "sb.by": "BY", "nashaniva.com": "BY-niezalezne", "zerkalo.io": "BY-niezalezne",
    # polskie
    "notesfrompoland.com": "PL", "tvpworld.com": "PL", "pap.pl": "PL", "onet.pl": "PL",
    "wyborcza.pl": "PL", "rp.pl": "PL", "tvn24.pl": "PL", "polskieradio.pl": "PL", "wnp.pl": "PL",
    # zachodnie
    "bbc.com": "ZACHOD", "bbc.co.uk": "ZACHOD", "theguardian.com": "ZACHOD", "reuters.com": "ZACHOD",
    "apnews.com": "ZACHOD", "cnn.com": "ZACHOD", "nytimes.com": "ZACHOD", "washingtonpost.com": "ZACHOD",
    "ft.com": "ZACHOD", "politico.eu": "ZACHOD", "dw.com": "ZACHOD", "spiegel.de": "ZACHOD",
    "lemonde.fr": "ZACHOD", "euronews.com": "ZACHOD", "telegraph.co.uk": "ZACHOD", "nbcnews.com": "ZACHOD",
    "abcnews.go.com": "ZACHOD", "cbsnews.com": "ZACHOD", "foxnews.com": "ZACHOD", "newsweek.com": "ZACHOD",
}

# Country domains that map onto a side on their own.
TLD_SIDES = {"ru": "RU", "ua": "UA", "by": "BY", "pl": "PL", "de": "ZACHOD", "fr": "ZACHOD",
             "uk": "ZACHOD", "it": "ZACHOD", "es": "ZACHOD", "nl": "ZACHOD", "se": "ZACHOD",
             "no": "ZACHOD", "dk": "ZACHOD", "fi": "ZACHOD", "lt": "ZACHOD", "lv": "ZACHOD",
             "ee": "ZACHOD", "cz": "ZACHOD", "sk": "ZACHOD"}

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
        """Side of the telling, or None when we have not assigned this outlet to any."""
        domain = self.source.lower().strip()
        if domain in OUTLET_SIDES:
            return OUTLET_SIDES[domain]
        parts = domain.split(".")
        if len(parts) >= 2 and ".".join(parts[-2:]) in OUTLET_SIDES:
            return OUTLET_SIDES[".".join(parts[-2:])]
        tld = parts[-1] if parts else ""
        return TLD_SIDES.get(tld)


@dataclass(frozen=True)
class SideView:
    side: str
    articles: int
    mean_tone: float
    languages: tuple[str, ...]
    examples: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class Versions:
    event_id: str
    sides: tuple[SideView, ...]

    @property
    def total_articles(self) -> int:
        return sum(s.articles for s in self.sides)

    @property
    def is_weak(self) -> bool:
        """True when some side speaks with a single article - a comparison, but a thin one."""
        return any(s.articles < 2 for s in self.sides)

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


def compare_sides(mentions: Iterable[Mention], min_articles: int = 1) -> Versions | None:
    """Groups one event's mentions by side. Sides below `min_articles` are dropped, not averaged in.

    The default of one article is deliberate: measured on four hours of GDELT, requiring two articles
    per side left three comparable events in the whole world, while one article left twenty-two. A
    thin comparison flagged as thin (see `is_weak`) beats no comparison at all.
    """
    by_side: dict[str, list[Mention]] = {}
    event_id = None
    for m in mentions:
        event_id = event_id or m.event_id
        side = m.side
        if m.tone is None or side is None:   # nieprzypisana redakcja nie jest zadna strona
            continue
        by_side.setdefault(side, []).append(m)

    sides = []
    for side, group in by_side.items():
        if len(group) < min_articles:
            continue
        sides.append(SideView(
            side=side,
            articles=len(group),
            mean_tone=round(mean(m.tone for m in group), 2),
            languages=tuple(sorted({m.language for m in group if m.language})),
            examples=tuple(m.url for m in sorted(group, key=lambda x: -x.confidence)[:2]),
        ))

    if not sides or event_id is None:
        return None
    return Versions(event_id=event_id, sides=tuple(sorted(sides, key=lambda s: -s.articles)))


def group_by_event(mentions: Iterable[Mention]) -> dict[str, list[Mention]]:
    grouped: dict[str, list[Mention]] = {}
    for m in mentions:
        grouped.setdefault(m.event_id, []).append(m)
    return grouped
