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
            DELETE FROM aircraft_position WHERE hex IN ('api001','api002','api003','api004');
            DELETE FROM ship_position WHERE mmsi IN ('999000001','999000002','999000003');
            INSERT INTO ship_position (ts, mmsi, name, ship_type, nav_status, lat, lon, sog_kt, cog_deg, source_id, fetched_at) VALUES
              (now() - interval '3 minutes',  '999000001', 'TEST CARGO', '70', '0', 60.0, 25.0, 12.0,  90, 'digitraffic-ais', now()),
              (now() - interval '20 minutes', '999000002', 'TEST MOORED','52', '5', 60.1, 25.1,  0.0,   0, 'digitraffic-ais', now()),
              (now() - interval '3 minutes',  '999000003', 'TEST FAR',   '70', '0', 33.9,-118.4, 9.0,  10, 'digitraffic-ais', now());
            INSERT INTO aircraft_position (ts, hex, flight, type_code, is_military, lat, lon, alt_baro_ft, on_ground, gs_kt, track_deg, nic, nac_p, source_id, fetched_at) VALUES
              (now() - interval '90 seconds', 'api001', 'OLD1', 'K35R', true,  55.0, 19.0, 25000, false, 400, 90, 8, 9, 'adsblol-mil', now()),
              (now() - interval '10 seconds', 'api001', 'NEW1', 'K35R', true,  55.1, 19.2, 25000, false, 400, 90, 8, 9, 'adsblol-mil', now()),
              (now() - interval '10 seconds', 'api002', 'CIV1', 'A320', false, 54.0, 18.0, 36000, false, 450, 45, 8, 9, 'adsblol-baltic-s', now()),
              (now() - interval '10 minutes', 'api003', 'GONE', 'C17',  true,  56.0, 20.0, 30000, false, 420, 10, 8, 9, 'adsblol-mil', now()),
              (now() - interval '10 seconds', 'api004', 'FARAWAY', 'C17', true, 33.9, -118.4, 30000, false, 420, 10, 8, 9, 'adsblol-mil', now());
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
    public async Task The_map_is_not_sent_military_traffic_from_other_continents()
    {
        // adsb.lol's military endpoint is worldwide, the area ones are not. Broadcasting the first
        // unbounded put ~300 aircraft from other continents into every update: never visible at the
        // Baltic zoom, always counted, so the header read "446 aircraft in range, 58% military".
        // Mutacja: usuniecie granic z CurrentAircraft przywraca api004 i wywraca ten test.
        await using var conn = new NpgsqlConnection(_db.ConnectionString);
        await conn.OpenAsync();
        var live = await LiveBroadcaster.CurrentAircraft(conn);

        Assert.DoesNotContain(live, a => a.Hex == "api004");
        Assert.Contains(live, a => a.Hex == "api001");   // wojskowy W obszarze zostaje
        Assert.Contains(live, a => a.Hex == "api002");   // cywilny tez
        Assert.All(live, a => Assert.True(LiveBroadcaster.Area.Contains(a.Lat, a.Lon), $"{a.Hex} poza obszarem"));
    }

    [DockerFact]
    public async Task Ships_are_broadcast_and_a_moored_one_is_not_dropped_by_the_window()
    {
        // Osiemset statkow siedzialo w bazie i nie bylo ich na mapie, bo nie bylo czym ich wyslac.
        // Okno 30 minut, a nie 2 jak przy samolotach: statek na kotwicy nadaje co kilka minut, wiec
        // krotkie okno po cichu gubiloby wlasnie te jednostki, ktorymi zajmuja sie D5 i D6.
        await using var conn = new NpgsqlConnection(_db.ConnectionString);
        await conn.OpenAsync();
        var statki = await LiveBroadcaster.CurrentShips(conn);

        Assert.Contains(statki, s => s.Mmsi == "999000001");
        Assert.Contains(statki, s => s.Mmsi == "999000002");   // zacumowany sprzed 20 minut zostaje
        Assert.DoesNotContain(statki, s => s.Mmsi == "999000003");  // spoza obszaru odpada
        Assert.All(statki, s => Assert.True(LiveBroadcaster.Area.Contains(s.Lat, s.Lon)));

        var cargo = Assert.Single(statki, s => s.Mmsi == "999000001");
        Assert.Equal("TEST CARGO", cargo.Name);
        Assert.Equal("70", cargo.ShipType);
        Assert.Equal(90, cargo.CogDeg);
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
