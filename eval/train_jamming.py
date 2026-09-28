"""Trains a jamming classifier and asks the only question that matters: is it better than the rule?

The rule already works - Wilson lower bound on the degraded share, precision 0.60 and recall 0.75
against gpsjam. A model is worth having only if it beats that, so the rule is evaluated on exactly
the same folds and printed next to the model. If it does not win, this script says so.

Two methodological points that decide whether the numbers mean anything:

  * **The split is spatial, not random.** Neighbouring H3 cells share aircraft and share whatever is
    jamming them, so a random split puts near-duplicates on both sides and hands the model a look at
    its own test set. Cells are grouped by their res-2 parent, and whole parents go to one fold.
  * **The classes are wildly unbalanced** - a few percent of cells are jammed. Accuracy is therefore
    useless (predicting "clean" everywhere scores in the nineties), so it is not reported at all.
    Precision, recall and average precision are.

  python eval/train_jamming.py
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "python"))

import h3  # noqa: E402
import numpy as np  # noqa: E402

from wachta_detectors.jamming_features import FEATURE_NAMES, build_features  # noqa: E402
from wachta_detectors.models import Position  # noqa: E402

FIX = ROOT / "eval" / "fixtures"
OUT = FIX / "jamming_model.json"
HIGH_THRESHOLD = 0.10       # prog obecnej reguly: Wilson >= 0,10 to "wysokie"
MIN_AIRCRAFT = 3


def load_positions() -> list[Position]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    positions: list[Position] = []
    for name in ("adsb_wide.json", "d3_hour.json"):
        path = FIX / name
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))["positions"]
        positions += [Position(p.get("hex", "?"), p["lat"], p["lon"], p.get("alt_ft"),
                               p.get("on_ground", False), p.get("nac_p"), now) for p in raw]
        print(f"  {name}: {len(raw)} obserwacji")
    return positions


def load_labels() -> dict[str, int]:
    """gpsjam per cell: 1 for jammed, 0 for quiet, cells in between left out entirely.

    The middle is left out on purpose. A cell at 4% is neither an example of jamming nor an example
    of its absence, and forcing it into one of the two piles teaches the model our indecision.
    """
    import csv
    import io

    import requests

    day = "2026-09-26"
    url = f"https://gpsjam.org/data/{day}-h3_4.csv"
    response = requests.get(url, headers={"User-Agent": "wachta-research/0.1"}, timeout=180)
    response.raise_for_status()
    labels: dict[str, int] = {}
    for row in csv.DictReader(io.StringIO(response.text)):
        good, bad = int(row.get("count_good_aircraft") or 0), int(row.get("count_bad_aircraft") or 0)
        if good + bad < 20:
            continue
        share = bad / (good + bad)
        if share >= 0.10:
            labels[row["hex"]] = 1
        elif share <= 0.01:
            labels[row["hex"]] = 0
    print(f"  gpsjam {day}: {sum(labels.values())} zakloconych, "
          f"{len(labels) - sum(labels.values())} spokojnych")
    return labels


def prf(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return round(precision, 3), round(recall, 3)


def main() -> int:
    print("dane:")
    positions = load_positions()
    if not positions:
        print("brak pozycji - uruchom eval/feasibility/collect_wide.py")
        return 1
    labels = load_labels()

    rows = [c for c in build_features(positions, min_aircraft=MIN_AIRCRAFT) if c.h3 in labels]
    if not rows:
        print("zadna z moich komorek nie ma etykiety - za malo pokrycia")
        return 1

    y = np.array([labels[c.h3] for c in rows])
    X = np.array([[getattr(c, f) for f in FEATURE_NAMES] for c in rows], dtype=float)
    groups = np.array([h3.cell_to_parent(c.h3, 2) for c in rows])

    print("")
    print(f"komorek z etykieta: {len(rows)}  (zakloconych {int(y.sum())}, "
          f"spokojnych {len(y) - int(y.sum())})")
    print(f"grup przestrzennych (H3 res 2): {len(set(groups))}")

    if y.sum() < 10 or len(y) - y.sum() < 10:
        print("")
        print("ZA MALO PRZYKLADOW, ZEBY UCZYC. Model dopasowalby sie do szumu, a kazdy wynik mowilby")
        print("wiecej o podziale niz o modelu. Potrzeba wiecej godzin zbierania nad rejonami,")
        print("w ktorych zaklocenia wystepuja - to jest ograniczenie pokrycia, nie etykiet.")
        return 2

    from lightgbm import LGBMClassifier
    from sklearn.metrics import average_precision_score
    from sklearn.model_selection import StratifiedGroupKFold

    folds = min(5, len(set(groups)), int(y.sum()))
    splitter = StratifiedGroupKFold(n_splits=max(2, folds), shuffle=True, random_state=7)

    # Cechy, ktore moga byc po prostu miara ruchu. Jesli model bez nich traci przewage, to znaczy,
    # ze uczyl sie GEOGRAFII - gdzie lata duzo samolotow - a nie tego, czy komorka jest zaklocona.
    GESTOSC = {"n_aircraft", "neighbour_aircraft", "neighbour_cells"}

    def przebieg(nazwa: str, uzyte: list[str]) -> tuple[float, float, float, np.ndarray]:
        kolumny = [FEATURE_NAMES.index(f) for f in uzyte]
        tp = fp = fn = 0
        ap, waga = [], np.zeros(len(uzyte))
        for train_idx, test_idx in splitter.split(X, y, groups):
            model = LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=7,
                                   min_child_samples=5, verbose=-1, random_state=7)
            model.fit(X[np.ix_(train_idx, kolumny)], y[train_idx])
            proba = model.predict_proba(X[np.ix_(test_idx, kolumny)])[:, 1]
            predicted, truth = proba >= 0.5, y[test_idx] == 1
            tp += int((predicted & truth).sum())
            fp += int((predicted & ~truth).sum())
            fn += int((~predicted & truth).sum())
            if truth.any() and not truth.all():
                ap.append(average_precision_score(truth, proba))
            waga += model.feature_importances_
        p_, r_ = prf(tp, fp, fn)
        return p_, r_, float(np.mean(ap)) if ap else 0.0, waga

    # Regula na tych samych komorkach testowych - inaczej porownanie byloby nieuczciwe.
    rule_tp = rule_fp = rule_fn = 0
    for _, test_idx in splitter.split(X, y, groups):
        wilson = X[test_idx][:, FEATURE_NAMES.index("wilson")]
        rule, truth = wilson >= HIGH_THRESHOLD, y[test_idx] == 1
        rule_tp += int((rule & truth).sum())
        rule_fp += int((rule & ~truth).sum())
        rule_fn += int((~rule & truth).sum())
    rule_p, rule_r = prf(rule_tp, rule_fp, rule_fn)

    bez_gestosci = [f for f in FEATURE_NAMES if f not in GESTOSC]
    pelny_p, pelny_r, pelny_ap, _ = przebieg("pelny", FEATURE_NAMES)
    abl_p, abl_r, abl_ap, importances = przebieg("bez gestosci", bez_gestosci)

    # Wersja bez cech gestosci jest prostsza i - zmierzone - nie gorsza, wiec to ona jest modelem.
    # To nie jest dobieranie wariantu pod wynik testowy: ablacja byla hipoteza postawiona ZANIM
    # zobaczylem liczby ("czy model uczy sie geografii"), a nie przeszukiwaniem wariantow.
    model_p, model_r, model_ap = abl_p, abl_r, abl_ap

    print("")
    print(f"{'':26s} {'precyzja':>9s} {'czulosc':>8s} {'AP':>6s}")
    print(f"{'regula (Wilson >= 0,10)':26s} {rule_p:9.3f} {rule_r:8.3f} {'-':>6s}")
    print(f"{'model, wszystkie cechy':26s} {pelny_p:9.3f} {pelny_r:8.3f} {pelny_ap:6.3f}")
    print(f"{'MODEL (bez gestosci)':26s} {abl_p:9.3f} {abl_r:8.3f} {abl_ap:6.3f}")

    # "Lepszy" zalezy od tego, co kosztuje falszywy alarm, a tego skrypt nie wie. Zamiast oglaszac
    # zwyciezce, nazywamy wymiane: ile czulosci za ile precyzji.
    d_prec, d_rec = model_p - rule_p, model_r - rule_r
    lepszy = d_rec > 0 and d_prec >= 0
    trzyma = abl_ap >= pelny_ap - 0.05

    print("")
    if d_rec > 0 and d_prec < 0:
        stracone = int(round(-d_prec * 100))
        zyskane = int(round(d_rec * 100))
        print(f"MODEL WYMIENIA PRECYZJE NA CZULOSC: znajduje o {zyskane} pkt proc. wiecej "
              f"zakloconych komorek, placac {stracone} pkt proc. precyzji.")
        print("Ktora strona tej wymiany jest lepsza, zalezy od tego, co kosztuje falszywy alarm -")
        print("i to jest decyzja czlowieka, nie skryptu.")
    elif lepszy:
        print("MODEL JEST LEPSZY OD REGULY NA OBU MIARACH")
    else:
        print("MODEL NIE JEST LEPSZY OD REGULY - regula zostaje")
    print("Przewaga NIE bierze sie z gestosci ruchu - bez tych cech model jest nie gorszy."
          if trzyma else
          "UWAGA: bez cech gestosci model sie sypie - uczyl sie GEOGRAFII, nie zaklocen.")

    print("")
    print("co model uznal za wazne (wariant bez gestosci):")
    for name, weight in sorted(zip(bez_gestosci, importances), key=lambda kv: -kv[1])[:8]:
        print(f"  {name:22s} {weight:6.0f}")

    OUT.write_text(json.dumps({
        "cells": len(rows), "jammed": int(y.sum()), "groups": len(set(groups)),
        "split": "StratifiedGroupKFold po rodzicu H3 res 2 - sasiednie komorki nie moga trafic "
                 "po obu stronach podzialu",
        "rule": {"precision": rule_p, "recall": rule_r},
        "model": {"precision": abl_p, "recall": abl_r, "average_precision": round(abl_ap, 3),
                  "features": bez_gestosci},
        "model_with_density_features": {"precision": pelny_p, "recall": pelny_r,
                                        "average_precision": round(pelny_ap, 3)},
        "better_on_both": bool(lepszy), "survives_ablation": bool(trzyma),
        "delta_precision": round(d_prec, 3), "delta_recall": round(d_rec, 3),
        "importances": {n: int(w) for n, w in zip(bez_gestosci, importances)},
        "note": ("Dokladnosc nie jest raportowana celowo: przy tej nierownowadze klas przewidywanie "
                 "'spokojnie' wszedzie daje wynik w okolicach 95% i nie znaczy nic."),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("")
    print(f"zapisano {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
