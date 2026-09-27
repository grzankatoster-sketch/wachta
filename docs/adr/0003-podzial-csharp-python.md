# ADR-0003: Podział pracy między C# i Pythona

Data: 2026-09-22 · Status: przyjęte

## Kontekst
Oferta, pod którą powstaje portfolio, wymaga obu języków. Sztuczny podział („C# dla ozdoby”) byłby
widoczny na rozmowie. Potrzebny jest podział, który da się obronić merytorycznie.

## Decyzja
- **C#**: pobieranie danych (długo działające usługi, WebSockety, wysoka przepustowość, zapis
  masowy przez COPY), API i SignalR, a w F3 serwer MCP na oficjalnym SDK Microsoftu i Anthropic.
- **Python**: detektory, uczenie maszynowe, przetwarzanie języka, agent — tam, gdzie liczy się
  ekosystem (scikit-learn, h3, transformery).
- **Kontrakt między nimi**: schemat bazy z migracjami w jednym miejscu (`Wachta.Db/Scripts`).
  Testy Pythona wykonują dokładnie te same skrypty SQL, więc rozjazd schematu wychodzi w CI.

## Konsekwencje
- Każdy język robi to, w czym jest dobry, i da się to uzasadnić jednym zdaniem.
- Cena: dwa zestawy narzędzi i dwa przebiegi testów w pipeline.
- Warstwa C# jest celowo prosta (adapter, dekorator, repozytorium, workery), żeby autor umiał
  wytłumaczyć każdą klasę.
