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


def test_unknown_dataset_is_not_promoted_to_a_sanction():
    # Znalezione w audycie: kategoryzacja dzialala na liscie wykluczen, wiec kazdy nieznany zbior
    # (nowy w OpenSanctions albo literowka) awansowal statek do "sankcjonowanego".
    assert match("jakis_nowy_rejestr_2027").category == "nieznany wykaz"
    assert not match("jakis_nowy_rejestr_2027").is_sanctions_list


def test_typo_in_a_known_name_does_not_become_a_sanction():
    assert match("tokyo_mou_detentions").category == "nieznany wykaz"


def test_unknown_alongside_a_real_sanction_still_counts():
    assert match("jakis_nowy_rejestr_2027", "us_ofac_sdn").category == "sankcje"


def test_several_rows_about_one_hull_are_merged(tmp_path):
    """Znalezione w audycie: liczyl sie tylko pierwszy wiersz z pliku.

    W tym pliku 5976 kadlubow ma wiecej niz jeden wiersz na ten sam numer IMO, a w 484 przypadkach
    pierwszy wiersz nie mial sankcji, a pozniejszy mial - czyli te statki byly po cichu raportowane
    jako niesankcjonowane.
    """
    import csv

    from wachta_detectors.sanctions import SanctionIndex

    path = tmp_path / "maritime.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["type", "caption", "risk", "datasets", "flag", "imo", "mmsi", "url"])
        w.writeheader()
        w.writerow({"type": "VESSEL", "caption": "ALFA", "risk": "mare.detained",
                    "datasets": "tokyo_mou_detention", "flag": "mt", "imo": "9000001",
                    "mmsi": "111000001", "url": "u1"})
        w.writerow({"type": "VESSEL", "caption": "ALFA", "risk": "sanction",
                    "datasets": "us_ofac_sdn", "flag": "", "imo": "9000001",
                    "mmsi": "111000001", "url": "u2"})

    m = SanctionIndex.from_csv(path).match(imo="9000001")
    assert set(m.datasets) == {"tokyo_mou_detention", "us_ofac_sdn"}
    assert set(m.risk) == {"mare.detained", "sanction"}
    assert m.category == "sankcje", "sankcje z drugiego wiersza nie moga zniknac"
