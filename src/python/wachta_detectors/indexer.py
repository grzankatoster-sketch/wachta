"""Fills the vector store, so that searching by meaning has something to search.

`PgVectorStore` and the migration that creates its table have existed for a while and nothing ever
wrote to them: the table was empty, and a search over an empty table answers "nothing found" to
every question, which looks exactly like a working search over a quiet world. This module is what
closes that gap.

Two kinds of document go in, and they are different enough to be worth naming:

  * **alerts** - what the detectors decided, from the live database. This is the corpus a person
    actually wants to question ("was anything odd near the cables last night"), and it grows on its
    own as the stack runs.
  * **events** - what the world reported, from the GDELT snapshot. Broader, older, and useful for
    context, but it does not refresh unless somebody fetches it.

Both carry `kind` in their metadata so a query can be narrowed to one or the other. Re-running is
safe: the store upserts on id, so an alert whose text changed is replaced rather than duplicated,
and one that did not change costs one write and no new row.

  python -m wachta_detectors.indexer [alerty|zdarzenia|wszystko]
"""
import json
import os
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .embeddings import DIMENSIONS, OllamaEmbedder
from .vector_store import Document, PgVectorStore, index_documents

def fixtures_dir(module_file: str | Path = __file__) -> Path:
    """Where the frozen GDELT snapshot lives, when this runs from a checkout of the repository.

    The image copies only `src/python`, so above the package there is no repository layout to walk up
    to and `parents[3]` raised IndexError - at IMPORT time, which took the whole detector loop down
    with it the moment the loop started importing this module. The snapshot is optional anyway:
    event_documents() already answers "no events" when the file is not there, so its absence has to
    look like a missing file and not like a crash.
    """
    here = Path(module_file).resolve()
    korzen = here.parents[3] if len(here.parents) > 3 else here.parent
    return korzen / "eval" / "fixtures"


FIXTURES = fixtures_dir()
ALERT_WINDOW = timedelta(days=7)


def alert_documents(conn, since: datetime, limit: int = 2000) -> list[Document]:
    """Detector alerts as text a model can match a question against.

    The text is deliberately the human-readable sentence rather than the raw evidence JSON: an
    embedding of `{"gap_min": 46, "listeners": 12}` matches nothing anyone would type.
    """
    rows = conn.execute(
        """SELECT id, detector, entity_id, started_at, lat, lon, score, evidence::text, state
           FROM alert WHERE created_at >= %s ORDER BY created_at DESC LIMIT %s""",
        (since, limit)).fetchall()

    out = []
    for alert_id, detector, entity, started, lat, lon, score, evidence, state in rows:
        # Nie wystarczy zlapac wyjatku: json.loads("null") zwraca None, a "12" liczbe - i jedno,
        # i drugie przechodzi przez jsonb NOT NULL. Ten sam blad wywrocil dzis panel alertow we
        # froncie, wiec tutaj warunek jest o TYP, nie o brak wyjatku.
        try:
            wczytane = json.loads(evidence) if evidence else None
        except (TypeError, ValueError):
            wczytane = None
        szczegoly = wczytane if isinstance(wczytane, dict) else {}
        opis = ", ".join(f"{k} {v}" for k, v in list(szczegoly.items())[:6])
        tekst = f"{OPISY.get(detector, detector)}: {entity}"
        if opis:
            tekst += f" ({opis})"
        out.append(Document(
            id=f"alert:{alert_id}",
            text=tekst,
            metadata={"kind": "alert", "detector": detector, "entity": entity,
                      "started_at": started.isoformat() if started else None,
                      "lat": lat, "lon": lon, "score": score, "state": state},
        ))
    return out


OPISY = {
    "D1": "samolot przestal nadawac",
    "D2": "samolot na dyzurze, tor wyscigowy",
    "D3": "zaklocenia GPS w komorce",
    "D4": "statek zamilkl na AIS w ruchu",
    "D5": "przeladunek burta w burte",
    "D6": "podejrzenie wleczenia kotwicy po kablu",
    "D7": "jeden numer MMSI w dwoch miejscach",
    "D8": "nietypowe skupisko doniesien",
}


def event_documents(path: Path | None = None, limit: int = 2000) -> list[Document]:
    """GDELT events from the frozen snapshot, as one line each."""
    snapshot = path or FIXTURES / "events_snapshot.json"
    if not snapshot.exists():
        return []
    events = json.loads(snapshot.read_text(encoding="utf-8"))["events"]

    out = []
    for e in events[:limit]:
        czesci = [e.get("actor1") or "", e.get("actor2") or "", e.get("kind") or "", e.get("place") or ""]
        tekst = " | ".join(c for c in czesci if c)
        if not tekst.strip():
            continue
        out.append(Document(
            id=f"event:{e['id']}",
            text=tekst,
            metadata={"kind": "event", "place": e.get("place"), "url": e.get("url"),
                      "lat": e.get("lat"), "lon": e.get("lon"),
                      "conflict": e.get("conflict"), "sources": e.get("sources")},
        ))
    return out


def index(conn, documents: Iterable[Document], embedder=None, on_progress=None) -> int:
    """Embeds and upserts. Returns how many documents went in."""
    store = PgVectorStore(conn, dimensions=DIMENSIONS)
    return index_documents(store, embedder or OllamaEmbedder(), documents, on_progress)


def main() -> int:
    import psycopg

    sys.stdout.reconfigure(encoding="utf-8")
    czego = sys.argv[1] if len(sys.argv) > 1 else "wszystko"
    dsn = os.environ.get("WACHTA_DB")
    if not dsn:
        print("brak WACHTA_DB - nie ma gdzie zapisac wektorow")
        return 1

    since = datetime.now(timezone.utc) - ALERT_WINDOW
    with psycopg.connect(dsn, autocommit=True, connect_timeout=15) as conn:
        docs: list[Document] = []
        if czego in ("alerty", "wszystko"):
            alerty = alert_documents(conn, since)
            print(f"alertow z ostatnich {ALERT_WINDOW.days} dni: {len(alerty)}")
            docs += alerty
        if czego in ("zdarzenia", "wszystko"):
            zdarzenia = event_documents()
            print(f"zdarzen z migawki GDELT: {len(zdarzenia)}")
            docs += zdarzenia

        if not docs:
            print("nie ma czego indeksowac - to nie blad, tylko pusty korpus")
            return 0

        print(f"licze wektory dla {len(docs)} dokumentow (to trwa okolo {len(docs) * 0.16:.0f} s)")
        ile = index(conn, docs, on_progress=lambda d, t: print(f"  {d}/{t}", flush=True)
                    if d % 200 < 30 else None)
        total = conn.execute("SELECT count(*) FROM document_embedding").fetchone()[0]
        print(f"zapisano {ile}, w bazie wektorowej lacznie: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
