using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.SignalR.Client;
using Npgsql;
using Wachta.Api;

namespace Wachta.Tests;

[Collection("postgres")]
public sealed class LiveHubTests(PostgresFixture db)
{
    [DockerFact]
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
