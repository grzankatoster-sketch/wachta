using Npgsql;
using Wachta.Domain;
using Wachta.Ingestion;

namespace Wachta.Tests;

[Collection("postgres")]
public sealed class PositionWriterTests(PostgresFixture db)
{
    [Fact]
    public async Task Writes_positions_and_fetch_log_with_provenance()
    {
        await using var ds = NpgsqlDataSource.Create(db.ConnectionString);
        var writer = new PositionWriter(ds);
        var fetchedAt = DateTimeOffset.UtcNow;
        var obs = new AircraftObservation("43c6f1", "RRR2302", "A332", true, 54.9, 19.8, 27000, false, 410.5f, 92.1f, 8, 9, fetchedAt.AddSeconds(-1));
        var nullable = obs with { Hex = "ae1234", Flight = null, AltBaroFt = null, Nic = null, NacP = null, GroundSpeedKt = null, TrackDeg = null };
        var contacts = new[]
        {
            new AircraftContact("43c6f1", fetchedAt.AddSeconds(-1), fetchedAt.AddSeconds(-1)),
            new AircraftContact("silent1", fetchedAt.AddSeconds(-4), null),
        };
        var snap = new SourceSnapshot("adsblol-mil", new Uri("https://api.adsb.lol/v2/mil"), fetchedAt, "abc123", [obs, nullable], contacts);

        var written = await writer.WriteAsync(snap, snap.Aircraft, CancellationToken.None);

        Assert.Equal(2, written);
        await using var conn = await ds.OpenConnectionAsync();
        await using var q1 = new NpgsqlCommand("SELECT count(*) FROM aircraft_position WHERE hex IN ('43c6f1','ae1234') AND source_id = 'adsblol-mil'", conn);
        Assert.Equal(2L, (long)(await q1.ExecuteScalarAsync())!);
        await using var q2 = new NpgsqlCommand("SELECT n_received, n_written FROM fetch_log WHERE content_hash = 'abc123'", conn);
        await using var r = await q2.ExecuteReaderAsync();
        Assert.True(await r.ReadAsync());
        Assert.Equal(2, r.GetInt32(0));
        Assert.Equal(2, r.GetInt32(1));
    }

    [Fact]
    public async Task Contacts_are_upserted_and_never_go_backwards()
    {
        await using var ds = NpgsqlDataSource.Create(db.ConnectionString);
        var writer = new PositionWriter(ds);
        var t0 = DateTimeOffset.UtcNow;
        var snapshot = (DateTimeOffset msg, DateTimeOffset? pos) => new SourceSnapshot(
            "adsblol-mil", new Uri("https://x"), t0, "c-hash", [], [new AircraftContact("con001", msg, pos)]);

        await writer.WriteAsync(snapshot(t0, t0), [], CancellationToken.None);
        await writer.WriteAsync(snapshot(t0.AddSeconds(-30), null), [], CancellationToken.None);

        await using var conn = await ds.OpenConnectionAsync();
        await using var q = new NpgsqlCommand("SELECT last_message_at, last_position_at FROM aircraft_contact WHERE hex = 'con001'", conn);
        await using var r = await q.ExecuteReaderAsync();
        Assert.True(await r.ReadAsync());
        Assert.Equal(t0.UtcDateTime, r.GetDateTime(0), TimeSpan.FromMilliseconds(1));
        Assert.False(await r.IsDBNullAsync(1));
    }

    [Fact]
    public async Task Empty_batch_still_logs_fetch()
    {
        await using var ds = NpgsqlDataSource.Create(db.ConnectionString);
        var snap = new SourceSnapshot("adsblol-baltic-s", new Uri("https://x"), DateTimeOffset.UtcNow, "empty-hash", [], []);
        Assert.Equal(0, await new PositionWriter(ds).WriteAsync(snap, [], CancellationToken.None));
        await using var conn = await ds.OpenConnectionAsync();
        await using var q = new NpgsqlCommand("SELECT count(*) FROM fetch_log WHERE content_hash = 'empty-hash'", conn);
        Assert.Equal(1L, (long)(await q.ExecuteScalarAsync())!);
    }
}
