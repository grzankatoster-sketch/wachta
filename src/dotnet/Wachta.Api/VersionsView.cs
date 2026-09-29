namespace Wachta.Api;

/// <summary>One stored mention, as the comparison sees it.
///
/// <c>Side</c> and <c>FromTld</c> are read, never recomputed. Who speaks for whom is an analytical
/// decision that lives in a versioned data file next to the Python detectors
/// (<c>data/analysis/outlet_sides.json</c>) and is applied once, when the row is written. An API
/// that re-derived it would be a second copy of that policy, free to drift from the first.
/// </summary>
/// <param name="Side">Side of the telling, or null when the publisher was never assigned one.</param>
/// <param name="Tone">GDELT document tone; negative is negative. Null when GDELT gave none.</param>
/// <param name="FromTld">True when the side was guessed from the country domain, not from a list.</param>
public sealed record MentionRow(
    string? Side, string Url, double? Tone, string? Language, int Confidence, bool FromTld);

/// <summary>
/// Two versions of the same event: who reported it, in what language, with what tone.
///
/// This is a C# transcription of <c>compare_sides</c> / <c>SideView</c> / <c>Versions</c> in
/// <c>src/python/wachta_detectors/versions.py</c>, and it is deliberately nothing more than that.
/// The Python module is the tested definition of the semantics; two implementations that quietly
/// disagree - a comparison the detectors call thin and the screen calls solid - would be the worst
/// possible bug in this project, so every rule below names the Python rule it mirrors.
///
/// What it does NOT do, on purpose, exactly as over there:
///   * it does not say who is lying. It shows that coverage differs, and by how much;
///   * it does not treat tone as truth. Tone is a property of the text, not of the world;
///   * a side with one article is not "a side" - see <see cref="EventVersionsDto.IsWeak"/>.
/// </summary>
public static class VersionsView
{
    /// <summary>Groups one event's mentions by side, mirroring <c>compare_sides(min_articles=1)</c>.
    ///
    /// The Python default of one article per side is kept: measured on four hours of GDELT,
    /// requiring two left three comparable events in the whole world, while one left twenty-two. A
    /// thin comparison flagged as thin beats no comparison at all.
    ///
    /// Where Python returns None - nothing at all to compare - this returns a body with no sides
    /// rather than nothing, because the caller is an HTTP endpoint and the front end still has an
    /// event to render. Every number in it comes out of the same expression applied to an empty
    /// list, so no rule is bent: totalArticles 0, toneGap 0, isWeak false (Python's `any([])`).
    /// An empty `sides` is the signal that there was nothing to compare.</summary>
    public static EventVersionsDto Compare(string eventId, IEnumerable<MentionRow> mentions)
    {
        // Unassigned publisher is not a side, and an article without tone cannot be averaged.
        // Same guard, same order, as the `if m.tone is None or side is None: continue` over there.
        var bySide = mentions
            .Where(m => m.Tone is not null && !string.IsNullOrEmpty(m.Side))
            .GroupBy(m => m.Side!, StringComparer.Ordinal);

        var sides = new List<SideVersionDto>();
        foreach (var group in bySide)
        {
            // One article is one voice. GDELT emits a row per MENTION, so the same text can come
            // back several times - and then it doubles its weight in the mean, pushes the side over
            // the threshold and erases the warning about a thin basis. The most confident mention of
            // each address wins, as in the `najlepsze` dict in Python.
            var articles = group
                .OrderByDescending(m => m.Confidence)
                .GroupBy(m => m.Url, StringComparer.Ordinal)
                .Select(byUrl => byUrl.First())
                .ToList();

            // round(mean(...), 2): .NET's default rounding is to-even, the same as Python's round().
            var meanTone = Math.Round(articles.Average(m => m.Tone!.Value), 2, MidpointRounding.ToEven);

            var languages = articles
                .Select(m => m.Language)
                .Where(l => !string.IsNullOrEmpty(l))
                .Select(l => l!)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(l => l, StringComparer.Ordinal)
                .ToList();

            // Two most confident addresses, so a reader can go and look at the telling itself.
            var examples = articles
                .OrderByDescending(m => m.Confidence)
                .Take(2)
                .Select(m => m.Url)
                .ToList();

            var fromTld = articles.Count(m => m.FromTld);

            sides.Add(new SideVersionDto(
                Side: group.Key,
                Articles: articles.Count,
                MeanTone: meanTone,
                Languages: languages,
                Examples: examples,
                FromTld: fromTld,
                // SideView.only_guessed: nothing here was a named outlet, so the whole voice is an
                // assumption - a bucket of country domains, not a side anybody edited.
                OnlyGuessed: articles.Count > 0 && fromTld == articles.Count));
        }

        // Python sorts by -articles; the secondary key by name is ours, so that two sides of equal
        // size come back in the same order on every call instead of in row order from Postgres.
        var ordered = sides
            .OrderByDescending(s => s.Articles)
            .ThenBy(s => s.Side, StringComparer.Ordinal)
            .ToList();

        return new EventVersionsDto(
            EventId: eventId,
            TotalArticles: ordered.Sum(s => s.Articles),
            ToneGap: ToneGap(ordered),
            // Versions.is_weak: one article, or a side built only from guesses. Both look identical
            // in the output and both deserve the same warning.
            IsWeak: ordered.Any(s => s.Articles < 2 || s.OnlyGuessed),
            Sides: ordered);
    }

    /// <summary>Versions.tone_gap: the distance between the most and the least negative side.
    ///
    /// Computed from the ALREADY ROUNDED means, as in Python, where <c>tone_gap</c> reads
    /// <c>s.mean_tone</c> - a value that was rounded when the side was built. Taking the gap from
    /// the raw averages instead would put the API one hundredth away from the detectors on exactly
    /// the number the screen shows biggest.</summary>
    private static double ToneGap(IReadOnlyList<SideVersionDto> sides)
    {
        if (sides.Count < 2)
        {
            return 0.0;     // nothing to compare against
        }

        return Math.Round(sides.Max(s => s.MeanTone) - sides.Min(s => s.MeanTone), 2, MidpointRounding.ToEven);
    }
}
