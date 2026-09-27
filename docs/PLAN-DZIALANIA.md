# WACHTA — plan działania

> Dokument wykonawczy do [PLAN.md](PLAN.md) (architektura, źródła, detektory).
> Szczegółowy plan krok po kroku dla F0+F1: [superpowers/plans/2026-09-22-f0-f1-fundament-powietrze.md](superpowers/plans/2026-09-22-f0-f1-fundament-powietrze.md).
> Plany szczegółowe F2+ piszemy na starcie każdej fazy — na podstawie danych i wniosków z poprzedniej.

## Założenia (domyślne odpowiedzi na otwarte decyzje z PLAN.md §16 — zmień, jeśli chcesz inaczej)

| Decyzja | Przyjęte | Dlaczego |
|---|---|---|
| Nazwa | **WACHTA** | robocza; zmiana nazwy = 1 commit |
| Demo | **lokalne + nagranie wideo + zrzuty w README**; publiczne online dopiero po przeglądzie licencji | licencje niekomercyjne i dane ze stref wojny |
| Repozytorium | **GitHub (publiczne, portfolio)** + **Azure DevOps: Boards + Pipelines** podpięte do GitHuba | rekruter widzi kod na GitHubie, a Azure DevOps jest w użyciu naprawdę |
| Start | **Bałtyk** (Polska, Kaliningrad, Zatoka Fińska) | działa bez kluczy, zakłócenia GPS widoczne od razu, incydenty kablowe do ewaluacji |
| Twój czas | ok. **15 h / tydzień** | kod piszą agenci, Ty: decyzje, weryfikacja, etykiety, zrozumienie |

## Kalendarz

| Tydzień | Daty | Faza | Kamień milowy |
|---|---|---|---|
| 0 | 23.09 – 29.09 | **F0 Fundament** | repo + zielony pipeline + baza w Dockerze + klucze |
| 1–3 | 30.09 – 20.10 | **F1 Powietrze** | mapa samolotów wojskowych na żywo, heksy zakłóceń GPS, alarmy „zgaszony transponder”, suwak czasu |
| — | **do 1.11** | — | **demo F1 gotowe do CV / zgłoszeń** (m.in. termin Glamox) |
| 4–6 | 21.10 – 10.11 | **F2 Morze** | statki + flota cieni, luki AIS, STS, odtworzenie incydentu Eagle S |
| 7–8 | 11.11 – 24.11 | **F3 Agent + MCP** | Claude Desktop odpowiada z bazy WACHTY; raporty agenta |
| — | **~25.11** | — | **MVP: README z metrykami + nagranie demo** |
| 9–10 | 25.11 – 8.12 | F4 Ląd | pożary FIRMS, zdarzenia, alarmy, awarie internetu |
| 11–13 | 9.12 – 29.12 | F5 Dwie wersje | panel UA / RU / zachód / PL |
| 14+ | 2027 | F6 Rozwój | tankowanie ML, tożsamość statków, Sentinel-1, nowe AOI |

## Laboratorium

Od 2026-09-26 na projekcie działa laboratorium (`lab status wachta`, panel na porcie 8768): w tle
wymyśla i buduje usprawnienia **w kopii** projektu, a sędzia-automat dopuszcza tylko te z dowodem
(testy-specyfikacja czerwone przed zmianą, zielone po). Zakres ograniczony do `src/python/wachta_detectors/**`,
bo tylko ta warstwa ma pełny zestaw testów i nie potrzebuje Dockera ani kluczy.
Zamrożone: fixtury, baseline, dane, dokumentacja, C# i front.
Odkrycia lądują w `firma/outbox/lab/wachta/` i **czekają na moją weryfikację** — nic nie wchodzi do repo samo.

## Kto robi które zadanie

Podział całego backlogu F0-F3 między skrypty, qwena, Codeksa i Claude: [ROUTING.md](ROUTING.md)
(wynik `route.py` z 2026-09-26 plus cztery poprawki tam, gdzie router się mylił).
Najważniejsze: **oznaczanie alarmów do metryk robisz Ty, nie model** — etykiety od modelu
unieważniłyby precyzję i recall, którymi potem chwalimy się w README.

## Jak pracujemy (każde zadanie)

1. Gałąź `feat/<id>-<krótko>` (np. `feat/t1.3-position-writer`).
2. Test najpierw (TDD) → kod → testy zielone lokalnie.
3. Commit w konwencji `feat:` / `fix:` / `test:` / `docs:` / `chore:`.
4. PR na GitHubie → Azure Pipelines musi być zielony.
5. Zadania oznaczone **[R]** → przegląd Codeksa (tylko odczyt) przed scaleniem; wnioski sprawdza Claude.
6. Po scaleniu: aktualizacja tablicy w Azure Boards; raz w tygodniu aktualizacja `PLAN.md` (§17) i `docs/SOURCES.md`.
7. **Ty** przed zamknięciem zadania z C#: czytasz kod i umiesz powiedzieć, co robi każda klasa (lista pytań w §„Przygotowanie do rozmowy”).

Kto co robi — skrót: **Claude Code** pisze kod i testy, integruje, decyduje technicznie; **Codex** przegląda [R];
**qwen** naprawia przy gotowych testach i przeszukuje logi; **Ty** decydujesz o zakresie, etykietujesz dane, weryfikujesz na mapie.

---

## Postęp

**2026-09-26 (praca nocna):** zrobione i zweryfikowane bez uprawnień administratora —
szkielet repo, detektory w Pythonie (36 testów), bramka ewaluacji z testami mutacyjnymi,
front z mapą (testy jednostkowe, budowa z kontrolą typów, 2 testy Playwright), README, ADR-y,
`docs/SOURCES.md`, skrypty `scripts/check.ps1` i `scripts/bootstrap.ps1`.
Szczegóły i lista rzeczy czekających na Ciebie: [STATUS.md](STATUS.md).
Zostaje: WSL2 + Docker + .NET SDK (administrator), klucze API (T0.2), solution .NET i pierwszy `docker compose up`.

## F0 — Fundament (tydzień 0)

**Cel:** wszystko gotowe, żeby w F1 pisać tylko funkcje, nie walczyć ze środowiskiem.

| ID | Zadanie | Kto | Gotowe, gdy |
|---|---|---|---|
| T0.1 | Instalacja: WSL2, Docker Desktop, .NET 10 SDK, Node 22 LTS, uv, Git | **Ty** (admin + restart) | wszystkie komendy weryfikujące z planu szczegółowego zwracają wersje |
| T0.2 | Konta i klucze: GitHub repo, Azure DevOps org, AISStream, OpenSky (klient OAuth2), NASA FIRMS, GFW; maile do UCDP i airplanes.live | **Ty** | klucze w `.env` (nie w repo), maile wysłane |
| ~~T0.3~~ | Szkielet repo — **zrobione 26.09** (bez solution .NET: wymaga SDK) | Claude | `uv run pytest` 36/36, `npm run build` OK |
| T0.4 | Baza: `compose.yaml` z TimescaleDB-HA, migracje DbUp (`Wachta.Db`), test migracji na Testcontainers | Claude | `docker compose up db migrator` tworzy tabele; test zielony |
| T0.5 | Pipeline Azure: testy .NET / Python / web, podpięty do GitHuba | Claude + **Ty** (podpięcie w UI) | PR pokazuje zielony status z Azure |
| ~~T0.6~~ | Testy wykonalności w repo + `docs/SOURCES.md` — **zrobione 26.09** (źródła z kluczami czekają na konta) | Claude | każdy wiersz ma status z datą |
| T0.7 | Makieta UI w Figmie: mapa, panel alarmu, stopka „Źródła” | Claude (Figma MCP) + **Ty** (akceptacja) | 1 ekran zaakceptowany |

**Punkt decyzyjny F0 → F1:** Docker działa, adsb.lol nadal bez klucza. Jeśli adsb.lol wprowadził klucz → rejestracja feedera albo przełączenie F1 na OpenSky (adapter się nie zmienia, zmienia się tylko źródło).

---

## F1 — Powietrze (tygodnie 1–3)

**Cel:** pierwsza działająca warstwa z własnymi detektorami i zmierzoną jakością.

| ID | Zadanie | [R] | Gotowe, gdy |
|---|---|---|---|
| T1.1 | Model domeny + parser ADS-B v2 (C#) | | testy parsera na nagranym pliku zielone |
| T1.2 | Źródło adsb.lol + dekorator limitu zapytań + fabryka źródeł z konfiguracji | [R] | test z fałszywym zegarem potwierdza odstępy |
| T1.3 | Zapis pozycji (COPY) + deduplikacja + dziennik pobrań (rodowód) | [R] | test integracyjny na prawdziwym Postgresie |
| T1.4 | Worker pobierania + Docker | | po 10 min w bazie są tysiące pozycji z 3 źródeł |
| T1.5 | API: samoloty na żywo, tor, źródła | | testy API zielone, OpenAPI pod `/openapi/v1.json` |
| T1.6 | SignalR: push pozycji co 5 s | | test klienta huba odbiera wiadomość |
| T1.7 | Python: D3 zakłócenia GPS (agregacja H3) | | testy + na nagranym odczycie Kaliningrad wychodzi jako „wysoki” |
| T1.8 | Model pokrycia odbiorników | | testy krawędzi pokrycia zielone |
| T1.9 | D1 zgaszony transponder (reguła bazowa) | [R] | testy scenariuszy: dziura w zasięgu ≠ alarm, lotnisko ≠ alarm |
| T1.10 | Runner detektorów + Docker | | alarmy i heksy pojawiają się w bazie same |
| T1.11 | API: alarmy, heksy zakłóceń, odtwarzanie | | testy API zielone |
| T1.12 | Mapa: samoloty na żywo | | na mapie widać samoloty wojskowe odświeżane co 5 s |
| T1.13 | Mapa: heksy GPS, panel alarmów, stopka źródeł | | kliknięcie alarmu centruje mapę, stopka pokazuje licencje |
| T1.14 | Suwak czasu (ostatnie 6 h) | | odtwarzanie torów wojskowych działa płynnie |
| T1.15 | Ewaluacja: etykietowanie D1, metryki D1/D3, bramka w pipeline | [R] | `eval/results/latest.json` + pipeline pada przy spadku metryki |
| T1.16 | README z GIF-em i metrykami, 3 ADR-y | | README zrozumiałe dla rekrutera w 60 s |
| T1.17 | Testy UI w przeglądarce (Playwright) + sprawdzenie ich mutacjami | | 2 testy dymne; usunięcie reguły CSS i błąd workera mapy wywalają zestaw |

**Twoje zadania w F1 (poza przeglądem):** po tygodniu zbierania danych — oznaczenie **min. 50 alarmów D1** jako trafny / nietrafny (narzędzie z T1.15 daje link do odtworzenia lotu). Ok. 2 h.

**Punkt decyzyjny F1 → F2:**
- Precyzja D1 ≥ 0,5 na Twoich etykietach → idziemy dalej. Poniżej → tydzień na poprawę modelu pokrycia (najczęstsza przyczyna) przed F2.
- Baza po 14 dniach < 20 GB → retencja OK. Więcej → zmniejszamy częstotliwość dla ruchu cywilnego.

**Co pokazać po F1:** GIF mapy z heksami zakłóceń nad Kaliningradem + alarm „zgaszony transponder” z odtworzeniem lotu + tabela metryk.

---

## F2 — Morze (tygodnie 4–6)

Plan szczegółowy: `docs/superpowers/plans/<data>-f2-morze.md` (piszemy na starcie F2).

| ID | Zadanie | [R] | Gotowe, gdy |
|---|---|---|---|
| T2.1 | Źródło AISStream (WebSocket, C#) — adapter do wspólnego modelu | [R] | statki z płd. Bałtyku w bazie |
| T2.2 | Źródło Digitraffic (pozycje + metadane statków) | | Zatoka Fińska w bazie, IMO/typ/zanurzenie |
| T2.3 | Import historyczny DMA (strumieniowo, filtr AOI + tankowce) — okna incydentów XI 2024 – I 2025 | | 3 okna incydentów w bazie, surowe pliki usunięte |
| T2.4 | Sankcje: OpenSanctions (maritime, ua_war_sanctions, eu_fsf) → tabela z datami dopisania | | statki na mapie oznaczone jako sankcjonowane ze źródłem |
| T2.5 | Infrastruktura: kable z OSM, rurociągi z EMODnet → PostGIS | | Estlink 2, C-Lion 1, BCS North widoczne na mapie |
| T2.6 | D4 podejrzana luka AIS (z dowodem pokrycia z sąsiednich statków) | [R] | testy + porównanie z GFW gaps |
| T2.7 | D5 przeładunek STS | | testy + porównanie z GFW encounters |
| ~~T2.8~~ | D6 wleczenie kotwicy — **reguła i 18 testów gotowe 26.09** (`anchor.py`); zostaje ewaluacja na Eagle S | [R] | **Eagle S, Yi Peng 3, Vezhen wykryte w danych historycznych**; fałszywe alarmy / dzień zmierzone na 30 dniach normalnego ruchu |
| T2.9 | Warstwa morska na mapie + panel statku (tożsamość, sankcje, historia) | | klik w statek pokazuje rodowód danych |
| T2.10 | Ewaluacja D4–D6 w pipeline | [R] | metryki w README |

**Punkt decyzyjny F2 → F3:** D6 łapie min. 2 z 3 incydentów. Jeśli nie — analiza, czemu (dziura w danych DMA? bufor kabla?) i poprawka przed agentem, bo agent będzie się na tym opierał.

---

## F3 — Agent + MCP (tygodnie 7–8)

| ID | Zadanie | [R] | Gotowe, gdy |
|---|---|---|---|
| T3.1 | `Wachta.Mcp` (C#, ModelContextProtocol.AspNetCore): narzędzia `get_alerts`, `get_track`, `get_entity`, `nearby`, `coverage` | [R] | MCP Inspector widzi narzędzia; testy |
| T3.2 | Podłączenie do Claude Desktop / Claude Code (token, tylko odczyt) | | pytanie „co działo się nad Bałtykiem w nocy” → odpowiedź z bazy |
| T3.3 | Agent (pętla z `wlasny-agent`) jako klient MCP, qwen lokalnie; limit narzędzi, zapis śladu | [R] | raport dla alarmu D6 z przesłankami i poziomami zaufania |
| T3.4 | Redis Streams: alarmy → agent automatycznie (dopiero teraz, ADR-002) | | nowy alarm D6 → raport w ciągu 2 min |
| T3.5 | Ewaluacja „agent vs stały pipeline” na 30 alarmach | [R] | tabela w README |
| T3.6 | Nagranie demo (3 min) + README MVP | | gotowe do wysłania rekruterowi |

---

## F4 — Ląd (tygodnie 9–10) · F5 — Dwie wersje (11–13) · F6 — Rozwój

Szczegóły zadań w [PLAN.md §11](PLAN.md). Skrót:

- **F4:** NASA FIRMS (klucz), GDELT (pliki CSV), UCDP (token), alarmy UA, IODA → **D8 kandydat na zdarzenie** z przesłankami; ewaluacja względem UCDP.
- **F5:** RSS (UA/RU/PL/EN) → ekstrakcja qwen do JSON (test wykonalności: 5 s / artykuł) → klastry bge-m3 (margines 0,66–0,74 vs 0,35) → NLI → panel porównania; ewaluacja na 100 ręcznie opisanych artykułach.
- **F6:** D2 tankowanie (ML na torach), D7 tożsamość statków (pgvector), Sentinel-1 + YOLO, lokalizacja źródła zakłóceń GPS, NOTAM-y, Bliski Wschód.

---

## Przygotowanie do rozmowy — co musisz umieć wyjaśnić

| Po fazie | Pytania, na które odpowiadasz bez notatek |
|---|---|
| F0 | Czemu jedna baza Postgres zamiast Postgres + Qdrant + Influx? Co robi migracja i czemu DbUp? Co sprawdza pipeline? |
| F1 | Jak działa dekorator limitu i czemu to dekorator, a nie `if` w adapterze? Czemu COPY zamiast INSERT? Skąd wiesz, że zniknięcie samolotu to nie dziura w zasięgu? Jak liczysz zakłócenia GPS (NACp)? Jaka jest precyzja D1 i jak ją zmierzyłeś? |
| F2 | Czemu luka AIS nie oznacza wyłączenia nadajnika? Jak wykryłeś Eagle S i ile masz fałszywych alarmów dziennie? |
| F3 | Co to MCP i czemu serwer jest w C#? Kiedy agent jest lepszy od stałego pipeline'u — i czy u Ciebie jest (liczby)? Jak zabezpieczasz agenta przed zmyślaniem? |
| F5 | Jak łączysz artykuły w różnych językach w jedno zdarzenie? Co robi NLI? Czemu system nie ocenia, kto kłamie? |

## Mierniki sukcesu MVP (~25.11)

- Działa lokalnie jednym `docker compose up`.
- 3 warstwy: powietrze, morze, infrastruktura; 5 detektorów (D1, D3, D4, D5, D6) z metrykami w README.
- Incydent Eagle S odtworzony na mapie z alarmem D6.
- Serwer MCP używany przez Claude Desktop i własnego agenta.
- Pipeline Azure: testy + bramka ewaluacji; historia commitów pokazuje regularną pracę.
