namespace Wachta.Domain;

/// <summary>Last time we heard an aircraft at all (message), and last time it reported a position.</summary>
public sealed record AircraftContact(string Hex, DateTimeOffset LastMessageAt, DateTimeOffset? LastPositionAt);

public sealed record ParseResult(
    IReadOnlyList<AircraftObservation> Aircraft,
    IReadOnlyList<AircraftContact> Contacts);

/// <summary>One fetch from one source, with provenance (who, when, from where, content hash).</summary>
public sealed record SourceSnapshot(
    string SourceId,
    Uri Url,
    DateTimeOffset FetchedAt,
    string ContentHash,
    IReadOnlyList<AircraftObservation> Aircraft,
    IReadOnlyList<AircraftContact> Contacts);
