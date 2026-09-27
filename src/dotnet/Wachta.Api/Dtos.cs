namespace Wachta.Api;

public sealed record LiveAircraft(
    string Hex, string? Flight, string? TypeCode, bool IsMilitary, double Lat, double Lon,
    int? AltBaroFt, bool OnGround, float? GsKt, float? TrackDeg, DateTime Ts);

public sealed record TrackPoint(DateTime Ts, double Lat, double Lon, int? AltBaroFt);

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
