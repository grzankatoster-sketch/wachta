namespace Wachta.Api;

public sealed record LiveAircraft(
    string Hex, string? Flight, string? TypeCode, bool IsMilitary, double Lat, double Lon,
    int? AltBaroFt, bool OnGround, float? GsKt, float? TrackDeg, DateTime Ts);

public sealed record TrackPoint(DateTime Ts, double Lat, double Lon, int? AltBaroFt);

public sealed record SourceInfo(string Id, string Name, string Url, string License, short TrustTier, string Attribution);
