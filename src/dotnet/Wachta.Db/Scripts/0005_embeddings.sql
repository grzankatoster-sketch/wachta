-- Wyszukiwanie po znaczeniu, nie po slowie kluczowym.
--
-- Korpus jest z natury wielojezyczny: to samo zdarzenie opisuje redakcja rosyjska, ukrainska i
-- zachodnia, a pytania zadaje sie po polsku. Wyszukiwanie po slowach tego nie przeskoczy. Model
-- bge-m3 mapuje wszystkie te jezyki na jedna przestrzen - zmierzone na tej maszynie: polskie zdanie
-- i jego angielski odpowiednik daja 0,72, a zdanie bez zwiazku 0,27.
--
-- Wymiar 1024 jest wlasciwoscia modelu. Zmiana modelu na inny wymaga migracji tej kolumny, wiec
-- nazwa modelu jest tu zapisana przy kazdym wierszu - inaczej po podmianie modelu stare i nowe
-- wektory lezalyby obok siebie w jednej przestrzeni, nie znaczac juz tego samego.

CREATE TABLE IF NOT EXISTS document_embedding (
    id          text PRIMARY KEY,
    text        text        NOT NULL,
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    model       text        NOT NULL DEFAULT 'bge-m3',
    embedding   vector(1024) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- HNSW po odleglosci kosinusowej. Operator zapytania (<=>) musi zgadzac sie z klasa operatora
-- indeksu, inaczej planista po cichu zignoruje indeks i przejdzie cala tabele.
CREATE INDEX IF NOT EXISTS document_embedding_hnsw
    ON document_embedding USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS document_embedding_model
    ON document_embedding (model);

-- Metadane sa filtrem PRZED wyborem najblizszych sasiadow, nie po nim: filtrowanie po wybraniu k
-- najblizszych cicho zwraca mniej wynikow, czasem zero.
CREATE INDEX IF NOT EXISTS document_embedding_metadata
    ON document_embedding USING gin (metadata jsonb_path_ops);

COMMENT ON TABLE document_embedding IS
    'Zdarzenia i alerty zamienione na wektory do wyszukiwania po znaczeniu. Wynik to podobienstwo, '
    'nie trafnosc: najblizszy sasiad istnieje zawsze, takze wtedy, gdy nic w korpusie nie pasuje. '
    'Prog odciecia zmierzony na tym korpusie wynosi 0,50 (patrz analyst.MIN_RELEVANT).';
