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
