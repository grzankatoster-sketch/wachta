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

    [Fact]
    public void One_record_with_a_hex_that_is_not_a_string_does_not_cost_the_whole_batch()
    {
        // hexEl.GetString() rzuca na liczbie, a wyjatek leci przez cala petle: jeden wadliwy rekord
        // zabieral ze soba kazdy poprawny w tej samej paczce, czyli cala minute obserwacji.
        // Zgloszone przez Codeksa 2026-09-28, potwierdzone na kodzie.
        var json = """
            {"now":1790078400000,"ac":[
              {"hex":4849152,"lat":55.0,"lon":19.0,"seen_pos":1},
              {"hex":"3c6444","lat":55.1,"lon":19.1,"seen_pos":1}]}
            """;

        var wynik = AdsbV2Parser.Parse(json, FetchedAt);

        Assert.Single(wynik.Aircraft);
        Assert.Equal("3c6444", wynik.Aircraft[0].Hex);
    }

    [Fact]
    public void A_negative_age_does_not_place_an_aircraft_in_the_future()
    {
        // Ujemne "seen"/"seen_pos" cofalo odejmowanie: pozycja dostawala czas pozniejszy niz moment
        // odbioru, kontrola swiezosci (fetchedAt - fixedAt) wychodzila ujemna i przechodzila, a w
        // aircraft_contact zostawal szczyt, ktorego zaden pozniejszy poprawny raport juz nie pobije.
        var json = """
            {"now":1790078400000,"ac":[{"hex":"3c6444","lat":55.0,"lon":19.0,"seen":-86400,"seen_pos":-86400}]}
            """;

        var wynik = AdsbV2Parser.Parse(json, FetchedAt);

        Assert.All(wynik.Contacts, c => Assert.True(c.LastMessageAt <= FetchedAt,
            $"kontakt z przyszlosci: {c.LastMessageAt:o} > {FetchedAt:o}"));
        Assert.All(wynik.Aircraft, a => Assert.True(a.Timestamp <= FetchedAt, "pozycja z przyszlosci"));
    }

    [Fact]
    public void A_source_clock_far_from_ours_is_not_believed()
    {
        // "now" w roku 5000 postarza wszystko wzgledem siebie i wycisza D1. Poza tolerancja
        // zostajemy przy wlasnym zegarze - dwa pobrania tej samej paczki daja wtedy rozne czasy,
        // i to jest tansze niz detektor, ktory przestaje strzelac.
        var json = """
            {"now":95617584000000,"ac":[{"hex":"3c6444","lat":55.0,"lon":19.0,"seen_pos":1}]}
            """;

        var wynik = AdsbV2Parser.Parse(json, FetchedAt);

        var kontakt = Assert.Single(wynik.Contacts);
        Assert.True((kontakt.LastMessageAt - FetchedAt).Duration() <= AdsbV2Parser.MaxClockSkew);
    }

    [Theory]
    [InlineData("@@@@@@@@", null)]                 // samolot nie podaje znaku - same znaki wypelniajace
    [InlineData("ZLY41 @@", "ZLY41")]              // znak podany, reszta pola wypelniona
    [InlineData("  RRR2116  ", "RRR2116")]
    [InlineData("", null)]
    [InlineData(null, null)]
    public void Padding_characters_are_not_a_callsign(string? raw, string? expected)
    {
        // Znalezione w bazie po pierwszym uruchomieniu na zywo: "@@@@@@@@" trafialo na mape jako
        // identyfikator. W kodowaniu Mode-S "@" to wypelniacz, czyli BRAK znaku wywolawczego.
        Assert.Equal(expected, AdsbV2Parser.CleanCallsign(raw));
    }
}
