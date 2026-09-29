using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Npgsql;
using Wachta.Api;

namespace Wachta.Tests;

/// <summary>The conflict id and its label, without a database in the way.</summary>
public sealed class ConflictIdTests
{
    [Fact]
    public void An_unmapped_country_keeps_its_code_instead_of_getting_a_guessed_name()
    {
        // Lista polskich nazw jest krotka i celowo nie udaje pelnego slownika CAMEO. Kod, ktorego
        // na niej nie ma, ma zostac kodem - zmyslone tlumaczenie bylo by gorsze niz zadne.
        // Mutacja: GetValueOrDefault(kod, kod) -> GetValueOrDefault(kod) wstawia tu pusty napis.
        Assert.Equal("Rosja – XKX", ConflictEndpoints.Nazwa("RUS", "XKX"));
        Assert.Equal("QQQ – ZZZ", ConflictEndpoints.Nazwa("QQQ", "ZZZ"));
    }

    [Theory]
    [InlineData("RUS-UKR")]
    [InlineData("UKR-RUS")]
    [InlineData("ukr-rus")]
    [InlineData("  rus-ukr  ")]
    public void The_pair_always_comes_back_in_the_same_canonical_order(string id)
    {
        // Mutacja: usuniecie ToUpperInvariant przepuszcza "ukr-rus" jako inna pare.
        Assert.True(ConflictEndpoints.TryParseId(id, out var a, out var b));
        Assert.Equal("RUS", a);
        Assert.Equal("UKR", b);
    }

    [Theory]
    [InlineData("RUSUKR")]
    [InlineData("RUS-UKR-BLR")]
    [InlineData("RUS-")]
    [InlineData("-UKR")]
    [InlineData("RUS-U'")]
    [InlineData("")]
    [InlineData(null)]
    public void Anything_that_is_not_two_plain_codes_is_rejected(string? id)
    {
        Assert.False(ConflictEndpoints.TryParseId(id, out _, out _));
    }
}

/// <summary>
/// The land war over HTTP: pick a conflict, look at the front, open one event's two versions.
///
/// The tables are created here rather than assumed, with CREATE TABLE IF NOT EXISTS: the migration
/// that adds them is being written in parallel, and a test suite that goes red because somebody
/// else has not merged yet says nothing about this code. Once the migration lands the DDL below is
/// a no-op, and the shape it declares is the shape agreed with that migration.
/// </summary>
[Collection("postgres")]
public sealed class ConflictApiTests : IAsyncLifetime
{
    private readonly PostgresFixture _db;
    private WebApplicationFactory<Program> _factory = null!;
    private HttpClient _client = null!;

    public ConflictApiTests(PostgresFixture db) => _db = db;

    private const string Ddl = """
        CREATE TABLE IF NOT EXISTS event (
            id              text PRIMARY KEY,
            day             date,
            ts              timestamptz,
            actor1          text,
            actor1_country  text,
            actor2          text,
            actor2_country  text,
            kind            text,
            root            text,
            quad            smallint,
            goldstein       real,
            mentions        int,
            sources         int,
            conflict        boolean,
            place           text,
            lat             double precision,
            lon             double precision,
            url             text,
            source_id       text REFERENCES source(id),
            fetched_at      timestamptz
        );
        CREATE TABLE IF NOT EXISTS event_mention (
            event_id    text REFERENCES event(id),
            source      text,
            url         text,
            tone        real,
            language    text,
            confidence  smallint,
            side        text,
            from_tld    boolean,
            fetched_at  timestamptz,
            PRIMARY KEY (event_id, url)
        );
        INSERT INTO source (id, name, url, license, trust_tier, attribution) VALUES
          ('gdelt-events', 'GDELT 2.0 events', 'https://data.gdeltproject.org/gdeltv2/',
           'CC BY-NC-SA 4.0', 2, 'Data: The GDELT Project')
        ON CONFLICT (id) DO NOTHING;
        """;

    /// <summary>Fixture in the shape the reader will meet it: one war told from both ends, one war
    /// with a single event, and the rows that must NOT become a war - cooperation, an actor against
    /// its own country, an actor whose country GDELT left empty.</summary>
    private const string Seed = """
        DELETE FROM event_mention WHERE event_id LIKE 'ev-%';
        DELETE FROM event WHERE id LIKE 'ev-%';

        INSERT INTO event (id, day, ts, actor1, actor1_country, actor2, actor2_country, kind, root,
                           quad, goldstein, mentions, sources, conflict, place, lat, lon, url,
                           source_id, fetched_at) VALUES
          ('ev-ruua-1', current_date, now() - interval '1 hour',  'RUSMIL', 'RUS', 'UKR', 'UKR',
           'walka', '19', 4, -10.0, 42, 7, true, 'Pokrovsk', 48.28, 37.17,
           'https://example.org/ruua1', 'gdelt-events', now()),
          ('ev-ruua-2', current_date, now() - interval '2 hours', 'UKRMIL', 'UKR', 'RUS', 'RUS',
           'napasc', '18', 4,  -9.0, 11, 3, true, 'Belgorod', 50.59, 36.58,
           'https://example.org/ruua2', 'gdelt-events', now()),
          ('ev-ruua-old', current_date - 3, now() - interval '3 days', 'RUSMIL', 'RUS', 'UKR', 'UKR',
           'walka', '19', 4, -10.0, 5, 2, true, 'Bachmut', 48.59, 38.00,
           'https://example.org/ruuaold', 'gdelt-events', now()),
          ('ev-blpl-1', current_date, now() - interval '30 minutes', 'BLRGOV', 'BLR', 'POL', 'POL',
           'grozba', '13', 3, -5.0, 8, 4, true, 'Kuznica', 53.51, 23.63,
           'https://example.org/blpl1', 'gdelt-events', now()),
          ('ev-wspolpraca', current_date, now() - interval '10 minutes', 'RUS', 'RUS', 'UKR', 'UKR',
           'konsultacje', '04', 1, 5.0, 3, 1, false, 'Stambul', 41.01, 28.98,
           'https://example.org/coop', 'gdelt-events', now()),
          ('ev-sam-ze-soba', current_date, now() - interval '5 minutes', 'RUSGOV', 'RUS', 'RUSREB', 'RUS',
           'przymus', '17', 4, -7.0, 2, 1, true, 'Moskwa', 55.75, 37.61,
           'https://example.org/self', 'gdelt-events', now()),
          ('ev-bez-kraju', current_date, now() - interval '5 minutes', 'RUSMIL', 'RUS', NULL, NULL,
           'walka', '19', 4, -8.0, 2, 1, true, 'Gdzies', 50.0, 30.0,
           'https://example.org/nocountry', 'gdelt-events', now());

        -- ev-ruua-1: dwie pelne strony, obie z nazwanych redakcji. RU -1.5, UA -8.5, luka 7.0.
        -- Doklejone: redakcja nieprzypisana (side NULL) i artykul bez wydzwieku - zadne nie moze
        -- podniesc liczby artykulow.
        INSERT INTO event_mention (event_id, source, url, tone, language, confidence, side, from_tld, fetched_at) VALUES
          ('ev-ruua-1', 'tass.ru',        'https://tass.ru/1',        -1.0, 'rus', 90, 'RU',     false, now()),
          ('ev-ruua-1', 'rt.com',         'https://rt.com/1',         -2.0, NULL,  50, 'RU',     false, now()),
          ('ev-ruua-1', 'unian.ua',       'https://unian.ua/1',       -8.0, 'ukr', 40, 'UA',     false, now()),
          ('ev-ruua-1', 'pravda.com.ua',  'https://pravda.com.ua/1',  -9.0, 'ukr', 30, 'UA',     false, now()),
          ('ev-ruua-1', 'iheart.com',     'https://iheart.com/1',      9.0, NULL,  70, NULL,     false, now()),
          ('ev-ruua-1', 'sputnikglobe.com','https://sputnikglobe.com/1', NULL, NULL, 80, 'RU',   false, now());

        -- ev-ruua-2: strona RU zlozona wylacznie z domen .ru, ktorych nikt nie czytal. Wyglada jak
        -- strona i nia nie jest - to ma zobaczyc czytelnik.
        INSERT INTO event_mention (event_id, source, url, tone, language, confidence, side, from_tld, fetched_at) VALUES
          ('ev-ruua-2', 'kremlin-mirror.ru', 'https://kremlin-mirror.ru/1', -8.0, NULL, 20, 'RU',     true,  now()),
          ('ev-ruua-2', 'blog-jakis.ru',     'https://blog-jakis.ru/1',     -7.0, NULL, 15, 'RU',     true,  now()),
          ('ev-ruua-2', 'bbc.com',           'https://bbc.com/1',            1.0, 'eng', 60, 'ZACHOD', false, now()),
          ('ev-ruua-2', 'theguardian.com',   'https://theguardian.com/1',    2.0, 'eng', 55, 'ZACHOD', false, now());
        """;

    public async Task InitializeAsync()
    {
        Environment.SetEnvironmentVariable("ConnectionStrings__Wachta", _db.ConnectionString);
        _factory = new WebApplicationFactory<Program>();
        _client = _factory.CreateClient();

        await using var conn = new NpgsqlConnection(_db.ConnectionString);
        await conn.OpenAsync();
        await using var ddl = new NpgsqlCommand(Ddl, conn);
        await ddl.ExecuteNonQueryAsync();
        await using var seed = new NpgsqlCommand(Seed, conn);
        await seed.ExecuteNonQueryAsync();
    }

    public async Task DisposeAsync() => await _factory.DisposeAsync();

    private async Task<T> Get<T>(string url)
    {
        var res = await _client.GetAsync(url);
        Assert.True(res.IsSuccessStatusCode, $"{url} -> {res.StatusCode}: {await res.Content.ReadAsStringAsync()}");
        return (await res.Content.ReadFromJsonAsync<T>())!;
    }

    [DockerFact]
    public async Task Conflicts_merge_both_directions_of_the_same_war_under_one_stable_id()
    {
        // RUS uderza w UKR i UKR uderza w RUS to jedna wojna opowiadana z dwoch koncow. Gdyby
        // kazdy kierunek byl osobna pozycja, lista dawalaby dwie "wojny" o tej samej tresci.
        // Mutacja: zamiana least/greatest na actor1_country/actor2_country rozbija to na RUS-UKR
        // i UKR-RUS i wywraca zarowno identyfikator, jak i liczbe zdarzen.
        var lista = await Get<List<ConflictDto>>("/api/conflicts");

        var ruua = Assert.Single(lista, c => c.Id == "RUS-UKR");
        Assert.Equal("RUS", ruua.Actor1);
        Assert.Equal("UKR", ruua.Actor2);
        Assert.Equal(3, ruua.Events);       // dwa swieze plus jedno sprzed trzech dni
        Assert.DoesNotContain(lista, c => c.Id == "UKR-RUS");
    }

    [DockerFact]
    public async Task Conflicts_are_ordered_by_how_much_happened_and_carry_the_last_event()
    {
        // Mutacja: ORDER BY count(*) ASC stawia BLR-POL przed RUS-UKR.
        var lista = await Get<List<ConflictDto>>("/api/conflicts");
        var moje = lista.Where(c => c.Id is "RUS-UKR" or "BLR-POL").ToList();

        Assert.Equal(["RUS-UKR", "BLR-POL"], moje.Select(c => c.Id));

        var ruua = moje[0];
        Assert.NotNull(ruua.LastEventAt);
        // Najswiezsze zdarzenie tej pary jest sprzed godziny, nie sprzed trzech dni.
        var ostatnie = ruua.LastEventAt!.Value.ToUniversalTime();
        Assert.True(ostatnie > DateTime.UtcNow.AddHours(-2), $"lastEventAt = {ostatnie:O}");
    }

    [DockerFact]
    public async Task Conflicts_leave_out_what_is_not_a_war_between_two_sides()
    {
        // Wspolpraca nie jest konfliktem; aktor przeciwko wlasnemu krajowi nie jest dwiema stronami;
        // aktor bez kraju nie tworzy stabilnej pary i trafilby pod pusty kod.
        // Mutacja: usuniecie `WHERE conflict` wpuszcza RUS-UKR ze wspolpracy (liczba zdarzen rosnie
        // do 4); usuniecie `actor1_country <> actor2_country` dodaje pozycje RUS-RUS.
        var lista = await Get<List<ConflictDto>>("/api/conflicts");

        Assert.DoesNotContain(lista, c => c.Id == "RUS-RUS");
        Assert.DoesNotContain(lista, c => c.Id.StartsWith('-') || c.Id.EndsWith('-'));
        Assert.Equal(3, Assert.Single(lista, c => c.Id == "RUS-UKR").Events);
    }

    [DockerFact]
    public async Task Conflicts_are_named_in_polish_with_the_code_as_the_fallback()
    {
        var lista = await Get<List<ConflictDto>>("/api/conflicts");

        Assert.Equal("Rosja – Ukraina", Assert.Single(lista, c => c.Id == "RUS-UKR").Nazwa);
        Assert.Equal("Białoruś – Polska", Assert.Single(lista, c => c.Id == "BLR-POL").Nazwa);
    }

    [DockerFact]
    public async Task Front_shows_both_directions_within_the_window_newest_first()
    {
        // Mutacja: ORDER BY ts ASC odwraca kolejnosc; zamiana `ts >` na `ts <` gubi oba zdarzenia.
        var zdarzenia = await Get<List<ConflictEventDto>>("/api/conflicts/RUS-UKR/events?hours=24");

        Assert.Equal(["ev-ruua-1", "ev-ruua-2"], zdarzenia.Select(e => e.Id));
        Assert.DoesNotContain(zdarzenia, e => e.Id == "ev-ruua-old");   // poza oknem
        Assert.DoesNotContain(zdarzenia, e => e.Id == "ev-wspolpraca"); // nie konflikt

        var pierwsze = zdarzenia[0];
        Assert.Equal("walka", pierwsze.Kind);
        Assert.Equal("RUSMIL", pierwsze.Actor1);
        Assert.Equal("Pokrovsk", pierwsze.Place);
        Assert.Equal(48.28, pierwsze.Lat!.Value, 2);
        Assert.Equal(-10.0f, pierwsze.Goldstein);
        Assert.Equal(7, pierwsze.Sources);
        Assert.Equal(42, pierwsze.Mentions);
        Assert.Equal("https://example.org/ruua1", pierwsze.Url);
    }

    [DockerFact]
    public async Task A_wider_window_reaches_further_back_and_the_limit_cuts_the_list()
    {
        var szerokie = await Get<List<ConflictEventDto>>("/api/conflicts/RUS-UKR/events?hours=168");
        Assert.Contains(szerokie, e => e.Id == "ev-ruua-old");

        var przyciete = await Get<List<ConflictEventDto>>("/api/conflicts/RUS-UKR/events?hours=168&limit=1");
        Assert.Single(przyciete);
        Assert.Equal("ev-ruua-1", przyciete[0].Id);   // limit tnie od konca, nie od poczatku
    }

    [DockerFact]
    public async Task A_conflict_id_written_the_other_way_round_finds_the_same_war()
    {
        // Identyfikator jest stabilny, wiec link sklejony recznie z odwroconej pary ma dzialac,
        // zamiast po cichu zwracac pustke.
        var odwrotnie = await Get<List<ConflictEventDto>>("/api/conflicts/ukr-rus/events?hours=24");

        Assert.Equal(["ev-ruua-1", "ev-ruua-2"], odwrotnie.Select(e => e.Id));
    }

    [DockerFact]
    public async Task A_malformed_conflict_id_is_rejected_instead_of_queried()
    {
        foreach (var zle in new[] { "RUSUKR", "RUS-UKR-BLR", "RUS-", "RUS-U%27" })
        {
            var res = await _client.GetAsync($"/api/conflicts/{Uri.EscapeDataString(zle)}/events");
            Assert.Equal(HttpStatusCode.BadRequest, res.StatusCode);
        }
    }

    [DockerFact]
    public async Task An_unknown_pair_is_an_empty_front_not_an_error()
    {
        var puste = await Get<List<ConflictEventDto>>("/api/conflicts/AAA-BBB/events");

        Assert.Empty(puste);
    }

    [DockerFact]
    public async Task Versions_report_both_sides_with_the_tone_gap_between_them()
    {
        // Te same liczby co w test_versions.py: RU -1.5, UA -8.5, luka 7.0. Nieprzypisana redakcja
        // i artykul bez wydzwieku nie licza sie do zadnej strony.
        // Mutacja: usuniecie filtra na NULL side w VersionsView wpuszcza iheart.com i podnosi
        // totalArticles do 5.
        var w = await Get<EventVersionsDto>("/api/events/ev-ruua-1/versions");

        Assert.Equal("ev-ruua-1", w.EventId);
        Assert.Equal(4, w.TotalArticles);
        Assert.Equal(7.0, w.ToneGap);
        Assert.False(w.IsWeak);

        var ru = Assert.Single(w.Sides, s => s.Side == "RU");
        var ua = Assert.Single(w.Sides, s => s.Side == "UA");
        Assert.Equal(-1.5, ru.MeanTone);
        Assert.Equal(-8.5, ua.MeanTone);
        Assert.Equal(2, ru.Articles);
        Assert.Equal(["rus"], ru.Languages);
        Assert.Equal("https://tass.ru/1", ru.Examples[0]);   // najpewniejsza wzmianka pierwsza
        Assert.Equal(0, ru.FromTld);
        Assert.False(ru.OnlyGuessed);
    }

    [DockerFact]
    public async Task Versions_flag_a_side_that_is_nothing_but_country_domains()
    {
        // Dwie strony, dwie liczby, roznica wydzwieku - i jedna z tych stron to dwa blogi pod .ru,
        // ktorych nikt nie przypisal. Bez tej flagi wyglada to identycznie jak porownanie solidne.
        // Mutacja: `OnlyGuessed` zawsze false albo `FromTld` zawsze 0 gasi oba ostrzezenia.
        var w = await Get<EventVersionsDto>("/api/events/ev-ruua-2/versions");

        var ru = Assert.Single(w.Sides, s => s.Side == "RU");
        Assert.Equal(2, ru.FromTld);
        Assert.True(ru.OnlyGuessed);
        Assert.False(Assert.Single(w.Sides, s => s.Side == "ZACHOD").OnlyGuessed);
        Assert.True(w.IsWeak);
    }

    [DockerFact]
    public async Task An_event_nobody_comparable_wrote_about_is_an_empty_comparison_not_a_404()
    {
        // Rozroznienie, ktorego front potrzebuje: "nie ma czego porownac" to nie to samo co
        // "nie ma takiego zdarzenia". Pusta lista stron jest tu sygnalem - nie IsWeak, bo ten
        // liczy sie tym samym wyrazeniem co w Pythonie, a `any([])` jest falszem.
        var w = await Get<EventVersionsDto>("/api/events/ev-blpl-1/versions");

        Assert.Equal("ev-blpl-1", w.EventId);
        Assert.Empty(w.Sides);
        Assert.Equal(0, w.TotalArticles);
        Assert.Equal(0.0, w.ToneGap);
        Assert.False(w.IsWeak);
    }

    [DockerFact]
    public async Task The_json_keys_are_the_ones_the_front_end_was_built_against()
    {
        // Ksztalt jest umowa z frontem pisanym rownolegle, a testy wyzej czytaja przez DTO, wiec
        // nie zobaczylyby zmiany samych nazw pol. Tu patrzymy na surowy JSON.
        var konflikty = await _client.GetStringAsync("/api/conflicts");
        foreach (var klucz in new[] { "\"id\"", "\"nazwa\"", "\"actor1\"", "\"actor2\"", "\"events\"", "\"lastEventAt\"" })
        {
            Assert.Contains(klucz, konflikty);
        }

        var zdarzenia = await _client.GetStringAsync("/api/conflicts/RUS-UKR/events");
        foreach (var klucz in new[] { "\"id\"", "\"ts\"", "\"kind\"", "\"actor1\"", "\"actor2\"", "\"place\"",
                                      "\"lat\"", "\"lon\"", "\"goldstein\"", "\"sources\"", "\"url\"", "\"mentions\"" })
        {
            Assert.Contains(klucz, zdarzenia);
        }

        var wersje = await _client.GetStringAsync("/api/events/ev-ruua-1/versions");
        foreach (var klucz in new[] { "\"eventId\"", "\"totalArticles\"", "\"toneGap\"", "\"isWeak\"", "\"sides\"",
                                      "\"side\"", "\"articles\"", "\"meanTone\"", "\"languages\"", "\"examples\"",
                                      "\"fromTld\"", "\"onlyGuessed\"" })
        {
            Assert.Contains(klucz, wersje);
        }
    }

    [DockerFact]
    public async Task Versions_of_an_unknown_event_are_a_404()
    {
        var res = await _client.GetAsync("/api/events/nie-ma-takiego/versions");

        Assert.Equal(HttpStatusCode.NotFound, res.StatusCode);
    }

    [DockerFact]
    public async Task A_database_without_the_event_tables_says_so_instead_of_crashing()
    {
        // Migracja zakladajaca event / event_mention jedzie osobno od tego kodu, wiec stack, w
        // ktorym obie polowy spotkaly sie w zlej kolejnosci, to stan normalny - wart jednego
        // czytelnego zdania, a nie sladu stosu. 503, nie pusta lista: pusta lista mowilaby "nie
        // bylo zadnej wojny", co jest gorszym klamstwem niz "warstwa nie jest tu zalozona".
        // Mutacja: usuniecie catch PostgresException daje 500 zamiast 503.
        var bezTabel = new NpgsqlConnectionStringBuilder(_db.ConnectionString) { Database = "postgres" }.ToString();
        var stare = Environment.GetEnvironmentVariable("ConnectionStrings__Wachta");
        try
        {
            Environment.SetEnvironmentVariable("ConnectionStrings__Wachta", bezTabel);
            await using var factory = new WebApplicationFactory<Program>();
            using var client = factory.CreateClient();

            foreach (var url in new[] { "/api/conflicts", "/api/conflicts/RUS-UKR/events", "/api/events/x/versions" })
            {
                var res = await client.GetAsync(url);
                Assert.Equal(HttpStatusCode.ServiceUnavailable, res.StatusCode);
            }
        }
        finally
        {
            Environment.SetEnvironmentVariable("ConnectionStrings__Wachta", stare);
        }
    }

    [DockerFact]
    public async Task An_empty_database_answers_with_empty_lists_not_with_an_error()
    {
        // Tabele powstaja przed danymi - stack postawiony minute temu ma pusta tabele zdarzen.
        // Pusta lista jest wtedy odpowiedzia, a nie awaria, dokladnie jak przy wyszukiwaniu.
        await using var conn = new NpgsqlConnection(_db.ConnectionString);
        await conn.OpenAsync();
        await using var wipe = new NpgsqlCommand("DELETE FROM event_mention; DELETE FROM event;", conn);
        await wipe.ExecuteNonQueryAsync();

        Assert.Empty(await Get<List<ConflictDto>>("/api/conflicts"));
        Assert.Empty(await Get<List<ConflictEventDto>>("/api/conflicts/RUS-UKR/events"));

        var res = await _client.GetAsync("/api/events/ev-ruua-1/versions");
        Assert.Equal(HttpStatusCode.NotFound, res.StatusCode);
    }
}
