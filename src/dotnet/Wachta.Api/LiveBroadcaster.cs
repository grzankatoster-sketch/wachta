using Dapper;
using Microsoft.AspNetCore.SignalR;
using Npgsql;

namespace Wachta.Api;

/// <summary>Observer: polls the latest positions and alerts and pushes them to all connected map clients.</summary>
public sealed class LiveBroadcaster(NpgsqlDataSource db, IHubContext<LiveHub> hub, ILogger<LiveBroadcaster> log) : BackgroundService
{
    public static readonly TimeSpan Interval = TimeSpan.FromSeconds(5);

    private const string BroadcastSql = $"""
        SELECT * FROM ({AircraftEndpoints.LiveSql}) live
        """;

    private DateTime _alertsSince = DateTime.UtcNow;

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
