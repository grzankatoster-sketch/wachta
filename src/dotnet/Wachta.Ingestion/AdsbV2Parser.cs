using System.Text.Json;
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Parses the ADSBExchange-v2-compatible JSON returned by adsb.lol (and airplanes.live).</summary>
public static class AdsbV2Parser
{
    private const int MilitaryDbFlag = 1;

    public static ParseResult Parse(
        string json, DateTimeOffset fetchedAt, bool forceMilitary = false, double maxPositionAgeSeconds = 30)
    {
        using var doc = JsonDocument.Parse(json);
        var result = new List<AircraftObservation>();
        var contacts = new List<AircraftContact>();
        if (!doc.RootElement.TryGetProperty("ac", out var ac) || ac.ValueKind != JsonValueKind.Array)
        {
            return new ParseResult(result, contacts);
        }

        // Source clock: the same payload fetched twice must produce identical timestamps.
        var sourceNow = GetDouble(doc.RootElement, "now") is { } nowMs
            ? DateTimeOffset.FromUnixTimeMilliseconds((long)nowMs)
            : fetchedAt;

        foreach (var a in ac.EnumerateArray())
        {
            if (!a.TryGetProperty("hex", out var hexEl) || hexEl.GetString() is not { Length: > 0 } rawHex)
            {
                continue;
            }

            var hex = rawHex.Trim().ToLowerInvariant();
            var lat = GetDouble(a, "lat");
            var lon = GetDouble(a, "lon");
            var seenPos = GetDouble(a, "seen_pos");
            var hasPosition = lat is not null && lon is not null;
            var positionTime = hasPosition ? sourceNow.AddSeconds(-(seenPos ?? 0)) : (DateTimeOffset?)null;

            // "seen" = age of the last message of any kind; without it fall back to the position age.
            var seenMessage = GetDouble(a, "seen") ?? seenPos ?? 0;
            contacts.Add(new AircraftContact(hex, sourceNow.AddSeconds(-seenMessage), positionTime));

            if (!hasPosition || fetchedAt - positionTime!.Value > TimeSpan.FromSeconds(maxPositionAgeSeconds))
            {
                continue;
            }

            var onGround = a.TryGetProperty("alt_baro", out var alt)
                && alt.ValueKind == JsonValueKind.String
                && alt.GetString() == "ground";
            int? altFt = alt.ValueKind == JsonValueKind.Number ? (int)Math.Round(alt.GetDouble()) : null;
            var flight = GetString(a, "flight")?.Trim();

            result.Add(new AircraftObservation(
                Hex: hex,
                Flight: string.IsNullOrEmpty(flight) ? null : flight,
                TypeCode: GetString(a, "t"),
                IsMilitary: forceMilitary || ((int)(GetDouble(a, "dbFlags") ?? 0) & MilitaryDbFlag) != 0,
                Lat: lat.Value,
                Lon: lon.Value,
                AltBaroFt: onGround ? null : altFt,
                OnGround: onGround,
                GroundSpeedKt: (float?)GetDouble(a, "gs"),
                TrackDeg: (float?)GetDouble(a, "track"),
                Nic: (short?)GetDouble(a, "nic"),
                NacP: (short?)GetDouble(a, "nac_p"),
                Timestamp: positionTime.Value));
        }

        return new ParseResult(result, contacts);
    }

    private static double? GetDouble(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;

    private static string? GetString(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
}
