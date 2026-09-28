import pytest

from wachta_detectors.embeddings import DeterministicEmbedder, cosine, normalise
from wachta_detectors.vector_store import Document, InMemoryVectorStore, index_documents

EMBEDDER = DeterministicEmbedder()


def store_with(*texts: str) -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    docs = [Document(id=f"d{i}", text=t) for i, t in enumerate(texts)]
    index_documents(store, EMBEDDER, docs)
    return store


def ask(store: InMemoryVectorStore, question: str, **kwargs):
    return store.search(EMBEDDER.embed([question])[0], **kwargs)


def test_normalise_gives_unit_length():
    v = normalise([3.0, 4.0])
    assert abs(sum(x * x for x in v) - 1.0) < 1e-9


def test_normalise_survives_a_zero_vector():
    assert normalise([0.0, 0.0]) == [0.0, 0.0]


def test_cosine_of_a_vector_with_itself_is_one():
    assert abs(cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) - 1.0) < 1e-9


def test_cosine_of_a_zero_vector_is_zero_not_an_error():
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_refuses_vectors_of_different_width():
    # Cichy zwrot 0.0 ukrywalby pomylke modelu albo migracji kolumny.
    with pytest.raises(ValueError):
        cosine([1.0, 2.0], [1.0, 2.0, 3.0])


def test_the_closest_document_comes_first():
    store = store_with("tankowiec zgasil transponder przy kablu",
                       "prognoza pogody na weekend",
                       "kuter rybacki wrocil do portu")
    assert ask(store, "transponder kablu tankowiec")[0].document.text.startswith("tankowiec")


def test_score_is_reported_so_the_caller_can_disbelieve_it():
    store = store_with("zupelnie inny temat bez zwiazku")
    hit = ask(store, "tankowiec transponder kabel")[0]
    assert 0.0 <= hit.score <= 1.0
    assert hit.score < 0.5, "nic wspolnego, wiec wynik ma to pokazywac"


def test_min_score_lets_the_caller_reject_everything():
    store = store_with("zupelnie inny temat bez zwiazku")
    assert ask(store, "tankowiec transponder kabel", min_score=0.9) == []


def test_nearest_neighbour_is_returned_even_when_nothing_fits():
    # To jest wlasnie pulapka wyszukiwania wektorowego: zawsze cos zwroci.
    store = store_with("zupelnie inny temat bez zwiazku")
    assert len(ask(store, "tankowiec transponder kabel")) == 1


def test_k_limits_the_answer():
    store = store_with("alfa beta", "beta gamma", "gamma delta", "delta epsilon")
    assert len(ask(store, "beta", k=2)) == 2


def test_the_same_document_added_twice_does_not_count_twice():
    store = InMemoryVectorStore()
    doc = Document(id="x", text="tankowiec przy kablu")
    index_documents(store, EMBEDDER, [doc])
    index_documents(store, EMBEDDER, [doc])
    assert len(store) == 1


def test_filter_runs_before_the_cut_not_after():
    # Filtrowanie po wybraniu k najblizszych po cichu zwraca mniej wynikow, czasem zero.
    store = InMemoryVectorStore()
    docs = [Document(f"d{i}", "tankowiec przy kablu", {"rok": 2024 if i < 3 else 2026})
            for i in range(6)]
    index_documents(store, EMBEDDER, docs)
    hits = ask(store, "tankowiec przy kablu", k=3, where=lambda d: d.metadata["rok"] == 2026)
    assert len(hits) == 3
    assert all(h.document.metadata["rok"] == 2026 for h in hits)


def test_metadata_travels_with_the_document():
    store = InMemoryVectorStore()
    index_documents(store, EMBEDDER, [Document("x", "cos", {"zrodlo": "GDELT", "kraj": "UA"})])
    assert ask(store, "cos")[0].document.metadata["zrodlo"] == "GDELT"


def test_mismatched_counts_are_refused():
    store = InMemoryVectorStore()
    with pytest.raises(ValueError):
        store.add([Document("a", "x"), Document("b", "y")], [[1.0, 0.0]])


def test_empty_store_answers_with_nothing():
    store = InMemoryVectorStore()
    assert len(store) == 0
    assert store.search([1.0, 0.0]) == []


def test_indexing_nothing_is_not_an_error():
    assert index_documents(InMemoryVectorStore(), EMBEDDER, []) == 0


def test_identical_texts_embed_identically():
    a, b = EMBEDDER.embed(["ten sam tekst", "ten sam tekst"])
    assert a == b


def test_ties_are_broken_by_id_so_the_order_is_stable():
    store = InMemoryVectorStore()
    docs = [Document("b", "identyczny tekst"), Document("a", "identyczny tekst")]
    index_documents(store, EMBEDDER, docs)
    assert [h.document.id for h in ask(store, "identyczny tekst", k=2)] == ["a", "b"]
