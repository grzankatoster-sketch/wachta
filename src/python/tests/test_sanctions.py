import pytest

from wachta_detectors.sanctions import SanctionIndex, digits

CSV = """type,caption,imo,risk,countries,flag,mmsi,id,url,datasets
VESSEL,SHPINEL,IMO9346744,mare.shadow;poi,ru,ru,273######,os-1,https://x/1,ru_gur_vessels
VESSEL,PALLADIUM,IMO9773923,poi,lr,lr,,os-2,https://x/2,opensanctions
VESSEL,BEZ IMO,,sanction,ru,ru,987654321,os-3,https://x/3,eu_fsf
VESSEL,CZYSTY WPIS,IMO9000001,,gb,gb,,os-4,https://x/4,abuja_mou
ORGANIZATION,JAKAS FIRMA,,sanction,ru,,,os-5,https://x/5,eu_fsf
"""


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "maritime.csv"
    path.write_text(CSV.replace("######", "111111"), encoding="utf-8")
    return SanctionIndex.from_csv(path)


def test_digits_strips_the_imo_prefix_and_accepts_numbers():
    assert digits("IMO9427366") == "9427366"
    assert digits(9427366) == "9427366"
    assert digits(None) == ""
    assert digits("") == ""


def test_organisations_are_not_indexed_as_vessels(index):
    assert len(index) == 3  # trzy statki z IMO, firma pominieta


def test_match_by_imo_with_or_without_prefix(index):
    for value in ("IMO9346744", "9346744", 9346744):
        found = index.match(imo=value)
        assert found is not None
        assert found.caption == "SHPINEL"
        assert found.matched_on == "imo"


def test_shadow_fleet_and_sanction_flags_come_from_the_risk_field(index):
    shadow = index.match(imo="9346744")
    assert shadow.is_shadow_fleet
    assert not shadow.is_sanctioned
    assert shadow.risk == ("mare.shadow", "poi")

    plain = index.match(imo="9000001")
    assert plain.risk == ()
    assert not plain.is_shadow_fleet


def test_mmsi_is_only_a_fallback(index):
    # IMO wins when both are known: the hull keeps its IMO, MMSI travels with the flag.
    both = index.match(imo="9346744", mmsi="987654321")
    assert both.caption == "SHPINEL"
    assert both.matched_on == "imo"

    only_mmsi = index.match(imo=None, mmsi="987654321")
    assert only_mmsi.caption == "BEZ IMO"
    assert only_mmsi.matched_on == "mmsi"


def test_unknown_ship_matches_nothing(index):
    assert index.match(imo="1234567", mmsi="111222333") is None
    assert index.match() is None
