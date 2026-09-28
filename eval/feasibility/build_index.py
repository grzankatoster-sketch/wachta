"""Indexes the collected events by meaning and asks questions in Polish about English text.

This is the measurement that decides whether the semantic layer is worth having. Keyword search
over this corpus is close to useless: the events come from GDELT in English, the two-versions layer
adds Russian and Ukrainian outlets, and the questions a person actually asks are in Polish. If the
index cannot bridge that, it is decoration.

  python eval/feasibility/build_index.py ["pytanie"]
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.embeddings import OllamaEmbedder  # noqa: E402
from wachta_detectors.vector_store import Document, InMemoryVectorStore, index_documents  # noqa: E402

FIX = ROOT / "eval" / "fixtures"
OUT = FIX / "events_index.json"

PYTANIA = [
    "rosyjski statek przy kablu podmorskim",
    "protesty i zamieszki w miastach",
    "pomoc wojskowa dla Ukrainy",
    "porwanie i zatrzymanie ludzi",
    "wybuch i ostrzal artyleryjski",
]


def opis(e: dict) -> str:
    """One line per event, in the words the source used - no translation, no summary of a summary."""
    czesci = [e.get("actor1") or "", e.get("actor2") or "", e.get("kind") or "",
              e.get("place") or "", e.get("actor1_country") or "", e.get("actor2_country") or ""]
    return " | ".join(c for c in czesci if c)


def main() -> int:
    snapshot = FIX / "events_snapshot.json"
    if not snapshot.exists():
        print("brak events_snapshot.json - uruchom najpierw fetch_events.py")
        return 1
    events = json.loads(snapshot.read_text(encoding="utf-8"))["events"]
    docs = [Document(id=str(e["id"]), text=opis(e),
                     metadata={"place": e.get("place"), "kind": e.get("kind"),
                               "conflict": e.get("conflict"), "aid": e.get("aid"),
                               "sources": e.get("sources"), "url": e.get("url"),
                               "lat": e.get("lat"), "lon": e.get("lon")})
            for e in events if opis(e).strip()]

    embedder = OllamaEmbedder()
    store = InMemoryVectorStore()
    start = time.time()
    print(f"licze wektory dla {len(docs)} zdarzen ({embedder.model}, {embedder.dimensions} wymiarow)")
    index_documents(store, embedder, docs,
                    on_progress=lambda done, total: print(f"  {done}/{total}", flush=True)
                    if done % 100 < 25 else None)
    trwalo = time.time() - start
    print(f"gotowe w {trwalo:.0f} s ({trwalo / max(1, len(docs)) * 1000:.0f} ms na zdarzenie)")

    pytania = [sys.argv[1]] if len(sys.argv) > 1 else PYTANIA
    wyniki = []
    for pytanie in pytania:
        vector = embedder.embed([pytanie])[0]
        hits = store.search(vector, k=4)
        print("")
        print(f'PYTANIE (po polsku): "{pytanie}"')
        for h in hits:
            print(f"  {h.score:.3f}  {h.document.text[:78]}")
        wyniki.append({"question": pytanie,
                       "hits": [{"score": h.score, "text": h.document.text,
                                 "place": h.document.metadata.get("place"),
                                 "url": h.document.metadata.get("url")} for h in hits]})

    OUT.write_text(json.dumps({
        "model": embedder.model, "dimensions": embedder.dimensions,
        "documents": len(docs), "seconds": round(trwalo, 1),
        "note": ("Teksty zdarzen sa po angielsku, pytania po polsku. Wynik to podobienstwo, nie "
                 "trafnosc - najblizszy sasiad istnieje zawsze, takze gdy nic nie pasuje."),
        "questions": wyniki,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("")
    print(f"zapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
