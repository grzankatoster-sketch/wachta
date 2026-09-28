namespace Wachta.Api;

/// <summary>
/// The patch of the world this installation watches.
///
/// It exists because the two feeds behind the map do not cover the same ground. The area sources
/// return traffic around the Baltic; adsb.lol's military endpoint returns military traffic
/// WORLDWIDE. Broadcasting both unbounded put around three hundred aircraft from other continents
/// into every map update - almost none of them on screen, all of them counted. Measured on live
/// data 2026-09-28: 335 military aircraft between 33 S and 62 N, of which 32 fell inside the map's
/// default view and none inside the narrow Baltic box, against 241 civil aircraft. The map reported
/// "446 aircraft in range" and a 58% military share, and neither number described anything real.
///
/// So the area is stated once, here, and both the map and the sentence under the header mean the
/// same thing by it. Ingestion stays global on purpose - the military registry has to recognise a
/// hull wherever it was first seen - this bound applies only to what gets drawn.
/// </summary>
public readonly record struct WatchedArea(double MinLat, double MinLon, double MaxLat, double MaxLon)
{
    /// <summary>
    /// The Baltic and its approaches - chosen as the largest box in which BOTH feeds have data.
    ///
    /// Measured 2026-09-28 on one live quarter of an hour, counting distinct hulls:
    ///
    ///   53.5-66 /  9-30.5   0 military, 160 civil   (0%)  - clips military entirely, and civil too:
    ///                                                       the civil feed reaches down to 50.9 N
    ///   48-70   /  0-40    13 military, 241 civil   (5%)  - every civil aircraft the ingestion
    ///                                                       produces, plus the military traffic
    ///                                                       actually on screen at the default zoom
    ///   45-72   / -12-45   35 military, 241 civil  (13%)  - civil does not grow, so the extra
    ///                                                       military has nothing to be a share OF
    ///
    /// The middle one is where the two feeds are comparable. Widening past it only adds military,
    /// which is how the 58% figure came about in the first place; narrowing past it hides aircraft
    /// the reader can see on the map and would have to be told about anyway.
    /// </summary>
    public static readonly WatchedArea Baltic = new(48.0, 0.0, 70.0, 40.0);

    public bool Contains(double lat, double lon) =>
        lat >= MinLat && lat <= MaxLat && lon >= MinLon && lon <= MaxLon;
}
