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

            // Rozpakowane wzorcem, a nie przez ".Value" po osobnym bool-u: kompilator nie wiaze
            // "hasPosition" z tym, ze lat i lon nie sa null, wiec tamta wersja wymagalaby "!",
            // czyli obietnicy bez pokrycia. Tu nie-nullowosc wynika wprost z warunku.
            if (lat is not { } latitude || lon is not { } longitude
                || positionTime is not { } fixedAt
                || fetchedAt - fixedAt > TimeSpan.FromSeconds(maxPositionAgeSeconds))
            {
                continue;
            }

            var onGround = a.TryGetProperty("alt_baro", out var alt)
                && alt.ValueKind == JsonValueKind.String
                && alt.GetString() == "ground";
            int? altFt = alt.ValueKind == JsonValueKind.Number ? (int)Math.Round(alt.GetDouble()) : null;
            var flight = CleanCallsign(GetString(a, "flight"));

            result.Add(new AircraftObservation(
                Hex: hex,
                Flight: string.IsNullOrEmpty(flight) ? null : flight,
                TypeCode: GetString(a, "t"),
                IsMilitary: forceMilitary || ((int)(GetDouble(a, "dbFlags") ?? 0) & MilitaryDbFlag) != 0,
                Lat: latitude,
                Lon: longitude,
                AltBaroFt: onGround ? null : altFt,
                OnGround: onGround,
                GroundSpeedKt: (float?)GetDouble(a, "gs"),
                TrackDeg: (float?)GetDouble(a, "track"),
                Nic: (short?)GetDouble(a, "nic"),
                NacP: (short?)GetDouble(a, "nac_p"),
                Timestamp: fixedAt));
        }

        return new ParseResult(result, contacts);
    }

    /// <summary>Strips the Mode-S padding from a callsign, and drops one made of nothing else.
    ///
    /// The callsign field is eight fixed characters and an aircraft that declares none fills them
    /// with '@'. Trimming only whitespace let "@@@@@@@@" and "ZLY41 @@" reach the database and the
    /// map, where they read as identifiers rather than as absence. Found by looking at what the
    /// live pipeline actually stored, not by a test.</summary>
    public static string? CleanCallsign(string? raw)
    {
        var cleaned = raw?.Replace('@', ' ').Trim();
        return string.IsNullOrEmpty(cleaned) ? null : cleaned;
    }

    private static double? GetDouble(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;

    private static string? GetString(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
}
