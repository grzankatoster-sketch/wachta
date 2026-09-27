# ADR-0001: Jedna baza PostgreSQL zamiast kilku systemów

Data: 2026-09-22 · Status: przyjęte

## Kontekst
Projekt potrzebuje trzech rzeczy: szeregów czasowych (pozycje samolotów i statków), geometrii
(bufory kabli, obszary) i wyszukiwania wektorowego (RAG nad newsami, odcisk statku w F6).
Naturalny odruch to trzy systemy: Timescale/Influx + PostGIS + Qdrant. Całość ma działać na
laptopie z 16 GB RAM, obsługiwanym przez jedną osobę uczącą się C#.

## Decyzja
Jeden PostgreSQL 17 w obrazie `timescale/timescaledb-ha`, z rozszerzeniami TimescaleDB, PostGIS
i pgvector. Dostęp przez klasy repozytoriów, nie przez bezpośrednie zapytania rozsiane po kodzie.

## Konsekwencje
- Jeden kontener do utrzymania, jedna kopia zapasowa, jeden zestaw migracji (DbUp).
- Mniej pamięci niż trzy silniki naraz — istotne przy modelach AI na tym samym sprzęcie.
- Wyszukiwanie wektorowe będzie wolniejsze niż w dedykowanej bazie; przy skali F1–F5 to nie problem.
- Jeśli pgvector przestanie wystarczać, wymieniamy implementację repozytorium na Qdranta bez
  ruszania detektorów — dlatego dostęp do danych jest za interfejsem od początku.
