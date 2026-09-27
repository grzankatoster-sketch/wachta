namespace Wachta.Domain;

public sealed record AircraftObservation(
    string Hex,
    string? Flight,
    string? TypeCode,
    bool IsMilitary,
    double Lat,
    double Lon,
    int? AltBaroFt,
    bool OnGround,
    float? GroundSpeedKt,
    float? TrackDeg,
    short? Nic,
    short? NacP,
    DateTimeOffset Timestamp);
