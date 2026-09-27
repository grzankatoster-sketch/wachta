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

## Zweryfikowane, wchodzą w kolejnych fazach

| Źródło | Co daje | Dostęp | Uwagi | Sprawdzone |
|---|---|---|---|---|
| **Digitraffic (Fintraffic)** | AIS: pozycje + metadane statków (IMO, typ, zanurzenie, cel) | 🔓 | **tylko wody fińskie (≥ 57,7°N)** — południowy Bałtyk wymaga AISStream | 2026-09-22: 1056 statków, mediana świeżości 2,3 min, 129 tankowców |
| **OpenSanctions** | statki i podmioty sankcjonowane | 🔓 pobrania | niekomercyjnie | 2026-09-22: zbiory `sanctions`, `maritime`, `ua_war_sanctions`, `eu_fsf` dostępne |
| **GDELT (pliki CSV co 15 min)** | zdarzenia z newsów | 🔓 | DOC API odmawia (429) — używamy surowych plików | 2026-09-22: `lastupdate.txt` OK, pliki dostępne |
| **EMODnet Human Activities** | rurociągi (Balticconnector, Nord Stream) | 🔓 WFS | **kabli w Zatoce Fińskiej brak** — stąd OSM | 2026-09-22: warstwa `pipelines` zwraca dane, warstwy kabli puste |

## Odrzucone lub zablokowane

| Źródło | Powód | Sprawdzone |
|---|---|---|
| **airplanes.live** | HTTP 403, wymaga maila z opisem projektu | 2026-09-22 |
| **GDELT DOC API** | dwa razy HTTP 429 (limit) | 2026-09-22 |
| **TeleGeography** | trasy kabli są schematyczne, nie nadają się do detektora D6 | 2026-09-22 (analiza) |

## Czeka na konto lub klucz (zadanie T0.2)

| Źródło | Potrzebne | Po co |
|---|---|---|
| **AISStream** | klucz (logowanie GitHubem) | AIS południowego Bałtyku, F2 |
| **OpenSky** | klient OAuth2 | zapasowe źródło ADS-B, historia |
| **NASA FIRMS** | MAP_KEY | pożary, F4 |
| **Global Fishing Watch** | token | luki AIS i przeładunki jako etykiety, F2 |
| **UCDP** | token mailem | etykiety zdarzeń, F4 |

| **Duńska Adm. Morska (DMA)** | dzienne pliki AIS w CSV (ok. 550 MB spakowane) | 🔓 publiczny bucket S3 | otwarte; **tylko wody duńskie** — Zatoki Fińskiej nie obejmuje, więc incydentu Eagle S w tych danych nie ma | 2026-09-26: pobrana i przefiltrowana doba 2024-12-25; adres `http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/2024/aisdk-2024-12-25.zip` (host `web.ais.dk` ma certyfikat na inną nazwę i odpada) |

## Limity zapytań — zmierzone 2026-09-26

| Źródło | Co wychodzi w praktyce |
|---|---|
| **adsb.lol** | Pojedyncze odpytanie co 5 s przechodzi w 7/8 przypadków, co 30 s w 8/8. **Ale trzy źródła strzelające równocześnie dostają HTTP 429** — liczy się równoczesność, nie sama częstotliwość. Stąd w `appsettings.json` źródła są rozsunięte (`StartDelaySeconds` 0/10/20), a obszary odpytywane co 30 s zamiast co 15 s. |
| **Overpass (OSM)** | Zapytanie o cały Bałtyk z geometrią (`out geom`) kończy się 504. Nawet dwa warunki naraz są za ciężkie. Działa: jeden warunek na zapytanie, obszar podzielony na cztery części, 8 s przerwy. Skrypt: `eval/feasibility/fetch_cables.py`. |

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
