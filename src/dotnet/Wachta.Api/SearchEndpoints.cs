using System.Globalization;
using System.Text;
using System.Text.Json;
using Dapper;
using Npgsql;

namespace Wachta.Api;

/// <summary>Search by meaning over what the detectors and the feeds produced.
///
/// The corpus is multilingual - events arrive in English, outlets write in Russian, Ukrainian and
/// Polish - while the question is typed in whatever language the reader thinks in. Keyword search
/// cannot bridge that, so the question is turned into a vector by the same local model that indexed
/// the documents, and pgvector finds the nearest ones.
///
/// Two things the caller is never allowed to forget, and which are therefore part of the response
/// rather than of the documentation:
///
///   * a nearest neighbour ALWAYS exists, including when nothing in the corpus is relevant. The
///     score is returned with every hit and a measured floor is applied by default.
///   * an empty result is an answer, not a failure. It means the corpus holds nothing above the
///     floor, which for a freshly started stack is simply true.
/// </summary>
public static class SearchEndpoints
{
    /// <summary>Measured on 600 GDELT events: sensible questions scored 0.570-0.782 and questions
    /// with no answer in the corpus 0.354-0.445. The floor sits in that gap, and it is the same
    /// number the Python analyst uses (analyst.MIN_RELEVANT).</summary>
    public const double MinScore = 0.50;

    public const string EmbedModel = "bge-m3";
    public const int Dimensions = 1024;

    private const string SearchSql = """
        SELECT id AS Id, text AS Text, metadata::text AS Metadata,
               1 - (embedding <=> @vector::vector) AS Score
        FROM document_embedding
        WHERE (@kind IS NULL OR metadata->>'kind' = @kind)
        ORDER BY embedding <=> @vector::vector
        LIMIT @limit
        """;

    public static void MapSearchEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapGet("/api/search", async (NpgsqlDataSource db, IHttpClientFactory httpFactory,
                                         IConfiguration config, ILoggerFactory logs, string q, string? kind,
                                         int? limit, double? minScore, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(q))
            {
                return Results.BadRequest("Query 'q' must not be empty.");
            }

            var take = Math.Clamp(limit ?? 10, 1, 50);
            var floor = Math.Clamp(minScore ?? MinScore, 0.0, 1.0);

            float[] vector;
            try
            {
                vector = await EmbedAsync(httpFactory, config, q, ct);
            }
            catch (Exception e) when (e is HttpRequestException or TaskCanceledException or JsonException)
            {
                // Bez modelu nie ma jak zamienic pytania na wektor. To nie jest blad zapytania i nie
                // jest to pusty wynik - te dwie rzeczy znaczylyby, ze w korpusie nic nie ma.
                // Bez e.Message: tresc wyjatku niesie adres i port wewnetrznego modelu ("Connection
                // refused (host.docker.internal:11434)"), a to jest odpowiedz dla anonimowego klienta.
                // Nazwa modelu zostaje - mowi czytelnikowi, czego brakuje, i nie jest adresem.
                // Zgloszone przez Codeksa 2026-09-28 (SearchEndpoints.cs:67).
                logs.CreateLogger("Wachta.Api.Search").LogWarning(e, "Embedding model {Model} unreachable", EmbedModel);
                return Results.Problem(
                    detail: $"Model osadzen ({EmbedModel}) nie odpowiada. Wyszukiwanie po znaczeniu jest chwilowo niedostepne.",
                    statusCode: StatusCodes.Status503ServiceUnavailable);
            }

            await using var conn = await db.OpenConnectionAsync(ct);
            var rows = await conn.QueryAsync<SearchRow>(SearchSql,
                new { vector = Literal(vector), kind, limit = take });

            var hits = rows
                .Where(r => r.Score >= floor)
                .Select(r => new SearchHit(r.Id, r.Text, Math.Round(r.Score, 4), ParseMetadata(r.Metadata)))
                .ToList();

            return Results.Ok(new SearchResult(
                Query: q,
                Model: EmbedModel,
                MinScore: floor,
                Found: hits.Count,
                Hits: hits,
                Caveat: hits.Count == 0
                    ? "Nic w korpusie nie przekroczylo progu podobienstwa. To jest odpowiedz, nie awaria - "
                      + "swiezo uruchomiony stos ma pusta historie, a najblizszy sasiad istnieje zawsze."
                    : "Wynik to podobienstwo znaczenia, nie trafnosc. Najblizszy dokument istnieje takze "
                      + "wtedy, gdy nic nie pasuje - dlatego przy kazdym trafieniu jest jego wynik."));
        });
    }

    /// <summary>Turns the question into a vector with the same model that indexed the documents.
    ///
    /// It has to be the same model: two embeddings from different models live in different spaces
    /// and the distance between them is a number without meaning. The column stores which model
    /// produced each row for exactly this reason.</summary>
    private static async Task<float[]> EmbedAsync(IHttpClientFactory httpFactory, IConfiguration config,
                                                  string text, CancellationToken ct)
    {
        var url = config["Ollama:Url"] ?? "http://localhost:11434";
        var http = httpFactory.CreateClient("ollama");
        http.Timeout = TimeSpan.FromSeconds(120);

        using var response = await http.PostAsync($"{url.TrimEnd('/')}/api/embed",
            new StringContent(JsonSerializer.Serialize(new { model = EmbedModel, input = text }),
                              Encoding.UTF8, "application/json"), ct);
        response.EnsureSuccessStatusCode();

        using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(ct));
        var first = doc.RootElement.GetProperty("embeddings")[0];
        var vector = new float[first.GetArrayLength()];
        for (var i = 0; i < vector.Length; i++)
        {
            vector[i] = first[i].GetSingle();
        }

        if (vector.Length != Dimensions)
        {
            throw new JsonException($"model zwrocil {vector.Length} wymiarow zamiast {Dimensions}");
        }

        return Normalise(vector);
    }

    /// <summary>Unit length, so the cosine distance pgvector computes means what the caller thinks.</summary>
    private static float[] Normalise(float[] v)
    {
        var length = MathF.Sqrt(v.Sum(x => x * x));
        if (length == 0)
        {
            return v;
        }

        for (var i = 0; i < v.Length; i++)
        {
            v[i] /= length;
        }

        return v;
    }

    /// <summary>pgvector's text form. Invariant culture on purpose: a comma decimal separator would
    /// turn one vector into twice as many numbers and the cast would fail somewhere far from here.</summary>
    private static string Literal(float[] v) =>
        "[" + string.Join(",", v.Select(x => x.ToString("G9", CultureInfo.InvariantCulture))) + "]";

    private static Dictionary<string, JsonElement> ParseMetadata(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return [];
        }

        try
        {
            // jsonb NOT NULL przepuszcza JSON-owego nulla, liczbe i napis - sam brak wyjatku nie
            // wystarczy, trzeba sprawdzic, czy to naprawde obiekt.
            return JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(raw) ?? [];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    private sealed record SearchRow(string Id, string Text, string? Metadata, double Score);
}
