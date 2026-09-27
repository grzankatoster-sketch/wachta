# Kto robi które zadanie w WACHCIE

Wynik przepuszczenia backlogu F0–F3 przez `route.py` (2026-09-26) plus moje poprawki tam, gdzie
router się mylił. Zasada nadrzędna: **tokeny Claude są najdroższym zasobem**, więc zadanie schodzi
tak nisko, jak pozwala na to walidator.

Stan wykonawców w chwili ustalania: **Codex niedostępny do 30.09 14:51** (limit). Zgodnie z twardą
zasadą jego zadania przejmuje Claude w trybie tylko do odczytu, a raport podpisuje
„Claude, zastępczo za Codex”. Projekt nie czeka.

## Podział

| Zadanie | Wykonawca | Walidator |
|---|---|---|
| **F0** Baza w Dockerze + migracje DbUp | skrypt | `docker compose run --rm migrator` i test `DbMigratorTests` |
| **F0** Pipeline Azure DevOps → GitHub | Claude (sonnet) | zielony przebieg na PR |
| **F1** Kompilacja C# i naprawa błędów po instalacji SDK | Claude (sonnet) | `dotnet build` bez ostrzeżeń, `dotnet test` |
| **F1** Testy jednostkowe przy gotowej specyfikacji | qwen lokalnie → ja sprawdzam | uruchomienie testów; **każda liczba do weryfikacji** |
| **F1** Endpointy API + testy integracyjne | Claude (sonnet) | testy na Testcontainers |
| **F1** Uruchomienie runnera detektorów w kontenerze | skrypt | zapytanie SQL: czy alarmy przybywają |
| **F1** Oznaczenie 50 alarmów jako trafne/nietrafne | **Ty (człowiek)** | to jest prawda odniesienia dla metryk — **żaden model** |
| **F1** Przegląd bezpieczeństwa repozytorium | Codex (po 30.09) lub ja zastępczo | raport z dowodami, ja weryfikuję każde ustalenie |
| **F1** Audyt dostępności i UX frontu | Codex (po 30.09) lub ja zastępczo | raport + `impeccable detect` |
| **F2** Konektor AISStream (WebSocket, C#) | Claude (sonnet) | test z podstawionym strumieniem + ruch w bazie |
| **F2** Detektor wleczenia kotwicy (D6) | Claude (sonnet) | wykrycie Eagle S w danych historycznych, fałszywe alarmy na dzień |
| **F3** Serwer MCP w C# | Claude (sonnet) | MCP Inspector widzi narzędzia + testy |
| **F3** Agent-analityk | Claude (opus) | porównanie z pipeline'em bez agenta na 30 alarmach |
| Szukanie przyczyny awarii w logu kontenera | qwen lokalnie | czy wskazana przyczyna tłumaczy objaw |
| Wyszukanie wzorca w plikach repozytorium | skrypt (`rg`) | liczba trafień |
| Przegląd diffa przed scaleniem fazy | Codex (po 30.09) lub ja zastępczo | ja weryfikuję, zanim cokolwiek poprawię |

## Gdzie router się pomylił (zgłoszone do jego nauki)

Router sam deklaruje około 3 błędy na 10 zadań. W tym backlogu cztery, wszystkie oznaczone przez
`route.py --zle` i użyte do przetrenowania klasyfikatora zapasowego:

| Nr | Zadanie | Router | Poprawnie | Dlaczego |
|---|---|---|---|---|
| 76 | Baza w Dockerze + migracje | Claude (opus) | skrypt | trzy komendy i test, nie ma tu decyzji |
| 83 | Testy przy gotowej specyfikacji | skrypt | qwen lokalnie | skrypt nie napisze testu; qwen zdał to w pomiarach (8/10) |
| 86 | Ręczne oznaczenie 50 alarmów | qwen lokalnie | człowiek | **groźne**: model etykietujący własne dane zatruwa metrykę, którą potem pokazujemy jako dowód jakości |
| 94 | Wyszukanie wzorca w repozytorium | Claude | skrypt | to jest `rg`, nie analiza |

Najgroźniejszy jest 86 — nie chodzi o koszt, tylko o to, że etykiety od modelu unieważniłyby
precyzję i recall detektora D1.

## Drabina eskalacji

Czerwony walidator to jeden poziom wyżej, maksymalnie raz, potem pytanie do Ciebie.

- Implementacja: skrypt → qwen → Claude
- Analiza: qwen → Codex → Claude (Codex niczego nie zmienia w plikach)

## Czego nie wysyłamy na zewnątrz

`.env`, klucze API, tokeny. W tym projekcie nie ma danych osobowych ani płatności, więc bramka
pieniędzy i danych gości nie podnosi tu niczego do Opusa — poza decyzjami architektonicznymi
(agent, model danych) i tym, co zmienia zachowanie systemu w sposób trudny do cofnięcia.
