namespace Wachta.Api;

public sealed record LiveAircraft(
    string Hex, string? Flight, string? TypeCode, bool IsMilitary, double Lat, double Lon,
    int? AltBaroFt, bool OnGround, float? GsKt, float? TrackDeg, DateTime Ts);

public sealed record TrackPoint(DateTime Ts, double Lat, double Lon, int? AltBaroFt);

/// <summary>One ship as the map draws it. ShipType is the raw AIS number - the front end decides
/// what a 70 looks like, because that mapping is a display choice, not a fact about the hull.</summary>
public sealed record LiveShip(
    string Mmsi, string? Name, string? ShipType, string? NavStatus,
    double Lat, double Lon, float? SogKt, float? CogDeg, DateTime Ts);

public sealed record ShipTrackPoint(DateTime Ts, double Lat, double Lon, float? SogKt, float? CogDeg);

public sealed record SourceInfo(string Id, string Name, string Url, string License, short TrustTier, string Attribution);

/// <summary>One detector alert. Evidence stays raw JSON: the reader must be able to see what the
/// rule actually looked at, not a sentence the API wrote about it.</summary>
public sealed record AlertDto(
    long Id, string Detector, string EntityId, DateTime StartedAt, double Lat, double Lon,
    float Score, string Evidence, string State);

/// <summary>One H3 cell in one hour. Both counts travel together on purpose - a share without its
/// denominator hides how few aircraft it was computed from.</summary>
public sealed record JammingDto(string H3, int NAircraft, int NDegraded);

/// <summary>One aircraft's path over the replay window. Path[i] is [lon, lat] to match GeoJSON
/// order; Timestamps[i] is Unix seconds for the same index.</summary>
public sealed record ReplayPath(
    string Hex, string? Flight, string? TypeCode, double[][] Path, long[] Timestamps);

/// <summary>One document found by meaning, with the score that says how much to trust it.</summary>
public sealed record SearchHit(
    string Id, string Text, double Score, Dictionary<string, System.Text.Json.JsonElement> Metadata);

/// <summary>A whole answer, including the caveat. The caveat travels with the data because whoever
/// reads this - a person or a model - will be exactly as careful as the response makes them.</summary>
public sealed record SearchResult(
    string Query, string Model, double MinScore, int Found, IReadOnlyList<SearchHit> Hits, string Caveat);
