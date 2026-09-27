# ADR-0002: Bez Redisa w fazie F1

Data: 2026-09-22 · Status: przyjęte (do rewizji w F3)

## Kontekst
Plan architektury przewiduje szynę zdarzeń (Redis Streams) między pobieraniem, detektorami i API.
W F1 detektory liczą się raz na minutę, a mapa odświeża się co 5 sekund.

## Decyzja
W F1 komponenty komunikują się przez bazę: pobieranie zapisuje pozycje, detektory je odczytują
i zapisują alarmy, API odpytuje bazę i rozsyła zmiany przez SignalR.

## Konsekwencje
- O jeden kontener i jeden protokół mniej do nauczenia się i debugowania na starcie.
- Opóźnienie alarmu do 60 sekund — przy detektorze działającym na oknie 5–30 minut bez znaczenia.
- Redis wchodzi w F3, gdy agent ma reagować na alarm od razu po jego powstaniu; wtedy zmienia się
  wyzwalanie, a nie logika detektorów.
