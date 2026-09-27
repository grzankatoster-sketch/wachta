using Wachta.Domain;
using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class PositionDeduplicatorTests
{
    private static readonly DateTimeOffset T0 = new(2026, 9, 22, 12, 0, 0, TimeSpan.Zero);

    private static AircraftObservation Obs(string hex, int secondsAfterT0, bool military = true) =>
        new(hex, null, null, military, 54, 18, 30000, false, 400, 90, 8, 9, T0.AddSeconds(secondsAfterT0));

    [Fact]
    public void Passes_new_aircraft()
    {
        var sut = new PositionDeduplicator();
        Assert.Equal(2, sut.Filter([Obs("a", 0), Obs("b", 0)]).Count);
    }

    [Fact]
    public void Drops_same_or_older_timestamp_for_same_aircraft_across_batches()
    {
        var sut = new PositionDeduplicator();
        sut.Filter([Obs("a", 10)]);
        Assert.Empty(sut.Filter([Obs("a", 10)]));
        Assert.Empty(sut.Filter([Obs("a", 5)]));
        Assert.Single(sut.Filter([Obs("a", 11)]));
    }

    [Fact]
    public void Drops_duplicates_within_one_batch()
    {
        var sut = new PositionDeduplicator();
        Assert.Single(sut.Filter([Obs("a", 10), Obs("a", 10)]));
    }

    [Fact]
    public void Civil_aircraft_are_sampled_once_per_minute_military_are_not()
    {
        var sut = new PositionDeduplicator();
        sut.Filter([Obs("civ", 0, military: false), Obs("mil", 0)]);

        Assert.Empty(sut.Filter([Obs("civ", 30, military: false)]));
        Assert.Single(sut.Filter([Obs("mil", 30)]));
        Assert.Single(sut.Filter([Obs("civ", 61, military: false)]));
    }
}
