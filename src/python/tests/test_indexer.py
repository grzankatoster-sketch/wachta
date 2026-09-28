import json
from datetime import datetime, timezone

import pytest

from wachta_detectors.embeddings import DeterministicEmbedder
from wachta_detectors.indexer import alert_documents, event_documents, index
from wachta_detectors.vector_store import Document, InMemoryVectorStore

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


class FakeCursor:
    """Enough of psycopg to see what the indexer asks for, and to answer."""

    def __init__(self, rows):
        self.rows = rows
        self.seen: list[tuple] = []

    def execute(self, sql, params=None):
        self.seen.append((sql, params))
        return self

    def fetchall(self):
        return self.rows


def conn_with(rows):
    return FakeCursor(rows)


def alert_row(alert_id=1, detector="D4", entity="273258520", evidence='{"gap_min": 46, "listeners": 12}'):
    return (alert_id, detector, entity, NOW, 54.97, 13.56, 0.8, evidence, "new")


def test_an_alert_becomes_a_sentence_not_raw_json():
    # Zanurzenie '{"gap_min": 46}' nie pasuje do niczego, co czlowiek wpisalby w wyszukiwarke.
    [doc] = alert_documents(conn_with([alert_row()]), NOW)
    assert "statek zamilkl" in doc.text
    assert "273258520" in doc.text
    assert "gap_min 46" in doc.text
    assert not doc.text.startswith("{")


def test_an_unknown_detector_keeps_its_code_instead_of_vanishing():
    [doc] = alert_documents(conn_with([alert_row(detector="D99")]), NOW)
    assert doc.text.startswith("D99:")


def test_broken_evidence_does_not_stop_the_indexing():
    # jsonb NOT NULL przepuszcza JSON-owego nulla, liczbe i napis - kazde z nich tu trafi.
    for evidence in ("null", "12", '"tekst"', "", None, "{niepoprawny"):
        [doc] = alert_documents(conn_with([alert_row(evidence=evidence)]), NOW)
        assert doc.id == "alert:1"


def test_metadata_says_what_kind_of_document_this_is():
    [doc] = alert_documents(conn_with([alert_row()]), NOW)
    assert doc.metadata["kind"] == "alert"
    assert doc.metadata["detector"] == "D4"
    assert doc.metadata["lat"] == 54.97


def test_the_query_is_parameterised_and_bounded():
    kursor = conn_with([])
    alert_documents(kursor, NOW, limit=5)
    sql, params = kursor.seen[0]
    assert "%s" in sql and params == (NOW, 5)
    assert str(NOW) not in sql, "data nie moze byc wklejona w tresc zapytania"


def test_events_come_from_the_snapshot_with_their_source(tmp_path):
    snapshot = tmp_path / "events_snapshot.json"
    snapshot.write_text(json.dumps({"events": [
        {"id": "7", "actor1": "RUSSIA", "actor2": "UKRAINE", "kind": "walka",
         "place": "Sumy", "url": "http://x", "lat": 50.9, "lon": 34.8, "conflict": True, "sources": 3},
    ]}), encoding="utf-8")
    [doc] = event_documents(snapshot)
    assert doc.id == "event:7"
    assert doc.text == "RUSSIA | UKRAINE | walka | Sumy"
    assert doc.metadata["kind"] == "event"
    assert doc.metadata["url"] == "http://x"


def test_an_event_with_nothing_to_say_is_skipped(tmp_path):
    snapshot = tmp_path / "events_snapshot.json"
    snapshot.write_text(json.dumps({"events": [
        {"id": "1", "actor1": None, "actor2": None, "kind": None, "place": None},
    ]}), encoding="utf-8")
    assert event_documents(snapshot) == []


def test_a_missing_snapshot_is_an_empty_corpus_not_a_crash(tmp_path):
    assert event_documents(tmp_path / "nie-ma-takiego.json") == []


def test_alerts_and_events_can_be_told_apart_after_indexing():
    store = InMemoryVectorStore()
    docs = [Document("alert:1", "statek zamilkl na AIS", {"kind": "alert"}),
            Document("event:2", "RUSSIA | UKRAINE | walka", {"kind": "event"})]
    from wachta_detectors.vector_store import index_documents

    index_documents(store, DeterministicEmbedder(), docs)
    pytanie = DeterministicEmbedder().embed(["statek zamilkl na AIS"])[0]
    tylko_alerty = store.search(pytanie, k=5, where=lambda d: d.metadata["kind"] == "alert")
    assert [h.document.id for h in tylko_alerty] == ["alert:1"]


def test_indexing_the_same_document_twice_does_not_duplicate_it():
    store = InMemoryVectorStore()
    from wachta_detectors.vector_store import index_documents

    doc = Document("alert:1", "statek zamilkl na AIS", {"kind": "alert"})
    index_documents(store, DeterministicEmbedder(), [doc])
    index_documents(store, DeterministicEmbedder(), [doc])
    assert len(store) == 1


def test_index_returns_how_many_went_in():
    class Store:
        def __init__(self):
            self.added = 0

        def add(self, documents, vectors):
            self.added += len(documents)

    import wachta_detectors.indexer as modul

    store = Store()
    monkey = modul.PgVectorStore
    modul.PgVectorStore = lambda conn, dimensions=0: store
    try:
        ile = index(None, [Document("a", "x"), Document("b", "y")], DeterministicEmbedder())
    finally:
        modul.PgVectorStore = monkey
    assert ile == 2 and store.added == 2


def test_indexing_nothing_is_not_an_error():
    assert index(None, [], DeterministicEmbedder()) == 0
