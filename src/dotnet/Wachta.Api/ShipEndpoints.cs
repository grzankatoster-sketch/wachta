using Dapper;
using Npgsql;

namespace Wachta.Api;

/// <summary>
/// Ships, which until now were collected and never shown.
///
/// The detectors that produce most of the alerts are maritime - a ship going silent, two hulls
/// alongside, an anchor dragging near a cable, one MMSI on two hulls - and the map was showing
/// aircraft only. So the alert list said "przeladunek burta w burte" and there was no ship anywhere
/// on screen to look at. Measured 2026-09-29: 817 hulls in the last half hour, 804 of them named,
/// every one with a course, none of them drawn.
///
/// The window is 30 minutes rather than the 2 the aircraft use. A ship at anchor reports every few
/// minutes and a moving one every few seconds; a two-minute window would quietly drop the stationary
/// half of the traffic, which is exactly the half the anchor and rendezvous detectors care about.
/// </summary>
public static class ShipEndpoints
{
    public const string LiveSql = """
        SELECT DISTINCT ON (mmsi)
               mmsi AS Mmsi, name AS Name, ship_type AS ShipType, nav_status AS NavStatus,
               lat AS Lat, lon AS Lon, sog_kt AS SogKt, cog_deg AS CogDeg, ts AS Ts
        FROM ship_position
        WHERE ts > now() - interval '30 minutes'
          AND (@minLat IS NULL OR lat BETWEEN @minLat AND @maxLat)
          AND (@minLon IS NULL OR lon BETWEEN @minLon AND @maxLon)
        ORDER BY mmsi, ts DESC
        """;

    /// <summary>Where a ship has been, for the question "where is it coming from".</summary>
    public const string TrackSql = """
        SELECT ts AS Ts, lat AS Lat, lon AS Lon, sog_kt AS SogKt, cog_deg AS CogDeg
        FROM ship_position
        WHERE mmsi = @mmsi AND ts BETWEEN @from AND @to
        ORDER BY ts
        """;

    public static void MapShipEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapGet("/api/ships/live", async (NpgsqlDataSource db,
            double? minLat, double? minLon, double? maxLat, double? maxLon) =>
        {
            await using var conn = await db.OpenConnectionAsync();
            return await conn.QueryAsync<LiveShip>(LiveSql, new { minLat, minLon, maxLat, maxLon });
        });

        app.MapGet("/api/ships/{mmsi}/track", async (NpgsqlDataSource db, string mmsi, int? hours) =>
        {
            var okno = Math.Clamp(hours ?? 6, 1, 24);
            var to = DateTime.UtcNow;
            var from = to.AddHours(-okno);

            await using var conn = await db.OpenConnectionAsync();
            var punkty = (await conn.QueryAsync<ShipTrackPoint>(TrackSql, new { mmsi, from, to })).ToList();
            return Results.Ok(punkty);
        });
    }
}
