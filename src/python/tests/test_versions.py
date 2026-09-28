import json

from wachta_detectors.versions import (
    POLICY_PATH,
    Mention,
    SidePolicy,
    compare_sides,
    group_by_event,
    load_policy,
    parse_mentions,
)


_KOLEJNY = iter(range(1, 10_000))


def row(over: dict | None = None) -> str:
    """One GDELT mentions line: 16 tab-separated columns. Keys are column numbers, so not kwargs.

    Adres artykulu jest budowany z domeny i licznika, chyba ze test poda wlasny. Wczesniej kazdy
    wiersz mial ten sam URL, co bylo nieszkodliwe dopoki nie zaczelismy odsiewac powtorzonych
    artykulow - wtedy dwa rozne zrodla wygladaly jak jeden tekst policzony dwa razy.
    """
    parts = [""] * 16
    over = dict(over or {})
    domena = str(over.get(4, "kyivpost.com"))
    base = {0: "1325090334", 1: "20260927030000", 2: "20260927064500", 3: "1",
            4: "kyivpost.com", 5: f"https://{domena}/post/{next(_KOLEJNY)}", 6: "24",
            11: "10", 12: "5419", 13: "-3.2", 14: ""}
    base.update(over)
    for i, v in base.items():
        parts[i] = str(v)
    return "\t".join(parts)


class TestSideOfTheOutlet:
    def test_known_outlet_wins_over_the_domain(self):
        [m] = list(parse_mentions([row({4: "rt.com"})]))
        assert m.side == "RU"

    def test_assigned_outlet_maps_to_its_side(self):
        for domain, side in (("tass.ru", "RU"), ("unian.ua", "UA"), ("wyborcza.pl", "PL"),
                             ("dw.com", "ZACHOD"), ("belta.by", "BY")):
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

    def test_outlet_from_a_country_we_do_not_map_belongs_to_no_side(self):
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


class TestDuplicateArticles:
    """Znalezione w audycie: kazdy wiersz wzmianki liczyl sie jako osobny artykul.

    GDELT wystawia wiersz na kazda WZMIANKE, wiec ten sam tekst potrafi wrocic kilka razy. Liczony
    wielokrotnie podwaja swoj wplyw na srednia, przepycha strone przez prog min_articles i kasuje
    ostrzezenie o cienkiej podstawie - czyli dokladnie to ostrzezenie, ktore mialo chronic czytelnika.
    """

    @staticmethod
    def wzmianka(url: str, tone: float, source: str = "rt.com", confidence: int = 50) -> Mention:
        return Mention(event_id="e1", source=source, url=url, tone=tone,
                       language="rus", confidence=confidence)

    def test_the_same_article_counts_once(self):
        wynik = compare_sides([self.wzmianka("http://a", -10.0),
                               self.wzmianka("http://a", -10.0),
                               self.wzmianka("http://a", -10.0)])
        assert wynik.sides[0].articles == 1

    def test_a_repeated_article_does_not_drag_the_average(self):
        jeden_raz = compare_sides([self.wzmianka("http://a", -10.0), self.wzmianka("http://b", 0.0)])
        z_powtorka = compare_sides([self.wzmianka("http://a", -10.0), self.wzmianka("http://a", -10.0),
                                    self.wzmianka("http://a", -10.0), self.wzmianka("http://b", 0.0)])
        assert jeden_raz.sides[0].mean_tone == z_powtorka.sides[0].mean_tone

    def test_duplicates_cannot_clear_the_thin_basis_flag(self):
        strony = [self.wzmianka("http://a", -10.0), self.wzmianka("http://a", -10.0),
                  self.wzmianka("http://z", 5.0, source="bbc.com")]
        wynik = compare_sides(strony, min_articles=1)
        assert all(s.articles == 1 for s in wynik.sides)
        assert wynik.is_weak, "obie strony maja po jednym artykule, wiec podstawa jest cienka"

    def test_the_most_confident_version_of_a_repeat_is_the_one_kept(self):
        wynik = compare_sides([self.wzmianka("http://a", -10.0, confidence=10),
                               self.wzmianka("http://a", -10.0, confidence=90)])
        assert wynik.sides[0].examples == ("http://a",)

    def test_different_articles_still_count_separately(self):
        wynik = compare_sides([self.wzmianka("http://a", -10.0), self.wzmianka("http://b", -6.0)])
        assert wynik.sides[0].articles == 2
        assert wynik.sides[0].mean_tone == -8.0


class TestPolityka:
    """Znalezione w audycie: przypisania redakcji byly zaszyta polityka analityczna w kodzie.

    Dwie osobne sprawy zlaly sie tam w jedna. Przypisanie mowi "przeczytalismy te redakcje i
    umiescilismy ja po tej stronie". Fallback po domenie krajowej mowi cos zupelnie innego:
    "koncowka adresu wystarczy". Przy wlaczonym fallbacku obietnica z docstringu - redakcja
    nieprzypisana nie nalezy do zadnej strony - po prostu nie obowiazywala.
    """

    @staticmethod
    def wzmianka(source: str, tone: float = -1.0) -> Mention:
        return Mention(event_id="e1", source=source, url=f"http://{source}/1", tone=tone,
                       language=None, confidence=10)

    def test_policy_lives_in_a_data_file_not_in_the_module(self):
        assert POLICY_PATH.exists(), POLICY_PATH
        raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        assert raw["outlets"]["rt.com"] == "RU"
        assert "tld_fallback" in raw, "dopuszczalnosc fallbacku ma byc osobnym, widocznym ustawieniem"

    def test_a_side_taken_from_the_country_domain_is_marked_as_guessed(self):
        """Decyzja analityczna, podjeta po pomiarze, nie z zasady.

        Bez zgadywania po domenie warstwa znajduje 4 wydarzenia zamiast 18 na tym samym oknie 3 h -
        czyli traci trzy czwarte tresci. Zgadywanie zostaje, ale zgadniete znaczy zgadniete: jest
        policzone osobno i oznacza cale porownanie jako cienkie.
        """
        polityka = load_policy()
        assert polityka.tld_fallback is True
        assert polityka.side_with_origin("rt.com") == ("RU", "lista")
        assert polityka.side_with_origin("kremlin-mirror.ru") == ("RU", "domena")
        assert polityka.side_with_origin("sklep-rowerowy.lv") == ("ZACHOD", "domena")
        assert polityka.side_with_origin("portal.kz") == (None, "brak")

    def test_a_side_built_only_from_guesses_makes_the_comparison_weak(self):
        # Sklep rowerowy nie ma stanowiska w wojnie. Jesli cala "strona" to takie domeny,
        # porownanie ma o tym mowic, a nie wygladac jak kazde inne.
        wynik = compare_sides([self.wzmianka("kremlin-mirror.ru", -8.0),
                               self.wzmianka("blog-jakis.ru", -7.0),
                               self.wzmianka("bbc.com", +1.0),
                               self.wzmianka("theguardian.com", +2.0)])
        strona_ru = next(s for s in wynik.sides if s.side == "RU")
        assert strona_ru.from_tld == 2 and strona_ru.only_guessed
        assert wynik.is_weak, "strona zlozona z samych domen to nie jest strona, tylko kubelek"

    def test_a_named_outlet_is_not_counted_as_a_guess(self):
        wynik = compare_sides([self.wzmianka("tass.ru", -2.0), self.wzmianka("rt.com", -3.0)])
        assert wynik.sides[0].from_tld == 0
        assert not wynik.sides[0].only_guessed

    def test_the_fallback_is_a_setting_and_it_changes_the_answer(self):
        base = load_policy()
        z_fallbackiem = SidePolicy(base.outlets, base.tld_sides, tld_fallback=True)
        bez_fallbacku = SidePolicy(base.outlets, base.tld_sides, tld_fallback=False)
        assert z_fallbackiem.side("kremlin-mirror.ru") == "RU"
        assert bez_fallbacku.side("kremlin-mirror.ru") is None

    def test_an_unread_blog_moves_the_mean_but_leaves_a_trace(self):
        # Blog WPLYWA na srednia - taka jest cena zachowania trzech czwartych warstwy. Ale widac,
        # ze jeden z trzech glosow jest zgadniety, wiec czytelnik moze ten wynik zwazyc.
        znane = [self.wzmianka("tass.ru", -2.0), self.wzmianka("rt.com", -2.0)]
        z_blogiem = compare_sides(znane + [self.wzmianka("kremlin-mirror.ru", +9.0)])
        assert z_blogiem.sides[0].articles == 3
        assert z_blogiem.sides[0].from_tld == 1
        assert not z_blogiem.sides[0].only_guessed

    def test_an_explicit_assignment_still_wins_when_the_fallback_is_on(self):
        base = load_policy()
        polityka = SidePolicy(base.outlets, base.tld_sides, tld_fallback=True)
        # meduza.io to RU-niezalezne; fallback po .io nie ma prawa tego nadpisac
        assert polityka.side("meduza.io") == "RU-niezalezne"

    def test_compare_sides_takes_the_policy_it_is_given(self):
        wzmianki = [self.wzmianka("tass.ru", -2.0), self.wzmianka("kremlin-mirror.ru", +9.0)]
        base = load_policy()
        luzna = compare_sides(wzmianki, policy=SidePolicy(base.outlets, base.tld_sides, tld_fallback=True))
        scisla = compare_sides(wzmianki, policy=SidePolicy(base.outlets, base.tld_sides, tld_fallback=False))
        assert luzna.sides[0].articles == 2
        assert scisla.sides[0].articles == 1

    def test_policy_can_be_replaced_without_touching_the_code(self, tmp_path):
        plik = tmp_path / "strony.json"
        plik.write_text(json.dumps({"wersja": "test", "tld_fallback": False,
                                    "outlets": {"nowa-redakcja.example": "UA"}, "tld_sides": {}}),
                        encoding="utf-8")
        polityka = SidePolicy.from_file(plik)
        assert polityka.side("nowa-redakcja.example") == "UA"
        assert polityka.side("rt.com") is None
        assert polityka.version == "test"
