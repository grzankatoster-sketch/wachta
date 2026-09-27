# WACHTA

Mapa sytuacyjna Bałtyku z danych publicznych: ruch wojskowy w powietrzu, zakłócenia GPS, samoloty
gasnące w locie — z **rodowodem każdej informacji** (kto podaje, kiedy pobrane, na jakiej licencji)
i **zmierzoną jakością** detektorów.

> Stan: budowa, faza F0/F1. Projekt niekomercyjny, portfolio.
> Plan: [docs/PLAN.md](docs/PLAN.md) · [docs/PLAN-DZIALANIA.md](docs/PLAN-DZIALANIA.md) ·
> [plan wykonawczy F0+F1](docs/superpowers/plans/2026-09-22-f0-f1-fundament-powietrze.md)

## Czym się różni od gotowych map

Mapy typu World Monitor agregują i wyświetlają. WACHTA dokłada cztery rzeczy:

1. **Własne detektory zachowań** zamiast gotowych list — samolot gaśnie w zasięgu odbiorników (D1),
   obszary z osłabionym GPS liczone z ADS-B (D3), a w kolejnych fazach flota cieni i kable podmorskie.
2. **„Kto co podaje”** — każdy rekord ma źródło, czas pobrania, hash treści i poziom zaufania;
   mapa pokazuje atrybucję zgodnie z licencjami.
3. **Agent-analityk** przez własny serwer MCP (faza F3).
4. **Metryki w CI** — pipeline odrzuca zmianę, która pogarsza detektor; bramka jest sprawdzana
   mutacjami (detektor zwracający pustkę musi oblać).

## Uruchomienie

```bash
cp .env.example .env          # ustaw POSTGRES_PASSWORD
docker compose up -d --build  # baza, migracje, pobieranie, API, detektory, mapa
```
Mapa: http://localhost:8081 · API i OpenAPI: http://localhost:8080/openapi/v1.json

Tryb deweloperski frontu (z proxy do API): `cd web && npm run dev` → http://localhost:5173

![Mapa WACHTA — Bałtyk, panel alarmów, legenda zakłóceń GPS](docs/screenshots/mapa-dev.png)

## Warstwy

| Warstwa | Źródło | Stan |
|---|---|---|
| Powietrze | adsb.lol (ODbL) | działa |
| Zakłócenia GPS | wyliczane z ADS-B | działa, zmierzone |
| Morze | Digitraffic (Zatoka Fińska) | działa; południowy Bałtyk czeka na klucz AISStream |
| Sankcje i flota cieni | OpenSanctions | działa |
| Infrastruktura podmorska | OpenStreetMap | działa |
| Zdarzenia lądowe | GDELT | działa |
| Wsparcie dla Ukrainy | Kiel Institute | działa |
| Linia frontu | DeepStateMap | działa (licencja do wyjaśnienia) |
| Dwie wersje: jak opisały to strony | GDELT export + mentions (także strumień tłumaczeniowy) | działa |
| Anomalie: nietypowe skupiska doniesień | GDELT, test Poissona per komórka | działa |
| Pożary i uderzenia | NASA FIRMS | czeka na klucz |

## Detektory

| ID | Co wykrywa | Czego nie potrafi |
|---|---|---|
| **D1** | samolot przestaje nadawać w locie, choć obszar ma dobre pokrycie odbiorników i inne samoloty nadal widać | widzi tylko maszyny, które w ogóle nadają ADS-B; wiele wojskowych nie nadaje nic; zanim model pokrycia się zapełni (kilka godzin danych), detektor milczy |
| **D3** | obszary, gdzie samoloty raportują osłabioną dokładność GPS (pola NIC/NACp), w siatce H3 | pokazuje skutek, nie źródło zakłóceń; osłabiony GPS może mieć też inne przyczyny |

Samolot z zakłóconym GPS przestaje podawać pozycję, ale **nadal nadaje** — dlatego D1 liczy ciszę
w transmisji (tabela `aircraft_contact`), a nie brak pozycji. Bez tego rozróżnienia zakłócanie nad
Bałtykiem generowałoby fałszywe alarmy.

Każdy wynik detektora jest oznaczony jako **„do sprawdzenia”**, nigdy jako zarzut.

## Metryki

Liczone na zamrożonych danych przez `eval/run_eval.py`; pipeline odrzuca zmianę, która pogarsza
wynik o więcej niż 5 punktów procentowych. Stan na 2026-09-26:

| Detektor | Precyzja | Recall | Na czym liczone |
|---|---|---|---|
| **D3** (zakłócenia GPS) | **0,60** | **0,75** | godzina prawdziwych danych (13 781 pozycji) wobec **niezależnej referencji**: dziennych plików H3 z gpsjam.org (8 komórek zakłóconych, 22 czyste) |
| D1 (zgaszony transponder) — syntetyczne | 1,00 | 1,00 | 10 scenariuszy reguły; to test regresji, **nie** miara jakości |
| **D6** (wleczenie kotwicy nad kablem) | — | — | mierzony inaczej: **fałszywe alarmy na dobę prawdziwego ruchu** (patrz niżej) |
| **D8** (nietypowe skupisko doniesień) | — | — | próg to prawdopodobieństwo Poissona < 0,01 wobec własnego tła miejsca, nie krotność |
| D1 — rzeczywiste | — | — | powstaje po tygodniu zbierania, z ręcznie oznaczonej próby milczących samolotów (także tych, których detektor nie zgłosił) |

Referencja gpsjam pochodzi z poprzedniej doby i agreguje cały dzień, a nasz pomiar to jedna godzina —
zgodność jest z natury częściowa, więc recall liczony w ten sposób jest raczej zaniżony niż zawyżony.

### D6 — ile fałszywych alarmów na prawdziwym ruchu

Detektor przepuszczony przez **pełną dobę duńskiego AIS** (25.12.2024, 904 statki z trasą w pobliżu kabli):

| Zakres | Alarmy / dobę | Na godzinę |
|---|---|---|
| wszystkie statki | 35 | **1,46** |
| tylko handlowe (Cargo, Tanker, Passenger) | 1 | **0,04** |

Różnica nie bierze się z progu, tylko z tego, **kto** alarmuje. Wśród 35 alarmów 26 to jednostki
o typie „Undefined”, a nazwy kabli mówią resztę: Ostwind, Kriegers Flak, Fehmarn Belt, Kontek —
to statki pracujące przy tych właśnie liniach, plus dwa kutry rybackie. Wolne, nieregularne krążenie
nad kablem jest ich zawodem. D6 jest więc detektorem dla ruchu handlowego; jednostki robocze i rybackie
idą na osobną listę, nie do tego samego strumienia alarmów.

Zastrzeżenie: dane duńskie nie obejmują Zatoki Fińskiej, więc **samego incydentu Eagle S w nich nie ma**.
Zmierzone jest to, co dla detektora najgroźniejsze — poziom szumu na normalnym ruchu; potwierdzenie
na prawdziwym incydencie wymaga historycznego AIS z wód fińskich.

![Zakłócenia GPS nad Bałtykiem — wynik detektora D3 na godzinie danych z 2026-09-26](docs/screenshots/zaklocenia-gps.png)

Poziom komórki liczy się z **dolnej granicy przedziału ufności Wilsona**, nie z surowego udziału.
Przy surowym udziale i pięciu samolotach w komórce jeden zakłócony to od razu 20% — i na prawdziwej
godzinie danych 154 z 274 komórek wychodziło jako „wysokie”, także nad Niemcami i środkową Polską.
Po zmianie: 11 komórek wysokich, z czego 82% w promieniu 400 km od zmierzonego ogniska zakłóceń.

## Źródła i licencje

Pełna macierz: [docs/SOURCES.md](docs/SOURCES.md). W F1 dane pochodzą z **adsb.lol** (ODbL,
niefiltrowane, endpoint wojskowy i dwa obszary bałtyckie). Podkład mapy: OpenFreeMap,
© OpenStreetMap contributors.

## Architektura

```
adsb.lol ──► Wachta.Ingestion (C#, .NET 10)  ──┐
                adaptery + limit zapytań       │
                                               ▼
                                    PostgreSQL 17 + TimescaleDB
                                    PostGIS + pgvector
                                               │
                        ┌──────────────────────┼───────────────────────┐
                        ▼                      ▼                       ▼
              detectors (Python)        Wachta.Api (C#)          eval/ (metryki)
              D1, D3, pokrycie          REST + SignalR           bramka w CI
                                               │
                                               ▼
                                    web (React, MapLibre, deck.gl)
```

Decyzje: [docs/adr/](docs/adr/) — jedna baza zamiast czterech systemów, brak Redisa w F1,
podział pracy między C# i Pythona.

## Testy

```bash
cd src/python && python -m pytest tests -q --ignore=tests/integration   # detektory i bramka jakości
cd web && npm test && npm run build                                      # front: testy i kontrola typów
cd web && npm run test:ui                                                # front: testy w przeglądarce (Playwright)
cd src/dotnet && dotnet test                                             # C# (wymaga .NET 10 SDK i Dockera)
```

## Etyka i prawo

Tylko dane publiczne. Bez śledzenia osób prywatnych. Demo lokalne; dane ze stref działań wojennych
publikowane wyłącznie z opóźnieniem. Szczegóły w [docs/PLAN.md](docs/PLAN.md), sekcja 13.
