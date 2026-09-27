# F0 + F1: Fundament i warstwa powietrzna — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Działająca lokalnie mapa z samolotami wojskowymi na żywo nad Bałtykiem, heksami zakłóceń GPS (D3), alarmami „zgaszony transponder” (D1), suwakiem czasu i zmierzoną jakością detektorów w pipeline Azure DevOps.

**Architecture:** C# (.NET 10) pobiera ADS-B z adsb.lol przez adaptery z dekoratorem limitu zapytań i zapisuje pozycje do PostgreSQL/TimescaleDB (COPY) z dziennikiem pobrań (rodowód). Python co minutę liczy detektory D1/D3 i model pokrycia na danych z bazy i zapisuje alarmy/heksy. ASP.NET Core wystawia REST + SignalR, a front React + MapLibre + deck.gl rysuje warstwy. Bez Redisa w F1 (ADR-002): komponenty komunikują się przez bazę.

**Tech Stack:** .NET 10, ASP.NET Core minimal API, SignalR, Npgsql 9, Dapper, DbUp, xUnit 2.9, Testcontainers; Python 3.12, uv, psycopg 3, h3 4, pytest; React 19, Vite, TypeScript, maplibre-gl, react-map-gl 8, deck.gl 9, @microsoft/signalr, Vitest; TimescaleDB-HA (PostgreSQL 17 + PostGIS + pgvector); Docker Compose; Azure Pipelines.

**Spec:** [docs/PLAN.md](../../PLAN.md) (architektura, §2 detektory D1/D3, §3 źródła, §17 test wykonalności) oraz [docs/PLAN-DZIALANIA.md](../../PLAN-DZIALANIA.md) (zakres F0/F1, kryteria ukończenia).

## Global Constraints

- Repo root: `C:\Users\grzan\wachta` (dalej: `wachta/`). Wszystkie ścieżki w planie są względne wobec roota.
- .NET: `net10.0`, `<Nullable>enable</Nullable>`, `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>`.
- Python: `>=3.12`, zarządzanie wyłącznie przez `uv` (bez pip/venv ręcznie).
- Node 22 LTS, menedżer `npm`.
- Baza: obraz `timescale/timescaledb-ha:pg17`, baza `wachta`, użytkownik `postgres`.
- Connection string C#: klucz konfiguracji `ConnectionStrings:Wachta` (env: `ConnectionStrings__Wachta`). Python: env `WACHTA_DB` (URL `postgresql://...`).
- Sekrety tylko w `.env` (w `.gitignore`); w repo wyłącznie `.env.example`.
- Każdy rekord pozycji ma `source_id` i `fetched_at`; każde pobranie ma wiersz w `fetch_log` (rodowód — PLAN.md §3c).
- AOI F1: Bałtyk — dwa punkty adsb.lol: `55.0/20.0/250` (południe) i `60.0/24.0/250` (północ), plus globalny `/v2/mil`.
- Odstęp między zapytaniami do jednego endpointu adsb.lol: min. **15 s**, a źródła muszą być **rozsunięte w czasie** (`StartDelaySeconds`).
  Zmierzone 2026-09-26: pojedyncze odpytanie co 5 s przechodzi w 7/8 przypadków, co 30 s w 8/8, ale **trzy źródła strzelające równocześnie dostają HTTP 429**.
  Stąd konfiguracja: `mil` co 15 s (offset 0), oba obszary co 30 s (offsety 10 s i 20 s) — jedno zapytanie na ~10 s.
- Retencja surowych pozycji: **7 dni**; kompresja po 1 dniu.
- Wynik detektora zawsze opisany jako „do sprawdzenia” — nigdy jako oskarżenie (PLAN.md §13).
- Komunikaty commitów: Conventional Commits po angielsku, zakończone linią `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Komunikat commita przekazywać przez plik lub here-doc z pojedynczym cudzysłowem — nigdy z backtickami w podwójnym cudzysłowie.

## Struktura plików (po F1)

```
wachta/
  .gitignore  .editorconfig  .env.example  README.md  compose.yaml  azure-pipelines.yml
  docs/
    PLAN.md  PLAN-DZIALANIA.md  SOURCES.md
    adr/0001-jedna-baza-postgres.md  adr/0002-bez-redisa-w-f1.md  adr/0003-podzial-csharp-python.md
    superpowers/plans/2026-09-22-f0-f1-fundament-powietrze.md
  infra/docker/dotnet.Dockerfile  infra/docker/python.Dockerfile  infra/docker/web.Dockerfile  infra/docker/nginx.conf
  src/dotnet/
    Wachta.sln
    Wachta.Domain/        AircraftObservation.cs  SourceSnapshot.cs  IAircraftSource.cs
    Wachta.Db/            Program.cs  DbMigrator.cs  Scripts/0001..0004_*.sql
    Wachta.Ingestion/     Program.cs  AdsbV2Parser.cs  AdsbLolSource.cs  ThrottledAircraftSource.cs
                          SourceOptions.cs  SourceFactory.cs  PositionDeduplicator.cs  PositionWriter.cs
                          IngestionWorker.cs  appsettings.json
    Wachta.Api/           Program.cs  Dtos.cs  AircraftEndpoints.cs  DetectorEndpoints.cs  LiveHub.cs  LiveBroadcaster.cs
    Wachta.Tests/         GlobalUsings.cs  Fixtures/adsb_v2_sample.json  PostgresFixture.cs  AdsbV2ParserTests.cs
                          ThrottledAircraftSourceTests.cs  SourceFactoryTests.cs  PositionDeduplicatorTests.cs
                          DbMigratorTests.cs  PositionWriterTests.cs  ApiTests.cs  LiveHubTests.cs
  src/python/
    pyproject.toml  uv.lock
    wachta_detectors/     __init__.py  models.py  geo.py  jamming.py  coverage.py  dark.py  airports.py  repository.py  run.py
    tests/                test_jamming.py  test_coverage.py  test_dark.py  test_airports.py  integration/test_repository.py
  web/
    package.json  vite.config.ts  tsconfig.json  index.html
    src/  main.tsx  App.tsx  api.ts  live.ts  colors.ts  replay.ts
          layers/aircraft.ts  layers/jamming.ts  layers/alerts.ts  layers/trips.ts
          components/MapView.tsx  components/AlertsPanel.tsx  components/SourcesFooter.tsx  components/ReplayBar.tsx
          colors.test.ts  replay.test.ts
  eval/
    feasibility/probe_sources.py  feasibility/probe_llm.py  feasibility/probe_keyed.py
    fixtures/d3_hour.json (godzina pozycji z bazy)  fixtures/d3_labels.json
    export_d3_fixture.py
    fixtures/d1_cases.jsonl (syntetyczne, regresja)  fixtures/d1_real_cases.jsonl (oznaczone ręcznie, jakość)
    make_d3_labels.py  make_d1_seed.py  label_d1.py  run_eval.py
    labels/d1_to_label.csv (lokalnie)  baseline.json  results/.gitkeep
```

---

## F0 — Fundament

### Task 0.1: Środowisko (wykonuje użytkownik)

**Files:** brak (instalacja systemowa).

**Interfaces:** Produces: działające komendy `docker`, `dotnet` (SDK 10), `node` 22, `npm`, `uv`, `git`.

- [ ] **Step 1: Zainstaluj WSL2** (PowerShell jako Administrator)

```powershell
wsl --install --no-distribution
```
Uruchom ponownie komputer.

- [ ] **Step 2: Zainstaluj Docker Desktop, .NET 10 SDK, Node 22 LTS, uv**

```powershell
winget install -e --id Docker.DockerDesktop
winget install -e --id Microsoft.DotNet.SDK.10
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id astral-sh.uv
```
Uruchom Docker Desktop raz ręcznie (akceptacja warunków, backend WSL2).

- [ ] **Step 3: Zweryfikuj**

```powershell
docker run --rm hello-world
dotnet --list-sdks
node --version
uv --version
git --version
```
Expected: `Hello from Docker!`; SDK `10.0.x`; `v22.x`; `uv 0.x`; `git version 2.x`.

### Task 0.2: Konta i klucze (wykonuje użytkownik)

**Files:**
- Create: `.env` (lokalnie, nigdy w repo)

**Interfaces:** Produces: zmienne w `.env` używane w F2+ (`AISSTREAM_API_KEY`, `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`, `FIRMS_MAP_KEY`, `GFW_TOKEN`) oraz `POSTGRES_PASSWORD`.

- [ ] **Step 1: Utwórz konta**
  - GitHub: publiczne repo `wachta` (puste, bez README).
  - Azure DevOps: organizacja + projekt `wachta` (dev.azure.com).
  - AISStream (logowanie GitHubem) → wygeneruj klucz.
  - OpenSky: konto → Account → API client → `client_id` + `client_secret`.
  - NASA FIRMS: firms.modaps.eosdis.nasa.gov/api/map_key → MAP_KEY.
  - Global Fishing Watch: globalfishingwatch.org/our-apis → token (cel: niekomercyjny projekt badawczy).

- [ ] **Step 2: Wyślij dwa maile** (treść do skopiowania)

Do UCDP (adres z https://ucdp.uu.se/apidocs/) i do contact@airplanes.live:
```
Subject: API access request — WACHTA (non-commercial OSINT portfolio project)

Hello,
I am building WACHTA, a non-commercial, open-source situational awareness map
(portfolio project) that combines public ADS-B/AIS data with conflict event data
for the Baltic Sea region. Repository: https://github.com/<login>/wachta
I would like to request API access. Expected usage: a few requests per minute,
data shown with attribution, no redistribution of raw data.
Thank you,
<imię i nazwisko>
```

- [ ] **Step 3: Zapisz `.env`** w `wachta/` (po utworzeniu folderu w Task 0.3):

```
POSTGRES_PASSWORD=<losowe 24 znaki>
AISSTREAM_API_KEY=<...>
OPENSKY_CLIENT_ID=<...>
OPENSKY_CLIENT_SECRET=<...>
FIRMS_MAP_KEY=<...>
GFW_TOKEN=<...>
```

### Task 0.3: Szkielet repozytorium

**Files:**
- Create: `.gitignore`, `.editorconfig`, `.env.example`, `README.md`
- Create: `src/dotnet/Wachta.sln` + projekty `Wachta.Domain`, `Wachta.Db`, `Wachta.Ingestion`, `Wachta.Api`, `Wachta.Tests`
- Create: `src/dotnet/Directory.Build.props`
- Create: `src/python/pyproject.toml`, `src/python/wachta_detectors/__init__.py`, `src/python/tests/test_smoke.py`
- Create: `web/` (Vite React TS)

**Interfaces:** Produces: solution i projekty, do których kolejne zadania dodają pliki; pakiet Pythona `wachta_detectors`.

- [ ] **Step 1: Git + pliki bazowe**

```bash
cd /c/Users/grzan/wachta
git init -b main
```

`.gitignore`:
```gitignore
.env
bin/
obj/
*.user
.vs/
.vscode/
__pycache__/
.venv/
.pytest_cache/
node_modules/
web/dist/
eval/results/*.json
!eval/results/.gitkeep
*.log
```

`.editorconfig`:
```ini
root = true
[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 4
[*.{json,yml,yaml,ts,tsx,css,html}]
indent_size = 2
```

`.env.example`:
```
POSTGRES_PASSWORD=change-me
AISSTREAM_API_KEY=
OPENSKY_CLIENT_ID=
OPENSKY_CLIENT_SECRET=
FIRMS_MAP_KEY=
GFW_TOKEN=
```

`README.md`:
```markdown
# WACHTA

Własna mapa sytuacyjna (OSINT): ruch wojskowy w powietrzu, flota cieni na morzu, zdarzenia na lądzie —
z detektorami nietypowych zachowań i rodowodem każdej informacji („kto co podaje”).

Status: w budowie (F0). Plan: [docs/PLAN.md](docs/PLAN.md), [docs/PLAN-DZIALANIA.md](docs/PLAN-DZIALANIA.md).
```

- [ ] **Step 2: Solution .NET**

```bash
cd /c/Users/grzan/wachta/src/dotnet
dotnet new sln -n Wachta --format sln   # .NET 10 domyślnie tworzy Wachta.slnx; pipeline i komendy w planie używają .sln
dotnet new classlib -n Wachta.Domain -f net10.0
dotnet new console  -n Wachta.Db -f net10.0
dotnet new worker   -n Wachta.Ingestion -f net10.0
dotnet new web      -n Wachta.Api -f net10.0
dotnet new classlib -n Wachta.Tests -f net10.0
rm Wachta.Domain/Class1.cs Wachta.Tests/Class1.cs
dotnet sln add Wachta.Domain Wachta.Db Wachta.Ingestion Wachta.Api Wachta.Tests
dotnet add Wachta.Ingestion reference Wachta.Domain
dotnet add Wachta.Api reference Wachta.Domain
dotnet add Wachta.Tests reference Wachta.Domain Wachta.Db Wachta.Ingestion Wachta.Api
dotnet add Wachta.Tests package Microsoft.NET.Test.Sdk
dotnet add Wachta.Tests package xunit --version 2.9.3
dotnet add Wachta.Tests package xunit.runner.visualstudio
dotnet add Wachta.Tests package Microsoft.Extensions.TimeProvider.Testing
dotnet add Wachta.Tests package Testcontainers.PostgreSql
dotnet add Wachta.Tests package Microsoft.AspNetCore.Mvc.Testing
dotnet add Wachta.Tests package Microsoft.AspNetCore.SignalR.Client
```

`src/dotnet/Directory.Build.props`:
```xml
<Project>
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <LangVersion>latest</LangVersion>
  </PropertyGroup>
</Project>
```

W `Wachta.Tests/Wachta.Tests.csproj` dodaj w `<PropertyGroup>`: `<IsPackable>false</IsPackable>` i `<IsTestProject>true</IsTestProject>`.

`Wachta.Tests` powstał z `classlib`, więc nie ma `using Xunit` — bez tego żaden test się nie skompiluje. Utwórz `src/dotnet/Wachta.Tests/GlobalUsings.cs`:
```csharp
global using Xunit;
```

- [ ] **Step 3: Projekt Python**

`src/python/pyproject.toml`:
```toml
[project]
name = "wachta-detectors"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "psycopg[binary]>=3.2",
    "h3>=4.1",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "testcontainers[postgres]>=4.8",
]

[tool.pytest.ini_options]
pythonpath = ["."]
markers = ["integration: requires Docker"]
```

`src/python/wachta_detectors/__init__.py`:
```python
"""WACHTA detectors: D1 dark aircraft, D3 GPS jamming, receiver coverage model."""
```

`src/python/tests/test_smoke.py`:
```python
import wachta_detectors


def test_package_imports():
    assert wachta_detectors.__doc__.startswith("WACHTA detectors")
```

```bash
cd /c/Users/grzan/wachta/src/python
uv python install 3.12
uv sync
```

- [ ] **Step 4: Front**

```bash
cd /c/Users/grzan/wachta
npm create vite@latest web -- --template react-ts
cd web
npm install
npm install maplibre-gl react-map-gl @deck.gl/react @deck.gl/core @deck.gl/layers @deck.gl/geo-layers h3-js @microsoft/signalr
npm install -D vitest
```
W `web/package.json` w `scripts` dodaj: `"test": "vitest run"`.

- [ ] **Step 5: Weryfikacja**

```bash
cd /c/Users/grzan/wachta/src/dotnet && dotnet build
cd /c/Users/grzan/wachta/src/python && uv run pytest -q
cd /c/Users/grzan/wachta/web && npm run build
```
Expected: `Build succeeded` (0 ostrzeżeń); `1 passed`; `built in ...`.

- [ ] **Step 6: Commit + push**

```bash
cd /c/Users/grzan/wachta
git add -A
git commit -F - <<'EOF'
chore: scaffold repository (dotnet, python, web)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
git remote add origin https://github.com/<login>/wachta.git
git push -u origin main
```

### Task 0.4: Baza danych, migracje, Docker Compose

**Files:**
- Create: `compose.yaml`, `infra/docker/dotnet.Dockerfile`
- Create: `src/dotnet/Wachta.Db/DbMigrator.cs`, `src/dotnet/Wachta.Db/Program.cs` (nadpisz)
- Create: `src/dotnet/Wachta.Db/Scripts/0001_extensions.sql`, `0002_sources.sql`, `0003_aircraft.sql`, `0004_detectors.sql`
- Modify: `src/dotnet/Wachta.Db/Wachta.Db.csproj`
- Test: `src/dotnet/Wachta.Tests/PostgresFixture.cs`, `src/dotnet/Wachta.Tests/DbMigratorTests.cs`

**Interfaces:**
- Produces: `Wachta.Db.DbMigrator.Migrate(string connectionString)`; tabele `source`, `fetch_log`, `aircraft_position` (hypertable), `alert`, `jamming_cell`, `coverage_hourly`; `Wachta.Tests.PostgresFixture` z właściwością `ConnectionString` (baza po migracji).

- [ ] **Step 1: Test (failing)**

`src/dotnet/Wachta.Tests/PostgresFixture.cs`:
```csharp
using Testcontainers.PostgreSql;
using Wachta.Db;

namespace Wachta.Tests;

public sealed class PostgresFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _container = new PostgreSqlBuilder()
        .WithImage("timescale/timescaledb-ha:pg17")
        .WithDatabase("wachta")
        .WithUsername("postgres")
        .WithPassword("postgres")
        .Build();

    public string ConnectionString => _container.GetConnectionString();

    public async Task InitializeAsync()
    {
        await _container.StartAsync();
        DbMigrator.Migrate(ConnectionString);
    }

    public Task DisposeAsync() => _container.DisposeAsync().AsTask();
}

[CollectionDefinition("postgres")]
public sealed class PostgresCollection : ICollectionFixture<PostgresFixture>;
```

`src/dotnet/Wachta.Tests/DbMigratorTests.cs`:
```csharp
using Npgsql;

namespace Wachta.Tests;

[Collection("postgres")]
public sealed class DbMigratorTests(PostgresFixture db)
{
    [Theory]
    [InlineData("source")]
    [InlineData("fetch_log")]
    [InlineData("aircraft_position")]
    [InlineData("alert")]
    [InlineData("jamming_cell")]
    [InlineData("coverage_hourly")]
    public async Task Migration_creates_table(string table)
    {
        await using var conn = new NpgsqlConnection(db.ConnectionString);
        await conn.OpenAsync();
        await using var cmd = new NpgsqlCommand("SELECT to_regclass(@t) IS NOT NULL", conn);
        cmd.Parameters.AddWithValue("t", table);
        Assert.True((bool)(await cmd.ExecuteScalarAsync())!);
    }

    [Fact]
    public async Task Aircraft_position_is_hypertable()
    {
        await using var conn = new NpgsqlConnection(db.ConnectionString);
        await conn.OpenAsync();
        await using var cmd = new NpgsqlCommand(
            "SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'aircraft_position'", conn);
        Assert.Equal(1L, (long)(await cmd.ExecuteScalarAsync())!);
    }

    [Fact]
    public void Migration_is_idempotent()
    {
        Wachta.Db.DbMigrator.Migrate(db.ConnectionString);
    }
}
```

Dodaj do testów pakiet Npgsql: `dotnet add Wachta.Tests package Npgsql`.

Uwaga: nowsze wersje Testcontainers oznaczają bezparametrowy `new PostgreSqlBuilder()` jako przestarzały — przy `TreatWarningsAsErrors` to błąd kompilacji. Wtedy użyj `new PostgreSqlBuilder("timescale/timescaledb-ha:pg17")` i usuń `.WithImage(...)`.

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/dotnet && dotnet test --filter DbMigratorTests`
Expected: FAIL (błąd kompilacji: `DbMigrator` nie istnieje).

- [ ] **Step 3: Implementacja**

```bash
cd src/dotnet
dotnet add Wachta.Db package dbup-postgresql
dotnet add Wachta.Db package Npgsql
```

`src/dotnet/Wachta.Db/Wachta.Db.csproj` — dodaj:
```xml
<ItemGroup>
  <EmbeddedResource Include="Scripts\*.sql" />
</ItemGroup>
```

`src/dotnet/Wachta.Db/DbMigrator.cs`:
```csharp
using DbUp;

namespace Wachta.Db;

public static class DbMigrator
{
    public static void Migrate(string connectionString)
    {
        var result = DeployChanges.To
            .PostgresqlDatabase(connectionString)
            .WithScriptsEmbeddedInAssembly(typeof(DbMigrator).Assembly)
            .LogToConsole()
            .Build()
            .PerformUpgrade();

        if (!result.Successful)
        {
            throw new InvalidOperationException("Database migration failed", result.Error);
        }
    }
}
```

`src/dotnet/Wachta.Db/Program.cs`:
```csharp
using Wachta.Db;

var cs = Environment.GetEnvironmentVariable("ConnectionStrings__Wachta")
    ?? throw new InvalidOperationException("ConnectionStrings__Wachta is not set");
DbMigrator.Migrate(cs);
Console.WriteLine("Migrations applied.");
```

`src/dotnet/Wachta.Db/Scripts/0001_extensions.sql`:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
```

`src/dotnet/Wachta.Db/Scripts/0002_sources.sql`:
```sql
CREATE TABLE source (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    url         text NOT NULL,
    license     text NOT NULL,
    trust_tier  smallint NOT NULL CHECK (trust_tier BETWEEN 1 AND 5),
    attribution text NOT NULL
);

INSERT INTO source (id, name, url, license, trust_tier, attribution) VALUES
  ('adsblol-mil',     'adsb.lol — military (global)', 'https://api.adsb.lol/v2/mil',               'ODbL 1.0', 1, 'Data: adsb.lol contributors (ODbL)'),
  ('adsblol-baltic-s','adsb.lol — Baltic south',      'https://api.adsb.lol/v2/point/55.0/20.0/250','ODbL 1.0', 1, 'Data: adsb.lol contributors (ODbL)'),
  ('adsblol-baltic-n','adsb.lol — Baltic north',      'https://api.adsb.lol/v2/point/60.0/24.0/250','ODbL 1.0', 1, 'Data: adsb.lol contributors (ODbL)');
```

`src/dotnet/Wachta.Db/Scripts/0003_aircraft.sql`:
```sql
CREATE TABLE fetch_log (
    id           bigserial PRIMARY KEY,
    source_id    text NOT NULL REFERENCES source(id),
    url          text NOT NULL,
    fetched_at   timestamptz NOT NULL,
    content_hash text NOT NULL,
    n_received   integer NOT NULL,
    n_written    integer NOT NULL
);
CREATE INDEX fetch_log_source_time ON fetch_log (source_id, fetched_at DESC);

CREATE TABLE aircraft_position (
    ts          timestamptz NOT NULL,
    hex         text NOT NULL,
    flight      text,
    type_code   text,
    is_military boolean NOT NULL,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    alt_baro_ft integer,
    on_ground   boolean NOT NULL,
    gs_kt       real,
    track_deg   real,
    nic         smallint,
    nac_p       smallint,
    source_id   text NOT NULL REFERENCES source(id),
    fetched_at  timestamptz NOT NULL
);
SELECT create_hypertable('aircraft_position', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX aircraft_position_hex_ts ON aircraft_position (hex, ts DESC);
ALTER TABLE aircraft_position SET (timescaledb.compress, timescaledb.compress_segmentby = 'hex');
SELECT add_compression_policy('aircraft_position', INTERVAL '1 day');
SELECT add_retention_policy('aircraft_position', INTERVAL '7 days');

-- One row per aircraft: when did we last hear it at all, and when did it last report a position.
-- Small table (thousands of rows), upserted on every fetch. D1 needs "silent", not "no position".
CREATE TABLE aircraft_contact (
    hex              text PRIMARY KEY,
    last_message_at  timestamptz NOT NULL,
    last_position_at timestamptz,
    source_id        text NOT NULL REFERENCES source(id),
    updated_at       timestamptz NOT NULL
);
CREATE INDEX aircraft_contact_last_message ON aircraft_contact (last_message_at DESC);
```

`src/dotnet/Wachta.Db/Scripts/0004_detectors.sql`:
```sql
CREATE TABLE alert (
    id          bigserial PRIMARY KEY,
    detector    text NOT NULL,
    entity_id   text NOT NULL,
    started_at  timestamptz NOT NULL,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    score       real NOT NULL,
    evidence    jsonb NOT NULL,
    state       text NOT NULL DEFAULT 'new' CHECK (state IN ('new','triaged','confirmed','dismissed')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (detector, entity_id, started_at)
);
CREATE INDEX alert_created ON alert (created_at DESC);

CREATE TABLE jamming_cell (
    hour        timestamptz NOT NULL,
    h3          text NOT NULL,
    n_aircraft  integer NOT NULL,
    n_degraded  integer NOT NULL,
    PRIMARY KEY (hour, h3)
);

CREATE TABLE coverage_hourly (
    hour      timestamptz NOT NULL,
    h3        text NOT NULL,
    n_reports integer NOT NULL,
    PRIMARY KEY (hour, h3)
);

-- Frozen D1 inputs for EVERY aircraft that went silent, including those the rules rejected.
-- Without the rejected ones recall cannot be measured: the detector would be graded on its own output.
CREATE TABLE d1_sample (
    hex          text NOT NULL,
    evaluated_at timestamptz NOT NULL,
    alerted      boolean NOT NULL,
    inputs       jsonb NOT NULL,
    PRIMARY KEY (hex, evaluated_at)
);
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `cd src/dotnet && dotnet test --filter DbMigratorTests`
Expected: PASS (8 testów). Pierwsze uruchomienie pobiera obraz (~1 GB).

Dopisz też do testu `DbMigratorTests` przypadek `[InlineData("aircraft_contact")]`.

- [ ] **Step 5: Docker Compose (baza + migrator)**

`infra/docker/dotnet.Dockerfile`:
```dockerfile
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
ARG PROJECT
WORKDIR /src
COPY src/dotnet/ .
RUN dotnet publish ${PROJECT}/${PROJECT}.csproj -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:10.0
ARG PROJECT
ENV APP_DLL=${PROJECT}.dll
WORKDIR /app
COPY --from=build /app .
ENTRYPOINT ["sh", "-c", "exec dotnet $APP_DLL"]
```

`compose.yaml`:
```yaml
name: wachta

x-db-env: &db-env
  ConnectionStrings__Wachta: Host=db;Database=wachta;Username=postgres;Password=${POSTGRES_PASSWORD}

services:
  db:
    image: timescale/timescaledb-ha:pg17
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: wachta
    ports: ["5432:5432"]
    volumes: [dbdata:/home/postgres/pgdata]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d wachta"]
      interval: 5s
      retries: 30

  migrator:
    build: { context: ., dockerfile: infra/docker/dotnet.Dockerfile, args: { PROJECT: Wachta.Db } }
    environment: *db-env
    depends_on: { db: { condition: service_healthy } }

volumes:
  dbdata: {}
```

- [ ] **Step 6: Weryfikacja ręczna**

```bash
cd /c/Users/grzan/wachta
docker compose up -d db
docker compose run --rm migrator
docker compose exec db psql -U postgres -d wachta -c "\dt"
```
Expected: `Migrations applied.`; lista zawiera 6 tabel.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -F - <<'EOF'
feat(db): timescale schema with dbup migrations and compose

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 0.5: Azure Pipelines

**Files:**
- Create: `azure-pipelines.yml`

**Interfaces:** Consumes: projekty z Task 0.3. Produces: stage'e `Test` (joby `dotnet`, `python`, `web`); w Task 1.15 dochodzi stage `Eval`.

- [ ] **Step 1: Pipeline**

`azure-pipelines.yml`:
```yaml
trigger:
  branches: { include: [main] }
pr:
  branches: { include: [main] }

pool:
  vmImage: ubuntu-latest

stages:
  - stage: Test
    jobs:
      - job: dotnet
        steps:
          - task: UseDotNet@2
            inputs: { packageType: sdk, version: 10.0.x }
          - script: dotnet test src/dotnet/Wachta.sln -c Release --logger trx --results-directory $(Agent.TempDirectory)/tr
            displayName: dotnet test
          - task: PublishTestResults@2
            condition: always()
            inputs: { testResultsFormat: VSTest, testResultsFiles: '$(Agent.TempDirectory)/tr/*.trx' }

      - job: python
        steps:
          - script: curl -LsSf https://astral.sh/uv/install.sh | sh
            displayName: install uv
          - script: |
              export PATH="$HOME/.local/bin:$PATH"
              cd src/python
              uv sync
              uv run pytest -q --junitxml=$(Agent.TempDirectory)/pytest.xml
            displayName: pytest
          - task: PublishTestResults@2
            condition: always()
            inputs: { testResultsFormat: JUnit, testResultsFiles: '$(Agent.TempDirectory)/pytest.xml' }

      - job: web
        steps:
          - task: NodeTool@0
            inputs: { versionSpec: 22.x }
          - script: |
              cd web
              npm ci
              npm test
              npm run build
            displayName: web test + build
```

- [ ] **Step 2: Podpięcie (użytkownik, w przeglądarce)**
  Azure DevOps → projekt `wachta` → Pipelines → New pipeline → GitHub → wybierz repo → „Existing Azure Pipelines YAML file” → `/azure-pipelines.yml` → Run.
  Następnie GitHub → Settings → Branches → reguła dla `main`: wymagany status check z Azure Pipelines.

- [ ] **Step 3: Weryfikacja**
  Utwórz gałąź `chore/ci`, wypchnij, otwórz PR.
  Expected: status `wachta` zielony (3 joby). Uwaga: `npm test` bez testów zwróci błąd „No test files found” — w tym zadaniu dodaj `web/src/smoke.test.ts`:

```ts
import { describe, expect, it } from "vitest";

describe("smoke", () => {
  it("runs", () => expect(1 + 1).toBe(2));
});
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -F - <<'EOF'
ci: azure pipelines for dotnet, python and web

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 0.6: Testy wykonalności w repo + SOURCES.md

**Files:**
- Create: `eval/feasibility/probe_sources.py` (skopiuj `probe.py` + `probe2.py` z katalogu roboczego sesji z 22.09 i połącz), `eval/feasibility/probe_llm.py`
- Create: `eval/feasibility/probe_keyed.py`
- Create: `docs/SOURCES.md`

**Interfaces:** Produces: `docs/SOURCES.md` — tabela „źródło | status | data sprawdzenia | limit | uwagi” (czytana w F2+ przy dodawaniu konektorów).

- [ ] **Step 1: Skrypt dla źródeł z kluczem**

`eval/feasibility/probe_keyed.py`:
```python
"""Checks keyed sources using values from .env. Prints status only, never the keys."""
import os
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
env = dict(l.split("=", 1) for l in Path(".env").read_text().splitlines() if "=" in l and not l.startswith("#"))


def report(name, ok, detail):
    print(f"{'OK ' if ok else 'ERR'} {name}: {detail}")


def opensky():
    tok = requests.post(
        "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
        data={"grant_type": "client_credentials", "client_id": env["OPENSKY_CLIENT_ID"], "client_secret": env["OPENSKY_CLIENT_SECRET"]},
        timeout=30,
    )
    if not tok.ok:
        return report("OpenSky token", False, tok.status_code)
    r = requests.get("https://opensky-network.org/api/states/all", params={"lamin": 53.5, "lomin": 9, "lamax": 60, "lomax": 30},
                     headers={"Authorization": f"Bearer {tok.json()['access_token']}"}, timeout=30)
    report("OpenSky states", r.ok, f"HTTP {r.status_code}, {len((r.json() or {}).get('states') or []) if r.ok else 0} aircraft")


def firms():
    r = requests.get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{env['FIRMS_MAP_KEY']}/VIIRS_SNPP_NRT/22,44,40,53/1", timeout=60)
    report("NASA FIRMS", r.ok and not r.text.startswith("Invalid"), f"HTTP {r.status_code}, {max(0, r.text.count(chr(10)) - 1)} hotspots (Ukraine bbox, 1 day)")


def gfw():
    r = requests.get("https://gateway.api.globalfishingwatch.org/v3/vessels/search",
                     params={"query": "EAGLE S", "datasets[0]": "public-global-vessel-identity:latest"},
                     headers={"Authorization": f"Bearer {env['GFW_TOKEN']}"}, timeout=60)
    report("GFW vessels", r.ok, f"HTTP {r.status_code}")


def aisstream():
    import asyncio
    import json

    import websockets

    async def run():
        async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
            await ws.send(json.dumps({"APIKey": env["AISSTREAM_API_KEY"], "BoundingBoxes": [[[53.5, 9.0], [57.0, 22.0]]]}))
            n, t = 0, time.time()
            while time.time() - t < 20:
                await asyncio.wait_for(ws.recv(), timeout=20)
                n += 1
            return n

    n = asyncio.run(run())
    report("AISStream (south Baltic, 20 s)", n > 0, f"{n} messages")


for check in (opensky, firms, gfw, aisstream):
    try:
        check()
    except Exception as e:  # probe script: report and continue
        report(check.__name__, False, repr(e)[:120])
```

- [ ] **Step 2: Uruchom**

```bash
cd /c/Users/grzan/wachta
uv run --with requests --with websockets python eval/feasibility/probe_keyed.py
uv run --with requests python eval/feasibility/probe_sources.py
```
Expected: `OK` dla każdego źródła, do którego masz klucz. Każdy `ERR` → wpis w SOURCES.md z przyczyną.

- [ ] **Step 3: `docs/SOURCES.md`** — tabela ze statusem każdego źródła z PLAN.md §3a (data, wynik, limit, uwaga). Zacznij od wyników z PLAN.md §17 i dopisz wyniki z Step 2.

- [ ] **Step 4: Commit**

```bash
git add eval/feasibility docs/SOURCES.md
git commit -F - <<'EOF'
docs: feasibility probes and source status

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 0.7: Makieta UI (Figma)

**Files:** brak w repo; link do pliku Figma w `docs/SOURCES.md` → sekcja „Projekt UI”.

- [ ] **Step 1:** Załaduj skill `figma-use`, utwórz nowy plik `WACHTA — UI`, jedna ramka 1440×900: mapa na całym ekranie (ciemny motyw), lewy panel 360 px „Alarmy” (lista: typ, znacznik czasu, callsign, wynik), dolna belka „Suwak czasu” (6 h), prawy dolny róg „Źródła” (atrybucje), legenda heksów GPS (niski < 2%, średni 2–10%, wysoki > 10%).
- [ ] **Step 2:** Pokaż użytkownikowi zrzut; poprawki do akceptacji.
- [ ] **Step 3:** Wpisz link do `docs/SOURCES.md`, commit `docs: link ui mockup`.

---

## F1 — Warstwa powietrzna

### Task 1.1: Model domeny + parser ADS-B v2

**Files:**
- Create: `src/dotnet/Wachta.Domain/AircraftObservation.cs`, `SourceSnapshot.cs`, `IAircraftSource.cs`
- Create: `src/dotnet/Wachta.Ingestion/AdsbV2Parser.cs`
- Test: `src/dotnet/Wachta.Tests/Fixtures/adsb_v2_sample.json`, `src/dotnet/Wachta.Tests/AdsbV2ParserTests.cs`

**Interfaces:**
- Produces:
  - `record AircraftObservation(string Hex, string? Flight, string? TypeCode, bool IsMilitary, double Lat, double Lon, int? AltBaroFt, bool OnGround, float? GroundSpeedKt, float? TrackDeg, short? Nic, short? NacP, DateTimeOffset Timestamp)`
  - `record AircraftContact(string Hex, DateTimeOffset LastMessageAt, DateTimeOffset? LastPositionAt)` — **każdy** samolot w odpowiedzi, także bez pozycji
  - `record ParseResult(IReadOnlyList<AircraftObservation> Aircraft, IReadOnlyList<AircraftContact> Contacts)`
  - `record SourceSnapshot(string SourceId, Uri Url, DateTimeOffset FetchedAt, string ContentHash, IReadOnlyList<AircraftObservation> Aircraft, IReadOnlyList<AircraftContact> Contacts)`
  - `interface IAircraftSource { string Id { get; } Task<SourceSnapshot> FetchAsync(CancellationToken ct); }`
  - `static ParseResult AdsbV2Parser.Parse(string json, DateTimeOffset fetchedAt, bool forceMilitary = false, double maxPositionAgeSeconds = 30)`

**Dlaczego kontakty (ustalenie z przeglądu Codeksa):** w ADS-B `seen_pos` to wiek **pozycji**, a `seen` to wiek **ostatniej wiadomości**. Samolot z zakłóconym GPS przestaje nadawać pozycję, ale nadal nadaje — bez rozróżnienia D1 zgłaszałby każdy taki przypadek jako „zgaszony transponder”, a nad Bałtykiem byłby to najczęstszy fałszywy alarm. Czas obserwacji liczymy od `now` z odpowiedzi (czas źródła), nie od czasu pobrania — inaczej ten sam payload pobrany dwa razy tworzy dwie różne obserwacje i zawyża pokrycie oraz `n_points`.

- [ ] **Step 1: Fixture**

`src/dotnet/Wachta.Tests/Fixtures/adsb_v2_sample.json`:
```json
{
  "now": 1790078400000,
  "ac": [
    { "hex": "43C6F1", "flight": "RRR2302 ", "t": "A332", "dbFlags": 1, "lat": 54.9, "lon": 19.8, "seen": 0.3,
      "alt_baro": 27000, "gs": 410.5, "track": 92.1, "nic": 8, "nac_p": 9, "seen_pos": 1.2 },
    { "hex": "48ad01", "flight": "LOT3AB  ", "t": "B38M", "dbFlags": 0, "lat": 54.37, "lon": 18.47,
      "alt_baro": "ground", "gs": 12.0, "track": 290.0, "nic": 8, "nac_p": 10, "seen_pos": 0.4 },
    { "hex": "4b1815", "flight": "", "t": "A320", "lat": 55.2, "lon": 20.4,
      "alt_baro": 36000, "gs": 450, "track": 45, "nic": 0, "nac_p": 0, "seen_pos": 95.0 },
    { "hex": "4ca7b2", "flight": "RYR1XY", "t": "B738", "alt_baro": 38000, "seen": 3.0 },
    { "hex": "ae1234", "t": "K35R", "lat": 55.5, "lon": 17.0, "alt_baro": 24000.0, "seen_pos": 0 }
  ]
}
```

- [ ] **Step 2: Test (failing)**

W `Wachta.Tests.csproj` dodaj:
```xml
<ItemGroup>
  <None Update="Fixtures\**" CopyToOutputDirectory="PreserveNewest" />
</ItemGroup>
```

`src/dotnet/Wachta.Tests/AdsbV2ParserTests.cs`:
```csharp
using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class AdsbV2ParserTests
{
    private static readonly DateTimeOffset FetchedAt = new(2026, 9, 22, 12, 0, 0, TimeSpan.Zero);
    private static string Sample() => File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "adsb_v2_sample.json"));

    [Fact]
    public void Skips_aircraft_without_position_and_with_stale_position()
    {
        var result = AdsbV2Parser.Parse(Sample(), FetchedAt).Aircraft;
        Assert.Equal(new[] { "43c6f1", "48ad01", "ae1234" }, result.Select(a => a.Hex));
    }

    [Fact]
    public void Contacts_cover_every_aircraft_including_those_without_position()
    {
        var contacts = AdsbV2Parser.Parse(Sample(), FetchedAt).Contacts;
        Assert.Equal(5, contacts.Count);

        // still transmitting (seen 3 s) but no position at all -> contact without LastPositionAt
        var noPosition = Assert.Single(contacts, c => c.Hex == "4ca7b2");
        Assert.Equal(FetchedAt.AddSeconds(-3), noPosition.LastMessageAt);
        Assert.Null(noPosition.LastPositionAt);

        // stale position (95 s) but message age unknown -> message age falls back to position age
        var stalePosition = Assert.Single(contacts, c => c.Hex == "4b1815");
        Assert.Equal(FetchedAt.AddSeconds(-95), stalePosition.LastPositionAt);
    }

    [Fact]
    public void Timestamps_come_from_source_clock_not_fetch_time()
    {
        // Same payload fetched 40 s later must yield the same observation timestamps (dedup relies on it).
        var first = AdsbV2Parser.Parse(Sample(), FetchedAt).Aircraft[0];
        var second = AdsbV2Parser.Parse(Sample(), FetchedAt.AddSeconds(40), maxPositionAgeSeconds: 120).Aircraft[0];
        Assert.Equal(first.Timestamp, second.Timestamp);
    }

    [Fact]
    public void Stale_payload_is_rejected_by_position_age_against_fetch_time()
    {
        Assert.Empty(AdsbV2Parser.Parse(Sample(), FetchedAt.AddMinutes(5)).Aircraft);
    }

    [Fact]
    public void Maps_fields_of_airborne_military_aircraft()
    {
        var a = AdsbV2Parser.Parse(Sample(), FetchedAt).Aircraft[0];
        Assert.Equal("RRR2302", a.Flight);
        Assert.Equal("A332", a.TypeCode);
        Assert.True(a.IsMilitary);
        Assert.Equal(27000, a.AltBaroFt);
        Assert.False(a.OnGround);
        Assert.Equal(410.5f, a.GroundSpeedKt);
        Assert.Equal((short)8, a.Nic);
        Assert.Equal((short)9, a.NacP);
        Assert.Equal(FetchedAt.AddSeconds(-1.2), a.Timestamp);
    }

    [Fact]
    public void Ground_aircraft_has_no_altitude_and_is_not_military()
    {
        var a = AdsbV2Parser.Parse(Sample(), FetchedAt).Aircraft[1];
        Assert.True(a.OnGround);
        Assert.Null(a.AltBaroFt);
        Assert.False(a.IsMilitary);
    }

    [Fact]
    public void Force_military_marks_all_and_fractional_altitude_is_rounded()
    {
        var result = AdsbV2Parser.Parse(Sample(), FetchedAt, forceMilitary: true).Aircraft;
        Assert.All(result, a => Assert.True(a.IsMilitary));
        Assert.Equal(24000, result[2].AltBaroFt);
        Assert.Null(result[2].Flight);
    }

    [Fact]
    public void Empty_or_missing_ac_array_returns_empty_lists()
    {
        Assert.Empty(AdsbV2Parser.Parse("{\"now\":1790078400000}", FetchedAt).Aircraft);
        Assert.Empty(AdsbV2Parser.Parse("{\"now\":1790078400000,\"ac\":[]}", FetchedAt).Contacts);
    }
}
```

- [ ] **Step 3: Uruchom — ma nie przejść**

Run: `cd src/dotnet && dotnet test --filter AdsbV2ParserTests`
Expected: FAIL (kompilacja: brak `AdsbV2Parser`).

- [ ] **Step 4: Implementacja**

`src/dotnet/Wachta.Domain/AircraftObservation.cs`:
```csharp
namespace Wachta.Domain;

public sealed record AircraftObservation(
    string Hex,
    string? Flight,
    string? TypeCode,
    bool IsMilitary,
    double Lat,
    double Lon,
    int? AltBaroFt,
    bool OnGround,
    float? GroundSpeedKt,
    float? TrackDeg,
    short? Nic,
    short? NacP,
    DateTimeOffset Timestamp);
```

`src/dotnet/Wachta.Domain/SourceSnapshot.cs`:
```csharp
namespace Wachta.Domain;

/// <summary>Last time we heard an aircraft at all (message), and last time it reported a position.</summary>
public sealed record AircraftContact(string Hex, DateTimeOffset LastMessageAt, DateTimeOffset? LastPositionAt);

public sealed record ParseResult(
    IReadOnlyList<AircraftObservation> Aircraft,
    IReadOnlyList<AircraftContact> Contacts);

/// <summary>One fetch from one source, with provenance (who, when, from where, content hash).</summary>
public sealed record SourceSnapshot(
    string SourceId,
    Uri Url,
    DateTimeOffset FetchedAt,
    string ContentHash,
    IReadOnlyList<AircraftObservation> Aircraft,
    IReadOnlyList<AircraftContact> Contacts);
```

`src/dotnet/Wachta.Domain/IAircraftSource.cs`:
```csharp
namespace Wachta.Domain;

public interface IAircraftSource
{
    string Id { get; }
    Task<SourceSnapshot> FetchAsync(CancellationToken ct);
}
```

`src/dotnet/Wachta.Ingestion/AdsbV2Parser.cs`:
```csharp
using System.Text.Json;
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Parses the ADSBExchange-v2-compatible JSON returned by adsb.lol (and airplanes.live).</summary>
public static class AdsbV2Parser
{
    private const int MilitaryDbFlag = 1;

    public static ParseResult Parse(
        string json, DateTimeOffset fetchedAt, bool forceMilitary = false, double maxPositionAgeSeconds = 30)
    {
        using var doc = JsonDocument.Parse(json);
        var result = new List<AircraftObservation>();
        var contacts = new List<AircraftContact>();
        if (!doc.RootElement.TryGetProperty("ac", out var ac) || ac.ValueKind != JsonValueKind.Array)
        {
            return new ParseResult(result, contacts);
        }

        // Source clock: the same payload fetched twice must produce identical timestamps.
        var sourceNow = GetDouble(doc.RootElement, "now") is { } nowMs
            ? DateTimeOffset.FromUnixTimeMilliseconds((long)nowMs)
            : fetchedAt;

        foreach (var a in ac.EnumerateArray())
        {
            if (!a.TryGetProperty("hex", out var hexEl) || hexEl.GetString() is not { Length: > 0 } rawHex)
            {
                continue;
            }

            var hex = rawHex.Trim().ToLowerInvariant();
            var lat = GetDouble(a, "lat");
            var lon = GetDouble(a, "lon");
            var seenPos = GetDouble(a, "seen_pos");
            var hasPosition = lat is not null && lon is not null;
            var positionTime = hasPosition ? sourceNow.AddSeconds(-(seenPos ?? 0)) : (DateTimeOffset?)null;

            // "seen" = age of the last message of any kind; without it fall back to the position age.
            var seenMessage = GetDouble(a, "seen") ?? seenPos ?? 0;
            contacts.Add(new AircraftContact(hex, sourceNow.AddSeconds(-seenMessage), positionTime));

            if (!hasPosition || fetchedAt - positionTime!.Value > TimeSpan.FromSeconds(maxPositionAgeSeconds))
            {
                continue;
            }

            var onGround = a.TryGetProperty("alt_baro", out var alt)
                && alt.ValueKind == JsonValueKind.String
                && alt.GetString() == "ground";
            int? altFt = alt.ValueKind == JsonValueKind.Number ? (int)Math.Round(alt.GetDouble()) : null;
            var flight = GetString(a, "flight")?.Trim();

            result.Add(new AircraftObservation(
                Hex: hex,
                Flight: string.IsNullOrEmpty(flight) ? null : flight,
                TypeCode: GetString(a, "t"),
                IsMilitary: forceMilitary || ((int)(GetDouble(a, "dbFlags") ?? 0) & MilitaryDbFlag) != 0,
                Lat: lat.Value,
                Lon: lon.Value,
                AltBaroFt: onGround ? null : altFt,
                OnGround: onGround,
                GroundSpeedKt: (float?)GetDouble(a, "gs"),
                TrackDeg: (float?)GetDouble(a, "track"),
                Nic: (short?)GetDouble(a, "nic"),
                NacP: (short?)GetDouble(a, "nac_p"),
                Timestamp: positionTime.Value));
        }

        return new ParseResult(result, contacts);
    }

    private static double? GetDouble(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;

    private static string? GetString(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
}
```

- [ ] **Step 5: Uruchom — ma przejść**

Run: `cd src/dotnet && dotnet test --filter AdsbV2ParserTests`
Expected: PASS (5 testów).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -F - <<'EOF'
feat(ingestion): aircraft domain model and adsb v2 parser

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 1.2: Źródło adsb.lol, dekorator limitu, fabryka źródeł [R]

**Files:**
- Create: `src/dotnet/Wachta.Ingestion/AdsbLolSource.cs`, `ThrottledAircraftSource.cs`, `SourceOptions.cs`, `SourceFactory.cs`
- Test: `src/dotnet/Wachta.Tests/ThrottledAircraftSourceTests.cs`, `src/dotnet/Wachta.Tests/SourceFactoryTests.cs`

**Interfaces:**
- Consumes: `IAircraftSource`, `SourceSnapshot`, `AdsbV2Parser.Parse` (Task 1.1).
- Produces:
  - `sealed class AdsbLolSource(HttpClient http, string id, Uri url, bool forceMilitary, TimeProvider clock) : IAircraftSource`
  - `sealed class ThrottledAircraftSource(IAircraftSource inner, TimeSpan minInterval, TimeProvider clock) : IAircraftSource`
  - `sealed class SourceOptions { string Id; string Kind; string Url; bool ForceMilitary; int IntervalSeconds }`
  - `sealed class SourceFactory(IHttpClientFactory httpFactory, TimeProvider clock) { IAircraftSource Create(SourceOptions o); }` — rzuca `NotSupportedException` dla nieznanego `Kind`; wynik zawsze opakowany w `ThrottledAircraftSource`.

- [ ] **Step 1: Testy (failing)**

`src/dotnet/Wachta.Tests/ThrottledAircraftSourceTests.cs`:
```csharp
using Microsoft.Extensions.Time.Testing;
using Wachta.Domain;
using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class ThrottledAircraftSourceTests
{
    private sealed class CountingSource : IAircraftSource
    {
        public int Calls;
        public string Id => "fake";
        public Task<SourceSnapshot> FetchAsync(CancellationToken ct)
        {
            Calls++;
            return Task.FromResult(new SourceSnapshot("fake", new Uri("https://x"), DateTimeOffset.UnixEpoch, "h", [], []));
        }
    }

    [Fact]
    public async Task First_call_is_immediate()
    {
        var inner = new CountingSource();
        var sut = new ThrottledAircraftSource(inner, TimeSpan.FromSeconds(15), new FakeTimeProvider());
        await sut.FetchAsync(CancellationToken.None);
        Assert.Equal(1, inner.Calls);
    }

    [Fact]
    public async Task Second_call_waits_for_min_interval()
    {
        var clock = new FakeTimeProvider();
        var inner = new CountingSource();
        var sut = new ThrottledAircraftSource(inner, TimeSpan.FromSeconds(15), clock);
        await sut.FetchAsync(CancellationToken.None);

        var second = sut.FetchAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(14));
        Assert.False(second.IsCompleted);

        clock.Advance(TimeSpan.FromSeconds(1));
        await second;
        Assert.Equal(2, inner.Calls);
    }

    [Fact]
    public async Task No_wait_when_interval_already_passed()
    {
        var clock = new FakeTimeProvider();
        var inner = new CountingSource();
        var sut = new ThrottledAircraftSource(inner, TimeSpan.FromSeconds(15), clock);
        await sut.FetchAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(20));
        var second = sut.FetchAsync(CancellationToken.None);
        Assert.True(second.IsCompleted);
        await second;
    }

    [Fact]
    public async Task Start_delay_offsets_the_first_call()
    {
        var clock = new FakeTimeProvider();
        var inner = new CountingSource();
        var sut = new ThrottledAircraftSource(inner, TimeSpan.FromSeconds(15), clock, TimeSpan.FromSeconds(10));

        var first = sut.FetchAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(9));
        Assert.Equal(0, inner.Calls);

        clock.Advance(TimeSpan.FromSeconds(1));
        await first;
        Assert.Equal(1, inner.Calls);
    }

    [Fact]
    public void Id_is_passed_through()
    {
        var sut = new ThrottledAircraftSource(new CountingSource(), TimeSpan.FromSeconds(1), new FakeTimeProvider());
        Assert.Equal("fake", sut.Id);
    }
}
```

`src/dotnet/Wachta.Tests/SourceFactoryTests.cs`:
```csharp
using Microsoft.Extensions.Time.Testing;
using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class SourceFactoryTests
{
    private sealed class StubHttpFactory : IHttpClientFactory
    {
        public HttpClient CreateClient(string name) => new();
    }

    private readonly SourceFactory _factory = new(new StubHttpFactory(), new FakeTimeProvider());

    [Fact]
    public void Creates_throttled_adsb_source_with_configured_id()
    {
        var source = _factory.Create(new SourceOptions
        {
            Id = "adsblol-mil", Kind = "adsb-v2", Url = "https://api.adsb.lol/v2/mil", ForceMilitary = true, IntervalSeconds = 15,
        });
        Assert.IsType<ThrottledAircraftSource>(source);
        Assert.Equal("adsblol-mil", source.Id);
    }

    [Fact]
    public void Unknown_kind_throws()
    {
        Assert.Throws<NotSupportedException>(() =>
            _factory.Create(new SourceOptions { Id = "x", Kind = "carrier-pigeon", Url = "https://x", IntervalSeconds = 15 }));
    }

    [Fact]
    public void Interval_below_15_seconds_is_rejected()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            _factory.Create(new SourceOptions { Id = "x", Kind = "adsb-v2", Url = "https://x", IntervalSeconds = 5 }));
    }
}
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/dotnet && dotnet test --filter "ThrottledAircraftSourceTests|SourceFactoryTests"`
Expected: FAIL (kompilacja).

- [ ] **Step 3: Implementacja**

`dotnet add src/dotnet/Wachta.Tests package Microsoft.Extensions.Http` (dla `IHttpClientFactory` w testach) — w `Wachta.Ingestion` pakiet jest już przez szablon worker; jeśli nie: `dotnet add src/dotnet/Wachta.Ingestion package Microsoft.Extensions.Http`.

`src/dotnet/Wachta.Ingestion/AdsbLolSource.cs`:
```csharp
using System.Security.Cryptography;
using System.Text;
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Adapter: adsb.lol v2 endpoint -> common SourceSnapshot model.</summary>
public sealed class AdsbLolSource(HttpClient http, string id, Uri url, bool forceMilitary, TimeProvider clock) : IAircraftSource
{
    public string Id => id;

    public async Task<SourceSnapshot> FetchAsync(CancellationToken ct)
    {
        var body = await http.GetStringAsync(url, ct);
        var fetchedAt = clock.GetUtcNow();
        var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(body)));
        var parsed = AdsbV2Parser.Parse(body, fetchedAt, forceMilitary);
        return new SourceSnapshot(id, url, fetchedAt, hash, parsed.Aircraft, parsed.Contacts);
    }
}
```

`src/dotnet/Wachta.Ingestion/ThrottledAircraftSource.cs`:
```csharp
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Decorator: guarantees a minimum interval between calls to the wrapped source (API rate limits).</summary>
public sealed class ThrottledAircraftSource(
    IAircraftSource inner, TimeSpan minInterval, TimeProvider clock, TimeSpan startDelay = default) : IAircraftSource
{
    private DateTimeOffset? _lastCall;
    private bool _started;

    public string Id => inner.Id;

    public async Task<SourceSnapshot> FetchAsync(CancellationToken ct)
    {
        if (!_started)
        {
            _started = true;
            if (startDelay > TimeSpan.Zero)
            {
                await Task.Delay(startDelay, clock, ct);
            }
        }

        if (_lastCall is { } last)
        {
            var wait = last + minInterval - clock.GetUtcNow();
            if (wait > TimeSpan.Zero)
            {
                await Task.Delay(wait, clock, ct);
            }
        }

        _lastCall = clock.GetUtcNow();
        return await inner.FetchAsync(ct);
    }
}
```

`src/dotnet/Wachta.Ingestion/SourceOptions.cs`:
```csharp
namespace Wachta.Ingestion;

public sealed class SourceOptions
{
    public string Id { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Url { get; set; } = "";
    public bool ForceMilitary { get; set; }
    public int IntervalSeconds { get; set; } = 15;

    /// <summary>Staggers sources so they never fire together: simultaneous bursts are what adsb.lol answers with 429.</summary>
    public int StartDelaySeconds { get; set; }
}
```

`src/dotnet/Wachta.Ingestion/SourceFactory.cs`:
```csharp
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Factory: builds configured sources, always wrapped in the rate-limit decorator.</summary>
public sealed class SourceFactory(IHttpClientFactory httpFactory, TimeProvider clock)
{
    public const int MinIntervalSeconds = 15;

    public IAircraftSource Create(SourceOptions o)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(o.IntervalSeconds, MinIntervalSeconds, nameof(o.IntervalSeconds));

        IAircraftSource source = o.Kind switch
        {
            "adsb-v2" => new AdsbLolSource(httpFactory.CreateClient(o.Id), o.Id, new Uri(o.Url), o.ForceMilitary, clock),
            _ => throw new NotSupportedException($"Unknown source kind '{o.Kind}'"),
        };

        return new ThrottledAircraftSource(source, TimeSpan.FromSeconds(o.IntervalSeconds), clock,
            TimeSpan.FromSeconds(o.StartDelaySeconds));
    }
}
```

- [ ] **Step 4: Uruchom — ma przejść**

Run: `cd src/dotnet && dotnet test --filter "ThrottledAircraftSourceTests|SourceFactoryTests"`
Expected: PASS (7 testów).

- [ ] **Step 5: Commit** — `feat(ingestion): adsb.lol adapter, throttle decorator, source factory`.

### Task 1.3: Deduplikacja + zapis pozycji z rodowodem [R]

**Files:**
- Create: `src/dotnet/Wachta.Ingestion/PositionDeduplicator.cs`, `src/dotnet/Wachta.Ingestion/PositionWriter.cs`
- Test: `src/dotnet/Wachta.Tests/PositionDeduplicatorTests.cs`, `src/dotnet/Wachta.Tests/PositionWriterTests.cs`

**Interfaces:**
- Consumes: `SourceSnapshot`, `AircraftObservation` (1.1); `PostgresFixture` (0.4).
- Produces:
  - `sealed class PositionDeduplicator(TimeSpan? civilMinInterval = null) { IReadOnlyList<AircraftObservation> Filter(IReadOnlyList<AircraftObservation> batch); }` — przepuszcza pozycję tylko, jeśli jej `Timestamp` jest późniejszy niż ostatnio przepuszczona dla tego `Hex`; dla samolotów **niewojskowych** dodatkowo nie częściej niż raz na `civilMinInterval` (domyślnie 60 s — budżet danych ze spec).
  - `interface IPositionWriter { Task<int> WriteAsync(SourceSnapshot snapshot, IReadOnlyList<AircraftObservation> rows, CancellationToken ct); }` — zwraca liczbę zapisanych wierszy; zawsze dopisuje wiersz do `fetch_log` (także przy 0 wierszy) **i** upsertuje `snapshot.Contacts` do `aircraft_contact`.
  - `sealed class PositionWriter(NpgsqlDataSource db) : IPositionWriter`

- [ ] **Step 1: Testy (failing)**

`src/dotnet/Wachta.Tests/PositionDeduplicatorTests.cs`:
```csharp
using Wachta.Domain;
using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class PositionDeduplicatorTests
{
    private static readonly DateTimeOffset T0 = new(2026, 9, 22, 12, 0, 0, TimeSpan.Zero);

    private static AircraftObservation Obs(string hex, int secondsAfterT0, bool military = true) =>
        new(hex, null, null, military, 54, 18, 30000, false, 400, 90, 8, 9, T0.AddSeconds(secondsAfterT0));

    [Fact]
    public void Passes_new_aircraft()
    {
        var sut = new PositionDeduplicator();
        Assert.Equal(2, sut.Filter([Obs("a", 0), Obs("b", 0)]).Count);
    }

    [Fact]
    public void Drops_same_or_older_timestamp_for_same_aircraft_across_batches()
    {
        var sut = new PositionDeduplicator();
        sut.Filter([Obs("a", 10)]);
        Assert.Empty(sut.Filter([Obs("a", 10)]));
        Assert.Empty(sut.Filter([Obs("a", 5)]));
        Assert.Single(sut.Filter([Obs("a", 11)]));
    }

    [Fact]
    public void Drops_duplicates_within_one_batch()
    {
        var sut = new PositionDeduplicator();
        Assert.Single(sut.Filter([Obs("a", 10), Obs("a", 10)]));
    }

    [Fact]
    public void Civil_aircraft_are_sampled_once_per_minute_military_are_not()
    {
        var sut = new PositionDeduplicator();
        sut.Filter([Obs("civ", 0, military: false), Obs("mil", 0)]);

        Assert.Empty(sut.Filter([Obs("civ", 30, military: false)]));
        Assert.Single(sut.Filter([Obs("mil", 30)]));
        Assert.Single(sut.Filter([Obs("civ", 61, military: false)]));
    }
}
```

`src/dotnet/Wachta.Tests/PositionWriterTests.cs`:
```csharp
using Npgsql;
using Wachta.Domain;
using Wachta.Ingestion;

namespace Wachta.Tests;

[Collection("postgres")]
public sealed class PositionWriterTests(PostgresFixture db)
{
    [Fact]
    public async Task Writes_positions_and_fetch_log_with_provenance()
    {
        await using var ds = NpgsqlDataSource.Create(db.ConnectionString);
        var writer = new PositionWriter(ds);
        var fetchedAt = DateTimeOffset.UtcNow;
        var obs = new AircraftObservation("43c6f1", "RRR2302", "A332", true, 54.9, 19.8, 27000, false, 410.5f, 92.1f, 8, 9, fetchedAt.AddSeconds(-1));
        var nullable = obs with { Hex = "ae1234", Flight = null, AltBaroFt = null, Nic = null, NacP = null, GroundSpeedKt = null, TrackDeg = null };
        var contacts = new[]
        {
            new AircraftContact("43c6f1", fetchedAt.AddSeconds(-1), fetchedAt.AddSeconds(-1)),
            new AircraftContact("silent1", fetchedAt.AddSeconds(-4), null),
        };
        var snap = new SourceSnapshot("adsblol-mil", new Uri("https://api.adsb.lol/v2/mil"), fetchedAt, "abc123", [obs, nullable], contacts);

        var written = await writer.WriteAsync(snap, snap.Aircraft, CancellationToken.None);

        Assert.Equal(2, written);
        await using var conn = await ds.OpenConnectionAsync();
        await using var q1 = new NpgsqlCommand("SELECT count(*) FROM aircraft_position WHERE hex IN ('43c6f1','ae1234') AND source_id = 'adsblol-mil'", conn);
        Assert.Equal(2L, (long)(await q1.ExecuteScalarAsync())!);
        await using var q2 = new NpgsqlCommand("SELECT n_received, n_written FROM fetch_log WHERE content_hash = 'abc123'", conn);
        await using var r = await q2.ExecuteReaderAsync();
        Assert.True(await r.ReadAsync());
        Assert.Equal(2, r.GetInt32(0));
        Assert.Equal(2, r.GetInt32(1));
    }

    [Fact]
    public async Task Contacts_are_upserted_and_never_go_backwards()
    {
        await using var ds = NpgsqlDataSource.Create(db.ConnectionString);
        var writer = new PositionWriter(ds);
        var t0 = DateTimeOffset.UtcNow;
        var snapshot = (DateTimeOffset msg, DateTimeOffset? pos) => new SourceSnapshot(
            "adsblol-mil", new Uri("https://x"), t0, "c-hash", [], [new AircraftContact("con001", msg, pos)]);

        await writer.WriteAsync(snapshot(t0, t0), [], CancellationToken.None);
        await writer.WriteAsync(snapshot(t0.AddSeconds(-30), null), [], CancellationToken.None);

        await using var conn = await ds.OpenConnectionAsync();
        await using var q = new NpgsqlCommand("SELECT last_message_at, last_position_at FROM aircraft_contact WHERE hex = 'con001'", conn);
        await using var r = await q.ExecuteReaderAsync();
        Assert.True(await r.ReadAsync());
        Assert.Equal(t0.UtcDateTime, r.GetDateTime(0), TimeSpan.FromMilliseconds(1));
        Assert.False(await r.IsDBNullAsync(1));
    }

    [Fact]
    public async Task Empty_batch_still_logs_fetch()
    {
        await using var ds = NpgsqlDataSource.Create(db.ConnectionString);
        var snap = new SourceSnapshot("adsblol-baltic-s", new Uri("https://x"), DateTimeOffset.UtcNow, "empty-hash", [], []);
        Assert.Equal(0, await new PositionWriter(ds).WriteAsync(snap, [], CancellationToken.None));
        await using var conn = await ds.OpenConnectionAsync();
        await using var q = new NpgsqlCommand("SELECT count(*) FROM fetch_log WHERE content_hash = 'empty-hash'", conn);
        Assert.Equal(1L, (long)(await q.ExecuteScalarAsync())!);
    }
}
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/dotnet && dotnet test --filter "PositionDeduplicatorTests|PositionWriterTests"`
Expected: FAIL (kompilacja).

- [ ] **Step 3: Implementacja**

`dotnet add src/dotnet/Wachta.Ingestion package Npgsql.DependencyInjection` (zawiera Npgsql).

`src/dotnet/Wachta.Ingestion/PositionDeduplicator.cs`:
```csharp
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>
/// The same aircraft arrives from several overlapping sources; keep only strictly newer positions per hex.
/// Civil traffic is sampled down to one position per minute — full rate for everything would be ~40M rows/week.
/// </summary>
public sealed class PositionDeduplicator(TimeSpan? civilMinInterval = null)
{
    private readonly TimeSpan _civilMinInterval = civilMinInterval ?? TimeSpan.FromSeconds(60);
    private readonly Dictionary<string, DateTimeOffset> _lastByHex = new();

    public IReadOnlyList<AircraftObservation> Filter(IReadOnlyList<AircraftObservation> batch)
    {
        var accepted = new List<AircraftObservation>(batch.Count);
        foreach (var obs in batch)
        {
            if (_lastByHex.TryGetValue(obs.Hex, out var last)
                && (obs.Timestamp <= last || (!obs.IsMilitary && obs.Timestamp - last < _civilMinInterval)))
            {
                continue;
            }

            _lastByHex[obs.Hex] = obs.Timestamp;
            accepted.Add(obs);
        }

        return accepted;
    }
}
```

`src/dotnet/Wachta.Ingestion/PositionWriter.cs`:
```csharp
using Npgsql;
using NpgsqlTypes;
using Wachta.Domain;

namespace Wachta.Ingestion;

public interface IPositionWriter
{
    Task<int> WriteAsync(SourceSnapshot snapshot, IReadOnlyList<AircraftObservation> rows, CancellationToken ct);
}

/// <summary>Repository: writes positions with binary COPY (fast bulk insert) and one fetch_log row per fetch.</summary>
public sealed class PositionWriter(NpgsqlDataSource db) : IPositionWriter
{
    private const string CopySql =
        "COPY aircraft_position (ts, hex, flight, type_code, is_military, lat, lon, alt_baro_ft, on_ground, " +
        "gs_kt, track_deg, nic, nac_p, source_id, fetched_at) FROM STDIN (FORMAT BINARY)";

    public async Task<int> WriteAsync(SourceSnapshot snapshot, IReadOnlyList<AircraftObservation> rows, CancellationToken ct)
    {
        await using var conn = await db.OpenConnectionAsync(ct);
        await using var tx = await conn.BeginTransactionAsync(ct);

        if (rows.Count > 0)
        {
            await using var copy = await conn.BeginBinaryImportAsync(CopySql, ct);
            foreach (var r in rows)
            {
                await copy.StartRowAsync(ct);
                await copy.WriteAsync(r.Timestamp.UtcDateTime, NpgsqlDbType.TimestampTz, ct);
                await copy.WriteAsync(r.Hex, NpgsqlDbType.Text, ct);
                await WriteNullable(copy, r.Flight, NpgsqlDbType.Text, ct);
                await WriteNullable(copy, r.TypeCode, NpgsqlDbType.Text, ct);
                await copy.WriteAsync(r.IsMilitary, NpgsqlDbType.Boolean, ct);
                await copy.WriteAsync(r.Lat, NpgsqlDbType.Double, ct);
                await copy.WriteAsync(r.Lon, NpgsqlDbType.Double, ct);
                await WriteNullable(copy, r.AltBaroFt, NpgsqlDbType.Integer, ct);
                await copy.WriteAsync(r.OnGround, NpgsqlDbType.Boolean, ct);
                await WriteNullable(copy, r.GroundSpeedKt, NpgsqlDbType.Real, ct);
                await WriteNullable(copy, r.TrackDeg, NpgsqlDbType.Real, ct);
                await WriteNullable(copy, r.Nic, NpgsqlDbType.Smallint, ct);
                await WriteNullable(copy, r.NacP, NpgsqlDbType.Smallint, ct);
                await copy.WriteAsync(snapshot.SourceId, NpgsqlDbType.Text, ct);
                await copy.WriteAsync(snapshot.FetchedAt.UtcDateTime, NpgsqlDbType.TimestampTz, ct);
            }

            await copy.CompleteAsync(ct);
        }

        if (snapshot.Contacts.Count > 0)
        {
            await using var contacts = new NpgsqlCommand("""
                INSERT INTO aircraft_contact (hex, last_message_at, last_position_at, source_id, updated_at)
                SELECT h, m, p, @src, @upd FROM unnest(@hex, @msg, @pos) AS t(h, m, p)
                ON CONFLICT (hex) DO UPDATE SET
                    last_message_at  = GREATEST(aircraft_contact.last_message_at, EXCLUDED.last_message_at),
                    last_position_at = GREATEST(aircraft_contact.last_position_at, EXCLUDED.last_position_at),
                    source_id = EXCLUDED.source_id,
                    updated_at = EXCLUDED.updated_at
                """, conn, tx);
            contacts.Parameters.AddWithValue("hex", snapshot.Contacts.Select(c => c.Hex).ToArray());
            contacts.Parameters.AddWithValue("msg", snapshot.Contacts.Select(c => c.LastMessageAt.UtcDateTime).ToArray());
            // DateTime?[] maps to timestamptz[] with real NULLs; an object[] with DBNull does not.
            contacts.Parameters.AddWithValue("pos", snapshot.Contacts.Select(c => c.LastPositionAt?.UtcDateTime).ToArray());
            contacts.Parameters.AddWithValue("src", snapshot.SourceId);
            contacts.Parameters.AddWithValue("upd", snapshot.FetchedAt.UtcDateTime);
            await contacts.ExecuteNonQueryAsync(ct);
        }

        await using (var log = new NpgsqlCommand(
            "INSERT INTO fetch_log (source_id, url, fetched_at, content_hash, n_received, n_written) " +
            "VALUES (@s, @u, @f, @h, @nr, @nw)", conn, tx))
        {
            log.Parameters.AddWithValue("s", snapshot.SourceId);
            log.Parameters.AddWithValue("u", snapshot.Url.ToString());
            log.Parameters.AddWithValue("f", snapshot.FetchedAt.UtcDateTime);
            log.Parameters.AddWithValue("h", snapshot.ContentHash);
            log.Parameters.AddWithValue("nr", snapshot.Aircraft.Count);
            log.Parameters.AddWithValue("nw", rows.Count);
            await log.ExecuteNonQueryAsync(ct);
        }

        await tx.CommitAsync(ct);
        return rows.Count;
    }

    private static async Task WriteNullable<T>(NpgsqlBinaryImporter copy, T? value, NpgsqlDbType type, CancellationToken ct)
    {
        if (value is null)
        {
            await copy.WriteNullAsync(ct);
        }
        else
        {
            await copy.WriteAsync(value, type, ct);
        }
    }
}
```

- [ ] **Step 4: Uruchom — ma przejść**

Run: `cd src/dotnet && dotnet test --filter "PositionDeduplicatorTests|PositionWriterTests"`
Expected: PASS (5 testów).

- [ ] **Step 5: Przegląd [R]** — skill `codex-delegate`, tryb „przegląd diffa” dla `git diff main -- src/dotnet/Wachta.Ingestion`. Claude weryfikuje każde ustalenie przed poprawką.

- [ ] **Step 6: Commit** — `feat(ingestion): dedup and COPY-based position writer with fetch log`.

### Task 1.4: Worker pobierania + Docker

**Files:**
- Create: `src/dotnet/Wachta.Ingestion/IngestionWorker.cs`
- Modify: `src/dotnet/Wachta.Ingestion/Program.cs` (nadpisz), `src/dotnet/Wachta.Ingestion/appsettings.json` (nadpisz); usuń `Worker.cs` z szablonu
- Modify: `compose.yaml` (dodaj usługę `ingestion`)

**Interfaces:**
- Consumes: `SourceFactory`, `SourceOptions`, `PositionDeduplicator`, `IPositionWriter`.
- Produces: usługa `ingestion` w compose; sekcja konfiguracji `Sources` (tablica `SourceOptions`).

- [ ] **Step 1: Implementacja** (worker to cienka pętla nad przetestowanymi klasami — test ręczny w Step 3)

**Oznaczanie samolotów wojskowych — `MilitaryRegistry` (ustalenie z danych na żywo 2026-09-26).**
adsb.lol zwraca `dbFlags` **wyłącznie** z `/v2/mil`; w endpointach obszarowych pola nie ma ani razu
(0 na 92 samolotów w pomiarze). Bez rejestru samolot wojskowy złapany najpierw przez źródło obszarowe
trafiłby do bazy jako cywilny, a deduplikacja odrzuciłaby potem kopię z `/v2/mil` jako starszą.
Plik `src/dotnet/Wachta.Ingestion/MilitaryRegistry.cs` jest w repo: zapamiętuje adresy z `/v2/mil`
(retencja 12 h) i przywraca flagę obserwacjom z pozostałych źródeł. Worker woła `Remember`, potem
`Apply`, dopiero potem deduplikację. Testy: `Wachta.Tests/MilitaryRegistryTests.cs` (3 przypadki,
w tym wygasanie wpisu).

`src/dotnet/Wachta.Ingestion/IngestionWorker.cs`:
```csharp
using Wachta.Domain;

namespace Wachta.Ingestion;

public sealed class IngestionWorker(
    IEnumerable<IAircraftSource> sources,
    PositionDeduplicator dedup,
    MilitaryRegistry military,
    IPositionWriter writer,
    ILogger<IngestionWorker> log) : BackgroundService
{
    private readonly Lock _dedupLock = new();

    protected override Task ExecuteAsync(CancellationToken ct) =>
        Task.WhenAll(sources.Select(s => RunSourceAsync(s, ct)));

    private async Task RunSourceAsync(IAircraftSource source, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var snapshot = await source.FetchAsync(ct);
                IReadOnlyList<AircraftObservation> fresh;
                lock (_dedupLock)
                {
                    military.Remember(snapshot.Aircraft);
                    fresh = dedup.Filter(military.Apply(snapshot.Aircraft));
                }

                var written = await writer.WriteAsync(snapshot, fresh, ct);
                log.LogInformation("{Source}: received {Received}, written {Written}", source.Id, snapshot.Aircraft.Count, written);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                log.LogWarning(ex, "{Source}: fetch failed, retrying in 30 s", source.Id);
                await Task.Delay(TimeSpan.FromSeconds(30), ct);
            }
        }
    }
}
```

`src/dotnet/Wachta.Ingestion/Program.cs`:
```csharp
using Wachta.Domain;
using Wachta.Ingestion;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddHttpClient();
builder.Services.AddNpgsqlDataSource(builder.Configuration.GetConnectionString("Wachta")
    ?? throw new InvalidOperationException("ConnectionStrings:Wachta is not set"));
builder.Services.AddSingleton<SourceFactory>();
builder.Services.AddSingleton<PositionDeduplicator>();
builder.Services.AddSingleton<MilitaryRegistry>();
builder.Services.AddSingleton<IPositionWriter, PositionWriter>();

var sourceOptions = builder.Configuration.GetSection("Sources").Get<List<SourceOptions>>() ?? [];
foreach (var options in sourceOptions)
{
    builder.Services.AddSingleton<IAircraftSource>(sp => sp.GetRequiredService<SourceFactory>().Create(options));
}

builder.Services.AddHostedService<IngestionWorker>();
builder.Build().Run();
```

`src/dotnet/Wachta.Ingestion/appsettings.json`:
```json
{
  "Logging": { "LogLevel": { "Default": "Information", "System.Net.Http": "Warning" } },
  "Sources": [
    { "Id": "adsblol-mil",      "Kind": "adsb-v2", "Url": "https://api.adsb.lol/v2/mil",                "ForceMilitary": true,  "IntervalSeconds": 15, "StartDelaySeconds": 0 },
    { "Id": "adsblol-baltic-s", "Kind": "adsb-v2", "Url": "https://api.adsb.lol/v2/point/55.0/20.0/250", "ForceMilitary": false, "IntervalSeconds": 30, "StartDelaySeconds": 10 },
    { "Id": "adsblol-baltic-n", "Kind": "adsb-v2", "Url": "https://api.adsb.lol/v2/point/60.0/24.0/250", "ForceMilitary": false, "IntervalSeconds": 30, "StartDelaySeconds": 20 }
  ]
}
```

Usuń `src/dotnet/Wachta.Ingestion/Worker.cs`. W `Wachta.Ingestion.csproj` upewnij się, że `appsettings.json` ma `CopyToOutputDirectory` (szablon worker to robi).

`compose.yaml` — dodaj pod `services`:
```yaml
  ingestion:
    build: { context: ., dockerfile: infra/docker/dotnet.Dockerfile, args: { PROJECT: Wachta.Ingestion } }
    environment: *db-env
    restart: unless-stopped
    depends_on: { migrator: { condition: service_completed_successfully } }
```

- [ ] **Step 2: Build + testy całości**

Run: `cd src/dotnet && dotnet build && dotnet test`
Expected: PASS, 0 ostrzeżeń.

- [ ] **Step 3: Weryfikacja na żywo (10 minut)**

```bash
cd /c/Users/grzan/wachta
docker compose up -d --build db migrator ingestion
docker compose logs -f ingestion   # oczekuj: "adsblol-mil: received ~450, written ..." co ~15 s
```
Po 10 minutach:
```bash
docker compose exec db psql -U postgres -d wachta -c "SELECT source_id, count(*) FROM aircraft_position GROUP BY 1;"
docker compose exec db psql -U postgres -d wachta -c "SELECT source_id, count(*), max(fetched_at) FROM fetch_log GROUP BY 1;"
```
Expected: każde z 3 źródeł ma tysiące pozycji i ~40 wpisów w `fetch_log`.

- [ ] **Step 4: Commit** — `feat(ingestion): background worker and compose service`.

### Task 1.5: API — samoloty na żywo, tor, źródła

**Files:**
- Create: `src/dotnet/Wachta.Api/Dtos.cs`, `src/dotnet/Wachta.Api/AircraftEndpoints.cs`
- Modify: `src/dotnet/Wachta.Api/Program.cs` (nadpisz)
- Test: `src/dotnet/Wachta.Tests/ApiTests.cs`

**Interfaces:**
- Consumes: tabele z 0.4; `PostgresFixture`.
- Produces (JSON camelCase):
  - `GET /api/aircraft/live?militaryOnly=bool&minLat&minLon&maxLat&maxLon` → `LiveAircraft[]` (ostatnia pozycja na hex z ostatnich 2 min)
  - `GET /api/aircraft/{hex}/track?from=ISO&to=ISO` → `TrackPoint[]` (okno max 24 h, inaczej 400)
  - `GET /api/sources` → `SourceInfo[]`
  - `record LiveAircraft(string Hex, string? Flight, string? TypeCode, bool IsMilitary, double Lat, double Lon, int? AltBaroFt, bool OnGround, float? GsKt, float? TrackDeg, DateTime Ts)`
  - `record TrackPoint(DateTime Ts, double Lat, double Lon, int? AltBaroFt)`
  - `record SourceInfo(string Id, string Name, string Url, string License, short TrustTier, string Attribution)`
  - `public partial class Program;` (dla testów)

- [ ] **Step 1: Test (failing)**

`src/dotnet/Wachta.Tests/ApiTests.cs`:
```csharp
using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Npgsql;
using Wachta.Api;

namespace Wachta.Tests;

[Collection("postgres")]
public sealed class ApiTests : IAsyncLifetime
{
    private readonly PostgresFixture _db;
    private WebApplicationFactory<Program> _factory = null!;
    private HttpClient _client = null!;

    public ApiTests(PostgresFixture db) => _db = db;

    public async Task InitializeAsync()
    {
        Environment.SetEnvironmentVariable("ConnectionStrings__Wachta", _db.ConnectionString);
        _factory = new WebApplicationFactory<Program>();
        _client = _factory.CreateClient();

        await using var conn = new NpgsqlConnection(_db.ConnectionString);
        await conn.OpenAsync();
        await using var cmd = new NpgsqlCommand("""
            DELETE FROM aircraft_position WHERE hex IN ('api001','api002','api003');
            INSERT INTO aircraft_position (ts, hex, flight, type_code, is_military, lat, lon, alt_baro_ft, on_ground, gs_kt, track_deg, nic, nac_p, source_id, fetched_at) VALUES
              (now() - interval '90 seconds', 'api001', 'OLD1', 'K35R', true,  55.0, 19.0, 25000, false, 400, 90, 8, 9, 'adsblol-mil', now()),
              (now() - interval '10 seconds', 'api001', 'NEW1', 'K35R', true,  55.1, 19.2, 25000, false, 400, 90, 8, 9, 'adsblol-mil', now()),
              (now() - interval '10 seconds', 'api002', 'CIV1', 'A320', false, 54.0, 18.0, 36000, false, 450, 45, 8, 9, 'adsblol-baltic-s', now()),
              (now() - interval '10 minutes', 'api003', 'GONE', 'C17',  true,  56.0, 20.0, 30000, false, 420, 10, 8, 9, 'adsblol-mil', now());
            """, conn);
        await cmd.ExecuteNonQueryAsync();
    }

    public async Task DisposeAsync() => await _factory.DisposeAsync();

    [Fact]
    public async Task Live_returns_latest_position_per_aircraft_from_last_two_minutes()
    {
        var live = await _client.GetFromJsonAsync<List<LiveAircraft>>("/api/aircraft/live");
        var api001 = Assert.Single(live!, a => a.Hex == "api001");
        Assert.Equal("NEW1", api001.Flight);
        Assert.DoesNotContain(live!, a => a.Hex == "api003");
    }

    [Fact]
    public async Task Live_military_only_filters_civil()
    {
        var live = await _client.GetFromJsonAsync<List<LiveAircraft>>("/api/aircraft/live?militaryOnly=true");
        Assert.DoesNotContain(live!, a => a.Hex == "api002");
    }

    [Fact]
    public async Task Live_bbox_filters_by_position()
    {
        var live = await _client.GetFromJsonAsync<List<LiveAircraft>>("/api/aircraft/live?minLat=53&minLon=17&maxLat=54.5&maxLon=18.5");
        Assert.Contains(live!, a => a.Hex == "api002");
        Assert.DoesNotContain(live!, a => a.Hex == "api001");
    }

    [Fact]
    public async Task Track_returns_points_in_time_order()
    {
        var from = DateTime.UtcNow.AddMinutes(-5).ToString("O");
        var to = DateTime.UtcNow.ToString("O");
        var track = await _client.GetFromJsonAsync<List<TrackPoint>>($"/api/aircraft/api001/track?from={from}&to={to}");
        Assert.Equal(2, track!.Count);
        Assert.True(track[0].Ts < track[1].Ts);
    }

    [Fact]
    public async Task Track_window_over_24h_is_rejected()
    {
        var res = await _client.GetAsync($"/api/aircraft/api001/track?from={DateTime.UtcNow.AddDays(-2):O}&to={DateTime.UtcNow:O}");
        Assert.Equal(HttpStatusCode.BadRequest, res.StatusCode);
    }

    [Fact]
    public async Task Sources_lists_seeded_sources_with_license()
    {
        var sources = await _client.GetFromJsonAsync<List<SourceInfo>>("/api/sources");
        Assert.Contains(sources!, s => s.Id == "adsblol-mil" && s.License == "ODbL 1.0");
    }
}
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/dotnet && dotnet test --filter ApiTests`
Expected: FAIL (kompilacja: brak `LiveAircraft`).

- [ ] **Step 3: Implementacja**

```bash
cd src/dotnet
dotnet add Wachta.Api package Npgsql.DependencyInjection
dotnet add Wachta.Api package Dapper
dotnet add Wachta.Api package Microsoft.AspNetCore.OpenApi
```

`src/dotnet/Wachta.Api/Dtos.cs`:
```csharp
namespace Wachta.Api;

public sealed record LiveAircraft(
    string Hex, string? Flight, string? TypeCode, bool IsMilitary, double Lat, double Lon,
    int? AltBaroFt, bool OnGround, float? GsKt, float? TrackDeg, DateTime Ts);

public sealed record TrackPoint(DateTime Ts, double Lat, double Lon, int? AltBaroFt);

public sealed record SourceInfo(string Id, string Name, string Url, string License, short TrustTier, string Attribution);
```

`src/dotnet/Wachta.Api/AircraftEndpoints.cs`:
```csharp
using Dapper;
using Npgsql;

namespace Wachta.Api;

public static class AircraftEndpoints
{
    public const string LiveSql = """
        SELECT DISTINCT ON (hex)
               hex AS Hex, flight AS Flight, type_code AS TypeCode, is_military AS IsMilitary,
               lat AS Lat, lon AS Lon, alt_baro_ft AS AltBaroFt, on_ground AS OnGround,
               gs_kt AS GsKt, track_deg AS TrackDeg, ts AS Ts
        FROM aircraft_position
        WHERE ts > now() - interval '2 minutes'
          AND (NOT @militaryOnly OR is_military)
          AND (@minLat IS NULL OR lat BETWEEN @minLat AND @maxLat)
          AND (@minLon IS NULL OR lon BETWEEN @minLon AND @maxLon)
        ORDER BY hex, ts DESC
        """;

    public static void MapAircraftEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapGet("/api/aircraft/live", async (NpgsqlDataSource db, bool? militaryOnly,
            double? minLat, double? minLon, double? maxLat, double? maxLon) =>
        {
            await using var conn = await db.OpenConnectionAsync();
            return await conn.QueryAsync<LiveAircraft>(LiveSql,
                new { militaryOnly = militaryOnly ?? false, minLat, minLon, maxLat, maxLon });
        });

        app.MapGet("/api/aircraft/{hex}/track", async (NpgsqlDataSource db, string hex, DateTime from, DateTime to) =>
        {
            if (to <= from || to - from > TimeSpan.FromHours(24))
            {
                return Results.BadRequest("Window must be positive and at most 24 h.");
            }

            await using var conn = await db.OpenConnectionAsync();
            var points = await conn.QueryAsync<TrackPoint>("""
                SELECT ts AS Ts, lat AS Lat, lon AS Lon, alt_baro_ft AS AltBaroFt
                FROM aircraft_position
                WHERE hex = @hex AND ts BETWEEN @from AND @to
                ORDER BY ts
                """, new { hex = hex.ToLowerInvariant(), from = from.ToUniversalTime(), to = to.ToUniversalTime() });
            return Results.Ok(points);
        });

        app.MapGet("/api/sources", async (NpgsqlDataSource db) =>
        {
            await using var conn = await db.OpenConnectionAsync();
            return await conn.QueryAsync<SourceInfo>("""
                SELECT id AS Id, name AS Name, url AS Url, license AS License,
                       trust_tier AS TrustTier, attribution AS Attribution
                FROM source ORDER BY id
                """);
        });
    }
}
```

`src/dotnet/Wachta.Api/Program.cs`:
```csharp
using Wachta.Api;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddNpgsqlDataSource(builder.Configuration.GetConnectionString("Wachta")
    ?? throw new InvalidOperationException("ConnectionStrings:Wachta is not set"));
builder.Services.AddOpenApi();

var app = builder.Build();

app.MapOpenApi();
app.MapAircraftEndpoints();

app.Run();

public partial class Program;
```

Uwaga: `@minLat IS NULL` z parametrem Dapper typu `double?` — Npgsql potrzebuje typu dla `null`; jeśli test bbox rzuci `could not determine data type of parameter`, zamień warunki na `(@minLat::float8 IS NULL OR lat BETWEEN @minLat::float8 AND @maxLat::float8)` (analogicznie lon) — to jest oczekiwana poprawka, nie obejście.

- [ ] **Step 4: Uruchom — ma przejść**

Run: `cd src/dotnet && dotnet test --filter ApiTests`
Expected: PASS (6 testów).

- [ ] **Step 5: Commit** — `feat(api): live aircraft, track and sources endpoints`.

### Task 1.6: SignalR — push pozycji co 5 s

**Files:**
- Create: `src/dotnet/Wachta.Api/LiveHub.cs`, `src/dotnet/Wachta.Api/LiveBroadcaster.cs`
- Modify: `src/dotnet/Wachta.Api/Program.cs`
- Test: `src/dotnet/Wachta.Tests/LiveHubTests.cs`

**Interfaces:**
- Consumes: `AircraftEndpoints.LiveSql`, `LiveAircraft`.
- Produces: hub `/hubs/live`, wiadomość `"aircraft"` z argumentem `LiveAircraft[]` (tylko wojskowe + wszystkie w AOI Bałtyku `53.5–66.0 N`, `9.0–30.5 E`) co `LiveBroadcaster.Interval` (5 s).

- [ ] **Step 1: Test (failing)**

`src/dotnet/Wachta.Tests/LiveHubTests.cs`:
```csharp
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.SignalR.Client;
using Npgsql;
using Wachta.Api;

namespace Wachta.Tests;

[Collection("postgres")]
public sealed class LiveHubTests(PostgresFixture db)
{
    [Fact]
    public async Task Hub_pushes_aircraft_within_ten_seconds()
    {
        Environment.SetEnvironmentVariable("ConnectionStrings__Wachta", db.ConnectionString);
        await using (var conn = new NpgsqlConnection(db.ConnectionString))
        {
            await conn.OpenAsync();
            await using var cmd = new NpgsqlCommand("""
                INSERT INTO aircraft_position (ts, hex, flight, type_code, is_military, lat, lon, alt_baro_ft, on_ground, gs_kt, track_deg, nic, nac_p, source_id, fetched_at)
                VALUES (now(), 'hub001', 'HUB1', 'P8', true, 55.0, 19.0, 20000, false, 350, 180, 8, 9, 'adsblol-mil', now())
                """, conn);
            await cmd.ExecuteNonQueryAsync();
        }

        await using var factory = new WebApplicationFactory<Program>();
        var server = factory.Server;
        var hub = new HubConnectionBuilder()
            .WithUrl(new Uri(server.BaseAddress, "/hubs/live"), o => o.HttpMessageHandlerFactory = _ => server.CreateHandler())
            .Build();

        var received = new TaskCompletionSource<List<LiveAircraft>>();
        hub.On<List<LiveAircraft>>("aircraft", list => received.TrySetResult(list));
        await hub.StartAsync();

        var result = await received.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Contains(result, a => a.Hex == "hub001");
        await hub.DisposeAsync();
    }
}
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/dotnet && dotnet test --filter LiveHubTests`
Expected: FAIL (404 na `/hubs/live` → wyjątek przy `StartAsync`).

- [ ] **Step 3: Implementacja**

`src/dotnet/Wachta.Api/LiveHub.cs`:
```csharp
using Microsoft.AspNetCore.SignalR;

namespace Wachta.Api;

/// <summary>Server-to-client only. Clients listen for "aircraft" and "alerts".</summary>
public sealed class LiveHub : Hub;
```

`src/dotnet/Wachta.Api/LiveBroadcaster.cs`:
```csharp
using Dapper;
using Microsoft.AspNetCore.SignalR;
using Npgsql;

namespace Wachta.Api;

/// <summary>Observer: polls the latest positions and pushes them to all connected map clients.</summary>
public sealed class LiveBroadcaster(NpgsqlDataSource db, IHubContext<LiveHub> hub, ILogger<LiveBroadcaster> log) : BackgroundService
{
    public static readonly TimeSpan Interval = TimeSpan.FromSeconds(5);

    private const string BroadcastSql = $"""
        SELECT * FROM ({AircraftEndpoints.LiveSql}) live
        """;

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(Interval);
        do
        {
            try
            {
                await using var conn = await db.OpenConnectionAsync(ct);
                var military = await conn.QueryAsync<LiveAircraft>(BroadcastSql,
                    new { militaryOnly = true, minLat = (double?)null, minLon = (double?)null, maxLat = (double?)null, maxLon = (double?)null });
                var baltic = await conn.QueryAsync<LiveAircraft>(BroadcastSql,
                    new { militaryOnly = false, minLat = (double?)53.5, minLon = (double?)9.0, maxLat = (double?)66.0, maxLon = (double?)30.5 });
                var merged = military.Concat(baltic).DistinctBy(a => a.Hex).ToList();
                await hub.Clients.All.SendAsync("aircraft", merged, ct);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogWarning(ex, "Live broadcast failed");
            }
        }
        while (await timer.WaitForNextTickAsync(ct));
    }
}
```

Uwaga: jeśli w Task 1.5 dodano rzutowania `::float8`, `LiveSql` je zawiera — tu nic nie zmieniasz.

`src/dotnet/Wachta.Api/Program.cs` — dodaj przed `builder.Build()`:
```csharp
builder.Services.AddSignalR();
builder.Services.AddHostedService<LiveBroadcaster>();
```
i po `app.MapAircraftEndpoints();`:
```csharp
app.MapHub<LiveHub>("/hubs/live");
```

- [ ] **Step 4: Uruchom — ma przejść**

Run: `cd src/dotnet && dotnet test --filter LiveHubTests`
Expected: PASS.

- [ ] **Step 5: Compose** — dodaj usługę:
```yaml
  api:
    build: { context: ., dockerfile: infra/docker/dotnet.Dockerfile, args: { PROJECT: Wachta.Api } }
    environment: *db-env
    ports: ["8080:8080"]
    restart: unless-stopped
    depends_on: { migrator: { condition: service_completed_successfully } }
```
Weryfikacja: `docker compose up -d --build api` → `curl http://localhost:8080/api/aircraft/live?militaryOnly=true` zwraca tablicę JSON.

- [ ] **Step 6: Commit** — `feat(api): signalr live hub with periodic broadcaster`.

### Task 1.7: Python — modele + D3 zakłócenia GPS

**Files:**
- Create: `src/python/wachta_detectors/models.py`, `src/python/wachta_detectors/jamming.py`
- Test: `src/python/tests/test_jamming.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Position: hex: str; lat: float; lon: float; alt_ft: int | None; on_ground: bool; nac_p: int | None; ts: datetime`
  - `@dataclass(frozen=True) class JammingCell: h3: str; n_aircraft: int; n_degraded: int` + property `pct` (surowy udział, do wyświetlania), `confidence_floor` (dolna granica Wilsona) i `level` progowany na `confidence_floor` (`"low"` < 0.02 ≤ `"medium"` < 0.10 ≤ `"high"`)
  - `aggregate_jamming(positions: Iterable[Position], resolution: int = 4, degraded_below: int = 8, min_aircraft: int = 10) -> list[JammingCell]`
  - `wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float` — poziom komórki liczy się z dolnej granicy przedziału ufności, nie z surowego udziału

Reguła: samolot liczony raz na komórkę; „zakłócony”, jeśli **większość** jego raportów w komórce ma `nac_p < degraded_below`. Pomijamy samoloty na ziemi i raporty bez `nac_p`. Komórki z mniej niż `min_aircraft` samolotami pomijamy (za mało danych).

- [ ] **Step 1: Test (failing)**

`src/python/tests/test_jamming.py`:
```python
from datetime import datetime, timezone

import h3

from wachta_detectors.jamming import JammingCell, aggregate_jamming
from wachta_detectors.models import Position

T = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
KALININGRAD = (54.9, 20.3)


def pos(hex_, nac_p, lat=KALININGRAD[0], lon=KALININGRAD[1], on_ground=False):
    return Position(hex=hex_, lat=lat, lon=lon, alt_ft=30000, on_ground=on_ground, nac_p=nac_p, ts=T)


def test_counts_each_aircraft_once_per_cell_by_majority():
    positions = [pos("a", 3), pos("a", 3), pos("a", 9)] + [pos(f"ok{i}", 10) for i in range(4)]
    [cell] = aggregate_jamming(positions)
    assert cell.n_aircraft == 5
    assert cell.n_degraded == 1


def test_skips_ground_and_missing_nacp():
    positions = [pos(f"x{i}", 10) for i in range(5)] + [pos("g", 0, on_ground=True), pos("n", None)]
    [cell] = aggregate_jamming(positions)
    assert cell.n_aircraft == 5
    assert cell.n_degraded == 0


def test_drops_cells_with_too_few_aircraft():
    assert aggregate_jamming([pos(f"x{i}", 2) for i in range(4)]) == []


def test_cell_id_matches_h3_resolution():
    [cell] = aggregate_jamming([pos(f"x{i}", 2) for i in range(5)], resolution=4)
    assert cell.h3 == h3.latlng_to_cell(*KALININGRAD, 4)


def test_levels_follow_gpsjam_thresholds():
    assert JammingCell("c", 100, 1).level == "low"
    assert JammingCell("c", 100, 2).level == "medium"
    assert JammingCell("c", 100, 10).level == "high"
    assert JammingCell("c", 100, 10).pct == 0.10
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/python && uv run pytest tests/test_jamming.py -q`
Expected: FAIL (`ModuleNotFoundError: wachta_detectors.jamming`).

- [ ] **Step 3: Implementacja**

`src/python/wachta_detectors/models.py`:
```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Position:
    hex: str
    lat: float
    lon: float
    alt_ft: int | None
    on_ground: bool
    nac_p: int | None
    ts: datetime
```

`src/python/wachta_detectors/jamming.py`:
```python
"""D3: GPS interference map from ADS-B NACp values (method in the spirit of gpsjam.org)."""
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

import h3

from wachta_detectors.models import Position

MEDIUM_THRESHOLD = 0.02
HIGH_THRESHOLD = 0.10


@dataclass(frozen=True)
class JammingCell:
    h3: str
    n_aircraft: int
    n_degraded: int

    @property
    def pct(self) -> float:
        return self.n_degraded / self.n_aircraft

    @property
    def level(self) -> str:
        if self.pct >= HIGH_THRESHOLD:
            return "high"
        if self.pct >= MEDIUM_THRESHOLD:
            return "medium"
        return "low"


def aggregate_jamming(
    positions: Iterable[Position],
    resolution: int = 4,
    degraded_below: int = 8,
    min_aircraft: int = 5,
) -> list[JammingCell]:
    # cell -> hex -> [degraded_reports, total_reports]
    votes: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for p in positions:
        if p.on_ground or p.nac_p is None:
            continue
        v = votes[h3.latlng_to_cell(p.lat, p.lon, resolution)][p.hex]
        v[0] += p.nac_p < degraded_below
        v[1] += 1

    cells = []
    for cell, per_aircraft in votes.items():
        if len(per_aircraft) < min_aircraft:
            continue
        # Majority, not "any": over an hour a single bad report is noise, a jammed aircraft reports badly the whole way.
        degraded = sum(1 for bad, total in per_aircraft.values() if bad * 2 > total)
        cells.append(JammingCell(cell, len(per_aircraft), degraded))
    return cells
```

- [ ] **Step 4: Uruchom — ma przejść**

Run: `cd src/python && uv run pytest tests/test_jamming.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit** — `feat(detectors): D3 GPS jamming aggregation on H3`.

### Task 1.8: Model pokrycia odbiorników

**Files:**
- Create: `src/python/wachta_detectors/coverage.py`
- Test: `src/python/tests/test_coverage.py`

**Interfaces:**
- Consumes: `Position` (1.7).
- Produces:
  - `COVERAGE_RESOLUTION = 5`
  - `count_reports(positions: Iterable[Position], resolution: int = COVERAGE_RESOLUTION) -> dict[str, int]` (tylko samoloty w powietrzu)
  - `is_well_covered(coverage: Mapping[str, int], lat: float, lon: float, min_reports: int = 200, resolution: int = COVERAGE_RESOLUTION) -> bool` — `True` tylko, gdy komórka **i wszystkie 6 sąsiadów** (`h3.grid_disk(cell, 1)`) mają ≥ `min_reports` (wyklucza krawędź zasięgu).

- [ ] **Step 1: Test (failing)**

`src/python/tests/test_coverage.py`:
```python
from datetime import datetime, timezone

import h3

from wachta_detectors.coverage import COVERAGE_RESOLUTION, count_reports, is_well_covered
from wachta_detectors.models import Position

T = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
LAT, LON = 55.0, 18.0
CENTER = h3.latlng_to_cell(LAT, LON, COVERAGE_RESOLUTION)


def test_count_reports_ignores_ground():
    positions = [Position("a", LAT, LON, 30000, False, 9, T), Position("b", LAT, LON, None, True, 9, T)]
    assert count_reports(positions) == {CENTER: 1}


def test_well_covered_requires_center_and_all_neighbours():
    coverage = {c: 500 for c in h3.grid_disk(CENTER, 1)}
    assert is_well_covered(coverage, LAT, LON)


def test_edge_of_coverage_is_not_well_covered():
    coverage = {c: 500 for c in h3.grid_disk(CENTER, 1)}
    neighbour = next(c for c in coverage if c != CENTER)
    coverage[neighbour] = 3
    assert not is_well_covered(coverage, LAT, LON)


def test_unknown_area_is_not_well_covered():
    assert not is_well_covered({}, LAT, LON)
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/python && uv run pytest tests/test_coverage.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementacja**

`src/python/wachta_detectors/coverage.py`:
```python
"""Receiver coverage model: where do we normally see aircraft? Gaps outside coverage are not evidence."""
from collections import Counter
from collections.abc import Iterable, Mapping

import h3

from wachta_detectors.models import Position

COVERAGE_RESOLUTION = 5


def count_reports(positions: Iterable[Position], resolution: int = COVERAGE_RESOLUTION) -> dict[str, int]:
    return dict(Counter(h3.latlng_to_cell(p.lat, p.lon, resolution) for p in positions if not p.on_ground))


def is_well_covered(
    coverage: Mapping[str, int],
    lat: float,
    lon: float,
    min_reports: int = 200,
    resolution: int = COVERAGE_RESOLUTION,
) -> bool:
    center = h3.latlng_to_cell(lat, lon, resolution)
    return all(coverage.get(cell, 0) >= min_reports for cell in h3.grid_disk(center, 1))
```

- [ ] **Step 4: Uruchom — ma przejść** — `4 passed`.
- [ ] **Step 5: Commit** — `feat(detectors): receiver coverage model`.

### Task 1.9: D1 zgaszony transponder (reguła bazowa) [R]

**Files:**
- Create: `src/python/wachta_detectors/geo.py`, `src/python/wachta_detectors/airports.py`, `src/python/wachta_detectors/dark.py`
- Test: `src/python/tests/test_airports.py`, `src/python/tests/test_dark.py`

**Interfaces:**
- Consumes: `is_well_covered`, `COVERAGE_RESOLUTION` (1.8).
- Produces:
  - `haversine_km(lat1, lon1, lat2, lon2) -> float` (geo.py)
  - `load_airports(csv_path: Path, types: frozenset[str] = frozenset({"large_airport", "medium_airport", "small_airport"})) -> list[tuple[float, float]]` (airports.py; format OurAirports)
  - `nearest_airport_km(airports, lat, lon) -> float` (airports.py)
  - `@dataclass(frozen=True) class LastSeen: hex, flight, type_code, is_military, lat, lon, alt_ft, gs_kt, ts: datetime, n_points: int, last_message_at: datetime`
  - `@dataclass(frozen=True) class DarkCandidate: hex, lat, lon, last_seen: datetime, score: float, evidence: dict`
  - `@dataclass(frozen=True) class DarkRules` z polami domyślnymi: `min_gap=timedelta(minutes=5)`, `max_gap=timedelta(minutes=30)`, `min_alt_ft=3000`, `min_gs_kt=100`, `airport_radius_km=40.0`, `min_points=10`, `min_cell_reports=200`
  - `find_dark_candidates(last_seen: Iterable[LastSeen], coverage: Mapping[str,int], alive_cells: set[str], airports: list[tuple[float,float]], now: datetime, rules: DarkRules = DarkRules()) -> list[DarkCandidate]`

Reguła D1 (wszystkie warunki): **luka liczona od ostatniej wiadomości** (`last_message_at`), nie od ostatniej pozycji — samolot z zakłóconym GPS traci pozycję, ale nadal nadaje i nie jest „zgaszony”; luka w `[min_gap, max_gap]`; w powietrzu (`alt_ft ≥ min_alt_ft`, `gs_kt ≥ min_gs_kt`); ≥ `min_points` pozycji przed zniknięciem; dalej niż `airport_radius_km` od lotniska; `is_well_covered(...)`; **i** w komórce ostatniej pozycji lub sąsiedniej (`grid_disk(k=1)`) inne samoloty były widziane po zniknięciu (`alive_cells` = komórki z raportami z ostatnich 2 min). Wynik: `0.5 + 0.3·is_military + 0.2·min(1, n_points/100)`. `evidence` zawiera wszystkie wejścia (żeby oznaczony alarm dało się odtworzyć jako fixture w T1.15).

- [ ] **Step 1: Testy (failing)**

`src/python/tests/test_airports.py`:
```python
from pathlib import Path

from wachta_detectors.airports import load_airports, nearest_airport_km

CSV = """id,ident,type,name,latitude_deg,longitude_deg
1,EPGD,large_airport,Gdansk,54.3776,18.4662
2,XHEL,heliport,Some heliport,54.0,18.0
3,EPOK,medium_airport,Oksywie,54.5797,18.5172
"""


def test_loads_only_selected_types(tmp_path: Path):
    f = tmp_path / "airports.csv"
    f.write_text(CSV, encoding="utf-8")
    assert load_airports(f) == [(54.3776, 18.4662), (54.5797, 18.5172)]


def test_nearest_airport_distance():
    airports = [(54.3776, 18.4662)]
    assert nearest_airport_km(airports, 54.3776, 18.4662) < 0.01
    assert 110 < nearest_airport_km(airports, 55.3776, 18.4662) < 112
```

`src/python/tests/test_dark.py`:
```python
from datetime import datetime, timedelta, timezone

import h3

from wachta_detectors.coverage import COVERAGE_RESOLUTION
from wachta_detectors.dark import DarkRules, LastSeen, find_dark_candidates

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
LAT, LON = 55.5, 17.5  # open sea, south Baltic
CELL = h3.latlng_to_cell(LAT, LON, COVERAGE_RESOLUTION)
GOOD_COVERAGE = {c: 1000 for c in h3.grid_disk(CELL, 2)}
ALIVE = {CELL}
FAR_AIRPORTS = [(54.3776, 18.4662)]  # Gdansk, ~130 km away


def seen(**overrides):
    base = dict(hex="ae1234", flight="FORTE10", type_code="Q4", is_military=True, lat=LAT, lon=LON,
                alt_ft=30000, gs_kt=300.0, ts=NOW - timedelta(minutes=10), n_points=120,
                last_message_at=NOW - timedelta(minutes=10))
    base.update(overrides)
    return LastSeen(**base)


def run(items, coverage=GOOD_COVERAGE, alive=ALIVE, airports=FAR_AIRPORTS):
    return find_dark_candidates(items, coverage, alive, airports, NOW)


def test_disappearance_at_altitude_in_good_coverage_is_candidate():
    [c] = run([seen()])
    assert c.hex == "ae1234"
    assert c.score == 1.0
    assert c.evidence["nearest_airport_km"] > 40
    assert c.evidence["flight"] == "FORTE10"


def test_civil_aircraft_scores_lower():
    [c] = run([seen(is_military=False, n_points=50)])
    assert c.score == 0.6


def test_too_recent_or_too_old_gap_is_ignored():
    assert run([seen(ts=NOW - timedelta(minutes=2), last_message_at=NOW - timedelta(minutes=2))]) == []
    assert run([seen(ts=NOW - timedelta(minutes=45), last_message_at=NOW - timedelta(minutes=45))]) == []


def test_aircraft_still_transmitting_without_position_is_not_dark():
    """GPS jamming: position is 10 min old, but the aircraft was heard 20 s ago -> not a dark transponder."""
    assert run([seen(last_message_at=NOW - timedelta(seconds=20))]) == []


def test_low_or_slow_aircraft_is_ignored():
    assert run([seen(alt_ft=1500)]) == []
    assert run([seen(alt_ft=None)]) == []
    assert run([seen(gs_kt=60.0)]) == []


def test_near_airport_is_landing_not_dark():
    assert run([seen()], airports=[(LAT + 0.1, LON)]) == []


def test_edge_of_coverage_is_ignored():
    assert run([seen()], coverage={CELL: 1000}) == []


def test_no_other_aircraft_seen_after_means_receiver_outage():
    assert run([seen()], alive=set()) == []


def test_short_track_is_ignored():
    assert run([seen(n_points=3)]) == []


def test_rules_are_configurable():
    assert run([seen(alt_ft=2000)]) == []
    assert find_dark_candidates([seen(alt_ft=2000)], GOOD_COVERAGE, ALIVE, FAR_AIRPORTS, NOW, DarkRules(min_alt_ft=1000))
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/python && uv run pytest tests/test_airports.py tests/test_dark.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementacja**

`src/python/wachta_detectors/geo.py`:
```python
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))
```

`src/python/wachta_detectors/airports.py`:
```python
"""Airports from OurAirports (public domain): https://davidmegginson.github.io/ourairports-data/airports.csv"""
import csv
from pathlib import Path

from wachta_detectors.geo import haversine_km

DEFAULT_TYPES = frozenset({"large_airport", "medium_airport", "small_airport"})


def load_airports(csv_path: Path, types: frozenset[str] = DEFAULT_TYPES) -> list[tuple[float, float]]:
    with csv_path.open(encoding="utf-8", newline="") as f:
        return [(float(r["latitude_deg"]), float(r["longitude_deg"])) for r in csv.DictReader(f) if r["type"] in types]


def nearest_airport_km(airports: list[tuple[float, float]], lat: float, lon: float) -> float:
    return min((haversine_km(lat, lon, a_lat, a_lon) for a_lat, a_lon in airports), default=float("inf"))
```

`src/python/wachta_detectors/dark.py`:
```python
"""D1: aircraft that stop transmitting mid-air inside good receiver coverage. Output = 'to check', never a verdict."""
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import h3

from wachta_detectors.airports import nearest_airport_km
from wachta_detectors.coverage import COVERAGE_RESOLUTION, is_well_covered


@dataclass(frozen=True)
class LastSeen:
    hex: str
    flight: str | None
    type_code: str | None
    is_military: bool
    lat: float
    lon: float
    alt_ft: int | None
    gs_kt: float | None
    ts: datetime
    n_points: int
    last_message_at: datetime


@dataclass(frozen=True)
class DarkCandidate:
    hex: str
    lat: float
    lon: float
    last_seen: datetime
    score: float
    evidence: dict = field(hash=False)


@dataclass(frozen=True)
class DarkRules:
    min_gap: timedelta = timedelta(minutes=5)
    max_gap: timedelta = timedelta(minutes=30)
    min_alt_ft: int = 3000
    min_gs_kt: float = 100
    airport_radius_km: float = 40.0
    min_points: int = 10
    min_cell_reports: int = 200


def snapshot_inputs(
    s: LastSeen,
    coverage: Mapping[str, int],
    alive_cells: set[str],
    airports: list[tuple[float, float]],
    now: datetime,
    rules: DarkRules = DarkRules(),
) -> dict:
    """Everything the rules look at, frozen so a labelled case can be replayed offline."""
    cell = h3.latlng_to_cell(s.lat, s.lon, COVERAGE_RESOLUTION)
    disk = h3.grid_disk(cell, 1)
    return {
        "last_seen": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(s).items()},
        "now": now.isoformat(),
        "coverage": {c: coverage.get(c, 0) for c in disk},
        "alive": sorted(alive_cells & set(disk)),
        "airports": [[round(a_lat, 4), round(a_lon, 4)] for a_lat, a_lon in airports
                     if nearest_airport_km([(a_lat, a_lon)], s.lat, s.lon) <= rules.airport_radius_km * 3],
    }


def silent_aircraft(last_seen: Iterable[LastSeen], now: datetime, rules: DarkRules = DarkRules()) -> list[LastSeen]:
    """Everything that went quiet for min_gap..max_gap — the population to sample and label."""
    return [s for s in last_seen if rules.min_gap <= now - s.last_message_at <= rules.max_gap]


def find_dark_candidates(
    last_seen: Iterable[LastSeen],
    coverage: Mapping[str, int],
    alive_cells: set[str],
    airports: list[tuple[float, float]],
    now: datetime,
    rules: DarkRules = DarkRules(),
) -> list[DarkCandidate]:
    candidates = []
    for s in last_seen:
        # Silence of messages, not absence of position: a jammed aircraft keeps transmitting without a position.
        gap = now - s.last_message_at
        if not rules.min_gap <= gap <= rules.max_gap:
            continue
        if s.alt_ft is None or s.alt_ft < rules.min_alt_ft or s.gs_kt is None or s.gs_kt < rules.min_gs_kt:
            continue
        if s.n_points < rules.min_points:
            continue
        airport_km = nearest_airport_km(airports, s.lat, s.lon)
        if airport_km <= rules.airport_radius_km:
            continue
        if not is_well_covered(coverage, s.lat, s.lon, rules.min_cell_reports):
            continue
        cell = h3.latlng_to_cell(s.lat, s.lon, COVERAGE_RESOLUTION)
        if not alive_cells & set(h3.grid_disk(cell, 1)):
            continue

        score = 0.5 + 0.3 * s.is_military + 0.2 * min(1.0, s.n_points / 100)
        evidence = {
            **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(s).items()},
            "gap_minutes": round(gap.total_seconds() / 60, 1),
            "position_gap_minutes": round((now - s.ts).total_seconds() / 60, 1),
            "nearest_airport_km": round(airport_km, 1),
            "cell": cell,
            "cell_reports": coverage.get(cell, 0),
            "inputs": snapshot_inputs(s, coverage, alive_cells, airports, now, rules),
            "note": "Candidate to check, not a verdict.",
        }
        candidates.append(DarkCandidate(s.hex, s.lat, s.lon, s.ts, round(score, 3), evidence))
    return candidates
```

- [ ] **Step 4: Uruchom — ma przejść**

Run: `cd src/python && uv run pytest tests/test_airports.py tests/test_dark.py -q`
Expected: `11 passed`.

- [ ] **Step 5: Przegląd [R]** — `codex-delegate`, tryb „audyt logiki” dla `dark.py` + `coverage.py` (pytanie: które realne sytuacje dadzą fałszywy alarm?). Wnioski → nowe testy scenariuszy, jeśli zasadne.

- [ ] **Step 6: Commit** — `feat(detectors): D1 dark aircraft baseline rule`.

### Task 1.10: Repozytorium bazy + runner detektorów + Docker

**Files:**
- Create: `src/python/wachta_detectors/repository.py`, `src/python/wachta_detectors/run.py`
- Create: `infra/docker/python.Dockerfile`
- Test: `src/python/tests/integration/test_repository.py`
- Modify: `compose.yaml`

**Interfaces:**
- Consumes: `Position`, `aggregate_jamming`, `count_reports`, `find_dark_candidates`, `LastSeen`, `load_airports`.
- Produces (`repository.py`, wszystkie przyjmują `psycopg.Connection`):
  - `positions_between(conn, start: datetime, end: datetime) -> list[Position]`
  - `last_seen_since(conn, since: datetime) -> list[LastSeen]` (ostatnia pozycja + liczba punktów na hex)
  - `alive_cells(conn, since: datetime, resolution: int) -> set[str]`
  - `coverage_last_days(conn, days: int = 7) -> dict[str, int]`
  - `replace_jamming(conn, hour: datetime, cells: list[JammingCell]) -> None` (DELETE + INSERT w jednej transakcji — przeliczona godzina nie może zostawiać nieaktualnych komórek)
  - `last_jamming_hour(conn) -> datetime | None`, `last_coverage_hour(conn) -> datetime | None` (nadrabianie zaległych godzin po restarcie)
  - `upsert_coverage(conn, hour: datetime, counts: dict[str, int]) -> None`
  - `insert_alerts(conn, detector: str, candidates: list[DarkCandidate]) -> int` (ON CONFLICT DO NOTHING; zwraca liczbę nowych)
  - `insert_d1_samples(conn, samples: list[tuple[str, datetime, bool, dict]]) -> None` (zamrożone wejścia D1 dla wszystkich milczących samolotów — podstawa recall)
  - `run.py`: `python -m wachta_detectors.run` — pętla co 60 s: D1 zawsze; D3 dla bieżącej godziny co 10 min; pokrycie za poprzednią godzinę raz na godzinę.

- [ ] **Step 1: Test integracyjny (failing)**

`src/python/tests/integration/test_repository.py`:
```python
"""Applies the real C# migration scripts to a TimescaleDB container and exercises the repository."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from wachta_detectors import repository as repo
from wachta_detectors.dark import DarkCandidate
from wachta_detectors.jamming import JammingCell

pytestmark = pytest.mark.integration
SCRIPTS = Path(__file__).resolve().parents[3] / "dotnet" / "Wachta.Db" / "Scripts"


@pytest.fixture(scope="module")
def conn():
    with PostgresContainer("timescale/timescaledb-ha:pg17", username="postgres", password="postgres", dbname="wachta") as pg:
        url = pg.get_connection_url(driver=None)
        with psycopg.connect(url, autocommit=True) as c:
            for script in sorted(SCRIPTS.glob("*.sql")):
                c.execute(script.read_text(encoding="utf-8"))
            yield c


def insert(conn, hex_, minutes_ago, lat=55.5, lon=17.5, nac_p=9, mil=True):
    conn.execute(
        """INSERT INTO aircraft_position (ts, hex, flight, type_code, is_military, lat, lon, alt_baro_ft, on_ground,
           gs_kt, track_deg, nic, nac_p, source_id, fetched_at)
           VALUES (now() - make_interval(mins => %s), %s, 'F1', 'P8', %s, %s, %s, 30000, false, 300, 90, 8, %s, 'adsblol-mil', now())""",
        (minutes_ago, hex_, mil, lat, lon, nac_p),
    )


def test_last_seen_returns_latest_point_count_and_contact(conn):
    for m in (20, 15, 10):
        insert(conn, "rep001", m)
    now = datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO aircraft_contact (hex, last_message_at, last_position_at, source_id, updated_at)
           VALUES ('rep001', %s, %s, 'adsblol-mil', %s)
           ON CONFLICT (hex) DO UPDATE SET last_message_at = EXCLUDED.last_message_at""",
        (now - timedelta(seconds=30), now - timedelta(minutes=10), now),
    )
    [s] = [x for x in repo.last_seen_since(conn, now - timedelta(minutes=30)) if x.hex == "rep001"]
    assert s.n_points == 3
    assert timedelta(minutes=9) < now - s.ts < timedelta(minutes=11)
    assert now - s.last_message_at < timedelta(minutes=1)  # still transmitting -> D1 must not fire


def test_positions_between_and_alive_cells(conn):
    insert(conn, "rep002", 1)
    now = datetime.now(timezone.utc)
    assert any(p.hex == "rep002" for p in repo.positions_between(conn, now - timedelta(minutes=5), now))
    assert repo.alive_cells(conn, now - timedelta(minutes=2), 5)


def test_replace_jamming_overwrites_and_drops_stale_cells(conn):
    hour = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    repo.replace_jamming(conn, hour, [JammingCell("841f053ffffffff", 10, 3), JammingCell("841f05bffffffff", 8, 0)])
    repo.replace_jamming(conn, hour, [JammingCell("841f053ffffffff", 12, 4)])
    rows = conn.execute("SELECT h3, n_aircraft FROM jamming_cell WHERE hour=%s", (hour,)).fetchall()
    assert rows == [("841f053ffffffff", 12)]
    assert repo.last_jamming_hour(conn) >= hour
    repo.upsert_coverage(conn, hour, {"851f0533fffffff": 5})
    repo.upsert_coverage(conn, hour, {"851f0533fffffff": 7})
    assert conn.execute("SELECT n_reports FROM coverage_hourly WHERE hour=%s", (hour,)).fetchone()[0] == 7


def test_insert_alerts_skips_duplicates(conn):
    c = DarkCandidate("rep003", 55.5, 17.5, datetime(2026, 9, 22, 11, 50, tzinfo=timezone.utc), 0.9, {"note": "x"})
    assert repo.insert_alerts(conn, "D1", [c]) == 1
    assert repo.insert_alerts(conn, "D1", [c]) == 0
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `cd src/python && uv run pytest tests/integration -q`
Expected: FAIL (`ImportError: repository`).

- [ ] **Step 3: Implementacja**

`src/python/wachta_detectors/repository.py`:
```python
import json
from datetime import datetime

import h3
import psycopg

from wachta_detectors.coverage import COVERAGE_RESOLUTION
from wachta_detectors.dark import DarkCandidate, LastSeen
from wachta_detectors.jamming import JammingCell
from wachta_detectors.models import Position


def positions_between(conn: psycopg.Connection, start: datetime, end: datetime) -> list[Position]:
    rows = conn.execute(
        "SELECT hex, lat, lon, alt_baro_ft, on_ground, nac_p, ts FROM aircraft_position WHERE ts >= %s AND ts < %s",
        (start, end),
    ).fetchall()
    return [Position(*r) for r in rows]


def last_seen_since(conn: psycopg.Connection, since: datetime) -> list[LastSeen]:
    """Last position per aircraft + when it was last heard at all (aircraft_contact)."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (p.hex) p.hex, p.flight, p.type_code, p.is_military, p.lat, p.lon, p.alt_baro_ft, p.gs_kt, p.ts,
               count(*) OVER (PARTITION BY p.hex) AS n_points,
               COALESCE(c.last_message_at, p.ts) AS last_message_at
        FROM aircraft_position p
        LEFT JOIN aircraft_contact c USING (hex)
        WHERE p.ts >= %s
        ORDER BY p.hex, p.ts DESC
        """,
        (since,),
    ).fetchall()
    return [LastSeen(*r) for r in rows]


def alive_cells(conn: psycopg.Connection, since: datetime, resolution: int = COVERAGE_RESOLUTION) -> set[str]:
    rows = conn.execute("SELECT DISTINCT lat, lon FROM aircraft_position WHERE ts >= %s AND NOT on_ground", (since,)).fetchall()
    return {h3.latlng_to_cell(lat, lon, resolution) for lat, lon in rows}


def coverage_last_days(conn: psycopg.Connection, days: int = 7) -> dict[str, int]:
    rows = conn.execute(
        "SELECT h3, sum(n_reports)::int FROM coverage_hourly WHERE hour > now() - make_interval(days => %s) GROUP BY h3",
        (days,),
    ).fetchall()
    return dict(rows)


def replace_jamming(conn: psycopg.Connection, hour: datetime, cells: list[JammingCell]) -> None:
    """Whole hour is recomputed: stale cells must disappear, so delete first, then insert, in one transaction."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM jamming_cell WHERE hour = %s", (hour,))
        if cells:
            cur.executemany(
                "INSERT INTO jamming_cell (hour, h3, n_aircraft, n_degraded) VALUES (%s, %s, %s, %s)",
                [(hour, c.h3, c.n_aircraft, c.n_degraded) for c in cells],
            )


def last_jamming_hour(conn: psycopg.Connection) -> datetime | None:
    return conn.execute("SELECT max(hour) FROM jamming_cell").fetchone()[0]


def last_coverage_hour(conn: psycopg.Connection) -> datetime | None:
    return conn.execute("SELECT max(hour) FROM coverage_hourly").fetchone()[0]


def upsert_coverage(conn: psycopg.Connection, hour: datetime, counts: dict[str, int]) -> None:
    if not counts:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO coverage_hourly (hour, h3, n_reports) VALUES (%s, %s, %s)
               ON CONFLICT (hour, h3) DO UPDATE SET n_reports = EXCLUDED.n_reports""",
            [(hour, cell, n) for cell, n in counts.items()],
        )


def insert_d1_samples(conn: psycopg.Connection, samples: list[tuple[str, datetime, bool, dict]]) -> None:
    if not samples:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO d1_sample (hex, evaluated_at, alerted, inputs) VALUES (%s, %s, %s, %s)
               ON CONFLICT (hex, evaluated_at) DO NOTHING""",
            [(hex_, at, alerted, json.dumps(inputs)) for hex_, at, alerted, inputs in samples],
        )


def insert_alerts(conn: psycopg.Connection, detector: str, candidates: list[DarkCandidate]) -> int:
    inserted = 0
    for c in candidates:
        cur = conn.execute(
            """INSERT INTO alert (detector, entity_id, started_at, lat, lon, score, evidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (detector, c.hex, c.last_seen, c.lat, c.lon, c.score, json.dumps(c.evidence)),
        )
        inserted += cur.rowcount
    return inserted
```

`src/python/wachta_detectors/run.py`:
```python
"""Detector loop: D1 every minute, D3 (current hour) every 10 minutes, coverage for the previous hour once per hour."""
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from wachta_detectors import repository as repo
from wachta_detectors.airports import load_airports
from wachta_detectors.coverage import COVERAGE_RESOLUTION, count_reports
from wachta_detectors.dark import find_dark_candidates, silent_aircraft, snapshot_inputs
from wachta_detectors.jamming import aggregate_jamming

log = logging.getLogger("wachta.detectors")
TICK_SECONDS = 60


def run_d1(conn, airports, now):
    last_seen = repo.last_seen_since(conn, now - timedelta(minutes=35))
    coverage = repo.coverage_last_days(conn)
    alive = repo.alive_cells(conn, now - timedelta(minutes=2))
    candidates = find_dark_candidates(last_seen, coverage, alive, airports, now)
    alerted = {c.hex for c in candidates}

    # Freeze inputs for every silent aircraft, alerted or not — this is what recall is measured on.
    samples = [(s.hex, now, s.hex in alerted, snapshot_inputs(s, coverage, alive, airports, now))
               for s in silent_aircraft(last_seen, now)]
    repo.insert_d1_samples(conn, samples)
    log.info("D1: %d aircraft checked, %d silent, %d new alerts",
             len(last_seen), len(samples), repo.insert_alerts(conn, "D1", candidates))


def hour_of(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def run_d3(conn, now, max_catchup_hours=48):
    """Finalise every closed hour we have not computed yet, then refresh the current (partial) hour."""
    current = hour_of(now)
    last_done = repo.last_jamming_hour(conn)
    hour = max(last_done, current - timedelta(hours=max_catchup_hours)) if last_done else current
    finalised = 0
    while hour < current:
        repo.replace_jamming(conn, hour, aggregate_jamming(repo.positions_between(conn, hour, hour + timedelta(hours=1))))
        hour += timedelta(hours=1)
        finalised += 1
    cells = aggregate_jamming(repo.positions_between(conn, current, now))
    repo.replace_jamming(conn, current, cells)
    log.info("D3: %d closed hours recomputed, current hour %d cells, %d high",
             finalised, len(cells), sum(c.level == "high" for c in cells))


def run_coverage(conn, now, max_catchup_hours=48):
    current = hour_of(now)
    last_done = repo.last_coverage_hour(conn)
    hour = (last_done + timedelta(hours=1)) if last_done else current - timedelta(hours=1)
    hour = max(hour, current - timedelta(hours=max_catchup_hours))
    while hour < current:
        repo.upsert_coverage(conn, hour, count_reports(repo.positions_between(conn, hour, hour + timedelta(hours=1))))
        log.info("coverage: hour %s done", hour)
        hour += timedelta(hours=1)


def tick(conn, airports, now, last_d3):
    run_d1(conn, airports, now)
    run_coverage(conn, now)
    if last_d3 is None or now - last_d3 >= timedelta(minutes=10):
        run_d3(conn, now)
        return now
    return last_d3


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    airports = load_airports(Path(os.environ.get("AIRPORTS_CSV", "data/airports.csv")))
    last_d3 = None
    while True:
        now = datetime.now(timezone.utc)
        try:
            # New connection each tick: a database restart must not silently kill the detectors forever.
            with psycopg.connect(os.environ["WACHTA_DB"], autocommit=True, connect_timeout=10) as conn:
                last_d3 = tick(conn, airports, now, last_d3)
        except psycopg.Error:
            log.exception("detector tick failed, retrying next tick")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
```

`infra/docker/python.Dockerfile`:
```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY src/python/pyproject.toml src/python/uv.lock ./
RUN uv sync --frozen --no-dev
COPY src/python/ .
ADD https://davidmegginson.github.io/ourairports-data/airports.csv data/airports.csv
CMD ["uv", "run", "--no-dev", "python", "-m", "wachta_detectors.run"]
```

`compose.yaml` — dodaj:
```yaml
  detectors:
    build: { context: ., dockerfile: infra/docker/python.Dockerfile }
    environment:
      WACHTA_DB: postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/wachta
    restart: unless-stopped
    depends_on: { migrator: { condition: service_completed_successfully } }
```

- [ ] **Step 4: Uruchom testy**

Run: `cd src/python && uv run pytest -q`
Expected: wszystkie zielone (jednostkowe + 4 integracyjne).

- [ ] **Step 5: Weryfikacja na żywo** — `docker compose up -d --build detectors` → `docker compose logs -f detectors`. Oczekuj co minutę linii `D1: ... aircraft checked` i co 10 min `D3: ... cells`. Uwaga: przez pierwsze godziny D1 nie zgłosi nic, bo model pokrycia potrzebuje danych (`min_cell_reports=200`). To oczekiwane — wpisz to w README.

- [ ] **Step 6: Commit** — `feat(detectors): repository, runner loop and docker service`.

### Task 1.11: API — alarmy, heksy zakłóceń, odtwarzanie

**Files:**
- Create: `src/dotnet/Wachta.Api/DetectorEndpoints.cs`
- Modify: `src/dotnet/Wachta.Api/Dtos.cs`, `src/dotnet/Wachta.Api/Program.cs`, `src/dotnet/Wachta.Api/LiveBroadcaster.cs`
- Test: `src/dotnet/Wachta.Tests/ApiTests.cs` (dopisz testy)

**Interfaces:**
- Produces:
  - `GET /api/alerts?since=ISO` → `AlertDto[]` (max 200, najnowsze pierwsze; domyślnie 24 h)
  - `GET /api/jamming?at=ISO` → `JammingDto[]` (godzina zawierająca `at`; domyślnie bieżąca)
  - `GET /api/replay?from=ISO&to=ISO&militaryOnly=true` → `ReplayPath[]` (okno max 6 h; punkty co ≥ 30 s na samolot)
  - `record AlertDto(long Id, string Detector, string EntityId, DateTime StartedAt, double Lat, double Lon, float Score, string Evidence, string State)`
  - `record JammingDto(string H3, int NAircraft, int NDegraded)`
  - `record ReplayPath(string Hex, string? Flight, string? TypeCode, double[][] Path, long[] Timestamps)` — `Path[i] = [lon, lat]`, `Timestamps[i]` = sekundy Unix
  - SignalR: `"alerts"` z `AlertDto[]` nowych od ostatniego ticku.

- [ ] **Step 1: Testy (failing)** — dopisz do `ApiTests`:

W `InitializeAsync` na końcu:
```csharp
await using var seed = new NpgsqlCommand("""
    DELETE FROM alert WHERE entity_id = 'api001';
    INSERT INTO alert (detector, entity_id, started_at, lat, lon, score, evidence)
    VALUES ('D1', 'api001', now() - interval '10 minutes', 55.1, 19.2, 0.9, '{"note":"test"}')
    ON CONFLICT DO NOTHING;
    INSERT INTO jamming_cell (hour, h3, n_aircraft, n_degraded)
    VALUES (date_trunc('hour', now()), '841f053ffffffff', 20, 5)
    ON CONFLICT DO NOTHING;
    """, conn);
await seed.ExecuteNonQueryAsync();
```

Nowe testy:
```csharp
[Fact]
public async Task Alerts_returns_recent_alerts_with_evidence()
{
    var alerts = await _client.GetFromJsonAsync<List<AlertDto>>("/api/alerts");
    var a = Assert.Single(alerts!, x => x.EntityId == "api001");
    Assert.Equal("D1", a.Detector);
    Assert.Contains("note", a.Evidence);
}

[Fact]
public async Task Jamming_returns_cells_for_current_hour()
{
    var cells = await _client.GetFromJsonAsync<List<JammingDto>>("/api/jamming");
    Assert.Contains(cells!, c => c.H3 == "841f053ffffffff" && c.NDegraded == 5);
}

[Fact]
public async Task Replay_groups_points_per_aircraft_in_time_order()
{
    var from = DateTime.UtcNow.AddMinutes(-5).ToString("O");
    var to = DateTime.UtcNow.ToString("O");
    var paths = await _client.GetFromJsonAsync<List<ReplayPath>>($"/api/replay?from={from}&to={to}&militaryOnly=true");
    var p = Assert.Single(paths!, x => x.Hex == "api001");
    Assert.Equal(p.Path.Length, p.Timestamps.Length);
    Assert.Equal(new[] { 19.0, 55.0 }, p.Path[0]);
    Assert.DoesNotContain(paths!, x => x.Hex == "api002");
}

[Fact]
public async Task Replay_window_over_6h_is_rejected()
{
    var res = await _client.GetAsync($"/api/replay?from={DateTime.UtcNow.AddHours(-7):O}&to={DateTime.UtcNow:O}");
    Assert.Equal(HttpStatusCode.BadRequest, res.StatusCode);
}
```

- [ ] **Step 2: Uruchom — ma nie przejść** — `dotnet test --filter ApiTests` → FAIL (kompilacja).

- [ ] **Step 3: Implementacja**

`src/dotnet/Wachta.Api/Dtos.cs` — dopisz:
```csharp
public sealed record AlertDto(long Id, string Detector, string EntityId, DateTime StartedAt, double Lat, double Lon, float Score, string Evidence, string State);

public sealed record JammingDto(string H3, int NAircraft, int NDegraded);

public sealed record ReplayPath(string Hex, string? Flight, string? TypeCode, double[][] Path, long[] Timestamps);
```

`src/dotnet/Wachta.Api/DetectorEndpoints.cs`:
```csharp
using Dapper;
using Npgsql;

namespace Wachta.Api;

public static class DetectorEndpoints
{
    public const string AlertsSql = """
        SELECT id AS Id, detector AS Detector, entity_id AS EntityId, started_at AS StartedAt, lat AS Lat, lon AS Lon,
               score AS Score, evidence::text AS Evidence, state AS State
        FROM alert WHERE created_at > @since ORDER BY created_at DESC LIMIT 200
        """;

    private sealed record ReplayRow(string Hex, string? Flight, string? TypeCode, double Lon, double Lat, DateTime Ts);

    public static void MapDetectorEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapGet("/api/alerts", async (NpgsqlDataSource db, DateTime? since) =>
        {
            await using var conn = await db.OpenConnectionAsync();
            return await conn.QueryAsync<AlertDto>(AlertsSql, new { since = (since ?? DateTime.UtcNow.AddDays(-1)).ToUniversalTime() });
        });

        app.MapGet("/api/jamming", async (NpgsqlDataSource db, DateTime? at) =>
        {
            await using var conn = await db.OpenConnectionAsync();
            return await conn.QueryAsync<JammingDto>("""
                SELECT h3 AS H3, n_aircraft AS NAircraft, n_degraded AS NDegraded
                FROM jamming_cell WHERE hour = date_trunc('hour', @at::timestamptz)
                """, new { at = (at ?? DateTime.UtcNow).ToUniversalTime() });
        });

        app.MapGet("/api/replay", async (NpgsqlDataSource db, DateTime from, DateTime to, bool? militaryOnly) =>
        {
            if (to <= from || to - from > TimeSpan.FromHours(6))
            {
                return Results.BadRequest("Window must be positive and at most 6 h.");
            }

            await using var conn = await db.OpenConnectionAsync();
            var rows = await conn.QueryAsync<ReplayRow>("""
                SELECT DISTINCT ON (hex, time_bucket('30 seconds', ts))
                       hex AS Hex, flight AS Flight, type_code AS TypeCode, lon AS Lon, lat AS Lat, ts AS Ts
                FROM aircraft_position
                WHERE ts BETWEEN @from AND @to AND NOT on_ground AND (NOT @mil OR is_military)
                ORDER BY hex, time_bucket('30 seconds', ts), ts
                """, new { from = from.ToUniversalTime(), to = to.ToUniversalTime(), mil = militaryOnly ?? true });

            var paths = rows.GroupBy(r => r.Hex).Select(g =>
            {
                var pts = g.OrderBy(r => r.Ts).ToList();
                var last = pts[^1];
                return new ReplayPath(g.Key, last.Flight, last.TypeCode,
                    pts.Select(r => new[] { r.Lon, r.Lat }).ToArray(),
                    pts.Select(r => new DateTimeOffset(DateTime.SpecifyKind(r.Ts, DateTimeKind.Utc)).ToUnixTimeSeconds()).ToArray());
            });
            return Results.Ok(paths);
        });
    }
}
```

`src/dotnet/Wachta.Api/Program.cs` — po `app.MapAircraftEndpoints();` dodaj `app.MapDetectorEndpoints();`.

`src/dotnet/Wachta.Api/LiveBroadcaster.cs` — w klasie dodaj pole `private DateTime _alertsSince = DateTime.UtcNow;` i w bloku `try` po wysłaniu `"aircraft"`:
```csharp
var tickStart = DateTime.UtcNow;
var alerts = (await conn.QueryAsync<AlertDto>(DetectorEndpoints.AlertsSql, new { since = _alertsSince })).ToList();
if (alerts.Count > 0)
{
    await hub.Clients.All.SendAsync("alerts", alerts, ct);
}
_alertsSince = tickStart;
```

- [ ] **Step 4: Uruchom — ma przejść** — `dotnet test` (wszystkie testy .NET) → PASS.
- [ ] **Step 5: Commit** — `feat(api): alerts, jamming and replay endpoints; push alerts over signalr`.

### Task 1.12: Mapa — samoloty na żywo

**Files:**
- Create: `web/src/api.ts`, `web/src/live.ts`, `web/src/colors.ts`, `web/src/layers/aircraft.ts`, `web/src/components/MapView.tsx`
- Modify: `web/src/App.tsx`, `web/src/main.tsx`, `web/vite.config.ts`, `web/index.html`
- Delete: `web/src/App.css`, `web/src/index.css`, `web/src/assets/`, `web/src/smoke.test.ts`
- Test: `web/src/colors.test.ts`

**Interfaces:**
- Consumes: `/api/*`, `/hubs/live` (1.5, 1.6, 1.11).
- Produces:
  - `api.ts`: typy `LiveAircraft`, `AlertDto`, `JammingDto`, `ReplayPath`, `SourceInfo` (camelCase jak JSON z API) + `getJSON<T>(path: string): Promise<T>`
  - `live.ts`: `useLive(): { aircraft: LiveAircraft[]; alerts: AlertDto[]; setAlerts: Dispatch<SetStateAction<AlertDto[]>>; connected: boolean }`
  - `colors.ts`: `aircraftColor(a: LiveAircraft): [number, number, number]`, `jammingColor(pct: number): [number, number, number, number]`
  - `layers/aircraft.ts`: `aircraftLayers(data: LiveAircraft[]): Layer[]`
  - `MapView` props: `{ layers: Layer[]; viewState?: MapViewState; onViewStateChange?: (v: MapViewState) => void }`

- [ ] **Step 1: Test (failing)**

`web/src/colors.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { aircraftColor, jammingColor } from "./colors";
import type { LiveAircraft } from "./api";

const base: LiveAircraft = {
  hex: "a", flight: null, typeCode: null, isMilitary: false, lat: 0, lon: 0,
  altBaroFt: 30000, onGround: false, gsKt: 400, trackDeg: 0, ts: "2026-09-22T12:00:00Z",
};

describe("aircraftColor", () => {
  it("military is red, civil is grey", () => {
    expect(aircraftColor({ ...base, isMilitary: true })).toEqual([230, 57, 70]);
    expect(aircraftColor(base)).toEqual([150, 160, 170]);
  });
});

describe("jammingColor", () => {
  it("follows gpsjam thresholds", () => {
    expect(jammingColor(0.01)[3]).toBe(0);
    expect(jammingColor(0.05)).toEqual([255, 190, 0, 110]);
    expect(jammingColor(0.2)).toEqual([230, 57, 70, 150]);
  });
});
```

- [ ] **Step 2: Uruchom — ma nie przejść** — `cd web && npm test` → FAIL (`Cannot find module './colors'`).

- [ ] **Step 3: Implementacja**

`web/src/api.ts`:
```ts
export interface LiveAircraft {
  hex: string; flight: string | null; typeCode: string | null; isMilitary: boolean;
  lat: number; lon: number; altBaroFt: number | null; onGround: boolean;
  gsKt: number | null; trackDeg: number | null; ts: string;
}
export interface AlertDto {
  id: number; detector: string; entityId: string; startedAt: string;
  lat: number; lon: number; score: number; evidence: string; state: string;
}
export interface JammingDto { h3: string; nAircraft: number; nDegraded: number }
export interface ReplayPath { hex: string; flight: string | null; typeCode: string | null; path: [number, number][]; timestamps: number[] }
export interface SourceInfo { id: string; name: string; url: string; license: string; trustTier: number; attribution: string }

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}
```

`web/src/colors.ts`:
```ts
import type { LiveAircraft } from "./api";

export const RED: [number, number, number] = [230, 57, 70];
export const GREY: [number, number, number] = [150, 160, 170];

export function aircraftColor(a: LiveAircraft): [number, number, number] {
  return a.isMilitary ? RED : GREY;
}

/** gpsjam.org thresholds: < 2% low (transparent), 2–10% medium (amber), >= 10% high (red). */
export function jammingColor(pct: number): [number, number, number, number] {
  if (pct >= 0.1) return [230, 57, 70, 150];
  if (pct >= 0.02) return [255, 190, 0, 110];
  return [0, 0, 0, 0];
}
```

`web/src/live.ts`:
```ts
import { useEffect, useState } from "react";
import { HubConnectionBuilder, LogLevel } from "@microsoft/signalr";
import type { AlertDto, LiveAircraft } from "./api";

export function useLive() {
  const [aircraft, setAircraft] = useState<LiveAircraft[]>([]);
  const [alerts, setAlerts] = useState<AlertDto[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const hub = new HubConnectionBuilder().withUrl("/hubs/live").withAutomaticReconnect().configureLogging(LogLevel.Warning).build();
    hub.on("aircraft", (list: LiveAircraft[]) => setAircraft(list));
    hub.on("alerts", (list: AlertDto[]) => setAlerts((prev) => [...list, ...prev].slice(0, 200)));
    hub.onreconnecting(() => setConnected(false));
    hub.onreconnected(() => setConnected(true));
    hub.start().then(() => setConnected(true)).catch(() => setConnected(false));
    return () => { void hub.stop(); };
  }, []);

  return { aircraft, alerts, setAlerts, connected };
}
```

`web/src/layers/aircraft.ts`:
```ts
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveAircraft } from "../api";
import { aircraftColor } from "../colors";

export function aircraftLayers(data: LiveAircraft[]): Layer[] {
  const airborne = data.filter((a) => !a.onGround);
  return [
    new ScatterplotLayer<LiveAircraft>({
      id: "aircraft",
      data: airborne,
      getPosition: (a) => [a.lon, a.lat],
      getFillColor: (a) => aircraftColor(a),
      getRadius: (a) => (a.isMilitary ? 6 : 3),
      radiusUnits: "pixels",
      pickable: true,
    }),
    new TextLayer<LiveAircraft>({
      id: "aircraft-labels",
      data: airborne.filter((a) => a.isMilitary),
      getPosition: (a) => [a.lon, a.lat],
      getText: (a) => `${a.flight ?? a.hex} ${a.typeCode ?? ""}`.trim(),
      getSize: 11,
      getColor: [240, 240, 240],
      getPixelOffset: [0, -14],
    }),
  ];
}
```

`web/src/components/MapView.tsx`:
```tsx
import DeckGL from "@deck.gl/react";
import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

export const BALTIC_VIEW: MapViewState = { longitude: 20, latitude: 57, zoom: 5 };
const STYLE = "https://tiles.openfreemap.org/styles/positron";

interface Props {
  layers: Layer[];
  viewState?: MapViewState;
  onViewStateChange?: (v: MapViewState) => void;
}

function tooltip({ object }: PickingInfo) {
  if (!object) return null;
  if ("hex" in object) return `${object.flight ?? object.hex} · ${object.typeCode ?? "?"} · ${object.altBaroFt ?? "?"} ft`;
  if ("detector" in object) return `${object.detector} · ${object.entityId} · wynik ${object.score}`;
  return null;
}

export function MapView({ layers, viewState, onViewStateChange }: Props) {
  return (
    <DeckGL
      initialViewState={viewState ? undefined : BALTIC_VIEW}
      viewState={viewState}
      onViewStateChange={onViewStateChange ? ({ viewState: v }) => onViewStateChange(v as MapViewState) : undefined}
      controller
      layers={layers}
      getTooltip={tooltip}
    >
      <Map mapStyle={STYLE} />
    </DeckGL>
  );
}
```

`web/src/App.tsx`:
```tsx
import { MapView } from "./components/MapView";
import { aircraftLayers } from "./layers/aircraft";
import { useLive } from "./live";

export default function App() {
  const { aircraft, connected } = useLive();
  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <MapView layers={aircraftLayers(aircraft)} />
      <div className="status">{connected ? `na żywo · ${aircraft.length} samolotów` : "łączenie…"}</div>
    </div>
  );
}
```

`web/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
```

`web/src/styles.css`:
```css
:root {
  color-scheme: dark;
  font-family: system-ui, sans-serif;
}

body {
  margin: 0;
  background: #0d1117;
  color: #e6edf3;
}

.status {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 6px 10px;
  background: #0d1117cc;
  border-radius: 6px;
  font-size: 13px;
}

.panel {
  position: absolute;
  top: 12px;
  left: 12px;
  bottom: 48px;
  width: 340px;
  overflow-y: auto;
  background: #0d1117e6;
  border-radius: 8px;
  padding: 12px;
}

.panel h2 {
  font-size: 15px;
  margin: 0 0 8px;
}

.panel ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

.panel button {
  width: 100%;
  text-align: left;
  background: none;
  border: 0;
  border-bottom: 1px solid #30363d;
  color: inherit;
  padding: 8px 0;
  cursor: pointer;
  font: inherit;
}

.muted {
  color: #8b949e;
  font-size: 12px;
}

.legend {
  position: absolute;
  top: 48px;
  right: 12px;
  padding: 6px 10px;
  background: #0d1117cc;
  border-radius: 6px;
  font-size: 12px;
}

.legend i {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin: 0 4px 0 8px;
}

.legend .amber {
  background: rgb(255 190 0 / 0.6);
}

.legend .red {
  background: rgb(230 57 70 / 0.7);
}

.replay {
  position: absolute;
  left: 364px;
  right: 12px;
  bottom: 36px;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: #0d1117e6;
  border-radius: 8px;
  font-size: 13px;
}

.replay input {
  flex: 1;
}

.replay button {
  background: #21262d;
  color: inherit;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
}

.sources {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 6px 12px;
  background: #0d1117cc;
  font-size: 11px;
  color: #8b949e;
}
```

`web/vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // MapLibre renderuje w web workerze; przy prebundlowaniu zależności przez Vite worker nie startuje
  // („Worker failed to load”) i mapa zostaje pusta — sprawdzone 2026-09-26 w tym projekcie.
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: {
    proxy: {
      "/api": "http://localhost:8080",
      "/hubs": { target: "http://localhost:8080", ws: true },
    },
  },
});
```

W `web/index.html` ustaw `<title>WACHTA</title>`. Usuń pliki wymienione w „Delete”.

**Pułapka MapLibre (zmierzona 2026-09-26):** każda warstwa `symbol` musi mieć jawne
`"text-font": ["Noto Sans Regular"]`. Bez tego MapLibre prosi o domyślną „Open Sans Regular”,
której podkład OpenFreeMap nie serwuje, a nieudane pobranie glifów wyłącza renderowanie **całego
źródła** — nie tylko podpisów. Objaw: warstwa ma dane, kafle są „załadowane”, konsola milczy,
a na mapie nie ma nic.

- [ ] **Step 4: Testy + build** — `cd web && npm test && npm run build` → PASS, build OK.

- [ ] **Step 5: Weryfikacja wzrokowa** — przy działającym `docker compose up -d` (db, ingestion, api): `cd web && npm run dev` → http://localhost:5173. Oczekuj: mapa Bałtyku, szare kropki (cywilne), czerwone z podpisem (wojskowe), odświeżanie co 5 s, status „na żywo · N samolotów”. Zrób zrzut ekranu i pokaż użytkownikowi.

- [ ] **Step 6: Commit** — `feat(web): live aircraft map with signalr`.

### Task 1.13: Mapa — heksy GPS, panel alarmów, stopka źródeł

**Files:**
- Create: `web/src/layers/jamming.ts`, `web/src/layers/alerts.ts`, `web/src/components/AlertsPanel.tsx`, `web/src/components/SourcesFooter.tsx`
- Modify: `web/src/App.tsx`, `web/src/styles.css`
- Test: `web/src/colors.test.ts` (bez zmian — kolory już przetestowane), ręczna weryfikacja

**Interfaces:**
- Consumes: `jammingColor`, `JammingDto`, `AlertDto`, `SourceInfo`, `useLive`.
- Produces: `jammingLayer(cells: JammingDto[]): Layer`, `alertsLayer(alerts: AlertDto[]): Layer`, `AlertsPanel({ alerts, onSelect })`, `SourcesFooter()`.

- [ ] **Step 1: Implementacja**

`web/src/layers/jamming.ts`:
```ts
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import type { JammingDto } from "../api";
import { jammingColor } from "../colors";

export function jammingLayer(cells: JammingDto[]) {
  return new H3HexagonLayer<JammingDto>({
    id: "jamming",
    data: cells,
    getHexagon: (c) => c.h3,
    getFillColor: (c) => jammingColor(c.nDegraded / c.nAircraft),
    extruded: false,
    stroked: false,
    pickable: false,
  });
}
```

`web/src/layers/alerts.ts`:
```ts
import { ScatterplotLayer } from "@deck.gl/layers";
import type { AlertDto } from "../api";

export function alertsLayer(alerts: AlertDto[]) {
  return new ScatterplotLayer<AlertDto>({
    id: "alerts",
    data: alerts,
    getPosition: (a) => [a.lon, a.lat],
    getRadius: 14,
    radiusUnits: "pixels",
    stroked: true,
    filled: false,
    getLineColor: [255, 190, 0],
    lineWidthMinPixels: 2,
    pickable: true,
  });
}
```

`web/src/components/AlertsPanel.tsx`:
```tsx
import type { AlertDto } from "../api";

const LABELS: Record<string, string> = { D1: "Zgaszony transponder" };

export function AlertsPanel({ alerts, onSelect }: { alerts: AlertDto[]; onSelect: (a: AlertDto) => void }) {
  return (
    <aside className="panel">
      <h2>Alarmy (do sprawdzenia)</h2>
      {alerts.length === 0 && <p className="muted">Brak alarmów z ostatnich 24 h.</p>}
      <ul>
        {alerts.map((a) => {
          const ev = JSON.parse(a.evidence) as { flight?: string; type_code?: string; gap_minutes?: number };
          return (
            <li key={a.id}>
              <button onClick={() => onSelect(a)}>
                <strong>{LABELS[a.detector] ?? a.detector}</strong> · {ev.flight ?? a.entityId} {ev.type_code ?? ""}
                <br />
                <span className="muted">
                  {new Date(a.startedAt).toLocaleString("pl-PL")} · luka {ev.gap_minutes ?? "?"} min · wynik {a.score}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
```

`web/src/components/SourcesFooter.tsx`:
```tsx
import { useEffect, useState } from "react";
import { getJSON, type SourceInfo } from "../api";

export function SourcesFooter() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  useEffect(() => { getJSON<SourceInfo[]>("/api/sources").then(setSources).catch(() => setSources([])); }, []);
  const attributions = [...new Set(sources.map((s) => s.attribution))];
  return (
    <footer className="sources">
      Źródła: {attributions.join(" · ")} · Podkład: OpenFreeMap, © OpenStreetMap contributors
    </footer>
  );
}
```

`web/src/App.tsx`:
```tsx
import { useEffect, useState } from "react";
import type { MapViewState } from "@deck.gl/core";
import { getJSON, type AlertDto, type JammingDto } from "./api";
import { AlertsPanel } from "./components/AlertsPanel";
import { BALTIC_VIEW, MapView } from "./components/MapView";
import { SourcesFooter } from "./components/SourcesFooter";
import { aircraftLayers } from "./layers/aircraft";
import { alertsLayer } from "./layers/alerts";
import { jammingLayer } from "./layers/jamming";
import { useLive } from "./live";

export default function App() {
  const { aircraft, alerts, setAlerts, connected } = useLive();
  const [jamming, setJamming] = useState<JammingDto[]>([]);
  const [view, setView] = useState<MapViewState>(BALTIC_VIEW);

  useEffect(() => {
    getJSON<AlertDto[]>("/api/alerts").then(setAlerts).catch(() => undefined);
    const load = () => getJSON<JammingDto[]>("/api/jamming").then(setJamming).catch(() => undefined);
    load();
    const id = setInterval(load, 10 * 60 * 1000);
    return () => clearInterval(id);
  }, [setAlerts]);

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <MapView
        layers={[jammingLayer(jamming), ...aircraftLayers(aircraft), alertsLayer(alerts)]}
        viewState={view}
        onViewStateChange={setView}
      />
      <AlertsPanel alerts={alerts} onSelect={(a) => setView({ ...view, longitude: a.lon, latitude: a.lat, zoom: 8 })} />
      <div className="status">{connected ? `na żywo · ${aircraft.length} samolotów` : "łączenie…"}</div>
      <div className="legend">GPS: <i className="amber" /> 2–10% zakłóconych <i className="red" /> ≥ 10%</div>
      <SourcesFooter />
    </div>
  );
}
```

Style panelu, legendy, paska odtwarzania i stopki są już w pełnym `styles.css` z zadania T1.12 — nic nie dopisujesz.

- [ ] **Step 2: Testy + build** — `npm test && npm run build` → PASS.
- [ ] **Step 3: Weryfikacja wzrokowa** — heksy wokół Kaliningradu (bursztynowe/czerwone), panel alarmów (pusty przez pierwsze godziny — oczekiwane), stopka z atrybucją ODbL. Kliknięcie alarmu centruje mapę. Zrzut dla użytkownika.
- [ ] **Step 4: Commit** — `feat(web): jamming hexes, alerts panel, sources footer`.

### Task 1.14: Suwak czasu (ostatnie 6 h)

**Files:**
- Create: `web/src/replay.ts`, `web/src/layers/trips.ts`, `web/src/components/ReplayBar.tsx`
- Modify: `web/src/App.tsx`
- Test: `web/src/replay.test.ts`

**Interfaces:**
- Consumes: `ReplayPath`, `GET /api/replay`.
- Produces:
  - `replay.ts`: `replayBounds(paths: ReplayPath[]): { start: number; end: number } | null`; `toTrips(paths: ReplayPath[], start: number): Trip[]` gdzie `Trip = { hex: string; label: string; path: [number, number][]; timestamps: number[] }` a `timestamps` są względne (sekundy od `start`).
  - `tripsLayer(trips: Trip[], currentTime: number): Layer`
  - `ReplayBar({ onLoad, currentTime, setCurrentTime, max, playing, setPlaying })`

- [ ] **Step 1: Test (failing)**

`web/src/replay.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { replayBounds, toTrips } from "./replay";
import type { ReplayPath } from "./api";

const paths: ReplayPath[] = [
  { hex: "a", flight: "FORTE10", typeCode: "Q4", path: [[30, 45], [30.1, 45.1]], timestamps: [1000, 1030] },
  { hex: "b", flight: null, typeCode: "K35R", path: [[20, 55]], timestamps: [1010] },
];

describe("replay", () => {
  it("computes global time bounds", () => {
    expect(replayBounds(paths)).toEqual({ start: 1000, end: 1030 });
    expect(replayBounds([])).toBeNull();
  });

  it("makes timestamps relative and builds labels", () => {
    const trips = toTrips(paths, 1000);
    expect(trips[0].timestamps).toEqual([0, 30]);
    expect(trips[0].label).toBe("FORTE10 Q4");
    expect(trips[1].label).toBe("b K35R");
  });
});
```

- [ ] **Step 2: Uruchom — ma nie przejść** — `npm test` → FAIL.

- [ ] **Step 3: Implementacja**

`web/src/replay.ts`:
```ts
import type { ReplayPath } from "./api";

export interface Trip { hex: string; label: string; path: [number, number][]; timestamps: number[] }

export function replayBounds(paths: ReplayPath[]): { start: number; end: number } | null {
  // No spread: 6 h of Baltic traffic is ~300k timestamps and Math.min(...all) blows the call stack.
  let start = Infinity;
  let end = -Infinity;
  for (const p of paths) {
    for (const t of p.timestamps) {
      if (t < start) start = t;
      if (t > end) end = t;
    }
  }
  return start === Infinity ? null : { start, end };
}

export function toTrips(paths: ReplayPath[], start: number): Trip[] {
  return paths.map((p) => ({
    hex: p.hex,
    label: `${p.flight ?? p.hex} ${p.typeCode ?? ""}`.trim(),
    path: p.path,
    timestamps: p.timestamps.map((t) => t - start),
  }));
}
```

`web/src/layers/trips.ts`:
```ts
import { TripsLayer } from "@deck.gl/geo-layers";
import type { Trip } from "../replay";
import { RED } from "../colors";

export function tripsLayer(trips: Trip[], currentTime: number) {
  return new TripsLayer<Trip>({
    id: "trips",
    data: trips,
    getPath: (t) => t.path,
    getTimestamps: (t) => t.timestamps,
    getColor: RED,
    widthMinPixels: 2,
    trailLength: 1800,
    currentTime,
    pickable: false,
  });
}
```

`web/src/components/ReplayBar.tsx`:
```tsx
interface Props {
  active: boolean;
  onToggle: () => void;
  currentTime: number;
  max: number;
  setCurrentTime: (t: number) => void;
  playing: boolean;
  setPlaying: (p: boolean) => void;
  startEpoch: number | null;
}

export function ReplayBar({ active, onToggle, currentTime, max, setCurrentTime, playing, setPlaying, startEpoch }: Props) {
  const clock = startEpoch ? new Date((startEpoch + currentTime) * 1000).toLocaleTimeString("pl-PL") : "";
  return (
    <div className="replay">
      <button onClick={onToggle}>{active ? "Wróć na żywo" : "Odtwórz ostatnie 6 h"}</button>
      {active && (
        <>
          <button onClick={() => setPlaying(!playing)}>{playing ? "Pauza" : "Start"}</button>
          <input type="range" min={0} max={max} value={currentTime} onChange={(e) => setCurrentTime(Number(e.target.value))} />
          <span>{clock}</span>
        </>
      )}
    </div>
  );
}
```

`web/src/App.tsx` — dodaj stan i logikę odtwarzania:
```tsx
// dodatkowe importy
import { ReplayBar } from "./components/ReplayBar";
import { tripsLayer } from "./layers/trips";
import { replayBounds, toTrips, type Trip } from "./replay";
import type { ReplayPath } from "./api";

// w komponencie App, obok istniejących useState:
const [replay, setReplay] = useState<{ trips: Trip[]; start: number; max: number } | null>(null);
const [currentTime, setCurrentTime] = useState(0);
const [playing, setPlaying] = useState(false);

useEffect(() => {
  if (!playing || !replay) return;
  const id = setInterval(() => setCurrentTime((t) => (t + 60 > replay.max ? 0 : t + 60)), 100);
  return () => clearInterval(id);
}, [playing, replay]);

const toggleReplay = async () => {
  if (replay) { setReplay(null); setPlaying(false); return; }
  const to = new Date();
  const from = new Date(to.getTime() - 6 * 3600 * 1000);
  const paths = await getJSON<ReplayPath[]>(`/api/replay?from=${from.toISOString()}&to=${to.toISOString()}&militaryOnly=true`);
  const bounds = replayBounds(paths);
  if (!bounds) return;
  setReplay({ trips: toTrips(paths, bounds.start), start: bounds.start, max: bounds.end - bounds.start });
  setCurrentTime(0);
  setPlaying(true);
};

const layers = replay
  ? [jammingLayer(jamming), tripsLayer(replay.trips, currentTime), alertsLayer(alerts)]
  : [jammingLayer(jamming), ...aircraftLayers(aircraft), alertsLayer(alerts)];
```
Przekaż `layers={layers}` do `MapView` i dodaj przed `<SourcesFooter />`:
```tsx
<ReplayBar active={!!replay} onToggle={toggleReplay} currentTime={currentTime} max={replay?.max ?? 0}
  setCurrentTime={setCurrentTime} playing={playing} setPlaying={setPlaying} startEpoch={replay?.start ?? null} />
```

Style panelu, legendy, paska odtwarzania i stopki są już w pełnym `styles.css` z zadania T1.12 — nic nie dopisujesz.

- [ ] **Step 4: Testy + build** — `npm test && npm run build` → PASS.
- [ ] **Step 5: Weryfikacja wzrokowa** — „Odtwórz ostatnie 6 h” → czerwone smugi samolotów wojskowych, zegar biegnie; suwak przewija; „Wróć na żywo” przywraca kropki.
- [ ] **Step 6: Commit** — `feat(web): 6-hour replay with trips layer`.

### Task 1.15: Ewaluacja D1/D3 + bramka w pipeline [R]

**Files:**
- Create: `eval/label_d1.py`, `eval/run_eval.py`, `eval/baseline.json`, `eval/fixtures/d3_hour.json`, `eval/fixtures/d1_cases.jsonl`, `eval/results/.gitkeep`
- Modify: `azure-pipelines.yml` (stage `Eval`)

**Interfaces:**
- Consumes: `aggregate_jamming`, `Position`, `find_dark_candidates`, `LastSeen`, `DarkRules`, `COVERAGE_RESOLUTION`.
- Produces: `eval/results/latest.json` = `{"d3": {"precision": float, "recall": float}, "d1": {"precision": float, "recall": float, "n_cases": int}}`; `run_eval.py --check eval/baseline.json` kończy się kodem 1, gdy którakolwiek metryka spadnie o > 0,05 względem baseline.

**Etykiety D3 pochodzą z niezależnego źródła: dziennych plików H3 z gpsjam.org** (`count_good_aircraft`/`count_bad_aircraft`, inna implementacja i inny pipeline). Zamrożone w `d3_labels.json` jako listy `positive` i `negative`, więc detektor zwracający pustkę dostaje recall 0, a nie 1.

Pierwotny pomysł — etykietowanie odległością od Kaliningradu — **nie zadziałał na prawdziwych danych**: ognisko zakłóceń 2026-09-26 leżało na 56,2°N 21,3°E, ponad 200 km na północ, więc reguła dała zero etykiet dodatnich. Ograniczenia referencji (dzień wcześniejszy, cała doba wobec naszej jednej godziny) idą do README — recall liczony tak jest zaniżony.

Przypadki D1 (`d1_cases.jsonl`): jeden JSON na linię: `{"case": str, "last_seen": {...pola LastSeen, ts ISO...}, "now": ISO, "coverage": {cell: n}, "alive": [cell], "airports": [[lat, lon]], "expected": bool}`. Startowo: 9 scenariuszy z `test_dark.py` (zapisane jako dane). Po tygodniu zbierania: każdy alarm oznaczony przez użytkownika w `label_d1.py` jest dopisywany jako przypadek (wejścia są w `evidence`).

- [ ] **Step 1: Nagraj fixture D3 — godzina danych z bazy, nie pojedynczy odczyt**

Sprawdziłem to na prawdziwym odczycie z 22.09 (164 samoloty nad południowym Bałtykiem): przy produkcyjnym progu `min_aircraft=5` pojedynczy odczyt daje **zero komórek** — heks H3 res-4 ma ~1770 km², więc chwilowy ruch rozkłada się po kilka samolotów na komórkę. Produkcja agreguje całą godzinę, więc fixture musi wyglądać tak samo. Wymaga to działającego pobierania (T1.4), stąd to zadanie wykonujemy po co najmniej godzinie zbierania danych.

`eval/export_d3_fixture.py`:
```python
"""Exports one hour of positions from the database as the frozen D3 fixture."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

hour = datetime.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else (
    datetime.now(timezone.utc) - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
with psycopg.connect(os.environ["WACHTA_DB"]) as conn:
    rows = conn.execute(
        """SELECT hex, lat, lon, alt_baro_ft, on_ground, nac_p FROM aircraft_position
           WHERE ts >= %s AND ts < %s AND nac_p IS NOT NULL""",
        (hour, hour + timedelta(hours=1)),
    ).fetchall()

out = Path(__file__).parent / "fixtures" / "d3_hour.json"
out.write_text(json.dumps({"hour": hour.isoformat(), "positions": [
    {"hex": h, "lat": la, "lon": lo, "alt_ft": alt, "on_ground": g, "nac_p": n} for h, la, lo, alt, g, n in rows
]}), encoding="utf-8")
print(f"{len(rows)} positions from {hour:%Y-%m-%d %H:00} -> {out}")
```

Run: `uv run --project src/python python eval/export_d3_fixture.py`
Expected: dziesiątki tysięcy pozycji. Jeśli jest ich mniej niż 5000, zbieraj dane dłużej i powtórz.

W `run_eval.py` i `make_d3_labels.py` funkcja `load_snapshot_positions()` czyta ten plik:
```python
def load_snapshot_positions() -> list[Position]:
    raw = json.loads((FIX / "d3_hour.json").read_text(encoding="utf-8"))["positions"]
    now = datetime.now(timezone.utc)
    return [Position(p["hex"], p["lat"], p["lon"], p["alt_ft"], p["on_ground"], p["nac_p"], now) for p in raw]
```

- [ ] **Step 1b: Zaproponuj etykiety D3 i zatwierdź je**

`eval/make_d3_labels.py` — skrypt jest w repo (wersja z referencją gpsjam.org; poprzednia, oparta na odległości od Kaliningradu, dała zero etykiet na prawdziwych danych).

Run: `python eval/make_d3_labels.py [YYYY-MM-DD]` (domyślnie wczoraj — gpsjam publikuje z opóźnieniem).
**Przejrzyj wydruk**: dla każdej komórki dodatniej widać obok siebie wynik gpsjam i nasz. Wymagane minimum: 3 etykiety dodatnie i 10 ujemnych — skrypt sam kończy się błędem, jeśli ich nie ma.

- [ ] **Step 2: Fixture D1 — wygeneruj z testów**

`eval/make_d1_seed.py` (jednorazowy, commitowany dla powtarzalności):
```python
"""Writes the synthetic D1 seed cases (same scenarios as tests/test_dark.py) to eval/fixtures/d1_cases.jsonl."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "python"))
import h3  # noqa: E402

from wachta_detectors.coverage import COVERAGE_RESOLUTION  # noqa: E402

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
LAT, LON = 55.5, 17.5
CELL = h3.latlng_to_cell(LAT, LON, COVERAGE_RESOLUTION)
GOOD = {c: 1000 for c in h3.grid_disk(CELL, 2)}
FAR = [[54.3776, 18.4662]]


def case(name, expected, coverage=GOOD, alive=(CELL,), airports=FAR, **over):
    s = dict(hex="ae1234", flight="FORTE10", type_code="Q4", is_military=True, lat=LAT, lon=LON,
             alt_ft=30000, gs_kt=300.0, ts=(NOW - timedelta(minutes=10)).isoformat(), n_points=120,
             last_message_at=(NOW - timedelta(minutes=10)).isoformat())
    s.update(over)
    return {"case": name, "last_seen": s, "now": NOW.isoformat(), "coverage": coverage,
            "alive": list(alive), "airports": airports, "expected": expected}


cases = [
    case("dark_in_coverage", True),
    case("civil_dark_in_coverage", True, is_military=False, n_points=50),
    case("gap_too_recent", False, ts=(NOW - timedelta(minutes=2)).isoformat(),
         last_message_at=(NOW - timedelta(minutes=2)).isoformat()),
    case("gap_too_old", False, ts=(NOW - timedelta(minutes=45)).isoformat(),
         last_message_at=(NOW - timedelta(minutes=45)).isoformat()),
    case("jammed_but_still_transmitting", False, last_message_at=(NOW - timedelta(seconds=20)).isoformat()),
    case("low_altitude", False, alt_ft=1500),
    case("slow", False, gs_kt=60.0),
    case("near_airport", False, airports=[[LAT + 0.1, LON]]),
    case("edge_of_coverage", False, coverage={CELL: 1000}),
    case("receiver_outage", False, alive=()),
]
out = Path(__file__).parent / "fixtures" / "d1_cases.jsonl"
out.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
print(f"wrote {len(cases)} cases to {out}")
```

Run: `uv run --project src/python python eval/make_d1_seed.py` → `wrote 10 cases`.

Uwaga o tym, co te przypadki mierzą: są przepisane z testów jednostkowych, więc **są testem regresji reguły, a nie miarą jakości**. Prawdziwe metryki D1 powstają dopiero w Step 10 z ręcznie oznaczonej, niezależnej próby zniknięć (także tych, których detektor nie zgłosił) — inaczej recall liczyłby się wyłącznie z alarmów, które sam wygenerował. README musi rozróżniać te dwie liczby.

- [ ] **Step 3: `eval/run_eval.py`**

```python
"""Evaluates D1 and D3 on frozen fixtures. --check <baseline.json> fails (exit 1) on a drop > TOLERANCE."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python"))

import h3  # noqa: E402

from wachta_detectors.dark import LastSeen, find_dark_candidates  # noqa: E402
from wachta_detectors.geo import haversine_km  # noqa: E402
from wachta_detectors.jamming import aggregate_jamming  # noqa: E402
from wachta_detectors.models import Position  # noqa: E402

TOLERANCE = 0.05
FIX = Path(__file__).parent / "fixtures"
KALININGRAD = (54.71, 20.51)


def prf(tp: int, fp: int, fn: int) -> dict:
    return {"precision": round(tp / (tp + fp), 3) if tp + fp else 1.0, "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0}


def load_snapshot_positions() -> list[Position]:
    """One frozen hour of positions (a single snapshot is too sparse: res-4 cells need ~5 aircraft each)."""
    raw = json.loads((FIX / "d3_hour.json").read_text(encoding="utf-8"))["positions"]
    now = datetime.now(timezone.utc)
    return [Position(p["hex"], p["lat"], p["lon"], p["alt_ft"], p["on_ground"], p["nac_p"], now) for p in raw]


def eval_d3() -> dict:
    """Labels are frozen in d3_labels.json. A detector returning nothing must score recall 0, not 1."""
    labels = json.loads((FIX / "d3_labels.json").read_text(encoding="utf-8"))
    flagged = {c.h3 for c in aggregate_jamming(load_snapshot_positions()) if c.level != "low"}
    tp = sum(cell in flagged for cell in labels["positive"])
    fn = len(labels["positive"]) - tp
    fp = sum(cell in flagged for cell in labels["negative"])
    return {**prf(tp, fp, fn), "n_positive": len(labels["positive"]), "n_negative": len(labels["negative"])}


def eval_d1(path: Path) -> dict:
    if not path.exists():
        return {"precision": None, "recall": None, "n_cases": 0}
    tp = fp = fn = n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        s = dict(c["last_seen"])
        s["ts"] = datetime.fromisoformat(s["ts"])
        s["last_message_at"] = datetime.fromisoformat(s["last_message_at"])
        got = bool(find_dark_candidates([LastSeen(**s)], c["coverage"], set(c["alive"]),
                                        [tuple(a) for a in c["airports"]], datetime.fromisoformat(c["now"])))
        tp += got and c["expected"]
        fp += got and not c["expected"]
        fn += (not got) and c["expected"]
        n += 1
    return {**prf(tp, fp, fn), "n_cases": n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", type=Path)
    args = ap.parse_args()
    results = {
        "d3": eval_d3(),
        # Synthetic = regression test of the rule. Real = quality, from hand-labelled silent aircraft (T1.15 Step 10).
        "d1_synthetic": eval_d1(FIX / "d1_cases.jsonl"),
        "d1_real": eval_d1(FIX / "d1_real_cases.jsonl"),
    }
    out = Path(__file__).parent / "results" / "latest.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    if args.check:
        base = json.loads(args.check.read_text(encoding="utf-8"))
        drops = [f"{d}.{m}: {base[d][m]} -> {results[d][m]}" for d in base for m in ("precision", "recall")
                 if base[d].get(m) is not None
                 and (results[d][m] is None or results[d][m] < base[d][m] - TOLERANCE)]
        if drops:
            print("METRIC DROP:\n  " + "\n  ".join(drops))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Pierwszy przebieg → baseline**

```bash
uv run --project src/python python eval/run_eval.py
```
Expected: `d1_synthetic` ma `precision 1.0, recall 1.0, n_cases 10` (to test regresji reguły, nie miara jakości); `d1_real` ma `n_cases 0` do czasu etykietowania (Step 10). D3: liczby zależne od nagranego odczytu i zatwierdzonych etykiet.

**Zapisz rzeczywiste wartości** do `eval/baseline.json`, np.:
```json
{
  "d3": { "precision": 0.0, "recall": 0.0 },
  "d1_synthetic": { "precision": 1.0, "recall": 1.0 }
}
```
(zastąp zera wartościami z przebiegu; `d1_real` dopisujemy do baseline dopiero po Step 10). Jeśli D3 recall < 0,5 na odczycie, na którym widać zakłócenia (test z 22.09: 17% zakłóconych przy Kaliningradzie) — to błąd w agregacji albo w etykietach: debuguj przed commitem (skill `systematic-debugging`).

- [ ] **Step 5: Narzędzie do etykietowania D1**

`eval/label_d1.py`:
```python
"""Exports D1 cases for manual labelling, and turns labelled rows into eval cases.

  export: uv run --project src/python python eval/label_d1.py export   -> eval/labels/d1_to_label.csv
  (open the CSV, fill column 'label' with y/n using the replay link)
  import: uv run --project src/python python eval/label_d1.py import   -> appends to eval/fixtures/d1_cases.jsonl

The export deliberately lists EVERY aircraft that went silent for 5-30 minutes, not only the ones D1
reported. Alerts alone would make recall meaningless: the detector would be graded on its own output,
so the cases it silently missed could never show up. Column 'alerted' says whether D1 fired.
"""
import csv
import json
import os
import sys
from pathlib import Path

import psycopg

HERE = Path(__file__).parent
CSV_PATH = HERE / "labels" / "d1_to_label.csv"


SAMPLE_SQL = """
SELECT DISTINCT ON (hex) hex, evaluated_at, alerted, inputs
FROM d1_sample
ORDER BY hex, evaluated_at DESC
"""


def export():
    CSV_PATH.parent.mkdir(exist_ok=True)
    with psycopg.connect(os.environ["WACHTA_DB"]) as conn:
        rows = conn.execute(SAMPLE_SQL).fetchall()
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hex", "evaluated_at", "flight", "type", "military", "last_position_utc", "last_message_utc",
                    "alt_ft", "gs_kt", "alerted", "replay_url", "label"])
        for hex_, at, alerted, inputs in rows:
            s = inputs["last_seen"]
            url = f"https://globe.adsb.lol/?icao={hex_}&showTrace={at:%Y-%m-%d}"
            w.writerow([hex_, at.isoformat(), s["flight"], s["type_code"], s["is_military"], s["ts"],
                        s["last_message_at"], s["alt_ft"], s["gs_kt"], alerted, url, ""])
    print(f"{len(rows)} silent aircraft ({sum(r[2] for r in rows)} alerted) -> {CSV_PATH}")
    print("Oznacz y = transponder naprawdę zgasł, n = utrata zasięgu / lądowanie / sygnał wrócił.")
    print("Oznacz też wiersze z alerted=False — z nich liczy się recall.")


def import_():
    with psycopg.connect(os.environ["WACHTA_DB"]) as conn:
        rows = {(h, at.isoformat()): inputs for h, at, _, inputs in conn.execute(SAMPLE_SQL).fetchall()}
    cases = []
    with CSV_PATH.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["label"] not in ("y", "n"):
                continue
            inputs = rows[(r["hex"], r["evaluated_at"])]
            cases.append({
                "case": f"real_{r['hex']}_{r['evaluated_at']}",
                "last_seen": inputs["last_seen"], "now": inputs["now"], "coverage": inputs["coverage"],
                "alive": inputs["alive"], "airports": inputs["airports"], "expected": r["label"] == "y",
            })
    with (HERE / "fixtures" / "d1_real_cases.jsonl").open("a", encoding="utf-8") as f:
        f.writelines(json.dumps(c) + "\n" for c in cases)
    print(f"appended {len(cases)} labelled cases (real metrics file, separate from the synthetic regression set)")


if __name__ == "__main__":
    {"export": export, "import": import_}[sys.argv[1]]()
```

To wymaga, żeby `evidence` zawierał migawkę wejść. **Zmodyfikuj** `find_dark_candidates` w `dark.py`: do `evidence` dodaj
```python
"evaluated_at": now.isoformat(),
"coverage_snapshot": {c: coverage.get(c, 0) for c in h3.grid_disk(cell, 1)},
"alive_snapshot": sorted(alive_cells & set(h3.grid_disk(cell, 1))),
"airports_snapshot": [[round(a_lat, 4), round(a_lon, 4)] for a_lat, a_lon in airports
                      if nearest_airport_km([(a_lat, a_lon)], s.lat, s.lon) <= rules.airport_radius_km * 3],
```
Test migawki wejść (dopisz do `test_dark.py`):
```python
def test_snapshot_inputs_are_replayable():
    from wachta_detectors.dark import silent_aircraft, snapshot_inputs

    s = seen()
    snap = snapshot_inputs(s, GOOD_COVERAGE, ALIVE, FAR_AIRPORTS, NOW)
    assert snap["now"] == NOW.isoformat()
    assert set(snap["coverage"]) == set(h3.grid_disk(CELL, 1))
    assert snap["alive"] == [CELL]
    # replaying the frozen inputs gives the same verdict
    replayed = find_dark_candidates([LastSeen(**{**snap["last_seen"],
                                                 "ts": datetime.fromisoformat(snap["last_seen"]["ts"]),
                                                 "last_message_at": datetime.fromisoformat(snap["last_seen"]["last_message_at"])})],
                                    snap["coverage"], set(snap["alive"]), [tuple(a) for a in snap["airports"]],
                                    datetime.fromisoformat(snap["now"]))
    assert len(replayed) == 1
    assert [x.hex for x in silent_aircraft([s], NOW)] == ["ae1234"]
```
Run: `cd src/python && uv run pytest -q` → PASS.

Uwaga: migawka zawiera dokładnie to, czego dotykają reguły (`grid_disk(k=1)` dla pokrycia i „żywych” komórek, lotniska w promieniu 3× progu), więc odtworzenie offline daje ten sam wynik.

- [ ] **Step 6: Stage Eval w pipeline** — dopisz do `azure-pipelines.yml`:
```yaml
  - stage: Eval
    dependsOn: Test
    jobs:
      - job: eval
        steps:
          - script: curl -LsSf https://astral.sh/uv/install.sh | sh
            displayName: install uv
          - script: |
              export PATH="$HOME/.local/bin:$PATH"
              uv run --project src/python python eval/run_eval.py --check eval/baseline.json
            displayName: detector eval gate
```

- [ ] **Step 7: Sprawdź, że bramka naprawdę łapie zepsuty detektor** — trzy mutacje, każda musi dać exit 1 z `METRIC DROP`:
  1. `jamming.py`: `HIGH_THRESHOLD = MEDIUM_THRESHOLD = 0.9` (detektor przestaje oznaczać cokolwiek).
  2. `jamming.py`: `aggregate_jamming` zwraca `[]` na samym początku (**to przepuszczała pierwsza wersja bramki** — pusty wynik dawał precyzję i recall 1,0).
  3. `dark.py`: usuń warunek `alive_cells` (D1 zgłasza dziury w zasięgu).
  Po każdej mutacji cofnij zmianę i sprawdź, że `run_eval.py --check eval/baseline.json` kończy się kodem 0.

- [ ] **Step 8: Przegląd [R]** — `codex-delegate`, tryb „przegląd testów”: czy ewaluacja nie jest tautologiczna, czy etykieta D3 nie przecieka z progów.

- [ ] **Step 9: Commit** — `feat(eval): D1/D3 evaluation, labelling tool and CI gate`.

- [ ] **Step 10 (po 7 dniach zbierania, użytkownik):** `label_d1.py export` → oznacz **min. 50 wierszy, w tym co najmniej 20 z `alerted=False`** (y/n, z linkiem do odtworzenia lotu) → `label_d1.py import` → `run_eval.py` → wartości `d1_real` do `baseline.json` i do README. Bez wierszy `alerted=False` recall jest nieliczalny — to była uwaga z przeglądu Codeksa. **Punkt decyzyjny F1 → F2: precyzja `d1_real` ≥ 0,5.**

### Task 1.17: Testy UI w przeglądarce (Playwright)

**Files:**
- Create: `web/playwright.config.ts`, `web/tests/ui.spec.ts`
- Modify: `web/package.json` (dev-zależności `@playwright/test`, `playwright`)

**Interfaces:** Consumes: aplikację z T1.12–T1.14. Produces: `npx playwright test` — dwa testy dymne uruchamiane na `npm run dev` (konfiguracja startuje serwer sama).

**Dlaczego (znalezione 2026-09-26 przy pierwszym uruchomieniu):** dwa błędy przeszły przez testy jednostkowe i budowę z kontrolą typów, bo oba są widoczne dopiero w przeglądarce:
1. Niekompletny `styles.css` — panele były w DOM i „widoczne”, ale leżały w zwykłym przepływie na `x=0`, schowane pod kanwą mapy. Asercje obecności przechodziły; złapała to dopiero geometria.
2. `Worker failed to load` w MapLibre przy prebundlowaniu Vite — kafle pobierały się z HTTP 200, a mapa była pusta. Łapie to asercja „zero błędów konsoli poza brakiem API”.

- [ ] **Step 1: Instalacja**

```bash
cd web
npm install -D @playwright/test playwright
npx playwright install chromium
```

- [ ] **Step 2: Konfiguracja i testy** — pliki `web/playwright.config.ts` oraz `web/tests/ui.spec.ts` (w repo; `webServer` startuje `npm run dev` i korzysta z już działającego serwera, jeśli jest).

- [ ] **Step 3: Uruchom** — `npx playwright test` → 2 testy zielone.

- [ ] **Step 4: Sprawdź mutacjami, że testy cokolwiek łapią** (obie muszą oblać, potem przywróć):
  1. usuń regułę `.panel` z `styles.css` → test geometrii pada;
  2. usuń `optimizeDeps.exclude` z `vite.config.ts` i skasuj `node_modules/.vite` → test błędów konsoli pada.

- [ ] **Step 5: Commit** — `test(web): playwright smoke tests for map shell`.

### Task 1.16: Web w Dockerze, README, ADR-y

**Files:**
- Create: `infra/docker/web.Dockerfile`, `infra/docker/nginx.conf`
- Create: `docs/adr/0001-jedna-baza-postgres.md`, `docs/adr/0002-bez-redisa-w-f1.md`, `docs/adr/0003-podzial-csharp-python.md`
- Modify: `compose.yaml`, `README.md`

- [ ] **Step 1: Web w Dockerze**

`infra/docker/nginx.conf`:
```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  location / { try_files $uri /index.html; }
  location /api/ { proxy_pass http://api:8080; }
  location /openapi/ { proxy_pass http://api:8080; }
  location /hubs/ {
    proxy_pass http://api:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 1h;
  }
}
```

`infra/docker/web.Dockerfile`:
```dockerfile
FROM node:22-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
```

`compose.yaml` — dodaj:
```yaml
  web:
    build: { context: ., dockerfile: infra/docker/web.Dockerfile }
    ports: ["8081:80"]
    depends_on: [api]
```

Weryfikacja: `docker compose up -d --build` → http://localhost:8081 działa jak w trybie dev.

- [ ] **Step 2: ADR-y** (każdy: Kontekst / Decyzja / Konsekwencje, max 20 linii)
  - 0001: jedna baza PostgreSQL z TimescaleDB + PostGIS + pgvector zamiast osobnych systemów — laptop 16 GB, mniej do utrzymania; migracja do Qdranta możliwa za interfejsem repozytorium.
  - 0002: bez Redisa w F1 — komponenty komunikują się przez bazę (polling 5 s / 60 s); Redis Streams wchodzi w F3, gdy agent ma reagować na alarmy w czasie zbliżonym do rzeczywistego.
  - 0003: C# = pobieranie, API, SignalR, (F3) MCP — długo działające usługi i kontrakty; Python = detektory, ML, NLP — ekosystem; kontrakt = schemat bazy + migracje w jednym miejscu (`Wachta.Db/Scripts`), testy Pythona wykonują te same skrypty.

- [ ] **Step 3: README** — sekcje: Co to jest (2 zdania) · GIF (nagraj 20 s: mapa → heksy → alarm → odtwarzanie; ScreenToGif) · Jak uruchomić (`cp .env.example .env` → `docker compose up -d --build` → http://localhost:8081) · Warstwy i detektory (D1, D3 — jedno zdanie + ograniczenia: „widzimy tylko samoloty, które nadawały ADS-B”; „D1 potrzebuje kilku godzin danych, zanim zacznie działać”) · **Metryki** (tabela z `eval/results/latest.json`) · Źródła i licencje (tabela z `source`) · Architektura (diagram mermaid z PLAN.md §4, uproszczony do F1) · Etyka (PLAN.md §13, 3 punkty).

- [ ] **Step 4: Commit** — `docs: readme with metrics, adrs; web container`.

- [ ] **Step 5: Zamknięcie F1** — pełny `dotnet test`, `uv run pytest`, `npm test`, pipeline zielony; `codex-delegate` tryb „przegląd diffa” dla całego F1 (`git diff <commit-F0>..HEAD --stat` + wybrane pliki). Aktualizacja PLAN.md §17 (co się potwierdziło, co nie) i start planu F2.

---

## Self-review (wykonane przy pisaniu)

- **Pokrycie spec:** F0 (T0.1–0.7) i F1 (T1.1–1.16) z PLAN-DZIALANIA.md mają zadania 1:1. D1 i D3 z PLAN.md §2 — T1.7–1.9; model pokrycia §2 — T1.8; rodowód §3c — `fetch_log` + `source` + stopka (T0.4, T1.3, T1.13); ewaluacja §12 — T1.15; wzorce §8 w F1: Adapter (`AdsbLolSource`), Factory (`SourceFactory`), Decorator (`ThrottledAircraftSource`), Repository (`PositionWriter`, `repository.py`), Observer (`LiveBroadcaster` → SignalR), Strategy — pojawi się w F2, gdy dojdą kolejne detektory za wspólnym interfejsem (w F1 są dwa o różnych wejściach; wymuszanie interfejsu byłoby sztuczne). Redis — świadomie odłożony (ADR-0002). D2 (tankowanie) — F6 wg PLAN.md §11.
- **Placeholdery:** jedyne wartości do uzupełnienia w trakcie to dane zależne od świata zewnętrznego: `<login>` GitHuba, klucze w `.env` i liczby D3 w `baseline.json` (instrukcja podaje, skąd je wziąć).
- **Spójność typów:** `LiveAircraft` (C# `GsKt`, JSON `gsKt`, TS `gsKt`); `AlertDto.Evidence` jest stringiem JSON po obu stronach; `ReplayPath.Path` = `[lon, lat]` w C#, TS i teście; `DarkCandidate`/`LastSeen` identyczne w `dark.py`, `repository.py`, `run_eval.py`, `label_d1.py`.


---

## Zmiany po przeglądzie (2026-09-22)

Codex (tylko odczyt) przejrzał ten plan, qwen lokalnie przejrzał moduły Pythona, a ja zweryfikowałem każde ustalenie. Wprowadzone poprawki, od najpoważniejszej:

1. **D1 mylił zakłócanie GPS z zaniknięciem transpondera.** Samolot z zakłóconym GPS przestaje nadawać pozycję, ale nadal nadaje. Nad Bałtykiem, gdzie zakłócanie jest codzienne, byłby to najczęstszy fałszywy alarm — i to na tej samej mapie, na której obok pokazujemy heksy zakłóceń. Dodana tabela `aircraft_contact` (czas ostatniej wiadomości vs czas ostatniej pozycji), D1 wymaga ciszy w transmisji, doszedł test `test_aircraft_still_transmitting_without_position_is_not_dark`.
2. **Bramka jakości przepuszczała detektor zwracający pustkę.** Metryki liczyły się z wyników detektora, więc pusta lista dawała precyzję i recall 1,0. Etykiety D3 są teraz zamrożone w pliku, brak komórki liczy się jako FN, a Step 7 wymaga, żeby trzy mutacje (w tym „zwracaj zawsze pustą listę”) wywaliły pipeline.
3. **Recall D1 był niemierzalny** — liczyłby się wyłącznie z alarmów, które detektor sam wygenerował. Runner zapisuje teraz zamrożone wejścia dla **wszystkich** milczących samolotów (tabela `d1_sample`), a etykietowanie obejmuje też te, których D1 nie zgłosił. Metryki syntetyczne (regresja reguły) oddzielone od rzeczywistych.
4. **Czas obserwacji brany z zegara źródła** (`now` z odpowiedzi), nie z czasu pobrania — inaczej ten sam payload pobrany dwa razy tworzył dwie obserwacje i zawyżał pokrycie oraz `n_points`.
5. **Fixture D3 to godzina danych z bazy, nie pojedynczy odczyt.** Sprawdziłem na prawdziwych danych: 164 samoloty w jednym odczycie dają przy progu produkcyjnym **zero komórek**, bo heks res-4 ma ~1770 km².
6. **Restart bazy nie zabija detektorów** — połączenie otwierane w każdym cyklu (wcześniej proces żył dalej z martwym połączeniem, więc `restart: unless-stopped` nic nie dawał).
7. **D3 domyka godziny** i nadrabia zaległości po restarcie; przeliczona godzina kasuje nieaktualne komórki (`replace_jamming`).
8. **Budżet danych ze spec** wreszcie egzekwowany: ruch cywilny próbkowany raz na minutę (przy 15 s byłoby ~40 mln wierszy tygodniowo), wojskowy w pełnej rozdzielczości.
9. **`replayBounds` bez `Math.min(...)`** — 6 h ruchu to ~300 tys. znaczników czasu i przepełnienie stosu.
10. **Drobne:** `dotnet new sln --format sln` (.NET 10 domyślnie tworzy `.slnx`, a pipeline szukał `.sln`), `GlobalUsings.cs` z `global using Xunit` (bez tego nic się nie kompiluje), wartość domyślna `resolution` w `alive_cells`, straż przed pustą listą w `upsert_coverage`.

**Zweryfikowane uruchomieniem:** moduły Pythona i ich testy wyciągnięte z tego planu przechodzą (`22 passed`), agregacja D3 sprawdzona na prawdziwym odczycie z Bałtyku (stąd ustalenie 5). Kod C# nie był kompilowany — na komputerze nie ma jeszcze .NET SDK (T0.1).

**Nieprzyjęte z przeglądu qwena:** „licz każdy samolot z choć jednym słabym raportem” (myli raporty z samolotami), „poluzuj warunek pokrycia” i „zabezpiecz dzielenie przez zero w `pct`” — to świadome decyzje projektowe albo przypadki niemożliwe z konstrukcji. Model od 59. linii zapętlił się, powtarzając to samo zdanie; wpis o tym trafił do `skills/local-delegate/POMIARY.md`.
