from wachta_detectors.versions import Mention, compare_sides, group_by_event, parse_mentions


def row(over: dict | None = None) -> str:
    """One GDELT mentions line: 16 tab-separated columns. Keys are column numbers, so not kwargs."""
    parts = [""] * 16
    base = {0: "1325090334", 1: "20260927030000", 2: "20260927064500", 3: "1",
            4: "kyivpost.com", 5: "https://www.kyivpost.com/post/1", 6: "24",
            11: "10", 12: "5419", 13: "-3.2", 14: ""}
    base.update(over or {})
    for i, v in base.items():
        parts[i] = str(v)
    return "\t".join(parts)


class TestSideOfTheOutlet:
    def test_known_outlet_wins_over_the_domain(self):
        [m] = list(parse_mentions([row({4: "rt.com"})]))
        assert m.side == "RU"

    def test_country_domain_maps_to_a_side(self):
        for domain, side in (("tass.ru", "RU"), ("unian.ua", "UA"), ("wyborcza.pl", "PL"),
                             ("zeit.de", "ZACHOD"), ("belta.by", "BY")):
            [m] = list(parse_mentions([row({4: domain})]))
            assert m.side == side, domain

    def test_independent_russian_press_is_its_own_side(self):
        # Panstwowa TASS i niezalezna Meduza to nie ta sama perspektywa.
        [state] = list(parse_mentions([row({4: "tass.ru"})]))
        [independent] = list(parse_mentions([row({4: "meduza.io"})]))
        assert state.side == "RU"
        assert independent.side == "RU-niezalezne"

    def test_subdomain_is_resolved_to_its_outlet(self):
        [m] = list(parse_mentions([row({4: "www.kyivpost.com"})]))
        assert m.side == "UA"

    def test_unassigned_outlet_belongs_to_no_side(self):
        for domain in ("iheart.com", "prokerala.com", "portal.kz"):
            [m] = list(parse_mentions([row({4: domain})]))
            assert m.side is None, domain


class TestParsing:
    def test_reads_tone_confidence_and_source_language(self):
        [m] = list(parse_mentions([row({13: "-6.5", 11: "40", 14: "srclc:rus;eng:Moses 2.1.1"})]))
        assert m.tone == -6.5
        assert m.confidence == 40
        assert m.language == "rus"

    def test_article_without_translation_has_no_language(self):
        [m] = list(parse_mentions([row()]))
        assert m.language is None

    def test_broken_numbers_do_not_break_the_row(self):
        [m] = list(parse_mentions([row({13: "", 11: "x"})]))
        assert m.tone is None
        assert m.confidence == 0

    def test_short_rows_are_skipped(self):
        assert list(parse_mentions(["a\tb\tc"])) == []


class TestComparingSides:
    def build(self, spec: list[tuple[str, float]], **kw):
        rows = [row({4: domain, 13: tone, 5: f"https://{domain}/{i}"}) for i, (domain, tone) in enumerate(spec)]
        return compare_sides(parse_mentions(rows), **kw)

    def test_unassigned_outlets_are_left_out_of_the_comparison(self):
        versions = self.build([("tass.ru", -1.0), ("rt.com", -2.0),
                               ("iheart.com", +9.0), ("prokerala.com", +9.0)])
        assert [s.side for s in versions.sides] == ["RU"]
        assert versions.total_articles == 2   # dwa nieprzypisane artykuly nie podniosly liczby

    def test_two_sides_with_different_tone_are_reported_with_the_gap(self):
        versions = self.build([("tass.ru", -1.0), ("rt.com", -2.0),
                               ("unian.ua", -8.0), ("pravda.com.ua", -9.0)])
        assert {s.side for s in versions.sides} == {"RU", "UA"}
        assert versions.total_articles == 4
        assert versions.tone_gap == 7.0  # -1.5 vs -8.5

    def test_single_article_side_counts_but_is_flagged_as_thin(self):
        versions = self.build([("tass.ru", -1.0), ("rt.com", -2.0), ("unian.ua", -9.0)])
        assert [s.side for s in versions.sides] == ["RU", "UA"]
        assert versions.is_weak
        assert versions.tone_gap == 7.5

    def test_raising_the_minimum_drops_thin_sides(self):
        versions = self.build([("tass.ru", -1.0), ("rt.com", -2.0), ("unian.ua", -9.0)], min_articles=2)
        assert [s.side for s in versions.sides] == ["RU"]
        assert not versions.is_weak
        assert versions.tone_gap == 0.0

    def test_two_solid_sides_are_not_flagged_as_thin(self):
        versions = self.build([("tass.ru", -1.0), ("rt.com", -2.0), ("unian.ua", -8.0), ("pravda.com.ua", -9.0)])
        assert not versions.is_weak

    def test_sides_are_ordered_by_how_much_they_wrote(self):
        versions = self.build([("unian.ua", -8.0), ("pravda.com.ua", -9.0), ("ukrinform.net", -7.0),
                               ("tass.ru", -1.0), ("rt.com", -2.0)])
        assert [s.side for s in versions.sides] == ["UA", "RU"]
        assert versions.sides[0].articles == 3

    def test_examples_and_languages_are_carried_through(self):
        rows = [row({4: "tass.ru", 13: "-1.0", 11: "90", 5: "https://tass.ru/pewne", 14: "srclc:rus;eng:M"}),
                row({4: "tass.ru", 13: "-1.4", 11: "10", 5: "https://tass.ru/mniej"})]
        versions = compare_sides(parse_mentions(rows))
        [side] = versions.sides
        assert side.languages == ("rus",)
        assert side.examples[0] == "https://tass.ru/pewne"  # najpierw wiersz o wyzszej pewnosci

    def test_articles_without_tone_are_not_counted(self):
        versions = self.build([("tass.ru", -1.0), ("rt.com", -2.0)])
        with_missing = compare_sides(parse_mentions(
            [row({4: "tass.ru", 13: "-1.0"}), row({4: "rt.com", 13: "-2.0"}), row({4: "sputnikglobe.com", 13: ""})]))
        assert with_missing.sides[0].articles == versions.sides[0].articles

    def test_nothing_to_compare_returns_none(self):
        assert compare_sides([]) is None
        assert compare_sides(parse_mentions([row({13: ""})])) is None


def test_grouping_by_event():
    rows = [row({0: "1"}), row({0: "1", 4: "tass.ru"}), row({0: "2"})]
    grouped = group_by_event(parse_mentions(rows))
    assert sorted(grouped) == ["1", "2"]
    assert len(grouped["1"]) == 2


def test_mention_side_is_computed_not_stored():
    m = Mention(event_id="1", source="Wyborcza.PL", url="https://x", tone=-1.0, language=None, confidence=5)
    assert m.side == "PL"
