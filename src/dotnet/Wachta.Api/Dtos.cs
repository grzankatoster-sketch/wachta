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

/// <summary>One war the reader can pick off the list. <c>Id</c> is the two country codes in
/// alphabetical order ("RUS-UKR"), so the same pair keeps the same id no matter which side GDELT
/// happened to put in actor1 on a given row - which is what makes it safe to link to.</summary>
public sealed record ConflictDto(
    string Id, string Nazwa, string Actor1, string Actor2, int Events, DateTime? LastEventAt);

/// <summary>One event on the front. <c>Kind</c> is the Polish label the CAMEO root code was stored
/// under; <c>Sources</c> and <c>Mentions</c> measure how widely it was written up, not how true it
/// is - a hundred articles repeating one agency dispatch are still one dispatch.</summary>
public sealed record ConflictEventDto(
    string Id, DateTime? Ts, string? Kind, string? Actor1, string? Actor2, string? Place,
    double? Lat, double? Lon, float? Goldstein, int? Sources, string? Url, int? Mentions);

/// <summary>How one side told the event. <c>FromTld</c> is a COUNT, not a flag: it says how many of
/// these articles got their side from the country domain instead of from a named outlet, which is
/// what <see cref="OnlyGuessed"/> is built from. It mirrors <c>SideView.from_tld</c> in
/// <c>versions.py</c>, which is also a count.</summary>
public sealed record SideVersionDto(
    string Side, int Articles, double MeanTone, IReadOnlyList<string> Languages,
    IReadOnlyList<string> Examples, int FromTld, bool OnlyGuessed);

/// <summary>The two-versions comparison for one event.
///
/// <c>IsWeak</c> and <c>OnlyGuessed</c> travel with the data for the same reason the search endpoint
/// carries its caveat: a comparison resting on one article, or on nothing but country-domain
/// guesses, looks identical to a solid one - two sides, two numbers, a tone gap - so the reader is
/// exactly as careful as the response lets them be.</summary>
public sealed record EventVersionsDto(
    string EventId, int TotalArticles, double ToneGap, bool IsWeak, IReadOnlyList<SideVersionDto> Sides);
