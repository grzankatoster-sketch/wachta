using Microsoft.Extensions.Time.Testing;
using Wachta.Domain;
using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class ThrottledAircraftSourceTests
{
    private sealed class CountingSource : IAircraftSource
    {
        public int Calls;
        public string Id => "fake";
        public Task<SourceSnapshot> FetchAsync(CancellationToken ct)
        {
            Calls++;
            return Task.FromResult(new SourceSnapshot("fake", new Uri("https://x"), DateTimeOffset.UnixEpoch, "h", [], []));
        }
    }

    [Fact]
    public async Task First_call_is_immediate()
    {
        var inner = new CountingSource();
        var sut = new ThrottledAircraftSource(inner, TimeSpan.FromSeconds(15), new FakeTimeProvider());
        await sut.FetchAsync(CancellationToken.None);
        Assert.Equal(1, inner.Calls);
    }

    [Fact]
    public async Task Second_call_waits_for_min_interval()
    {
        var clock = new FakeTimeProvider();
        var inner = new CountingSource();
        var sut = new ThrottledAircraftSource(inner, TimeSpan.FromSeconds(15), clock);
        await sut.FetchAsync(CancellationToken.None);

        var second = sut.FetchAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(14));
        Assert.False(second.IsCompleted);

        clock.Advance(TimeSpan.FromSeconds(1));
        await second;
        Assert.Equal(2, inner.Calls);
    }

    [Fact]
    public async Task No_wait_when_interval_already_passed()
    {
        var clock = new FakeTimeProvider();
        var inner = new CountingSource();
        var sut = new ThrottledAircraftSource(inner, TimeSpan.FromSeconds(15), clock);
        await sut.FetchAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(20));
        var second = sut.FetchAsync(CancellationToken.None);
        Assert.True(second.IsCompleted);
        await second;
    }

    [Fact]
    public void Id_is_passed_through()
    {
        var sut = new ThrottledAircraftSource(new CountingSource(), TimeSpan.FromSeconds(1), new FakeTimeProvider());
        Assert.Equal("fake", sut.Id);
    }
}
