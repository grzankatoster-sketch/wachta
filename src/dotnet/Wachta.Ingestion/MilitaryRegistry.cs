using System.Collections.Concurrent;
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>
/// Remembers which aircraft the military endpoint reported.
///
/// Measured on live data 2026-09-26: adsb.lol returns <c>dbFlags</c> only from <c>/v2/mil</c> — in the
/// area endpoints the field is absent for every aircraft (0 of 92). Without this registry a military
/// aircraft picked up first by an area source would be stored as civil, and the dedup would then drop
/// the military copy as older.
/// </summary>
public sealed class MilitaryRegistry(TimeProvider clock, TimeSpan? retention = null)
{
    private readonly TimeSpan _retention = retention ?? TimeSpan.FromHours(12);
    private readonly ConcurrentDictionary<string, DateTimeOffset> _seen = new();

    public int Count => _seen.Count;

    public void Remember(IEnumerable<AircraftObservation> observations)
    {
        var now = clock.GetUtcNow();
        foreach (var o in observations.Where(o => o.IsMilitary))
        {
            _seen[o.Hex] = now;
        }

        if (_seen.Count > 0)
        {
            var cutoff = now - _retention;
            foreach (var (hex, at) in _seen)
            {
                if (at < cutoff)
                {
                    _seen.TryRemove(hex, out _);
                }
            }
        }
    }

    public bool IsKnownMilitary(string hex) => _seen.ContainsKey(hex);

    /// <summary>Restores the military flag on observations that came from a source which cannot report it.</summary>
    public IReadOnlyList<AircraftObservation> Apply(IReadOnlyList<AircraftObservation> observations)
    {
        if (_seen.IsEmpty)
        {
            return observations;
        }

        var result = new List<AircraftObservation>(observations.Count);
        foreach (var o in observations)
        {
            result.Add(!o.IsMilitary && IsKnownMilitary(o.Hex) ? o with { IsMilitary = true } : o);
        }

        return result;
    }
}
