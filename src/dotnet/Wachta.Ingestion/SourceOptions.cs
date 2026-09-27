namespace Wachta.Ingestion;

public sealed class SourceOptions
{
    public string Id { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Url { get; set; } = "";
    public bool ForceMilitary { get; set; }
    public int IntervalSeconds { get; set; } = 15;

    /// <summary>Staggers sources so they never fire together: simultaneous bursts are what adsb.lol answers with 429.</summary>
    public int StartDelaySeconds { get; set; }
}
