from wachta_detectors.ais import Eta, decode_eta


def packed(month: int, day: int, hour: int, minute: int) -> int:
    return (month << 16) | (day << 11) | (hour << 6) | minute


def test_decodes_a_real_value_from_the_feed():
    # 645376 przyszlo z Digitraffic dla statku BLUE SPIRIT (2026-09-27).
    eta = decode_eta(645376)
    assert eta == Eta(month=9, day=27, hour=4, minute=0)
    assert str(eta) == "27.09, 04:00 UTC"


def test_round_trip_for_a_few_dates():
    for month, day, hour, minute in ((1, 1, 0, 0), (12, 31, 23, 59), (6, 15, 12, 30)):
        assert decode_eta(packed(month, day, hour, minute)) == Eta(month, day, hour, minute)


def test_the_ais_not_available_value_means_nothing_was_declared():
    assert decode_eta(packed(0, 0, 24, 60)) is None


def test_zero_month_or_day_is_not_a_date():
    assert decode_eta(packed(0, 14, 10, 0)) is None
    assert decode_eta(packed(7, 0, 10, 0)) is None


def test_values_out_of_range_are_rejected_rather_than_shown():
    assert decode_eta(packed(13, 1, 10, 0)) is None
    assert decode_eta(packed(7, 1, 25, 0)) is None


def test_missing_or_unparsable_input():
    assert decode_eta(None) is None
    assert decode_eta("") is None
    assert decode_eta("nie liczba") is None
    assert decode_eta(0) is None
    assert decode_eta(-5) is None


def test_string_number_is_accepted_because_feeds_send_both():
    assert decode_eta("645376") == Eta(9, 27, 4, 0)
