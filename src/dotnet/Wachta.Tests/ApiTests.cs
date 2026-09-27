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

    [DockerFact]
    public async Task Live_returns_latest_position_per_aircraft_from_last_two_minutes()
    {
        var live = await _client.GetFromJsonAsync<List<LiveAircraft>>("/api/aircraft/live");
        var api001 = Assert.Single(live!, a => a.Hex == "api001");
        Assert.Equal("NEW1", api001.Flight);
        Assert.DoesNotContain(live!, a => a.Hex == "api003");
    }

    [DockerFact]
    public async Task Live_military_only_filters_civil()
    {
        var live = await _client.GetFromJsonAsync<List<LiveAircraft>>("/api/aircraft/live?militaryOnly=true");
        Assert.DoesNotContain(live!, a => a.Hex == "api002");
    }

    [DockerFact]
    public async Task Live_bbox_filters_by_position()
    {
        var live = await _client.GetFromJsonAsync<List<LiveAircraft>>("/api/aircraft/live?minLat=53&minLon=17&maxLat=54.5&maxLon=18.5");
        Assert.Contains(live!, a => a.Hex == "api002");
        Assert.DoesNotContain(live!, a => a.Hex == "api001");
    }

    [DockerFact]
    public async Task Track_returns_points_in_time_order()
    {
        var from = DateTime.UtcNow.AddMinutes(-5).ToString("O");
        var to = DateTime.UtcNow.ToString("O");
        var track = await _client.GetFromJsonAsync<List<TrackPoint>>($"/api/aircraft/api001/track?from={from}&to={to}");
        Assert.Equal(2, track!.Count);
        Assert.True(track[0].Ts < track[1].Ts);
    }

    [DockerFact]
    public async Task Track_window_over_24h_is_rejected()
    {
        var res = await _client.GetAsync($"/api/aircraft/api001/track?from={DateTime.UtcNow.AddDays(-2):O}&to={DateTime.UtcNow:O}");
        Assert.Equal(HttpStatusCode.BadRequest, res.StatusCode);
    }

    [DockerFact]
    public async Task Sources_lists_seeded_sources_with_license()
    {
        var sources = await _client.GetFromJsonAsync<List<SourceInfo>>("/api/sources");
        Assert.Contains(sources!, s => s.Id == "adsblol-mil" && s.License == "ODbL 1.0");
    }
}
