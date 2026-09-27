using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Factory: builds configured sources, always wrapped in the rate-limit decorator.</summary>
public sealed class SourceFactory(IHttpClientFactory httpFactory, TimeProvider clock)
{
    public const int MinIntervalSeconds = 15;

    public IAircraftSource Create(SourceOptions o)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(o.IntervalSeconds, MinIntervalSeconds, nameof(o.IntervalSeconds));

        IAircraftSource source = o.Kind switch
        {
            "adsb-v2" => new AdsbLolSource(httpFactory.CreateClient(o.Id), o.Id, new Uri(o.Url), o.ForceMilitary, clock),
            _ => throw new NotSupportedException($"Unknown source kind '{o.Kind}'"),
        };

        return new ThrottledAircraftSource(source, TimeSpan.FromSeconds(o.IntervalSeconds), clock,
            TimeSpan.FromSeconds(o.StartDelaySeconds));
    }
}
