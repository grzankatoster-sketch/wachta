"""Exports D1 cases for manual labelling, and turns labelled rows into eval cases.

  export: uv run --project src/python python eval/label_d1.py export   -> eval/labels/d1_to_label.csv
  (open the CSV, fill column 'label' with y/n using the replay link)
  import: uv run --project src/python python eval/label_d1.py import   -> appends to eval/fixtures/d1_cases.jsonl

The export deliberately lists EVERY aircraft that went silent for 5-30 minutes, not only the ones D1
reported. Alerts alone would make recall meaningless: the detector would be graded on its own output,
so the cases it silently missed could never show up. Column 'alerted' says whether D1 fired.
"""
import csv
import json
import os
import sys
from pathlib import Path

import psycopg

HERE = Path(__file__).parent
CSV_PATH = HERE / "labels" / "d1_to_label.csv"


SAMPLE_SQL = """
SELECT DISTINCT ON (hex) hex, evaluated_at, alerted, inputs
FROM d1_sample
ORDER BY hex, evaluated_at DESC
"""


def export():
    CSV_PATH.parent.mkdir(exist_ok=True)
    with psycopg.connect(os.environ["WACHTA_DB"]) as conn:
        rows = conn.execute(SAMPLE_SQL).fetchall()
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hex", "evaluated_at", "flight", "type", "military", "last_position_utc", "last_message_utc",
                    "alt_ft", "gs_kt", "alerted", "replay_url", "label"])
        for hex_, at, alerted, inputs in rows:
            s = inputs["last_seen"]
            url = f"https://globe.adsb.lol/?icao={hex_}&showTrace={at:%Y-%m-%d}"
            w.writerow([hex_, at.isoformat(), s["flight"], s["type_code"], s["is_military"], s["ts"],
                        s["last_message_at"], s["alt_ft"], s["gs_kt"], alerted, url, ""])
    print(f"{len(rows)} silent aircraft ({sum(r[2] for r in rows)} alerted) -> {CSV_PATH}")
    print("Oznacz y = transponder naprawdę zgasł, n = utrata zasięgu / lądowanie / sygnał wrócił.")
    print("Oznacz też wiersze z alerted=False — z nich liczy się recall.")


def import_():
    with psycopg.connect(os.environ["WACHTA_DB"]) as conn:
        rows = {(h, at.isoformat()): inputs for h, at, _, inputs in conn.execute(SAMPLE_SQL).fetchall()}
    cases = []
    with CSV_PATH.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["label"] not in ("y", "n"):
                continue
            inputs = rows[(r["hex"], r["evaluated_at"])]
            cases.append({
                "case": f"real_{r['hex']}_{r['evaluated_at']}",
                "last_seen": inputs["last_seen"], "now": inputs["now"], "coverage": inputs["coverage"],
                "alive": inputs["alive"], "airports": inputs["airports"], "expected": r["label"] == "y",
                # Progi jada razem z przypadkiem. Bez nich plik z etykietami jest jedna kupka probek
                # z roznych konfiguracji, a bramka usrednia pomiary, ktore nie opisuja tego samego
                # detektora - run_eval.eval_d1() rozdziela je wlasnie po tym polu.
                "rules": inputs.get("rules"), "rules_version": inputs.get("rules_version"),
            })
    with (HERE / "fixtures" / "d1_real_cases.jsonl").open("a", encoding="utf-8") as f:
        f.writelines(json.dumps(c) + "\n" for c in cases)
    print(f"appended {len(cases)} labelled cases (real metrics file, separate from the synthetic regression set)")


if __name__ == "__main__":
    {"export": export, "import": import_}[sys.argv[1]]()
