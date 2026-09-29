# Przekazanie sesji

Ten plik istnieje po to, żeby ktoś — człowiek albo Claude w przeglądarce — mógł podjąć tę pracę bez
czytania całej historii rozmowy. Stan na **2026-09-29**.

---

## 1. Czym to jest

WACHTA to obraz sytuacyjny Bałtyku budowany **wyłącznie z danych publicznych**, z własnymi
detektorami zachowań, jawnym pochodzeniem każdej informacji i mierzoną jakością. Nie agreguje cudzych
werdyktów — liczy własne i mówi, na jakiej podstawie.

Naczelna zasada, od której wszystko inne jest pochodną:

> **Żadne twierdzenie na ekranie nie może być mocniejsze niż dane, które za nim stoją.**

Każdy panel ma trzy sekcje: *co to jest* (zmierzone fakty), *co z tego wynika* (interpretacja
zdaniami) i *na jakiej podstawie* (źródło, reguła, progi — oraz **czego to NIE dowodzi**).

---

## 2. Czego sesja w chmurze NIE zrobi

Bądź wobec siebie uczciwy co do tego, zanim cokolwiek zadeklarujesz jako sprawdzone:

- **Nie ma Dockera ani żywego stosu.** Nie zobaczysz mapy, nie klikniesz w statek, nie uruchomisz
  bazy. Wszystko, co wymaga `docker compose`, jest poza zasięgiem.
- **Nie ma `.env`** (jest w `.gitignore`) ani żadnych kluczy.
- **Nie ma żywych danych.** Testy jednostkowe działają na fixturach; testy integracyjne (`DockerFact`)
  same się pominą.
- **Nie zobaczysz zrzutu ekranu.** Wiele dzisiejszych błędów wyszło dopiero na obrazku, nie z
  rozumowania — to ograniczenie jest realne, nie formalne.

Co **da się** zrobić w chmurze: pisać kod, pisać i uruchamiać testy jednostkowe (`pytest`, `vitest`),
sprawdzać typy, czytać i planować. Zmiany wymagające potwierdzenia na żywym stosie zostaw opisane
w commicie jako niesprawdzone i powiedz to wprost.

---

## 3. Jak uruchomić (na maszynie z Dockerem)

    WACHTA.cmd                  # podnosi stos i otwiera w przeglądarce
    desktop\ → skrót WACHTA     # okno pulpitu; samo podnosi Dockera i pokazuje, na którym kroku stoi

Ręcznie: `docker compose up -d`, front na `http://localhost:8083`, API na `http://localhost:8080`.

**Walidacja — dokładnie te polecenia:**

    py -m pytest -q                                   # Python, z korzenia repo
    py eval/run_eval.py --check eval/baseline.json    # bramka jakości, MUSI dać 0
    cd web && npm run typecheck && npx vitest run     # front
    export PATH="$HOME/.dotnet:$PATH" && dotnet test src/dotnet/Wachta.slnx --nologo -v q

Stan na dzień przekazania: **520 testów Python, 186 frontu, 98 C#, bramka eval 0.**

---

## 4. Zasady pracy w tym repo

Nie są ozdobne. Połowa dzisiejszych znalezisk wzięła się z ich łamania.

1. **Każdy próg z pomiaru.** Liczba w kodzie ma mieć obok komentarz z tym, co zmierzono i na czym.
   „Wygląda rozsądnie" nie jest uzasadnieniem.
2. **Każdy test udowodniony mutacją.** Zepsuj kod, sprawdź, że test pada, przywróć. Test, którego
   nikt nie widział jak pada, nie jest dowodem — bramka eval przepuściła kiedyś cztery mutacje
   pokazując zieleń.
3. **Komentarze po angielsku tłumaczą DLACZEGO, z liczbami.** Nie co robi kod — to widać.
4. **Teksty widoczne dla użytkownika po polsku.**
5. **Nie twierdź, że coś działa, zanim tego nie uruchomisz.** Raport agenta to deklaracja, nie dowód.
6. **Zamrożone:** `eval/fixtures/**` i `eval/baseline.json` to dowody, nie kod. Nie dostrajaj ich,
   żeby testy przeszły.

---

## 5. Pułapki, które już kosztowały czas

Każda z nich zabrała godziny. Nie odkrywaj ich drugi raz.

| Pułapka | Objaw |
|---|---|
| `npx tsc --noEmit` w `web/` **nie sprawdza niczego** (główny tsconfig to plik rozwiązania z `files: []`) | Błędy typów wychodzą dopiero przy budowaniu obrazu. Używaj `npm run typecheck`. |
| Escapowanie w heredoc powłoki | `\n` w generowanym kodzie staje się prawdziwym końcem linii i cicho rozbija plik. Do kodu z escapami używaj edytora plików, nie `cat <<EOF`. |
| `urllib` nie rozpakowuje gzipa | Cały AIS byłby martwy w produkcji mimo zielonych testów. |
| Źródła odrzucają zapytania bez `User-Agent` | adsb.lol odpowiada 403. Jest `WachtaHttp.UserAgent`. |
| deck.gl `TextLayer` domyślnie ASCII 32–127 | Polskie znaki jako puste prostokąty. Potrzebne `characterSet: "auto"`. |
| deck.gl `IconLayer` na SVG bez `width`/`height` | Warstwa nie rysuje **nic**, bez błędu na mapie. Sam `viewBox` nie wystarczy. |
| Obraz `wachta-web` bywa podmieniany przy równoległym budowaniu | Po `docker compose build web` sprawdź, że serwowany bundel zawiera Twój kod; w razie czego `--no-cache`. |
| `ELECTRON_RUN_AS_NODE` dziedziczone ze środowiska Claude Code | Electron startuje jako Node i wywala się na `app is undefined`. |
| Rzutowanie stopni na piksele „na własną rękę" | Mój skrypt testowy klikał obok przez cały czas i dawał fałszywe wnioski. Nie ufaj własnej projekcji bez kontroli na dużym obiekcie. |

---

## 6. Co jest w trakcie: mapa wojen

Użytkownik chce **wybrać wojnę i zobaczyć, jak każda ze stron opisuje front**. Prace rozdzielone na
trzy części pracujące przeciwko wspólnemu kontraktowi.

### Co już jest w repo

- `src/python/wachta_detectors/versions.py` — **silnik porównania wersji, napisany i przetestowany**.
  Ma `Mention`, `SideView`, `Versions`, `compare_sides`. Dyscyplina zapisana w dokumentacji modułu:
  *nie mówi, kto kłamie; pokazuje, że relacje się różnią*; *wydźwięk to cecha tekstu, nie świata*;
  *strona z jednym artykułem to nie strona*.
- `data/analysis/outlet_sides.json` — polityka 7 stron, 66 wydawców. **`RU` i `RU-niezalezne` to
  osobne strony i nie wolno ich łączyć** — to celowa decyzja analityczna.
- **API: scalone** (`ConflictEndpoints.cs`, `VersionsView.cs`).

### Kontrakt — wiążący dla wszystkich trzech części

Tabele (migracja `0008_events.sql`):

    event(id text PK, day date, ts timestamptz, actor1 text, actor1_country text,
          actor2 text, actor2_country text, kind text, root text, quad smallint,
          goldstein real, mentions int, sources int, conflict boolean,
          place text, lat double precision, lon double precision, url text,
          source_id text REFERENCES source(id), fetched_at timestamptz)

    event_mention(event_id text REFERENCES event(id), source text, url text,
                  tone real, language text, confidence smallint,
                  side text, from_tld boolean, fetched_at timestamptz,
                  PRIMARY KEY (event_id, url))

`side` i `from_tld` wylicza się **przy zapisie** z `outlet_sides.json`. API i front nie znają tej
polityki. `side IS NULL` znaczy „wydawca nieprzypisany" i jest poprawnym stanem.

Endpointy:

    GET /api/conflicts                          -> [{ id, nazwa, actor1, actor2, events, lastEventAt }]
    GET /api/conflicts/{id}/events?hours&limit  -> [{ id, ts, kind, actor1, actor2, place, lat, lon,
                                                     goldstein, sources, url, mentions }]
    GET /api/events/{eventId}/versions          -> { eventId, totalArticles, toneGap, isWeak,
                                                     sides: [{ side, articles, meanTone, languages,
                                                               examples, fromTld, onlyGuessed }] }

**`isWeak` i `onlyGuessed` muszą dojść aż na ekran jako ostrzeżenie.** Porównanie oparte na jednym
artykule albo na samych zgadniętych wydawcach wygląda identycznie jak solidne — dwie strony, dwie
liczby, różnica wydźwięku. Bez tego widok kłamie najczęściej wtedy, gdy danych jest najmniej.

Subtelność wyłapana i potwierdzona: **`toneGap` liczy się z JUŻ ZAOKRĄGLONYCH średnich.** −1/3 i
+1/3 dają 0,66, nie 0,67. Jest na to osobny test po obu stronach.

### Co zostało

- **Pobieranie GDELT do bazy — NIEZROBIONE.** Migracja 0008, pętla pobierająca, deduplikacja,
  wyliczanie strony przy zapisie, wpis w `docs/SOURCES.md`. Bez tego API zwraca `503` („warstwa
  zdarzeń nie jest założona"), a front nie ma czego pokazać. **To jest następny krok.**
  Materiał wyjściowy: `eval/feasibility/fetch_events.py` i `fetch_versions.py` — działające skrypty
  badawcze, w których pobieranie i rozpakowywanie zipów jest już rozwiązane.
- **Widok wojny** — gałąź `worktree-agent-a6187d36637653b0d`, commit `bcb78de`, **niescalony i
  niezweryfikowany**. Sprawdź go zanim scalisz.

---

## 7. Otwarte sprawy poza mapą wojen

- **Ślad statku** jest scalony i przetestowany jednostkowo, ale **nikt nie widział go na ekranie**.
  Do sprawdzenia: kliknąć płynący statek i potwierdzić, że panel mówi „Przypłynęła z kierunku…",
  a za kadłubem ciągnie się linia z przerwami w miejscach ciszy AIS.
- **Trasy samolotów** — `adsbdb.com` daje za darmo i bez klucza lotnisko startu i celu po znaku
  wywoławczym. Sprawdzone na żywym ruchu: `AFL1015` → Kaliningrad→Moskwa. Niewdrożone.
- **Linia frontu** — `deepstatemap.live/api/history/last` zwraca GeoJSON okupowanego terytorium
  publicznie, bez klucza. Niewdrożone. Uwaga: projekt `engelde/ukrainewar`, z którego wzięło się
  rozpoznanie, jest na **AGPL-3.0** — jego kodu nie wolno przenosić, źródła danych są niezależne.
- **Klucze, których brakuje:** `AISSTREAM_API_KEY` (południowy Bałtyk — kod gotowy, czeka na klucz),
  `FIRMS_MAP_KEY` (anomalie termiczne z satelity), `GFW_TOKEN`.
- **Drony** — nie da się ich wykrywać przez ADS-B; szahedy nie nadają transpondera. Widać skutki
  pośrednie: skok zakłóceń GPS i omijanie przestrzeni przez ruch cywilny. Nie obiecywać więcej.
- **Rozjazd zakłóceń GPS** na środkowym Bałtyku względem gpsjam (41–46% u nas, 0–3% u nich) —
  nierozstrzygnięty.

---

## 8. Gałęzie

`main` jest stanem scalonym i zweryfikowanym. Gałęzie `worktree-agent-*` to prace agentów: część
scalona, część nie. Przed scaleniem czegokolwiek: sprawdź zakres (`git diff --name-only` od punktu
rozgałęzienia, nie od dowolnego starszego commita), uruchom testy w tamtym drzewie i **zweryfikuj
przynajmniej jedną liczbę z raportu samodzielnie**. Dzisiaj raporty agentów okazywały się rzetelne,
ale jeden pomylił się co do faktu, a ja sam wpisałem do kodu pomiar, który był nieważny.
