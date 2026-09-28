"""The evaluation gate must fail a broken detector.

The first version of the gate scored a detector that returned nothing as precision = recall = 1.0,
because metrics were computed from the detector's own output. These tests pin that down: labels are
frozen, and a detector that flags nothing scores recall 0 on D3 and on D1.
"""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h3
import pytest

ROOT = Path(__file__).resolve().parents[3]
KALININGRAD = (54.71, 20.51)
FAR_AWAY = (44.0, 9.0)  # Ligurian Sea, ~1700 km from Kaliningrad


def load_run_eval():
    spec = importlib.util.spec_from_file_location("run_eval", ROOT / "eval" / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_eval"] = module
    spec.loader.exec_module(module)
    return module


def write_fixtures(fix: Path) -> None:
    """One jammed area (Kaliningrad) and one clean area, each with enough aircraft to pass min_aircraft (10)."""
    fix.mkdir(parents=True, exist_ok=True)
    positions = []
    for i in range(12):
        positions.append({"hex": f"jam{i}", "lat": KALININGRAD[0], "lon": KALININGRAD[1],
                          "alt_ft": 30000, "on_ground": False, "nac_p": 2})
        positions.append({"hex": f"ok{i}", "lat": FAR_AWAY[0], "lon": FAR_AWAY[1],
                          "alt_ft": 30000, "on_ground": False, "nac_p": 10})
    (fix / "d3_hour.json").write_text(json.dumps({"hour": "2026-09-22T12:00:00+00:00", "positions": positions}), encoding="utf-8")
    (fix / "d3_labels.json").write_text(json.dumps({
        "positive": [h3.latlng_to_cell(*KALININGRAD, 4)],
        "negative": [h3.latlng_to_cell(*FAR_AWAY, 4)],
    }), encoding="utf-8")

    now = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    lat, lon = 55.5, 17.5
    cell = h3.latlng_to_cell(lat, lon, 5)
    case = {
        "case": "dark", "expected": True, "now": now.isoformat(),
        "last_seen": {"hex": "ae1234", "flight": "FORTE10", "type_code": "Q4", "is_military": True,
                      "lat": lat, "lon": lon, "alt_ft": 30000, "gs_kt": 300.0,
                      "ts": (now - timedelta(minutes=10)).isoformat(), "n_points": 120,
                      "last_message_at": (now - timedelta(minutes=10)).isoformat()},
        "coverage": {c: 1000 for c in h3.grid_disk(cell, 1)},
        "alive": [cell],
        "airports": [[54.3776, 18.4662]],
    }
    (fix / "d1_cases.jsonl").write_text(json.dumps(case) + "\n", encoding="utf-8")


@pytest.fixture
def evaluator(tmp_path, monkeypatch):
    module = load_run_eval()
    fix = tmp_path / "fixtures"
    write_fixtures(fix)
    monkeypatch.setattr(module, "FIX", fix)
    return module


def test_working_detectors_score_full_marks(evaluator):
    assert evaluator.eval_d3() == {"precision": 1.0, "recall": 1.0, "n_positive": 1, "n_negative": 1}
    assert evaluator.eval_d1(evaluator.FIX / "d1_cases.jsonl")["recall"] == 1.0


def test_detector_returning_nothing_fails_the_gate(evaluator, monkeypatch):
    """The mutation the first gate let through."""
    monkeypatch.setattr(evaluator, "aggregate_jamming", lambda *a, **kw: [])
    assert evaluator.eval_d3()["recall"] == 0.0

    monkeypatch.setattr(evaluator, "find_dark_candidates", lambda *a, **kw: [])
    assert evaluator.eval_d1(evaluator.FIX / "d1_cases.jsonl")["recall"] == 0.0


def test_detector_flagging_everything_fails_on_precision(evaluator, monkeypatch):
    from wachta_detectors.jamming import JammingCell

    labels = json.loads((evaluator.FIX / "d3_labels.json").read_text(encoding="utf-8"))
    everything = [JammingCell(c, 10, 10) for c in labels["positive"] + labels["negative"]]
    monkeypatch.setattr(evaluator, "aggregate_jamming", lambda *a, **kw: everything)
    result = evaluator.eval_d3()
    assert result["recall"] == 1.0
    assert result["precision"] == 0.5


def test_missing_real_cases_file_is_reported_not_scored(evaluator):
    assert evaluator.eval_d1(evaluator.FIX / "d1_real_cases.jsonl") == {"precision": None, "recall": None, "n_cases": 0}


# --- Progi, pod ktorymi powstala etykieta ------------------------------------------------------
# dark.snapshot_inputs() zapisuje w kazdej probce D1 uzyte progi i ich odcisk (rules_version).
# Bramka tego nie czytala, wiec probki sprzed i po zmianie progu wpadaly do jednej sredniej - a
# jedna liczba z dwoch konfiguracji nie opisuje zadnej z nich.

def real_case(hex_: str, expected: bool, rules_version: str | None, lat=55.5, lon=17.5) -> dict:
    now = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    cell = h3.latlng_to_cell(lat, lon, 5)
    case = {
        "case": hex_, "expected": expected, "now": now.isoformat(),
        "last_seen": {"hex": hex_, "flight": "FORTE10", "type_code": "Q4", "is_military": True,
                      "lat": lat, "lon": lon, "alt_ft": 30000, "gs_kt": 300.0,
                      "ts": (now - timedelta(minutes=10)).isoformat(), "n_points": 120,
                      "last_message_at": (now - timedelta(minutes=10)).isoformat()},
        "coverage": {c: 1000 for c in h3.grid_disk(cell, 1)},
        "alive": [cell],
        "airports": [[54.3776, 18.4662]],
    }
    if rules_version is not None:
        case["rules_version"] = rules_version
    return case


def write_real(fix: Path, cases: list[dict]) -> Path:
    path = fix / "d1_real_cases.jsonl"
    path.write_text("".join(json.dumps(c) + "\n" for c in cases), encoding="utf-8")
    return path


def test_labels_from_other_thresholds_stay_out_of_the_current_metric(evaluator):
    """Jedna trafna probka spod obecnych progow i dwie chybione spod starych.

    Bez podzialu precyzja wyszlaby 0,33 - liczba opisujaca mieszanke dwoch detektorow.
    """
    teraz = evaluator.CURRENT_RULES
    path = write_real(evaluator.FIX, [
        real_case("ae0001", True, teraz),
        real_case("ae0002", False, "stare1234567"),
        real_case("ae0003", False, "stare1234567"),
    ])
    wynik = evaluator.eval_d1(path)
    assert wynik["precision"] == 1.0 and wynik["recall"] == 1.0
    assert wynik["n_cases"] == 1
    assert wynik["rules_version"] == teraz
    # Stare probki nie znikaja - sa raportowane osobno, ze swoja wlasna (fatalna) precyzja.
    assert wynik["n_other_rules"] == 2
    assert wynik["by_rules"]["stare1234567"] == {"precision": 0.0, "recall": 1.0, "n_cases": 2}


def test_a_threshold_change_leaves_no_measurement_instead_of_a_free_pass(evaluator):
    """Wszystkie etykiety spod innych progow: bramka ma to zobaczyc jako brak pomiaru."""
    path = write_real(evaluator.FIX, [real_case("ae0004", True, "stare1234567")])
    wynik = evaluator.eval_d1(path)
    assert wynik["precision"] is None and wynik["recall"] is None
    assert wynik["n_cases"] == 0

    base = {"d1_real": {"precision": 0.8, "recall": 0.8}}
    assert evaluator.metric_drops(base, {"d1_real": wynik}) == [
        "d1_real.precision: 0.8 -> None", "d1_real.recall: 0.8 -> None"]


def test_hand_written_scenarios_without_a_version_still_count(evaluator):
    """Zestaw syntetyczny nie pochodzi z probkowania, wiec nie ma konfiguracji, ktora by go wybrala."""
    path = write_real(evaluator.FIX, [real_case("ae0005", True, None)])
    wynik = evaluator.eval_d1(path)
    assert wynik["n_cases"] == 1
    assert wynik["recall"] == 1.0
    assert "by_rules" not in wynik


def test_the_version_is_derived_from_the_thresholds_not_typed_in(evaluator):
    from wachta_detectors.dark import DarkRules, rules_version

    assert rules_version() == evaluator.CURRENT_RULES
    assert rules_version(DarkRules(min_cell_reports=999)) != evaluator.CURRENT_RULES


def test_the_labelling_step_carries_the_thresholds_into_the_case(tmp_path, monkeypatch):
    """Rozdzielanie po progach jest warte tyle, ile producent etykiet - a ten je wczesniej gubil.

    label_d1.py przepisywal ze snapshotu tylko wejscia detektora, wiec `rules_version` konczyl sie
    w bazie i nigdy nie docieral do pliku, po ktorym bramka miala rozrozniac konfiguracje.
    """
    import csv
    from contextlib import contextmanager

    spec = importlib.util.spec_from_file_location("label_d1", ROOT / "eval" / "label_d1.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["label_d1"] = module
    spec.loader.exec_module(module)

    at = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    inputs = {"last_seen": {"hex": "ae1234"}, "now": at.isoformat(), "coverage": {}, "alive": [],
              "airports": [], "rules": {"min_alt_ft": 3000}, "rules_version": "abc123456789"}

    class FakeConn:
        def execute(self, sql, params=None):
            return self

        def fetchall(self):
            return [("ae1234", at, False, inputs)]

    @contextmanager
    def connect(dsn):
        yield FakeConn()

    monkeypatch.setattr(module.psycopg, "connect", connect)
    monkeypatch.setenv("WACHTA_DB", "postgresql://fake")
    monkeypatch.setattr(module, "HERE", tmp_path)
    monkeypatch.setattr(module, "CSV_PATH", tmp_path / "labels" / "d1_to_label.csv")
    (tmp_path / "labels").mkdir()
    (tmp_path / "fixtures").mkdir()
    with module.CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hex", "evaluated_at", "alerted", "label"])
        w.writerow(["ae1234", at.isoformat(), "False", "y"])

    module.import_()
    [case] = [json.loads(line) for line in
              (tmp_path / "fixtures" / "d1_real_cases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert case["rules_version"] == "abc123456789"
    assert case["rules"] == {"min_alt_ft": 3000}
