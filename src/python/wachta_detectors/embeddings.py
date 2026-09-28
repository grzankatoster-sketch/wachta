"""Turning text into vectors, so that events can be found by meaning rather than by keyword.

The corpus this project collects is multilingual by nature: a Russian outlet, a Ukrainian one and a
Western one describe the same event in three languages, and the whole point of the "two versions"
layer is to put them side by side. Keyword search cannot do that. The model used here (bge-m3) maps
all three onto the same space - measured on this machine, a Polish sentence and its English
equivalent score 0.72 against each other, while an unrelated Polish sentence scores 0.27.

Embedding runs on the local Ollama, so no text leaves the machine and no request is billed. That
matters more here than speed: the corpus includes source material that should not be shipped to a
third party just to be indexed.
"""
import json
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import blake2b
from math import sqrt
from typing import Protocol

OLLAMA_EMBED = "http://localhost:11434/api/embed"
DEFAULT_MODEL = "bge-m3"
DIMENSIONS = 1024        # bge-m3; zmiana modelu wymaga migracji kolumny w bazie


class Embedder(Protocol):
    """Anything that turns texts into vectors of one fixed width."""

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def normalise(vector: Sequence[float]) -> list[float]:
    """Unit length, so that a dot product is the cosine and nothing has to remember to divide."""
    length = sqrt(sum(v * v for v in vector))
    return [v / length for v in vector] if length else list(vector)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity, safe on zero vectors and on vectors of different width."""
    if len(a) != len(b):
        raise ValueError(f"rozne wymiary: {len(a)} i {len(b)}")
    na, nb = sqrt(sum(x * x for x in a)), sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


@dataclass(frozen=True)
class OllamaEmbedder:
    """The real one. Local, free, and it keeps the corpus on this machine."""

    model: str = DEFAULT_MODEL
    url: str = OLLAMA_EMBED
    timeout: float = 240.0
    batch: int = 16

    @property
    def dimensions(self) -> int:
        return DIMENSIONS

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch):
            chunk = list(texts[start:start + self.batch])
            request = urllib.request.Request(
                self.url,
                data=json.dumps({"model": self.model, "input": chunk}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                vectors = json.load(response)["embeddings"]
            if len(vectors) != len(chunk):
                raise RuntimeError(f"model zwrocil {len(vectors)} wektorow na {len(chunk)} tekstow")
            out.extend(normalise(v) for v in vectors)
        return out


@dataclass(frozen=True)
class DeterministicEmbedder:
    """A stand-in for tests and for CI, where no Ollama is running.

    It hashes tokens into buckets, so identical texts land on identical vectors and texts sharing
    words land near each other. That is enough to test the plumbing - the store, the ordering, the
    filters - and it is nowhere near enough to test meaning. No result produced with this embedder
    says anything about how well the search works; that has to be measured against the real model.
    """

    dims: int = 64

    @property
    def dimensions(self) -> int:
        return self.dims

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vector = [0.0] * self.dims
            for token in text.lower().split():
                digest = blake2b(token.encode(), digest_size=8).digest()
                vector[int.from_bytes(digest[:4], "big") % self.dims] += 1.0
            out.append(normalise(vector))
        return out


def embed_in_batches(embedder: Embedder, texts: Iterable[str],
                     on_progress=None) -> list[list[float]]:
    """Embeds a long list, reporting progress - a few thousand events take minutes, not seconds."""
    texts = list(texts)
    vectors: list[list[float]] = []
    step = max(1, len(texts) // 20)
    for i in range(0, len(texts), step):
        vectors.extend(embedder.embed(texts[i:i + step]))
        if on_progress:
            on_progress(len(vectors), len(texts))
    return vectors
