# Uruchomienie WACHTY od zera

Instrukcja sprawdzona na Windows 11 (26200), Docker 29.8.0, Docker Compose v5.5.1, w Git Bash.
Każda komenda poniżej została uruchomiona; tam, gdzie czegoś nie sprawdzono, jest to napisane wprost.

Cały stos to sześć usług w jednym pliku `compose.yaml`:

| Usługa | Co robi | Port na hoście |
|---|---|---|
| `db` | PostgreSQL 17 + TimescaleDB + PostGIS + pgvector | 5432 |
| `migrator` | wgrywa migracje i kończy pracę (kontener wychodzi z kodem 0) | — |
| `ingestion` | pobiera ADS-B z adsb.lol i zapisuje pozycje | — |
| `api` | REST + SignalR | `WACHTA_API_PORT`, domyślnie 8080 |
| `detectors` | pętla D1 / D3 / pokrycie | — |
| `web` | zbudowany front na nginksie, proxy do API | `WACHTA_WEB_PORT`, domyślnie 8081 |

---

## 1. Czego potrzebujesz

Do samego uruchomienia stosu: **tylko Docker Desktop**. Wszystko inne jest w obrazach.

Do uruchomienia testów dodatkowo: Python 3.12, Node 22, .NET 10 SDK.

### WSL2 i Docker Desktop

Oba instalatory wymagają **uprawnień administratora** (okno UAC przy instalacji):

```powershell
wsl --install --no-distribution
winget install -e --id Docker.DockerDesktop
```

**Restart komputera nie jest potrzebny** — sprawdzone przy instalacji na tej maszynie (nie w sesji,
w której powstał ten dokument; wtedy oba składniki już były). Wystarczy uruchomić Docker Desktop
i poczekać, aż przestanie się inicjalizować. Komunikaty instalatorów sugerujące ponowne uruchomienie
systemu można zignorować, o ile odpowiada:

```bash
docker --version          # Docker version 29.8.0, build 88096ef
docker compose version    # Docker Compose version v5.5.1
```

Sprawdzenie, czy jest komplet narzędzi (także tych do testów):

```powershell
scripts\bootstrap.ps1
```

### Docker poza PATH

Jeśli `docker` nie jest widoczny w powłoce (typowe w Git Bashu), dopisz katalog Docker Desktop:

```bash
export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"
```

---

## 2. Plik `.env` — wymagany

Bez `POSTGRES_PASSWORD` **baza nie wstanie**. Sprawdzone: przy pustym haśle kontener `db`
kończy pracę już przy inicjalizacji, z komunikatem obrazu PostgreSQL o braku hasła.

```bash
cp .env.example .env
```

Potem otwórz `.env` i ustaw `POSTGRES_PASSWORD` na cokolwiek własnego. Format i komplet zmiennych
pokazuje [`.env.example`](../.env.example):

- `POSTGRES_PASSWORD` — **wymagane**;
- `WACHTA_API_PORT`, `WACHTA_WEB_PORT` — opcjonalne, porty na hoście (patrz niżej);
- `AISSTREAM_API_KEY`, `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`, `FIRMS_MAP_KEY`, `GFW_TOKEN` —
  opcjonalne klucze źródeł, opisane w [docs/SOURCES.md](SOURCES.md). Stos startuje i działa bez nich;
  usługa `ingestion` korzysta wyłącznie z adsb.lol, które klucza nie wymaga.

`.env` jest w `.gitignore` i nie trafia do repozytorium.

---

## 3. Konflikty portów

Domyślnie zajmowane są **5432**, **8080** i **8081**. Port 8081 bardzo łatwo koliduje z lokalnymi
narzędziami deweloperskimi — na tej maszynie trzymał go proces `node.exe`, przez co usługa `web`
w ogóle nie wstawała.

Porty API i mapy zmienia się **bez dotykania `compose.yaml`**, zmiennymi w `.env`:

```dotenv
WACHTA_API_PORT=8080
WACHTA_WEB_PORT=8083
```

Sprawdzenie, kto trzyma port:

```bash
netstat -ano | grep -E ":8081\s"     # Git Bash; ostatnia kolumna to PID
```

```powershell
netstat -ano | findstr ":8081"       # PowerShell
```

Weryfikacja, że compose widzi nowe wartości (wypisuje porty po podstawieniu zmiennych):

```bash
docker compose config | grep published
```

Port bazy (5432) nie jest sparametryzowany — jeśli kolidowałby z lokalnym PostgreSQL-em, trzeba
edytować `compose.yaml`.

---

## 4. Pierwsze uruchomienie

```bash
docker compose up -d --build
```

**Pierwsze uruchomienie trwa długo.** Największy koszt to obraz bazy: `timescale/timescaledb-ha:pg17`
waży **4,05 GB** (sprawdzone: `docker images`). Do tego budowa pięciu własnych obrazów — cztery .NET-owe
po ok. 345 MB i pythonowy 376 MB. Kolejne uruchomienia korzystają z cache'u i trwają sekundy.

Kolejność jest wymuszona w `compose.yaml`: `db` musi być zdrowa, potem `migrator` musi **zakończyć się
sukcesem**, dopiero wtedy startują `ingestion`, `api` i `detectors`. Kontener `migrator` po pracy
wychodzi — stan `Exited` jest **poprawny**, nie jest to awaria.

Ponowne `docker compose up -d` (bez `--build`) jest bezpieczne i idempotentne: usługi już działające
zostają nietknięte, `migrator` przebiega jeszcze raz i stwierdza „No new scripts need to be executed”.

Pojedynczą usługę podnosi się tak:

```bash
docker compose up -d web
```

---

## 5. Sprawdzenie, że działa

### 5.1. Stan kontenerów

```bash
docker compose ps
```

Powinno być pięć kontenerów `Up` (`db` dodatkowo `(healthy)`); `migrator` nie jest tu widoczny,
bo już zakończył pracę. Żeby zobaczyć także jego:

```bash
docker compose ps -a
```

### 5.2. Logi

```bash
docker compose logs --tail=20 migrator     # "Migrations applied."
docker compose logs --tail=20 ingestion    # "adsblol-mil: received 111, written 109"
docker compose logs --tail=20 detectors    # "D1: 481 aircraft checked, 128 silent, 0 new alerts"
```

Zero alertów D1 to stan normalny — detektor milczy, dopóki model pokrycia odbiorników się nie zapełni,
a to wymaga kilku godzin zebranych danych.

### 5.3. Baza

Flaga `-T` jest potrzebna, gdy komenda leci ze skryptu; w zwykłym terminalu też działa.

```bash
docker compose exec -T db psql -U postgres -d wachta -c "\dt"
```

Spodziewane tabele: `aircraft_contact`, `aircraft_position`, `alert`, `coverage_hourly`, `d1_sample`,
`document_embedding`, `fetch_log`, `jamming_cell`, `schemaversions`, `source`, `spatial_ref_sys`.

Czy dane naprawdę napływają (`ostatnia` ma być sprzed najwyżej kilku minut):

```bash
docker compose exec -T db psql -U postgres -d wachta -c "SELECT count(*) AS pozycje, max(ts) AS ostatnia FROM aircraft_position;"
docker compose exec -T db psql -U postgres -d wachta -c "SELECT id, license FROM source ORDER BY id;"
docker compose exec -T db psql -U postgres -d wachta -c "SELECT count(*) FROM jamming_cell;"
```

Tabela `source` po starcie zawiera trzy wpisy, wszystkie na licencji ODbL 1.0: `adsblol-baltic-n`,
`adsblol-baltic-s`, `adsblol-mil`.

### 5.4. API

W Git Bashu `curl` jest prawdziwym curlem. W PowerShellu `curl` to alias na `Invoke-WebRequest`
i poniższe flagi nie zadziałają — tam trzeba pisać `curl.exe`.

```bash
curl -s http://localhost:8080/api/aircraft/live | head -c 200
```

Odpowiedź to tablica JSON; każdy element ma `hex`, `flight`, `typeCode`, `isMilitary`, `lat`, `lon`,
`altBaroFt`, `onGround`, `gsKt`, `trackDeg`, `ts`.

Pozostałe endpointy (wszystkie sprawdzone, zwracają 200):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/sources
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/alerts
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/jamming
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/openapi/v1.json
```

SignalR nasłuchuje pod `/hubs/live`.

**Dwie pułapki, na które łatwo wpaść:**

1. Endpoint to `/api/aircraft/live`, **nie** `/api/live`. `/api/live` zwraca **404** i to nie jest awaria.
2. `/api/aircraft/{hex}/track` **wymaga** parametrów `from` i `to` (znaczniki czasu UTC).
   Bez nich zwraca **400 Bad Request** — to poprawne zachowanie, nie błąd usługi.
   Tak samo `/api/replay`: bez `from` i `to` zwraca 400, z nimi 200.

```bash
# 400 - brak from/to, tak ma być
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/aircraft/010285/track

# 200 - z parametrami
curl -s "http://localhost:8080/api/aircraft/010285/track?from=2026-09-28T06:51:13Z&to=2026-09-28T08:51:13Z"
curl -s "http://localhost:8080/api/replay?from=2026-09-28T08:00:00Z&to=2026-09-28T09:00:00Z"
```

`hex` bierze się z odpowiedzi `/api/aircraft/live`; samolot musi mieć zapisane pozycje w podanym oknie,
inaczej dostaniesz pustą tablicę (nadal 200). Okno `from`–`to` musi być dodatnie i nie dłuższe niż 24 h,
w przeciwnym razie API odpowiada 400 z treścią „Window must be positive and at most 24 h.”.

`/api/aircraft/live` przyjmuje opcjonalnie `militaryOnly` oraz ramkę `minLat`, `minLon`, `maxLat`, `maxLon`.

### 5.5. Mapa

Otwórz `http://localhost:8081` — albo swój `WACHTA_WEB_PORT`. Na tej maszynie było to **8083**
(8081 zajmował proces `node.exe`) i z tego portu pochodzą przykłady poniżej. Kontrola z terminala:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8083/            # 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8083/api/aircraft/live   # 200, przez proxy nginksa
```

Drugie wywołanie sprawdza konfigurację nginksa z `infra/docker/nginx.conf`: kontener `web`
przekazuje `/api/`, `/openapi/` i `/hubs/` do `api:8080` po wewnętrznej sieci compose. Dlatego
zmiana `WACHTA_API_PORT` **nie psuje mapy** — dotyczy wyłącznie portu na hoście.

Tryb deweloperski frontu (Vite z własnym proxy, port 5173):

```bash
cd web && npm run dev
```

---

## 6. Zatrzymanie i czyszczenie

```bash
docker compose stop            # zatrzymuje kontenery, zostawia je i wolumen
docker compose start           # podnosi z powrotem
docker compose down            # usuwa kontenery i sieć, WOLUMEN Z DANYMI ZOSTAJE
docker compose down -v         # usuwa też wolumen - WSZYSTKIE ZEBRANE DANE PRZEPADAJĄ
```

Każda z tych komend przyjmuje nazwę usługi, np. `docker compose stop web` — i tak właśnie
sprawdzono `stop`/`start`, żeby nie przerywać zbierania danych: po `stop web` kontener ma status
`Exited (0)`, po `start web` wraca `Up` i mapa znowu odpowiada 200.

Zachowanie `down` i `down -v` zostało sprawdzone na osobnym, jednorazowym projekcie compose z tym samym
obrazem bazy (żeby nie skasować danych zbieranych przez działającą instancję): po `down` wolumen nadal
jest na liście `docker volume ls`, po `down -v` znika.

Wolumen z danymi nazywa się `wachta_dbdata`:

```bash
docker volume ls | grep wachta
```

Po `down -v` następny start zaczyna od pustej bazy: migracje lecą od zera, a detektory milczą,
dopóki nie uzbiera się kilka godzin danych.

---

## 7. Testy

### Python — detektory

```bash
python -m pytest -q
```

Z korzenia repozytorium; konfiguracja jest w `pytest.ini` (`testpaths = src/python/tests`,
testy integracyjne wyłączone przez `norecursedirs`). Sprawdzone 2026-09-28: cały zestaw przechodzi
w ok. 2 s. Liczba testów szybko rośnie — tego samego przedpołudnia było **348**, a po niecałej
godzinie **379** — więc nie traktuj konkretnej liczby jako kryterium, tylko brak niepowodzeń.

### Python — testy integracyjne (wymagają Dockera)

```bash
cd src/python && python -m pytest tests/integration -q
```

Sprawdzone: **4 passed** w ok. 19 s. Stawiają własny kontener PostgreSQL przez `testcontainers`,
niezależnie od działającego stosu. Ostrzeżenie o `testcontainers.postgres is deprecated` jest nieszkodliwe.

### Bramka jakości detektorów

```bash
python eval/run_eval.py --check eval/baseline.json
```

Sprawdzone: kod wyjścia 0. Porównuje wynik detektorów z zamrożoną linią bazową i zwraca błąd,
gdy metryka spadnie o więcej niż 5 punktów procentowych.

### C# (wymaga Dockera)

```bash
cd src/dotnet && dotnet test
```

Sprawdzone: **40 passed** w ok. 27 s.

Uwaga na SDK: instalator `dotnet-install.ps1` nie wymaga administratora i domyślnie **nie dopisuje się
do PATH**, więc `dotnet` z PATH-a może być samym runtime'em bez żadnego SDK (`dotnet --list-sdks`
zwraca wtedy pustkę). Na tej maszynie SDK 10.0.401 leży w `~/.dotnet`. Wtedy:

```bash
export DOTNET_ROOT="$HOME/.dotnet"
export PATH="$DOTNET_ROOT:$PATH"
dotnet --list-sdks            # 10.0.401 [C:\Users\grzan\.dotnet\sdk]
cd src/dotnet && dotnet test
```

### Front

```bash
cd web && npm test          # vitest
cd web && npm run build     # tsc -b + vite build
```

Oba sprawdzone. `npm run build` warto uruchomić przed `docker compose build`: obraz `web` buduje front
od zera, bez lokalnego cache'u `tsc`, więc błąd typów, którego lokalny inkrementalny build nie pokaże,
wywali dopiero budowę obrazu. Pełny odpowiednik tego, co robi Docker, to `npx tsc -b --force`.

Testy w przeglądarce: `cd web && npm run test:ui` (Playwright). **Nie sprawdzone w tej sesji.**

### Wszystko naraz

```powershell
scripts\check.ps1
```

Skrypt uruchamia komplet kontroli i pomija te, do których brakuje narzędzi. **Nie sprawdzony
w tej sesji** — poszczególne kroki sprawdzono osobno.

---

## 8. Typowe problemy

| Objaw | Przyczyna | Co zrobić |
|---|---|---|
| `web` nie wstaje, `bind: address already in use` | port 8081 zajęty przez inny proces | ustaw `WACHTA_WEB_PORT` w `.env` |
| `db` wychodzi zaraz po starcie | brak `POSTGRES_PASSWORD` | utwórz `.env` z `.env.example` |
| `migrator` ma status `Exited` | tak ma być, to zadanie jednorazowe | nic |
| `/api/live` zwraca 404 | zła ścieżka | `/api/aircraft/live` |
| `/api/aircraft/{hex}/track` zwraca 400 | brak `from` i `to` | dodaj oba parametry |
| `docker: command not found` w Git Bashu | Docker Desktop poza PATH | `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"` |
| `curl` w PowerShellu nie rozumie `-s`/`-w` | alias na `Invoke-WebRequest` | pisz `curl.exe` |
| `dotnet test`: „nie znaleziono SDK” | w PATH jest sam runtime | `DOTNET_ROOT=~/.dotnet` (patrz wyżej) |
| brak alertów D1 | model pokrycia jeszcze pusty | zostaw ingestię na kilka godzin |
