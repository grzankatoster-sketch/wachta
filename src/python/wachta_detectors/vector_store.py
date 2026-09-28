"""Storing embedded documents and finding the nearest ones - in memory, or in pgvector.

Two implementations behind one interface, for a reason that is not academic. The in-memory one runs
in tests and in CI, where there is no database; the pgvector one is what the product uses. Keeping
them behind the same protocol means the analyst above them never learns which is underneath, and the
same test can be pointed at either.

What the search returns is a ranked list with a score, never a verdict. A nearest neighbour is the
most similar text in the corpus even when nothing in the corpus is relevant at all, so the caller is
given the score and has to decide whether it means anything. The `min_score` argument exists so that
decision can be made explicit instead of forgotten.
"""
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .embeddings import cosine, normalise


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Hit:
    document: Document
    score: float            # 1.0 = identyczny kierunek, 0.0 = brak zwiazku


class VectorStore(Protocol):
    def add(self, documents: Sequence[Document], vectors: Sequence[Sequence[float]]) -> None: ...

    def search(self, vector: Sequence[float], k: int = 5, min_score: float = 0.0,
               where: Callable[[Document], bool] | None = None) -> list[Hit]: ...

    def __len__(self) -> int: ...


class InMemoryVectorStore:
    """Exhaustive search over everything held. Honest about what that costs.

    There is no index here: every query compares against every document. For the few thousand events
    a day this project collects that is milliseconds, and it removes a whole class of "the index was
    stale" bugs from the tests. Past roughly a hundred thousand documents this is the wrong tool and
    pgvector is the right one.
    """

    def __init__(self) -> None:
        self._docs: list[Document] = []
        self._vectors: list[list[float]] = []

    def add(self, documents: Sequence[Document], vectors: Sequence[Sequence[float]]) -> None:
        if len(documents) != len(vectors):
            raise ValueError(f"{len(documents)} dokumentow na {len(vectors)} wektorow")
        known = {d.id for d in self._docs}
        for doc, vector in zip(documents, vectors):
            if doc.id in known:
                continue        # ten sam dokument dwa razy nie ma prawa podwoic swojej wagi w wynikach
            self._docs.append(doc)
            self._vectors.append(normalise(vector))
            known.add(doc.id)

    def search(self, vector: Sequence[float], k: int = 5, min_score: float = 0.0,
               where: Callable[[Document], bool] | None = None) -> list[Hit]:
        query = normalise(vector)
        hits = []
        for doc, stored in zip(self._docs, self._vectors):
            if where is not None and not where(doc):
                continue
            score = cosine(query, stored)
            if score >= min_score:
                hits.append(Hit(doc, round(score, 4)))
        hits.sort(key=lambda h: (-h.score, h.document.id))
        return hits[:k]

    def __len__(self) -> int:
        return len(self._docs)


class PgVectorStore:
    """The same interface over pgvector. Distance comes from the database, not from Python.

    pgvector's `<=>` is cosine DISTANCE, so the score is one minus it. Filtering is passed as SQL
    rather than as a Python callable, because filtering after the k nearest have already been chosen
    silently returns fewer - and sometimes zero - results.
    """

    def __init__(self, connection, table: str = "document_embedding", dimensions: int = 1024) -> None:
        self._conn = connection
        self._table = table
        self._dimensions = dimensions

    def add(self, documents: Sequence[Document], vectors: Sequence[Sequence[float]]) -> None:
        import json as _json

        if len(documents) != len(vectors):
            raise ValueError(f"{len(documents)} dokumentow na {len(vectors)} wektorow")
        rows = [(d.id, d.text, _json.dumps(d.metadata, ensure_ascii=False),
                 "[" + ",".join(f"{x:.6f}" for x in normalise(v)) + "]")
                for d, v in zip(documents, vectors)]
        with self._conn.cursor() as cur:
            cur.executemany(
                f"""INSERT INTO {self._table} (id, text, metadata, embedding)
                    VALUES (%s, %s, %s::jsonb, %s::vector)
                    ON CONFLICT (id) DO UPDATE
                    SET text = EXCLUDED.text, metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding""",
                rows)

    def search(self, vector: Sequence[float], k: int = 5, min_score: float = 0.0,
               where: str | None = None, params: Sequence[Any] = ()) -> list[Hit]:
        import json as _json

        literal = "[" + ",".join(f"{x:.6f}" for x in normalise(vector)) + "]"
        clause = f"WHERE {where}" if where else ""
        with self._conn.cursor() as cur:
            cur.execute(
                f"""SELECT id, text, metadata, 1 - (embedding <=> %s::vector) AS score
                    FROM {self._table} {clause}
                    ORDER BY embedding <=> %s::vector LIMIT %s""",
                (literal, *params, literal, k))
            rows = cur.fetchall()
        return [Hit(Document(r[0], r[1], r[2] if isinstance(r[2], dict) else _json.loads(r[2] or "{}")),
                    round(float(r[3]), 4))
                for r in rows if float(r[3]) >= min_score]

    def __len__(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {self._table}")
            return int(cur.fetchone()[0])


def index_documents(store: VectorStore, embedder, documents: Iterable[Document],
                    on_progress: Callable[[int, int], None] | None = None) -> int:
    """Embeds and stores in one pass. Returns how many went in."""
    docs = list(documents)
    if not docs:
        return 0
    from .embeddings import embed_in_batches

    vectors = embed_in_batches(embedder, [d.text for d in docs], on_progress)
    store.add(docs, vectors)
    return len(docs)
