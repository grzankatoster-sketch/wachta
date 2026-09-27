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
