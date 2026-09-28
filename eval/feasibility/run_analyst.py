"""The RAG analyst end to end: a Polish question, English evidence, and two mechanical gates.

Nothing here is a demo of an idea - it runs the real index over the real corpus on the local model,
and prints what was thrown away together with the reason. The rejected pile is the interesting one.

  python eval/feasibility/run_analyst.py ["pytanie"]
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "python"))

from wachta_detectors.analyst import Analyst  # noqa: E402
from wachta_detectors.embeddings import OllamaEmbedder  # noqa: E402
from wachta_detectors.vector_store import Document, InMemoryVectorStore, index_documents  # noqa: E402

FIX = ROOT / "eval" / "fixtures"
OUT = FIX / "analyst_answers.json"
OLLAMA = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"
LIMIT = 500

PYTANIA = [
    "jakie sa doniesienia o walkach na Ukrainie?",
    "co sie dzieje w Iranie?",
    "gdzie protestuja ludzie?",
    # Pytanie bez pokrycia w korpusie zostaje tu celowo: odpowiedz "brak danych" jest wynikiem,
    # ktory warto pokazac obok tych udanych.
    "czy sa doniesienia o statkach i kablach podmorskich?",
]


def zapytaj_model(prompt: str) -> str:
    request = urllib.request.Request(OLLAMA, data=json.dumps({
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "stream": False, "think": False, "options": {"temperature": 0.2, "num_ctx": 4096},
    }).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.load(response)["message"]["content"].strip()


def opis(e: dict) -> str:
    """Tylko to, co odroznia zdarzenie od innych.

    Pierwsza wersja doklejala tu "(opisane w N doniesieniach)". Zmierzone: ten sam dopisek w kazdym
    dokumencie obniza podobienstwo o 0,12-0,15, bo dodaje wszystkim wspolny kierunek i rozciencza
    to, czym dokumenty sie roznia. Dwa z trzech pytan spadly przez to pod prog. Liczba doniesien
    jest wazna, ale nalezy do metadanych - te nie ida do modelu.
    """
    czesci = [e.get("actor1") or "", e.get("actor2") or "", e.get("kind") or "", e.get("place") or ""]
    return " | ".join(c for c in czesci if c)


def main() -> int:
    events = json.loads((FIX / "events_snapshot.json").read_text(encoding="utf-8"))["events"]
    docs = [Document(str(e["id"]), opis(e),
                     {"url": e.get("url"), "place": e.get("place"), "sources": e.get("sources")})
            for e in events if opis(e)][:LIMIT]

    embedder = OllamaEmbedder()
    store = InMemoryVectorStore()
    start = time.time()
    print(f"indeksuje {len(docs)} zdarzen...", flush=True)
    index_documents(store, embedder, docs)
    print(f"gotowe w {time.time() - start:.0f} s")

    analyst = Analyst(store, embedder, ask_model=zapytaj_model, k=8)
    pytania = [sys.argv[1]] if len(sys.argv) > 1 else PYTANIA
    zapis = []

    for pytanie in pytania:
        print("")
        print("=" * 78)
        print(f"PYTANIE: {pytanie}")
        answer = analyst.answer(pytanie)

        print(f"\nZNALEZIONE FAKTY ({len(answer.facts)}):")
        for f in answer.facts:
            print(f"  {f}")

        print("\nODPOWIEDZ (tylko zdania, ktore przeszly obie bramki):")
        for zdanie in answer.accepted or ["  (nic nie przeszlo)"]:
            print(f"  {zdanie}")

        if answer.rejected:
            print(f"\nODRZUCONE ({len(answer.rejected)}):")
            for j in answer.rejected:
                print(f"  [{j.reason}] {j.sentence[:96]}")

        print(f"\nprzyjete {len(answer.accepted)} z "
              f"{len(answer.accepted) + len(answer.rejected)} ({answer.kept_share:.0%})")
        zapis.append({
            "question": pytanie,
            "facts": [{"n": f.number, "text": f.text, "source": f.source} for f in answer.facts],
            "accepted": answer.accepted,
            "rejected": [{"reason": j.reason, "sentence": j.sentence} for j in answer.rejected],
            "kept_share": round(answer.kept_share, 2),
        })

    OUT.write_text(json.dumps({
        "model": MODEL, "embedder": embedder.model, "documents": len(docs),
        "note": ("Bramka cytowan odsiewa zdania bez odnosnika, bramka liczb odsiewa zdania, ktorych "
                 "liczby nie wystepuja w cytowanym fakcie. Ta druga powstala, bo pierwsza sama "
                 "przepuszczala przekrecenia prawdziwych faktow."),
        "answers": zapis,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nzapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
