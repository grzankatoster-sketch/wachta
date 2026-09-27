from wachta_detectors.sanctions import SanctionMatch


def match(*datasets: str, risk: tuple[str, ...] = ()) -> SanctionMatch:
    return SanctionMatch(caption="X", risk=risk, flag="mt", datasets=datasets,
                         url="", matched_on="mmsi")


def test_port_state_inspection_is_not_a_sanction():
    # SIRINA z doby 2024-12-25: wpis z Abuja MoU, czyli protokol inspekcji, nie lista sankcyjna.
    m = match("ext_abuja_mou_psc")
    assert m.category == "inspekcje portowe"
    assert not m.is_sanctions_list


def test_detention_by_a_port_state_is_also_only_an_inspection():
    assert match("tokyo_mou_detention").category == "inspekcje portowe"
    assert match("paris_mou_banned").category == "inspekcje portowe"


def test_real_sanctions_lists_are_named_as_such():
    for dataset in ("us_ofac_sdn", "eu_sanctions_map", "ua_war_sanctions", "un_1718_vessels"):
        assert match(dataset).is_sanctions_list, dataset


def test_a_ship_on_both_counts_as_sanctioned():
    assert match("ext_tokyo_mou_psc", "us_ofac_sdn").category == "sankcje"


def test_research_report_is_its_own_thing():
    assert match("kp_rusi_reports").category == "raport badawczy"
    assert not match("kp_rusi_reports").is_sanctions_list


def test_no_datasets_at_all_is_not_called_a_sanction():
    assert match().category == "lista nieokreslona"
    assert not match().is_sanctions_list
