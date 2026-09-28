using System.Text.Json;
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Parses the ADSBExchange-v2-compatible JSON returned by adsb.lol (and airplanes.live).</summary>
public static class AdsbV2Parser
{
    private const int MilitaryDbFlag = 1;

    /// <summary>How far the source clock may differ from ours before we stop believing it.</summary>
    public static readonly TimeSpan MaxClockSkew = TimeSpan.FromMinutes(5);

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
        //
        // Trusted only while it stays near ours. Everything downstream is measured FROM this instant,
        // so a "now" in the year 5000 backdates nothing and postdates everything: the freshness check
        // below (fetchedAt - fixedAt) goes negative and passes, aircraft_contact records a maximum no
        // later report can beat, and D1 - which calls an aircraft dark when its last message is old
        // enough - stops firing. An out-of-range value would also throw straight out of
        // FromUnixTimeMilliseconds and cost the whole batch. Beyond the tolerance we keep our own
        // clock: timestamps then differ between two fetches of one payload, which is a smaller price.
        // Zgloszone przez Codeksa 2026-09-28 (AdsbV2Parser.cs:43), potwierdzone na kodzie.
        var sourceNow = fetchedAt;
        if (GetDouble(doc.RootElement, "now") is { } nowMs
            && nowMs is > -62135596800000d and < 253402300799999d)
        {
            var reported = DateTimeOffset.FromUnixTimeMilliseconds((long)nowMs);
            if ((reported - fetchedAt).Duration() <= MaxClockSkew)
            {
                sourceNow = reported;
            }
        }

        foreach (var a in ac.EnumerateArray())
        {
            // Przez GetString, a nie hexEl.GetString(): pomocnik sprawdza rodzaj wartosci, a goly
            // odczyt rzuca InvalidOperationException, gdy "hex" przyjdzie jako liczba albo null -
            // i jeden taki rekord w paczce kasowal wszystkie pozostale, tez poprawne.
            if (GetString(a, "hex") is not { Length: > 0 } rawHex)
            {
                continue;
            }

            var hex = rawHex.Trim().ToLowerInvariant();
            var lat = GetDouble(a, "lat");
            var lon = GetDouble(a, "lon");
            // Wiek nie bywa ujemny. Ujemny "seen_pos" przesuwalby pozycje w przyszlosc.
            var seenPos = GetDouble(a, "seen_pos") is { } sp ? Math.Max(0, sp) : (double?)null;
            var hasPosition = lat is not null && lon is not null;
            var positionTime = hasPosition ? sourceNow.AddSeconds(-(seenPos ?? 0)) : (DateTimeOffset?)null;

            // "seen" = age of the last message of any kind; without it fall back to the position age.
            var seenMessage = Math.Max(0, GetDouble(a, "seen") ?? seenPos ?? 0);
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
