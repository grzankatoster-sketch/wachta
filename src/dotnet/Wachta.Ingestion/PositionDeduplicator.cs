using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>
/// The same aircraft arrives from several overlapping sources; keep only strictly newer positions per hex.
/// Civil traffic is sampled down to one position per minute — full rate for everything would be ~40M rows/week.
/// </summary>
public sealed class PositionDeduplicator(TimeSpan? civilMinInterval = null)
{
    private readonly TimeSpan _civilMinInterval = civilMinInterval ?? TimeSpan.FromSeconds(60);
    private readonly Dictionary<string, DateTimeOffset> _lastByHex = new();

    public IReadOnlyList<AircraftObservation> Filter(IReadOnlyList<AircraftObservation> batch)
    {
        var accepted = new List<AircraftObservation>(batch.Count);
        foreach (var obs in batch)
        {
            if (_lastByHex.TryGetValue(obs.Hex, out var last)
                && (obs.Timestamp <= last || (!obs.IsMilitary && obs.Timestamp - last < _civilMinInterval)))
            {
                continue;
            }

            _lastByHex[obs.Hex] = obs.Timestamp;
            accepted.Add(obs);
        }

        return accepted;
    }
}
