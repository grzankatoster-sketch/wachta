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
