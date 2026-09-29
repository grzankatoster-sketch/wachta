using Wachta.Api;

namespace Wachta.Tests;

/// <summary>
/// The C# comparison must answer exactly what <c>src/python/wachta_detectors/versions.py</c> answers.
///
/// These cases are deliberately the same cases as in <c>src/python/tests/test_versions.py</c>, with
/// the same inputs and the same expected numbers, because the risk being guarded against is not
/// "the C# is wrong" but "the C# is plausibly, quietly different" - a comparison the detectors call
/// thin and the screen calls solid. Where a number looks arbitrary here, it was copied.
///
/// What the Python tests cover and these do not is the side assignment itself (which outlet speaks
/// for whom). That is applied when the row is written and arrives here already decided, which is
/// the point: there is one copy of that policy, and it is not in the API.
/// </summary>
public sealed class VersionsViewTests
{
    private static MentionRow M(string? side, double? tone, string url,
        string? language = null, int confidence = 10, bool fromTld = false) =>
        new(side, url, tone, language, confidence, fromTld);

    [Fact]
    public void Two_sides_with_different_tone_are_reported_with_the_gap()
    {
        // test_two_sides_with_different_tone_are_reported_with_the_gap: -1.5 vs -8.5 = 7.0.
        // Mutacja: zamiana round(...,2) na zaokraglenie surowych srednich albo Sum zamiast Average
        // rozjezdza te liczbe.
        var v = VersionsView.Compare("e1", [
            M("RU", -1.0, "http://tass.ru/1"), M("RU", -2.0, "http://rt.com/1"),
            M("UA", -8.0, "http://unian.ua/1"), M("UA", -9.0, "http://pravda.com.ua/1"),
        ]);

        Assert.Equal(["RU", "UA"], v.Sides.Select(s => s.Side).OrderBy(s => s));
        Assert.Equal(4, v.TotalArticles);
        Assert.Equal(7.0, v.ToneGap);
        Assert.Equal(-1.5, v.Sides.Single(s => s.Side == "RU").MeanTone);
        Assert.Equal(-8.5, v.Sides.Single(s => s.Side == "UA").MeanTone);
    }

    [Fact]
    public void Unassigned_publishers_are_left_out_of_the_comparison()
    {
        // A publisher nobody placed belongs to no side - better a missing voice than a wrong label.
        // Mutacja: usuniecie warunku na null Side wpuszcza te dwa artykuly i podnosi total do 4.
        var v = VersionsView.Compare("e1", [
            M("RU", -1.0, "http://tass.ru/1"), M("RU", -2.0, "http://rt.com/1"),
            M(null, +9.0, "http://iheart.com/1"), M(null, +9.0, "http://prokerala.com/1"),
        ]);

        Assert.Equal(["RU"], v.Sides.Select(s => s.Side));
        Assert.Equal(2, v.TotalArticles);
    }

    [Fact]
    public void Articles_without_tone_are_not_counted()
    {
        // Mutacja: usuniecie warunku na null Tone wywraca srednia (a wczesniej rzuca wyjatkiem).
        var v = VersionsView.Compare("e1", [
            M("RU", -1.0, "http://tass.ru/1"), M("RU", -2.0, "http://rt.com/1"),
            M("RU", null, "http://sputnikglobe.com/1"),
        ]);

        Assert.Equal(2, v.Sides.Single().Articles);
        Assert.Equal(-1.5, v.Sides.Single().MeanTone);
    }

    [Fact]
    public void A_single_article_side_counts_but_the_comparison_is_flagged_as_thin()
    {
        // test_single_article_side_counts_but_is_flagged_as_thin. Jeden artykul to nie jest strona,
        // ale lepszy niz brak porownania - wiec zostaje i jest oznaczony.
        // Mutacja: `s.Articles < 2` -> `s.Articles < 1` gasi ostrzezenie.
        var v = VersionsView.Compare("e1", [
            M("RU", -1.0, "http://tass.ru/1"), M("RU", -2.0, "http://rt.com/1"),
            M("UA", -9.0, "http://unian.ua/1"),
        ]);

        Assert.True(v.IsWeak);
        Assert.Equal(7.5, v.ToneGap);
    }

    [Fact]
    public void Two_solid_sides_are_not_flagged_as_thin()
    {
        // Straz przed odwrotnym bledem: gdyby IsWeak bylo zawsze true, ostrzezenie nic nie znaczy.
        var v = VersionsView.Compare("e1", [
            M("RU", -1.0, "http://tass.ru/1"), M("RU", -2.0, "http://rt.com/1"),
            M("UA", -8.0, "http://unian.ua/1"), M("UA", -9.0, "http://pravda.com.ua/1"),
        ]);

        Assert.False(v.IsWeak);
    }

    [Fact]
    public void Sides_are_ordered_by_how_much_they_wrote()
    {
        // test_sides_are_ordered_by_how_much_they_wrote.
        // Mutacja: OrderByDescending -> OrderBy stawia RU przed UA.
        var v = VersionsView.Compare("e1", [
            M("UA", -8.0, "http://unian.ua/1"), M("UA", -9.0, "http://pravda.com.ua/1"),
            M("UA", -7.0, "http://ukrinform.net/1"),
            M("RU", -1.0, "http://tass.ru/1"), M("RU", -2.0, "http://rt.com/1"),
        ]);

        Assert.Equal(["UA", "RU"], v.Sides.Select(s => s.Side));
        Assert.Equal(3, v.Sides[0].Articles);
    }

    [Fact]
    public void Examples_and_languages_are_carried_through()
    {
        // test_examples_and_languages_are_carried_through: najpierw wiersz o wyzszej pewnosci.
        // Mutacja: OrderByDescending(Confidence) -> OrderBy w Examples odwraca kolejnosc.
        var v = VersionsView.Compare("e1", [
            M("RU", -1.0, "https://tass.ru/pewne", language: "rus", confidence: 90),
            M("RU", -1.4, "https://tass.ru/mniej", confidence: 10),
        ]);

        var side = v.Sides.Single();
        Assert.Equal(["rus"], side.Languages);
        Assert.Equal("https://tass.ru/pewne", side.Examples[0]);
        Assert.Equal(2, side.Examples.Count);
    }

    [Fact]
    public void Languages_are_distinct_and_sorted()
    {
        var v = VersionsView.Compare("e1", [
            M("RU", -1.0, "http://a", language: "rus"),
            M("RU", -1.0, "http://b", language: "eng"),
            M("RU", -1.0, "http://c", language: "rus"),
            M("RU", -1.0, "http://d", language: null),
        ]);

        Assert.Equal(["eng", "rus"], v.Sides.Single().Languages);
    }

    [Fact]
    public void Only_two_examples_even_when_a_side_wrote_more()
    {
        var v = VersionsView.Compare("e1", Enumerable.Range(0, 6)
            .Select(i => M("RU", -1.0, $"http://tass.ru/{i}", confidence: i)));

        Assert.Equal(["http://tass.ru/5", "http://tass.ru/4"], v.Sides.Single().Examples);
    }

    [Fact]
    public void Tone_gap_is_zero_when_there_is_only_one_side()
    {
        // Versions.tone_gap: nie ma z czym porownac, wiec nie ma roznicy - nie "roznica zero".
        var v = VersionsView.Compare("e1", [M("RU", -9.0, "http://a"), M("RU", -1.0, "http://b")]);

        Assert.Equal(0.0, v.ToneGap);
        Assert.Single(v.Sides);
    }

    [Fact]
    public void Tone_gap_is_taken_from_the_rounded_means_like_python()
    {
        // -1/3 i +1/3 daja srednie -0.33 i 0.33, czyli luke 0.66. Ze zrodlowych liczb wyszloby
        // 0.6666..., a po zaokragleniu 0.67 - jedna setna rozjazdu z Pythonem na liczbie, ktora
        // front pokazuje najwiekszym drukiem.
        // Mutacja: liczenie luki z surowych srednich zamiast z zaokraglonych daje 0.67.
        var v = VersionsView.Compare("e1", [
            M("RU", -1.0 / 3.0, "http://a"), M("UA", 1.0 / 3.0, "http://b"),
        ]);

        Assert.Equal(0.66, v.ToneGap);
    }

    [Fact]
    public void Nothing_to_compare_gives_an_empty_body_not_an_invented_one()
    {
        // Python zwraca tu None. Endpoint musi cos oddac, wiec oddaje te same wzory policzone na
        // pustej liscie: zero artykulow, zero luki, brak ostrzezenia (`any([])` to falsz w Pythonie).
        // Pusta lista stron - a nie IsWeak - jest sygnalem, ze nie bylo czego porownywac.
        var v = VersionsView.Compare("e1", [M(null, -1.0, "http://a"), M("RU", null, "http://b")]);

        Assert.Empty(v.Sides);
        Assert.Equal(0, v.TotalArticles);
        Assert.Equal(0.0, v.ToneGap);
        Assert.False(v.IsWeak);
        Assert.Equal("e1", v.EventId);
    }

    /// <summary>GDELT wystawia wiersz na kazda WZMIANKE, nie na artykul. Ten sam tekst policzony
    /// dwa razy podwaja swoj wplyw na srednia i kasuje ostrzezenie o cienkiej podstawie.</summary>
    public sealed class Duplicates
    {
        [Fact]
        public void The_same_article_counts_once()
        {
            // Mutacja: usuniecie GroupBy(Url) daje 3 artykuly zamiast 1.
            var v = VersionsView.Compare("e1", [
                M("RU", -10.0, "http://a"), M("RU", -10.0, "http://a"), M("RU", -10.0, "http://a"),
            ]);

            Assert.Equal(1, v.Sides.Single().Articles);
        }

        [Fact]
        public void A_repeated_article_does_not_drag_the_average()
        {
            var raz = VersionsView.Compare("e1", [M("RU", -10.0, "http://a"), M("RU", 0.0, "http://b")]);
            var zPowtorka = VersionsView.Compare("e1", [
                M("RU", -10.0, "http://a"), M("RU", -10.0, "http://a"),
                M("RU", -10.0, "http://a"), M("RU", 0.0, "http://b"),
            ]);

            Assert.Equal(raz.Sides[0].MeanTone, zPowtorka.Sides[0].MeanTone);
            Assert.Equal(-5.0, zPowtorka.Sides[0].MeanTone);
        }

        [Fact]
        public void Duplicates_cannot_clear_the_thin_basis_flag()
        {
            var v = VersionsView.Compare("e1", [
                M("RU", -10.0, "http://a"), M("RU", -10.0, "http://a"),
                M("ZACHOD", 5.0, "http://z"),
            ]);

            Assert.All(v.Sides, s => Assert.Equal(1, s.Articles));
            Assert.True(v.IsWeak);
        }

        [Fact]
        public void The_most_confident_version_of_a_repeat_is_the_one_kept()
        {
            // Mutacja: OrderByDescending -> OrderBy przed GroupBy(Url) zostawia wersje o pewnosci 10,
            // wiec jezyk i przyklad pochodza z gorszego wiersza.
            var v = VersionsView.Compare("e1", [
                M("RU", -10.0, "http://a", language: "slabe", confidence: 10),
                M("RU", -10.0, "http://a", language: "mocne", confidence: 90),
            ]);

            Assert.Equal(["http://a"], v.Sides.Single().Examples);
            Assert.Equal(["mocne"], v.Sides.Single().Languages);
        }

        [Fact]
        public void Different_articles_still_count_separately()
        {
            var v = VersionsView.Compare("e1", [M("RU", -10.0, "http://a"), M("RU", -6.0, "http://b")]);

            Assert.Equal(2, v.Sides.Single().Articles);
            Assert.Equal(-8.0, v.Sides.Single().MeanTone);
        }
    }

    /// <summary>Strona zlozona z samych domen krajowych to nie strona, tylko kubelek. Sklep rowerowy
    /// pod .lv nie ma stanowiska w wojnie, a w wyniku wyglada tak samo jak redakcja.</summary>
    public sealed class Guessed
    {
        [Fact]
        public void A_side_built_only_from_guesses_makes_the_comparison_weak()
        {
            // test_a_side_built_only_from_guesses_makes_the_comparison_weak.
            // Mutacja: OnlyGuessed na stale false gasi ostrzezenie mimo dwoch pelnych stron.
            var v = VersionsView.Compare("e1", [
                M("RU", -8.0, "http://kremlin-mirror.ru/1", fromTld: true),
                M("RU", -7.0, "http://blog-jakis.ru/1", fromTld: true),
                M("ZACHOD", 1.0, "http://bbc.com/1"),
                M("ZACHOD", 2.0, "http://theguardian.com/1"),
            ]);

            var ru = v.Sides.Single(s => s.Side == "RU");
            Assert.Equal(2, ru.FromTld);
            Assert.True(ru.OnlyGuessed);
            Assert.False(v.Sides.Single(s => s.Side == "ZACHOD").OnlyGuessed);
            Assert.True(v.IsWeak);
        }

        [Fact]
        public void A_named_outlet_is_not_counted_as_a_guess()
        {
            var v = VersionsView.Compare("e1", [
                M("RU", -2.0, "http://tass.ru/1"), M("RU", -3.0, "http://rt.com/1"),
            ]);

            Assert.Equal(0, v.Sides.Single().FromTld);
            Assert.False(v.Sides.Single().OnlyGuessed);
        }

        [Fact]
        public void One_guess_among_named_outlets_is_counted_but_does_not_condemn_the_side()
        {
            // Blog WPLYWA na srednia - taka jest cena zachowania trzech czwartych warstwy. Ale widac,
            // ze jeden z trzech glosow jest zgadniety, wiec czytelnik moze ten wynik zwazyc.
            // Mutacja: `fromTld == articles` -> `fromTld > 0` oznaczylby te strone jako zgadniona.
            var v = VersionsView.Compare("e1", [
                M("RU", -2.0, "http://tass.ru/1"), M("RU", -2.0, "http://rt.com/1"),
                M("RU", 9.0, "http://kremlin-mirror.ru/1", fromTld: true),
            ]);

            var ru = v.Sides.Single();
            Assert.Equal(3, ru.Articles);
            Assert.Equal(1, ru.FromTld);
            Assert.False(ru.OnlyGuessed);
            Assert.False(v.IsWeak);
        }
    }
}
