using Microsoft.Extensions.Time.Testing;
using Wachta.Ingestion;

namespace Wachta.Tests;

public sealed class SourceFactoryTests
{
    private sealed class StubHttpFactory : IHttpClientFactory
    {
        public HttpClient CreateClient(string name) => new();
    }

    private readonly SourceFactory _factory = new(new StubHttpFactory(), new FakeTimeProvider());

    [Fact]
    public void Creates_throttled_adsb_source_with_configured_id()
    {
        var source = _factory.Create(new SourceOptions
        {
            Id = "adsblol-mil", Kind = "adsb-v2", Url = "https://api.adsb.lol/v2/mil", ForceMilitary = true, IntervalSeconds = 15,
        });
        Assert.IsType<ThrottledAircraftSource>(source);
        Assert.Equal("adsblol-mil", source.Id);
    }

    [Fact]
    public void Unknown_kind_throws()
    {
        Assert.Throws<NotSupportedException>(() =>
            _factory.Create(new SourceOptions { Id = "x", Kind = "carrier-pigeon", Url = "https://x", IntervalSeconds = 15 }));
    }

    [Fact]
    public void Interval_below_15_seconds_is_rejected()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            _factory.Create(new SourceOptions { Id = "x", Kind = "adsb-v2", Url = "https://x", IntervalSeconds = 5 }));
    }
}
