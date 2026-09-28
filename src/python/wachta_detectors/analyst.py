"""Answering a question from retrieved facts, and refusing to publish anything else.

The retrieval half is ordinary: embed the question, take the nearest documents above a threshold,
number them. The half that matters is what happens to the model's answer afterwards, because a
language model asked to summarise evidence will, given the chance, produce a fluent sentence that
the evidence does not support.

Two gates run on every sentence, and both are mechanical:

  * the citation gate - a sentence with no reference, or a reference to a fact that does not exist,
    is dropped. This catches invention.
  * the number gate - every number in a sentence must appear in the fact it cites. This catches the
    other failure, the one the first version missed: a sentence that cites a real fact and then
    misstates it. Measured on this project's own output, the citation gate alone passed "wsparcie
    dla Ukrainy wyniosło 426 mld" next to a claim that the figure was absent, and attributed results
    from Danish waters to the Gulf of Finland.

What survives both gates is printed together with the facts, so any claim can be traced in one
glance. What does not survive is printed too, under its own heading - a silent filter would hide how
often the model reaches past its evidence, and that number is worth knowing.
"""
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from .vector_store import Hit

# Zmierzone na 600 zdarzeniach GDELT modelem bge-m3 (2026-09-27): pytania sensowne trafialy z
# wynikiem 0,570-0,729, pytania bez zwiazku z korpusem 0,354-0,445. Prog lezy w tej luce.
MIN_RELEVANT = 0.50

LICZBA = re.compile(r"\d+(?:[.,]\d+)?")
# Model pisze odnosniki na trzy sposoby: [3], [1,2] i [1-8]. Pierwsza wersja znala tylko pierwszy,
# wiec odrzucala zdania z zakresem jako "bez odnosnika" - w tym uczciwe zastrzezenia typu
# "brak danych w podanych faktach [1-8]", czyli dokladnie te, ktore warto zachowac.
ODNOSNIK = re.compile(r"\[\s*(\d+(?:\s*[-,]\s*\d+)*)\s*\]")


@dataclass(frozen=True)
class Fact:
    number: int
    text: str
    source: str | None = None

    def __str__(self) -> str:
        return f"[{self.number}] {self.text}" + (f" ({self.source})" if self.source else "")


@dataclass(frozen=True)
class Judgement:
    sentence: str
    accepted: bool
    reason: str = ""


@dataclass
class Answer:
    question: str
    facts: list[Fact] = field(default_factory=list)
    accepted: list[str] = field(default_factory=list)
    rejected: list[Judgement] = field(default_factory=list)

    @property
    def kept_share(self) -> float:
        total = len(self.accepted) + len(self.rejected)
        return len(self.accepted) / total if total else 0.0


def facts_from_hits(hits: Sequence[Hit]) -> list[Fact]:
    """Numbered facts, in the order the model will see them."""
    return [Fact(number=i, text=h.document.text, source=h.document.metadata.get("url"))
            for i, h in enumerate(hits, start=1)]


def numbers_in(text: str) -> set[str]:
    """Numbers as written, with the decimal comma folded onto the dot so 9,5 and 9.5 agree."""
    return {n.replace(",", ".").rstrip(".0").rstrip(".") or "0" for n in LICZBA.findall(text)}


def split_sentences(note: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", note or "") if s.strip()]


def _cited_numbers(sentence: str) -> set[int]:
    """Every fact number a sentence points at, whether written singly, as a list or as a range."""
    out: set[int] = set()
    for group in ODNOSNIK.findall(sentence):
        if "-" in group:
            first, last = (int(x) for x in group.split("-", 1))
            out.update(range(min(first, last), max(first, last) + 1))
        else:
            out.update(int(x) for x in group.split(","))
    return out


MIN_SLOW = 3        # ponizej tego zdanie nie niesie tresci, tylko odnosnik


def _tresc(sentence: str) -> str:
    """The sentence with its citations removed - what it actually says."""
    return ODNOSNIK.sub(" ", sentence).strip(" .,:;-")


def judge(sentence: str, facts: Sequence[Fact]) -> Judgement:
    """Decides whether one sentence may be published, and says why when it may not."""
    cited = sorted(_cited_numbers(sentence))
    if not cited:
        return Judgement(sentence, False, "brak odnosnika do faktu")

    # Odnosnik bez zdania to nie jest zdanie. Model zapytany o Iran odpowiedzial osiem razy tym samym
    # zdaniem z kolejnymi numerami i raz samym "[8]" - wszystko z poprawnymi odnosnikami i bez liczb,
    # wiec pierwsza wersja bramki przepuscila osiem z dziewieciu i ogłosila 89% przyjetych.
    if len(_tresc(sentence).split()) < MIN_SLOW:
        return Judgement(sentence, False, "odnosnik bez tresci")

    known = {f.number: f for f in facts}
    missing = [n for n in cited if n not in known]
    if missing:
        return Judgement(sentence, False, f"odnosnik do nieistniejacego faktu: {missing}")

    # Liczba w zdaniu musi pochodzic z ktoregos z cytowanych faktow. Numery odnosnikow nie licza sie
    # jako liczby zdania - inaczej "[3]" sam by sie uzasadnial.
    bez_odnosnikow = ODNOSNIK.sub(" ", sentence)
    zrodlowe = set().union(*(numbers_in(known[n].text) for n in cited)) if cited else set()
    obce = numbers_in(bez_odnosnikow) - zrodlowe
    if obce:
        return Judgement(sentence, False, f"liczby spoza cytowanych faktow: {sorted(obce)}")

    return Judgement(sentence, True)


def review(note: str, facts: Sequence[Fact]) -> tuple[list[str], list[Judgement]]:
    """Runs every gate over a whole note, including the one that only a whole note can see."""
    accepted, rejected = [], []
    widziane: set[str] = set()
    for sentence in split_sentences(note):
        verdict = judge(sentence, facts)
        if verdict.accepted:
            # Powtorzone zdanie nie dodaje wiedzy, a osiem kopii robi z notatki sciane tekstu i
            # zawyza udzial przyjetych. Porownujemy TRESC, bo kopie roznily sie tylko numerem.
            klucz = " ".join(_tresc(sentence).lower().split())
            if klucz in widziane:
                rejected.append(Judgement(sentence, False, "powtorzenie zdania juz przyjetego"))
                continue
            widziane.add(klucz)
            accepted.append(sentence)
        else:
            rejected.append(verdict)
    return accepted, rejected


def build_prompt(question: str, facts: Sequence[Fact]) -> str:
    ponumerowane = "\n".join(str(f) for f in facts)
    return f"""Jestes analitykiem. Odpowiedz KROTKO po polsku (maksymalnie 6 zdan) wylacznie na
podstawie ponizszych faktow. Zasady bezwzglednie obowiazujace:
- Kazde zdanie musi zawierac odnosnik w nawiasie kwadratowym do numeru faktu, np. [3].
- Kazda liczba w zdaniu musi pochodzic z cytowanego faktu. Nie przeliczaj i nie zaokraglaj.
- Nie wolno dodawac informacji, ktorej nie ma w faktach. Zadnych domyslow o przyczynach.
- Jesli fakty nie odpowiadaja na pytanie, napisz wprost, ze danych brak.

PYTANIE: {question}

FAKTY:
{ponumerowane}

ODPOWIEDZ:"""


class Analyst:
    """Retrieval, one model call, two gates. Nothing is published that fails either."""

    def __init__(self, store, embedder, ask_model, k: int = 8,
                 min_score: float = MIN_RELEVANT) -> None:
        self._store = store
        self._embedder = embedder
        self._ask = ask_model
        self._k = k
        self._min_score = min_score

    def retrieve(self, question: str) -> list[Hit]:
        vector = self._embedder.embed([question])[0]
        return self._store.search(vector, k=self._k, min_score=self._min_score)

    def answer(self, question: str) -> Answer:
        hits = self.retrieve(question)
        facts = facts_from_hits(hits)
        if not facts:
            # Brak faktow powyzej progu to prawdziwa odpowiedz, a nie powod, zeby pytac model.
            return Answer(question=question, facts=[], accepted=[],
                          rejected=[Judgement("", False, "nic w korpusie nie przekroczylo progu")])
        accepted, rejected = review(self._ask(build_prompt(question, facts)), facts)
        return Answer(question=question, facts=facts, accepted=accepted, rejected=rejected)
