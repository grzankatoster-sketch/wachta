using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Decorator: guarantees a minimum interval between calls to the wrapped source (API rate limits).</summary>
public sealed class ThrottledAircraftSource(
    IAircraftSource inner, TimeSpan minInterval, TimeProvider clock, TimeSpan startDelay = default) : IAircraftSource
{
    private DateTimeOffset? _lastCall;
    private bool _started;

    public string Id => inner.Id;

    public async Task<SourceSnapshot> FetchAsync(CancellationToken ct)
    {
        if (!_started)
        {
            _started = true;
            if (startDelay > TimeSpan.Zero)
            {
                await Task.Delay(startDelay, clock, ct);
            }
        }

        if (_lastCall is { } last)
        {
            var wait = last + minInterval - clock.GetUtcNow();
            if (wait > TimeSpan.Zero)
            {
                await Task.Delay(wait, clock, ct);
            }
        }

        _lastCall = clock.GetUtcNow();
        return await inner.FetchAsync(ct);
    }
}
