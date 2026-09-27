using Microsoft.Extensions.Time.Testing;
using Wachta.Domain;
using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class MilitaryRegistryTests
{
    private static readonly DateTimeOffset T0 = new(2026, 9, 26, 12, 0, 0, TimeSpan.Zero);

    private static AircraftObservation Obs(string hex, bool military) =>
        new(hex, null, null, military, 55, 19, 25000, false, 400, 90, 8, 9, T0);

    [Fact]
    public void Aircraft_seen_as_military_stays_military_when_an_area_source_reports_it()
    {
        var sut = new MilitaryRegistry(new FakeTimeProvider());
        sut.Remember([Obs("ae1234", military: true)]);

        // The area endpoint carries no dbFlags at all, so everything arrives as civil.
        var fromArea = sut.Apply([Obs("ae1234", military: false), Obs("48ad01", military: false)]);

        Assert.True(fromArea[0].IsMilitary);
        Assert.False(fromArea[1].IsMilitary);
    }

    [Fact]
    public void Unknown_aircraft_are_left_alone()
    {
        var sut = new MilitaryRegistry(new FakeTimeProvider());
        var batch = new[] { Obs("48ad01", military: false) };
        Assert.Same(batch, sut.Apply(batch));
    }

    [Fact]
    public void Entries_expire_so_a_reused_address_does_not_stay_military_forever()
    {
        var clock = new FakeTimeProvider(T0);
        var sut = new MilitaryRegistry(clock, TimeSpan.FromHours(12));
        sut.Remember([Obs("ae1234", military: true)]);

        clock.Advance(TimeSpan.FromHours(13));
        sut.Remember([Obs("48ad01", military: true)]);

        Assert.False(sut.IsKnownMilitary("ae1234"));
        Assert.True(sut.IsKnownMilitary("48ad01"));
        Assert.Equal(1, sut.Count);
    }
}
