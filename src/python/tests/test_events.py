from datetime import date

from wachta_detectors.events import Event, group_repeats, in_box, parse_rows


def row(over: dict | None = None) -> str:
    """One GDELT export line: 61 tab-separated columns. Keys are column numbers, so not kwargs."""
    parts = [""] * 61
    base = {0: "1325060613", 1: "20260926", 6: "RUSSIA", 7: "RUS", 16: "UKRAINE", 17: "UKR",
            26: "190", 28: "19", 29: "4", 30: "-10.0", 31: "12", 34: "-6.5",
            52: "Kharkiv, Ukraine", 53: "UP", 56: "49.9808", 57: "36.2527",
            59: "20260926183000", 60: "https://example.org/a"}
    base.update(over or {})
    for i, v in base.items():
        parts[i] = str(v)
    return "\t".join(parts)


def test_parses_actors_action_place_and_source():
    [event] = list(parse_rows([row()]))
    assert event.actor1 == "RUSSIA"
    assert event.actor2 == "UKRAINE"
    assert event.day == date(2026, 9, 26)
    assert event.kind == "walka"
    assert event.quad == "konflikt zbrojny"
    assert event.is_conflict
    assert not event.is_aid
    assert event.place == "Kharkiv, Ukraine"
    assert event.country == "UP"
    assert event.url == "https://example.org/a"
    assert event.added is not None and event.added.hour == 18
    assert event.summary == "RUSSIA -> UKRAINE: walka"


def test_aid_events_are_recognised_separately():
    [event] = list(parse_rows([row({26: "071", 28: "07", 29: "2", 30: "7.4"})]))
    assert event.is_aid
    assert not event.is_conflict
    assert event.kind == "pomoc"


def test_rows_without_coordinates_or_with_broken_numbers_are_skipped():
    assert list(parse_rows([row({56: "", 57: ""})])) == []
    assert list(parse_rows([row({1: "nie-data"})])) == []
    assert list(parse_rows(["za,malo,kolumn"])) == []


def test_missing_optional_fields_do_not_break_parsing():
    [event] = list(parse_rows([row({16: "", 17: "", 30: "", 31: "", 52: ""})]))
    assert event.actor2 is None
    assert event.goldstein is None
    assert event.mentions == 1
    assert event.place is None
    assert event.summary == "RUSSIA: walka"


def test_root_code_is_padded_so_single_digit_codes_still_map():
    [event] = list(parse_rows([row({28: "7", 26: "070"})]))
    assert event.root_code == "07"
    assert event.kind == "pomoc"


def test_row_without_a_timestamp_still_parses():
    [event] = list(parse_rows([row({59: ""})]))
    assert event.added is None


def test_unknown_root_code_is_reported_as_a_code_not_guessed():
    [event] = list(parse_rows([row({28: "99"})]))
    assert event.kind == "kod 99"


def test_in_box_filters_by_position():
    events = list(parse_rows([row(), row({56: "48.85", 57: "2.35"})]))  # Kharkiv i Paryz
    baltic_and_ukraine = in_box(events, 44.0, 56.0, 22.0, 41.0)
    assert [e.place for e in baltic_and_ukraine] == ["Kharkiv, Ukraine"]


class TestGrouping:
    def test_same_happening_reported_by_many_articles_becomes_one_entry(self):
        rows = [row({0: "1", 31: "3", 60: "https://a"}),
                row({0: "2", 31: "9", 60: "https://b"}),
                row({0: "3", 31: "1", 56: "49.9811", 57: "36.2529", 60: "https://c"})]
        [(event, count)] = group_repeats(parse_rows(rows))
        assert count == 3
        assert event.url == "https://b"  # reprezentant to wiersz z najwieksza liczba wzmianek

    def test_different_actions_stay_separate(self):
        rows = [row({0: "1", 28: "19", 26: "190"}), row({0: "2", 28: "07", 26: "071"})]
        assert len(group_repeats(parse_rows(rows))) == 2

    def test_distant_places_stay_separate(self):
        rows = [row({0: "1"}), row({0: "2", 56: "50.45", 57: "30.52"})]  # Charkow i Kijow
        assert len(group_repeats(parse_rows(rows))) == 2

    def test_result_is_sorted_by_how_widely_it_was_reported(self):
        rows = ([row({0: "1", 28: "19", 26: "190"})] * 1
                + [row({0: str(i), 28: "14", 26: "140", 56: "50.45", 57: "30.52"}) for i in range(5)])
        grouped = group_repeats(parse_rows(rows))
        assert grouped[0][1] == 5
        assert grouped[0][0].kind == "protest"


def test_empty_input():
    assert list(parse_rows([])) == []
    assert group_repeats([]) == []
    assert in_box([], 0, 1, 0, 1) == []


class TestClustering:
    def test_cluster_returns_all_members_not_just_a_representative(self):
        from wachta_detectors.events import cluster_events

        rows = [row({0: "1"}), row({0: "2"}), row({0: "3", 56: "50.45", 57: "30.52"})]
        clusters = cluster_events(parse_rows(rows))
        assert [len(c) for c in clusters] == [2, 1]
        assert {e.id for e in clusters[0]} == {"1", "2"}

    def test_clusters_are_sorted_by_size(self):
        from wachta_detectors.events import cluster_events

        rows = [row({0: "a", 28: "14", 26: "140"})] + [row({0: str(i)}) for i in range(4)]
        clusters = cluster_events(parse_rows(rows))
        assert len(clusters[0]) == 4
        assert len(clusters[1]) == 1

    def test_different_actors_from_one_country_are_not_merged(self):
        """UKRGOV i UKRMIL maja ten sam kod kraju UKR - to nie jest ten sam aktor."""
        from wachta_detectors.events import cluster_events

        rows = [row({0: "1", 6: "UKRGOV", 7: "UKR"}), row({0: "2", 6: "UKRMIL", 7: "UKR"})]
        assert [len(c) for c in cluster_events(parse_rows(rows))] == [1, 1]

    def test_different_detailed_actions_under_one_root_are_not_merged(self):
        """190 (uzycie sily) i 195 (nalot) leza pod wspolnym rootem 19, ale to inne dzialania."""
        from wachta_detectors.events import cluster_events

        rows = [row({0: "1", 26: "190"}), row({0: "2", 26: "195"})]
        assert [len(c) for c in cluster_events(parse_rows(rows))] == [1, 1]

    def test_one_happening_in_two_articles_is_still_one_cluster(self):
        """Straznik przeciwnej pomylki: ostrzejszy klucz nie moze rozbic prawdziwych powtorzen."""
        from wachta_detectors.events import cluster_events

        rows = [row({0: "1", 60: "https://a"}), row({0: "2", 60: "https://b"})]
        assert [len(c) for c in cluster_events(parse_rows(rows))] == [2]
