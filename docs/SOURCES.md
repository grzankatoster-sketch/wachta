# Źródła danych — statusy

Kolumna **Sprawdzone** = data i wynik faktycznego odpytania (skrypty w `eval/feasibility/`).
Nie wpisujemy tu niczego „z dokumentacji” bez próby połączenia.

Legenda dostępu: 🔓 bez klucza · 🔑 darmowy klucz/konto · ✉️ na wniosek · 💰 płatne.

## W użyciu (faza F1)

| Źródło | Co daje | Dostęp | Licencja / atrybucja | Sprawdzone |
|---|---|---|---|---|
| **adsb.lol `/v2/mil`** | samoloty wojskowe, globalnie | 🔓 | ODbL, „Data: adsb.lol contributors” | 2026-09-22: HTTP 200, 0,8 s, 453 samoloty, pola `nic`/`nac_p` obecne u ~70% |
| **adsb.lol `/v2/point`** | cały ruch w promieniu (AOI Bałtyk) | 🔓 | ODbL; **nie zwraca `dbFlags`**, więc flaga „wojskowy” może pochodzić tylko z `/v2/mil` (stąd `MilitaryRegistry`) | 2026-09-22: 164 samoloty w promieniu 250 NM od 55N/20E, 17% z NACp < 8; 2026-09-26: 0 z 92 samolotów miało pole `dbFlags` |
| **adsb.lol trace** | pełny tor lotu (700–3000 punktów) | 🔓 | ODbL | 2026-09-22: OK dla 4 tankowców |
| **OpenStreetMap (Overpass)** | kable i rurociągi podmorskie | 🔓 | ODbL | 2026-09-22: 3327 odcinków w Zatoce Fińskiej, w tym Estlink 1/2, C-Lion 1, BCS North, EESF-2/3, Balticconnector |
| **OpenFreeMap** | podkład mapy | 🔓 | © OpenStreetMap contributors | 2026-09-26: styl `positron` renderuje się w aplikacji |
| **AISStream** | AIS południowego Bałtyku: pozycje klasy A + nazwa/IMO/typ | 🔑 darmowy klucz (GitHub) | warunki aisstream.io, darmowe; atrybucja „Data: aisstream.io”. **Kod gotowy, klucza w repo nie ma** — patrz sekcja niżej | 2026-09-29: `stream.aisstream.io:443` osiągalny, TLS 1.3; parser i klient WebSocket przetestowane offline na nagranej próbce (51 testów) |

## Zweryfikowane, wchodzą w kolejnych fazach

| Źródło | Co daje | Dostęp | Uwagi | Sprawdzone |
|---|---|---|---|---|
| **Digitraffic (Fintraffic)** | AIS: pozycje + metadane statków (IMO, typ, zanurzenie, cel) | 🔓 | **praktycznie tylko wody fińskie** — patrz pomiar niżej | 2026-09-22: 1056 statków, mediana świeżości 2,3 min, 129 tankowców; 2026-09-29: 1336 statków w 0,3 s, zakres 55,49–65,80°N, **ponad 57°N wszystko poza 8 statkami (0,6%)**, w Zatoce Gdańskiej / przy polskim wybrzeżu / pod Kaliningradem / w cieśninach duńskich **zero** |
| **OpenSanctions** | statki i podmioty sankcjonowane | 🔓 pobrania | niekomercyjnie | 2026-09-22: zbiory `sanctions`, `maritime`, `ua_war_sanctions`, `eu_fsf` dostępne |
| **GDELT (pliki CSV co 15 min)** | zdarzenia z newsów | 🔓 | DOC API odmawia (429) — używamy surowych plików | 2026-09-22: `lastupdate.txt` OK, pliki dostępne |
| **EMODnet Human Activities** | rurociągi (Balticconnector, Nord Stream) | 🔓 WFS | **kabli w Zatoce Fińskiej brak** — stąd OSM | 2026-09-22: warstwa `pipelines` zwraca dane, warstwy kabli puste |

## Odrzucone lub zablokowane

| Źródło | Powód | Sprawdzone |
|---|---|---|
| **airplanes.live** | HTTP 403, wymaga maila z opisem projektu | 2026-09-22 |
| **GDELT DOC API** | dwa razy HTTP 429 (limit) | 2026-09-22 |
| **TeleGeography** | trasy kabli są schematyczne, nie nadają się do detektora D6 | 2026-09-22 (analiza) |
| **Kystverket (Norwegia)** | otwarty strumień AIS (NMEA po TCP, `153.44.253.27:5631`, licencja NLOD, bez klucza) — ale zasięg to 40–60 Mm od **norweskiego** wybrzeża, czyli nie Bałtyk. Do tego surowy NMEA wymagałby dekodera 6-bitowego, którego w repo nie ma | 2026-09-29: połączenie TCP nie doszło (timeout po 20 s); odrzucone i tak, bo pokrycie jest nie to |
| **HELCOM** | 215 warstw w MADS to **gęstość ruchu w siatce i statystyki przejść**, nie pozycje pojedynczych statków. Surowy AIS HELCOM należy do państw członkowskich i wymaga porozumienia, nie klucza | 2026-09-29: `maps.helcom.fi/arcgis/rest/services/MADS/Shipping` HTTP 200, warstwy typu „AIS passage line crossings by ship type” |

## Czeka na konto lub klucz (zadanie T0.2)

| Źródło | Potrzebne | Po co |
|---|---|---|
| **AISStream** | klucz (logowanie GitHubem) | AIS południowego Bałtyku — **kod już jest**, instrukcja niżej |
| **OpenSky** | klient OAuth2 | zapasowe źródło ADS-B, historia |
| **NASA FIRMS** | MAP_KEY | pożary, F4 |
| **Global Fishing Watch** | token | luki AIS i przeładunki jako etykiety, F2 |
| **UCDP** | token mailem | etykiety zdarzeń, F4 |

| **Duńska Adm. Morska (DMA)** | dzienne pliki AIS w CSV (ok. 550 MB spakowane) | 🔓 publiczny bucket S3 | otwarte; **tylko wody duńskie** — Zatoki Fińskiej nie obejmuje, więc incydentu Eagle S w tych danych nie ma. **Nie nadaje się na mapę na żywo**: pliki są dobowe i publikowane z opóźnieniem | 2026-09-26: pobrana i przefiltrowana doba 2024-12-25; adres `http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/2024/aisdk-2024-12-25.zip` (host `web.ais.dk` ma certyfikat na inną nazwę i odpada). **2026-09-29: układ bucketu się zmienił** — ostatnie ~19 miesięcy leży w KORZENIU (`/aisdk-2026-09-26.zip`), lata do 2025 w katalogach `RRRR/`. Ścieżka z roku zwraca dziś 404 dla świeżych dób (skrypt `eval/feasibility/dma_day.py` używa starej ścieżki i wymaga poprawki). Najnowszy plik: 2026-09-26, czyli **3 doby opóźnienia** |

## Limity zapytań — zmierzone 2026-09-26

| Źródło | Co wychodzi w praktyce |
|---|---|
| **adsb.lol** | Pojedyncze odpytanie co 5 s przechodzi w 7/8 przypadków, co 30 s w 8/8. **Ale trzy źródła strzelające równocześnie dostają HTTP 429** — liczy się równoczesność, nie sama częstotliwość. Stąd w `appsettings.json` źródła są rozsunięte (`StartDelaySeconds` 0/10/20), a obszary odpytywane co 30 s zamiast co 15 s. |
| **Overpass (OSM)** | Zapytanie o cały Bałtyk z geometrią (`out geom`) kończy się 504. Nawet dwa warunki naraz są za ciężkie. Działa: jeden warunek na zapytanie, obszar podzielony na cztery części, 8 s przerwy. Skrypt: `eval/feasibility/fetch_cables.py`. |

## AISStream — południowy Bałtyk

### Dlaczego w ogóle

Mapa deklaruje 48–70°N / 0–40°E (`WatchedArea.cs`), a pokazywała Zatokę Fińską i Botnicką. Pomiar na
żywej bazie 2026-09-29 (20 h zbierania, 165 202 pozycje, 1210 kadłubów z Digitraffic):

| Akwen | Pozycje | Statki |
|---|---:|---:|
| Zatoka Gdańska (54,0–55,0°N / 18,0–19,8°E) | **0** | **0** |
| polskie wybrzeże (53,9–55,0°N / 14,0–19,8°E) | **0** | **0** |
| podejścia do Kaliningradu (54,4–55,4°N / 19,0–21,0°E) | **0** | **0** |
| cieśniny duńskie (54,5–58,0°N / 9,0–13,5°E) | **0** | **0** |
| poniżej 57°N razem | 178 (0,11%) | 10 |
| razem | 165 202 | 1210 |

### Porównanie kandydatów (wszystkie odpytane, nie przeczytane z dokumentacji)

| Źródło | Pokrycie południowego Bałtyku | Licencja | Klucz | Limity | Na żywo | Werdykt |
|---|---|---|---|---|---|---|
| **AISStream.io** | tak, globalne odbiorniki brzegowe (~200 km od lądu) | warunki aisstream.io, darmowe | 🔑 darmowy, logowanie GitHubem | 3 połączenia/konto, 3 na IP, aktualizacja subskrypcji 1/s, do 200 filtrów MMSI, subskrypcja w 3 s od połączenia, brak SLA i brak powtórek | tak (WebSocket push) | **wdrożone** |
| **Digitraffic (Fintraffic)** | nie — 0,6% pozycji poniżej 57°N, zero w czterech akwenach wyżej | CC BY 4.0 | 🔓 | brak twardych; wymaga `User-Agent` i `Digitraffic-User` | tak (odpytywanie) | zostaje jako źródło główne północy |
| **Kystverket (Norwegia)** | nie — 40–60 Mm od norweskiego wybrzeża | NLOD | 🔓 | brak | tak (NMEA po TCP) | odrzucone: złe morze; do tego surowy NMEA bez dekodera w repo |
| **Duńska Adm. Morska (DMA)** | częściowo — wody duńskie i cieśniny, bez Zatoki Gdańskiej | otwarte | 🔓 | ~500 MB na dobę | **nie** — pliki dobowe, 3 doby opóźnienia | zostaje jako materiał do backtestu, nie na mapę |
| **HELCOM** | brak pozycji jednostkowych | — | 🔓 (produkty) | — | nie | odrzucone: to gęstość w siatce, nie statki |

Wniosek: **jedynym źródłem, które daje pozycje pojedynczych statków południowego Bałtyku w czasie
rzeczywistym, jest AISStream.** Reszta albo pokrywa inne morze, albo daje pliki sprzed kilku dni,
albo nie daje pozycji w ogóle.

### Co wdrożone

* `src/python/wachta_detectors/websocket.py` — klient WebSocket na samej bibliotece standardowej
  (obraz detektorów wstaje z `uv sync --frozen`, więc nowa zależność oznaczałaby zmianę
  `pyproject.toml` **i** `uv.lock`). Klient **nie oferuje** `permessage-deflate`: serwer może włączyć
  tylko te rozszerzenia, o które klient poprosił, więc nieproszenie jest gwarancją, że ramki
  przychodzą nieskompresowane. To ta sama pułapka, która raz już zabiła AIS w tym projekcie —
  `urllib` nie rozpakowuje gzipa samo.
* `src/python/wachta_detectors/aisstream.py` — subskrypcja, parser, bufor, wątek czytający.
* Pobieranie wchodzi tam, gdzie już jest AIS: `run_ship_ingest()` w `run.py`, zaraz za Digitrafficiem.
* Źródło zarejestrowane migracją `0007_aisstream.sql` jako `aisstream-baltic-s`, `trust_tier` 3.

Pudełko subskrypcji: **53,5–58,5°N / 9,0–24,0°E** — wybrane pomiarem nakładania się z Digitrafficiem.
Z 886 kadłubów, które Digitraffic miał żywe (pozycja młodsza niż 30 min) 2026-09-29, w tym prostokącie
siedziało 11 (**1,24%**). Warianty: 53,5–59,0°N/9–24°E → 39 (4,4%), 53,5–60,0°N/9–30°E → 372 (42%),
53,5–57,5°N/9–24°E → 0, ale bez Zatoki Ryskiej i północnej Gotlandii.

### Deduplikacja: kto wygrywa i dlaczego

**Digitraffic wygrywa wszędzie tam, gdzie oba źródła słyszą ten sam kadłub.** AISStream dokłada tylko
te MMSI, których Digitraffic nie zgłosił w ostatnich **15 minutach** (`drop_covered()`).

Uzasadnienie wagi: Digitraffic to sieć brzegowa krajowego organu (`trust_tier` 2) z rejestrem statków
za sobą — stąd IMO, typ i zanurzenie, których sam `PositionReport` nie niesie. AISStream to agregacja
odbiorników ochotników (`trust_tier` 3), bez SLA i bez powtórek. Ważniejsze: trzymanie obu wpisów nie
byłoby tylko nadmiarowe, ale **szkodliwe** — dwa niezależne odbiorniki dają temu samemu kadłubowi dwie
pozycje oddalone o kilkaset metrów i kilka sekund, a D7 liczy prędkość wynikową między kolejnymi
pozycjami jednego MMSI. Dwa źródła na jeden statek produkują prędkości niemożliwe, czyli dokładnie
sygnaturę, którą D7 zgłasza jako „jeden numer, dwa kadłuby”.

Skąd 15 minut: 41 013 kolejnych różnic czasu między pozycjami tego samego MMSI z 12 h (2026-09-29) —
mediana 179 s, p90 240 s, p95 360 s, p99 801 s. Udział przerw mieszczących się w oknie: 6 min → 94,73%,
**15 min → 99,12%**, 30 min → 99,66%. Trzydzieści minut dokłada 0,54 pp, a dwa razy dłużej blokuje
statek, który naprawdę wyszedł z zasięgu fińskiej sieci. Reguła jest napisana po MMSI, nie po geografii
— gdyby Fintraffic rozszerzył sieć na południe, nic nie trzeba stroić od nowa.

Sprawdzone na żywej bazie 2026-09-29: z 5 kadłubów w próbce 1 (MMSI 230982000, Zatoka Fińska) był
w tym momencie pokryty przez Digitraffic i został odrzucony; 4 południowe zapisały się.

### CZEGO TO ŹRÓDŁO NIE POKRYWA

* **Klasy B nie bierzemy** (`FilterMessageTypes` = `PositionReport`, `ShipStaticData`). Jachty,
  motorówki i część kutrów nadają klasą B; w Zatoce Gdańskiej latem to ruch dominujący, dla
  detektorów ciemnej floty szum, a kosztuje pasmo i wiersze. Świadoma dziura, nie przeoczenie.
* **Pełne morze poza zasięgiem odbiorników brzegowych** (~200 km od lądu) — AISStream nie ma AIS
  satelitarnego. Środek Bałtyku Właściwego bywa cienki, choć morze jest wąskie.
* **Brak SLA, brak powtórek.** Cisza może znaczyć „nikt nie nadaje” albo „odbiornik ochotnika padł”.
  Dla D4 (cisza AIS) to różnica zasadnicza — alarm z tego obszaru jest słabszą przesłanką niż alarm
  z obszaru Digitraffic.
* **Nie ma historii.** Restart kontenera zaczyna od pustego bufora; nic się nie nadrabia.
* **Zanurzenie i cel podróży** są w `ShipStaticData` tylko wtedy, gdy załoga je wpisała — jak wszędzie
  w AIS, to deklaracja, nie pomiar.
* Poza pudełkiem 53,5–58,5°N / 9,0–24,0°E nie prosimy o nic. Zatoka Botnicka, Zatoka Fińska i
  Morze Barentsa zostają przy Digitrafficu albo są nieobsłużone.

### Jak zdobyć klucz i gdzie go wpisać

Klucz jest darmowy. **Musi to zrobić właściciel projektu — nie agent i nie w niczyim imieniu.**

1. Wejdź na `https://aisstream.io/` i kliknij **Sign in with GitHub** (to jedyny sposób logowania).
2. Po zalogowaniu otwórz `https://aisstream.io/account` i utwórz klucz przyciskiem tworzenia klucza
   API. **Klucz jest pokazany raz** — potem konto wyświetla go zamaskowanego, więc skopiuj od razu.
3. Wklej go do `.env` w korzeniu repozytorium (plik jest w `.gitignore`, nie commituj go):
   ```
   AISSTREAM_API_KEY=tu_wklej_klucz
   ```
4. Podnieś detektory: `docker compose up -d --build detectors`. W logu ma się pojawić
   `AISStream: subskrypcja [[[53.5, 9.0], [58.5, 24.0]]]`. Bez klucza logowane jest ostrzeżenie
   `brak AISSTREAM_API_KEY` i wszystko chodzi jak dotąd, na samym Digitrafficu.
5. Sprawdzenie, że dane wchodzą:
   ```
   docker compose exec -T db psql -U postgres -d wachta -c \
     "SELECT count(*), min(lat), max(lat) FROM ship_position WHERE source_id='aisstream-baltic-s';"
   ```
6. Gdy klucz już jest, warto podmienić syntetyczną próbkę testową na prawdziwą:
   `py eval/feasibility/record_aisstream.py 60 > src/python/tests/fixtures/aisstream_sample.jsonl`.
   Testy są napisane tak, żeby przeszły bez zmian.

Rotacja i odwołanie klucza: ta sama strona `account`. Klucz nie trafia do żadnego modelu ani do
repozytorium; w kontenerze jest zmienną środowiskową, przekazywaną przez `compose.yaml`.

### Uczciwa uwaga o testach

Parser i klient WebSocket są przetestowane offline (51 testów), ale próbka
`src/python/tests/fixtures/aisstream_sample.jsonl` **nie jest nagranym ruchem** — to repozytorium nie
ma jeszcze klucza. Została zbudowana pole po polu z modeli OpenAPI samego aisstream.io
(`github.com/aisstream/ais-message-models`, `PositionReport.md` i `ShipStaticData.md`, odczytane
2026-09-29), więc nazwy i typy pól pochodzą od dostawcy, a nie ze zgadywania. Cały łańcuch — wątek,
uzgodnienie połączenia, ramki, subskrypcja, parser, bufor — jest przepuszczony przez prawdziwe gniazdo
na pętli zwrotnej (`test_caly_lancuch_przez_prawdziwe_gniazdo`), a zapis do bazy sprawdzony na żywej
instancji. Niesprawdzone zostaje jedno: czy aisstream.io odpowiada dokładnie tak, jak opisuje własny
model. To zweryfikuje pierwszy przebieg z kluczem.

## Zasady

- Każdy rekord w bazie ma `source_id`, `fetched_at` i hash treści (`fetch_log`) — rodowód jest częścią danych, nie dokumentacji.
- Atrybucja wymagana licencją pojawia się w stopce mapy (`/api/sources` → `SourcesFooter`).
- Projekt pozostaje niekomercyjny, bo wymagają tego licencje GFW, OpenSky, airplanes.live i OpenSanctions.
- Sekretów nie wysyłamy do żadnego modelu ani nie commitujemy; `.env` jest w `.gitignore`.

## Projekt UI

Makieta w Figmie — do uzupełnienia w zadaniu T0.7 (link tutaj).

## Pełne tory lotu (adsb.lol)

`https://globe.adsb.lol/data/traces/{2 ostatnie znaki hex}/trace_full_{hex}.json` — cały tor samolotu
z bieżącej doby UTC, 140–3000 punktów. Bez klucza. Sprawdzone 2026-09-27: z 60 samolotów z `/v2/mil`
**47 miało tor w archiwum, 13 nie** (samolot dopiero wystartował albo nadaje spoza zasięgu odbiorników).
Pobierane po jednym, z sekundą przerwy — to jedyne miejsce w projekcie, gdzie jeden samolot kosztuje
więcej bajtów niż cała godzina nieba.
