using Dapper;
using Microsoft.AspNetCore.SignalR;
using Npgsql;

namespace Wachta.Api;

/// <summary>Observer: polls the latest positions and alerts and pushes them to all connected map clients.</summary>
public sealed class LiveBroadcaster(NpgsqlDataSource db, IHubContext<LiveHub> hub, ILogger<LiveBroadcaster> log) : BackgroundService
{
    public static readonly TimeSpan Interval = TimeSpan.FromSeconds(5);

    /// <summary>What the map is allowed to show. Public so a test can hold it to it.</summary>
    public static readonly WatchedArea Area = WatchedArea.Baltic;

    private const string BroadcastSql = $"""
        SELECT * FROM ({AircraftEndpoints.LiveSql}) live
        """;

    private DateTime _alertsSince = DateTime.UtcNow;

    /// <summary>
    /// Exactly what the map is sent each tick.
    ///
    /// A method rather than two lines inside the loop, so that a test can call the same code the
    /// broadcaster calls. Asserting on /api/aircraft/live with the bounds passed by hand would prove
    /// only that the SQL can filter - not that this is what actually goes out over the hub, which is
    /// the thing that was wrong.
    ///
    /// One query for both kinds. There used to be two, and the military one ran unbounded: adsb.lol
    /// serves military traffic worldwide, so every tick carried around three hundred aircraft from
    /// other continents.
    /// </summary>
    public static async Task<List<LiveAircraft>> CurrentAircraft(System.Data.Common.DbConnection conn) =>
        (await conn.QueryAsync<LiveAircraft>(BroadcastSql,
            new
            {
                militaryOnly = false,
                minLat = (double?)Area.MinLat, minLon = (double?)Area.MinLon,
                maxLat = (double?)Area.MaxLat, maxLon = (double?)Area.MaxLon,
            })).ToList();

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(Interval);
        do
        {
            try
            {
                await using var conn = await db.OpenConnectionAsync(ct);

                await hub.Clients.All.SendAsync("aircraft", await CurrentAircraft(conn), ct);

                var tickStart = DateTime.UtcNow;
                var alerts = (await conn.QueryAsync<AlertDto>(DetectorEndpoints.AlertsSql, new { since = _alertsSince })).ToList();
                if (alerts.Count > 0)
                {
                    await hub.Clients.All.SendAsync("alerts", alerts, ct);
                }

                _alertsSince = tickStart;
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogWarning(ex, "Live broadcast failed");
            }
        }
        while (await timer.WaitForNextTickAsync(ct));
    }
}
