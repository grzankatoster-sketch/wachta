using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class AdsbV2ParserTests
{
    private static readonly DateTimeOffset FetchedAt = new(2026, 9, 22, 12, 0, 0, TimeSpan.Zero);
    private static string Sample() => File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "adsb_v2_sample.json"));

    [Fact]
    public void Skips_aircraft_without_position_and_with_stale_position()
    {
        var result = AdsbV2Parser.Parse(Sample(), FetchedAt).Aircraft;
        Assert.Equal(new[] { "43c6f1", "48ad01", "ae1234" }, result.Select(a => a.Hex));
    }

    [Fact]
    public void Contacts_cover_every_aircraft_including_those_without_position()
    {
        var contacts = AdsbV2Parser.Parse(Sample(), FetchedAt).Contacts;
        Assert.Equal(5, contacts.Count);

        // still transmitting (seen 3 s) but no position at all -> contact without LastPositionAt
        var noPosition = Assert.Single(contacts, c => c.Hex == "4ca7b2");
        Assert.Equal(FetchedAt.AddSeconds(-3), noPosition.LastMessageAt);
        Assert.Null(noPosition.LastPositionAt);

        // stale position (95 s) but message age unknown -> message age falls back to position age
        var stalePosition = Assert.Single(contacts, c => c.Hex == "4b1815");
        Assert.Equal(FetchedAt.AddSeconds(-95), stalePosition.LastPositionAt);
    }

    [Fact]
    public void Timestamps_come_from_source_clock_not_fetch_time()
    {
        // Same payload fetched 40 s later must yield the same observation timestamps (dedup relies on it).
        var first = AdsbV2Parser.Parse(Sample(), FetchedAt).Aircraft[0];
        var second = AdsbV2Parser.Parse(Sample(), FetchedAt.AddSeconds(40), maxPositionAgeSeconds: 120).Aircraft[0];
        Assert.Equal(first.Timestamp, second.Timestamp);
    }

    [Fact]
    public void Stale_payload_is_rejected_by_position_age_against_fetch_time()
    {
        Assert.Empty(AdsbV2Parser.Parse(Sample(), FetchedAt.AddMinutes(5)).Aircraft);
    }

    [Fact]
    public void Maps_fields_of_airborne_military_aircraft()
    {
        var a = AdsbV2Parser.Parse(Sample(), FetchedAt).Aircraft[0];
        Assert.Equal("RRR2302", a.Flight);
        Assert.Equal("A332", a.TypeCode);
        Assert.True(a.IsMilitary);
        Assert.Equal(27000, a.AltBaroFt);
        Assert.False(a.OnGround);
        Assert.Equal(410.5f, a.GroundSpeedKt);
        Assert.Equal((short)8, a.Nic);
        Assert.Equal((short)9, a.NacP);
        Assert.Equal(FetchedAt.AddSeconds(-1.2), a.Timestamp);
    }

    [Fact]
    public void Ground_aircraft_has_no_altitude_and_is_not_military()
    {
        var a = AdsbV2Parser.Parse(Sample(), FetchedAt).Aircraft[1];
        Assert.True(a.OnGround);
        Assert.Null(a.AltBaroFt);
        Assert.False(a.IsMilitary);
    }

    [Fact]
    public void Force_military_marks_all_and_fractional_altitude_is_rounded()
    {
        var result = AdsbV2Parser.Parse(Sample(), FetchedAt, forceMilitary: true).Aircraft;
        Assert.All(result, a => Assert.True(a.IsMilitary));
        Assert.Equal(24000, result[2].AltBaroFt);
        Assert.Null(result[2].Flight);
    }

    [Fact]
    public void Empty_or_missing_ac_array_returns_empty_lists()
    {
        Assert.Empty(AdsbV2Parser.Parse("{\"now\":1790078400000}", FetchedAt).Aircraft);
        Assert.Empty(AdsbV2Parser.Parse("{\"now\":1790078400000,\"ac\":[]}", FetchedAt).Contacts);
    }
}
