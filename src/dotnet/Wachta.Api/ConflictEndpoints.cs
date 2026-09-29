using Dapper;
using Npgsql;

namespace Wachta.Api;

/// <summary>
/// The land war: which conflicts are in the data, what happened on the front, and how each side
/// told it.
///
/// Everything here was already being computed - GDELT events with a conflict flag, mentions with a
/// side attached at write time - and none of it was reachable. The reader could see aircraft and
/// ships and a list of alerts, and nothing at all about the war those alerts are about.
///
/// The three endpoints are one path, in order: pick a war, look at the front, open one event and
/// see the two versions of it.
/// </summary>
public static class ConflictEndpoints
{
    /// <summary>Wars, as pairs of countries that were in conflict with each other.
    ///
    /// The pair is normalised with least/greatest so that RUS attacking UKR and UKR attacking RUS
    /// land in the same row: they are one war, told from two ends, which is the whole point of the
    /// view this feeds. An actor whose country GDELT left empty cannot form a stable pair and is
    /// left out rather than bucketed under an empty code.</summary>
    public const string ConflictsSql = """
        SELECT least(actor1_country, actor2_country) || '-' || greatest(actor1_country, actor2_country) AS Id,
               least(actor1_country, actor2_country) AS Actor1,
               greatest(actor1_country, actor2_country) AS Actor2,
               count(*)::int AS Events,
               max(ts) AS LastEventAt
        FROM event
        WHERE conflict
          AND actor1_country IS NOT NULL AND actor2_country IS NOT NULL
          AND actor1_country <> actor2_country
        GROUP BY 1, 2, 3
        ORDER BY count(*) DESC, 1
        """;

    /// <summary>Events on one front. Either direction of the pair, newest first.</summary>
    public const string ConflictEventsSql = """
        SELECT id AS Id, ts AS Ts, kind AS Kind, actor1 AS Actor1, actor2 AS Actor2,
               place AS Place, lat AS Lat, lon AS Lon, goldstein AS Goldstein,
               sources AS Sources, url AS Url, mentions AS Mentions
        FROM event
        WHERE conflict
          AND least(actor1_country, actor2_country) = @a
          AND greatest(actor1_country, actor2_country) = @b
          AND ts > now() - make_interval(hours => @hours)
        ORDER BY ts DESC
        LIMIT @limit
        """;

    /// <summary>Everything written about one event. No filtering here on purpose: which mentions
    /// count is a rule of the comparison (<see cref="VersionsView"/>), transcribed once from
    /// <c>versions.py</c>. A WHERE clause repeating it would be a second copy free to drift.</summary>
    public const string MentionsSql = """
        SELECT side AS Side, url AS Url, tone::double precision AS Tone, language AS Language,
               coalesce(confidence, 0)::int AS Confidence, coalesce(from_tld, false) AS FromTld
        FROM event_mention
        WHERE event_id = @id
        ORDER BY coalesce(confidence, 0) DESC, url
        """;

    /// <summary>Polish names for the country codes this project actually watches.
    ///
    /// Display only: the code stays the identity, this is the label above it. Deliberately not a
    /// full CAMEO country table - an unknown code falls back to the code itself, which is honest,
    /// where a half-remembered translation would not be.</summary>
    private static readonly Dictionary<string, string> Nazwy = new(StringComparer.Ordinal)
    {
        ["RUS"] = "Rosja", ["UKR"] = "Ukraina", ["BLR"] = "Białoruś", ["POL"] = "Polska",
        ["LTU"] = "Litwa", ["LVA"] = "Łotwa", ["EST"] = "Estonia", ["FIN"] = "Finlandia",
        ["SWE"] = "Szwecja", ["NOR"] = "Norwegia", ["DNK"] = "Dania", ["DEU"] = "Niemcy",
        ["MDA"] = "Mołdawia", ["ROU"] = "Rumunia", ["SVK"] = "Słowacja", ["CZE"] = "Czechy",
        ["HUN"] = "Węgry", ["GEO"] = "Gruzja", ["ARM"] = "Armenia", ["AZE"] = "Azerbejdżan",
        ["KAZ"] = "Kazachstan", ["TUR"] = "Turcja", ["GBR"] = "Wielka Brytania",
        ["FRA"] = "Francja", ["USA"] = "Stany Zjednoczone", ["CHN"] = "Chiny", ["IRN"] = "Iran",
        ["ISR"] = "Izrael", ["PSE"] = "Palestyna", ["SYR"] = "Syria",
        ["NATO"] = "NATO", ["EUR"] = "Unia Europejska",
    };

    /// <summary>"RUS-UKR" -> "Rosja - Ukraina", and an unknown code stays the code.</summary>
    public static string Nazwa(string actor1, string actor2) =>
        $"{Nazwy.GetValueOrDefault(actor1, actor1)} – {Nazwy.GetValueOrDefault(actor2, actor2)}";

    /// <summary>Reads a conflict id back into its two country codes.
    ///
    /// Accepts the pair in either order and returns it normalised, so a link built by hand out of
    /// "UKR-RUS" finds the same war as the id the list handed out. Anything that is not two plain
    /// codes is rejected instead of being pushed into the query.</summary>
    public static bool TryParseId(string? id, out string a, out string b)
    {
        a = b = "";
        if (string.IsNullOrWhiteSpace(id))
        {
            return false;
        }

        var parts = id.Trim().ToUpperInvariant().Split('-');
        if (parts.Length != 2)
        {
            return false;
        }

        foreach (var part in parts)
        {
            if (part.Length is 0 or > 16 || !part.All(char.IsAsciiLetterOrDigit))
            {
                return false;
            }
        }

        (a, b) = string.CompareOrdinal(parts[0], parts[1]) <= 0
            ? (parts[0], parts[1])
            : (parts[1], parts[0]);
        return true;
    }

    /// <summary>The grouped row as Postgres returns it; the label is put on afterwards, in C#,
    /// because a translation table has no business being a CASE expression in SQL.</summary>
    private sealed record ConflictRow(string Id, string Actor1, string Actor2, int Events, DateTime? LastEventAt);

    /// <summary>Turns "that table does not exist" into an answer instead of a stack trace.
    ///
    /// The migration that creates <c>event</c> and <c>event_mention</c> ships separately from this
    /// code, so a stack meeting the two halves out of order is a normal state, not a bug - and it
    /// is worth exactly one clear sentence. Deliberately 503 and not an empty list: an empty list
    /// would say "no war has happened yet", which is a different and much worse lie than "the
    /// layer is not set up here".</summary>
    private static async Task<IResult> BezTabeli(Func<Task<IResult>> handler)
    {
        try
        {
            return await handler();
        }
        catch (PostgresException e) when (e.SqlState == PostgresErrorCodes.UndefinedTable)
        {
            return Results.Problem(
                "Warstwa zdarzen nie jest jeszcze zalozona w tej bazie (brak tabeli event / event_mention).",
                statusCode: StatusCodes.Status503ServiceUnavailable);
        }
    }

    public static void MapConflictEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapGet("/api/conflicts", (NpgsqlDataSource db) => BezTabeli(async () =>
        {
            await using var conn = await db.OpenConnectionAsync();
            var rows = await conn.QueryAsync<ConflictRow>(ConflictsSql);
            return Results.Ok(rows.Select(c => new ConflictDto(
                c.Id, Nazwa(c.Actor1, c.Actor2), c.Actor1, c.Actor2, c.Events, c.LastEventAt)));
        }));

        app.MapGet("/api/conflicts/{id}/events", (NpgsqlDataSource db, string id, int? hours, int? limit) => BezTabeli(async () =>
        {
            if (!TryParseId(id, out var a, out var b))
            {
                return Results.BadRequest("Identyfikator konfliktu ma postac dwoch kodow krajow, np. RUS-UKR.");
            }

            // Clamped rather than rejected: a window is a view preference, not a correctness
            // question, and a front end asking for a year should get a week, not an error page.
            var okno = Math.Clamp(hours ?? 24, 1, 24 * 30);
            var ile = Math.Clamp(limit ?? 500, 1, 5000);

            await using var conn = await db.OpenConnectionAsync();
            var rows = await conn.QueryAsync<ConflictEventDto>(ConflictEventsSql,
                new { a, b, hours = okno, limit = ile });
            return Results.Ok(rows);
        }));

        app.MapGet("/api/events/{eventId}/versions", (NpgsqlDataSource db, string eventId) => BezTabeli(async () =>
        {
            await using var conn = await db.OpenConnectionAsync();

            // 404 only when the event itself is unknown. An event that exists but nobody comparable
            // wrote about is a different answer - an empty comparison - and the front end has to be
            // able to tell those apart to say "nothing to compare yet" instead of "no such event".
            var exists = await conn.ExecuteScalarAsync<bool>(
                "SELECT exists(SELECT 1 FROM event WHERE id = @id)", new { id = eventId });
            if (!exists)
            {
                return Results.NotFound("Nie ma takiego zdarzenia.");
            }

            var mentions = await conn.QueryAsync<MentionRow>(MentionsSql, new { id = eventId });
            return Results.Ok(VersionsView.Compare(eventId, mentions));
        }));
    }
}
