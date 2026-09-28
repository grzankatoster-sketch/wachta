"""Features per H3 cell for a learned jamming detector, and the rule it has to beat.

The existing D3 rule looks at one number: what share of aircraft in a cell report degraded accuracy,
read through a Wilson lower bound so that three aircraft cannot shout as loudly as three hundred.
It scores precision 0.60 and recall 0.75 against gpsjam. That is the bar.

A model can see things the rule cannot, and the features here are chosen to be exactly those things
rather than a pile of everything:

  * how bad the degradation is, not only that it happened - a cell where accuracy collapses to the
    floor is a different animal from one hovering at the threshold;
  * altitude - jamming is line-of-sight, so it bites high aircraft over a wide radius and low ones
    barely at all; a cell whose degraded aircraft are all low is more likely a receiver artefact;
  * the neighbours - a transmitter on the ground does not respect cell borders, so a quiet cell
    ringed by loud ones is suspicious in a way the rule, which looks at one cell at a time, cannot
    express. This is where a model has the most room to win, and if it wins nowhere else, that is
    worth knowing too.

Nothing here decides anything. It turns positions into a table; the training script decides whether
the table is worth more than the rule.
"""
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from statistics import fmean, median, pstdev

import h3

from .jamming import wilson_lower_bound

# Dokladnie ten sam prog, ktorego uzywa regula (aggregate_jamming(degraded_below=8)). Gdyby model
# liczyl "zaklocone" inaczej niz regula, porownanie ich wynikow nie mowiloby nic o modelu.
DEGRADED_BELOW = 8

RESOLUTION = 4


@dataclass(frozen=True)
class CellFeatures:
    h3: str
    n_aircraft: int
    n_degraded: int
    share: float
    wilson: float               # to, co widzi obecna regula - model dostaje ja jako jedna z cech
    mean_nac_p: float
    min_nac_p: float
    share_missing_nac_p: float
    mean_alt_ft: float
    median_alt_ft: float
    spread_alt_ft: float
    mean_alt_degraded: float    # czy zaklocone lataly wysoko, czy nisko
    mean_alt_clean: float
    neighbour_share: float      # udzial zakloconych w pierscieniu dookola
    neighbour_aircraft: int
    neighbour_cells: int
    max_neighbour_share: float

    def row(self) -> dict:
        return asdict(self)


def _nac_p(position) -> int | None:
    value = getattr(position, "nac_p", None)
    return int(value) if isinstance(value, (int, float)) else None


def _alt(position) -> float | None:
    value = getattr(position, "alt_ft", None)
    return float(value) if isinstance(value, (int, float)) else None


def _group(positions: Iterable, resolution: int) -> dict[str, list]:
    cells: dict[str, list] = {}
    for p in positions:
        if getattr(p, "on_ground", False):
            continue
        cells.setdefault(h3.latlng_to_cell(p.lat, p.lon, resolution), []).append(p)
    return cells


def _degraded(position) -> bool:
    nac = _nac_p(position)
    return nac is not None and nac < DEGRADED_BELOW


def build_features(positions: Sequence, resolution: int = RESOLUTION,
                   min_aircraft: int = 3) -> list[CellFeatures]:
    """One row per cell that holds enough aircraft to say anything at all."""
    cells = _group(positions, resolution)
    counts = {cell: (sum(_degraded(p) for p in items), len(items)) for cell, items in cells.items()}

    out: list[CellFeatures] = []
    for cell, items in cells.items():
        if len(items) < min_aircraft:
            continue

        degraded = [p for p in items if _degraded(p)]
        nacs = [n for n in (_nac_p(p) for p in items) if n is not None]
        alts = [a for a in (_alt(p) for p in items) if a is not None]
        alts_bad = [a for a in (_alt(p) for p in degraded) if a is not None]
        alts_ok = [a for a in (_alt(p) for p in items if not _degraded(p)) if a is not None]

        ring = [c for c in h3.grid_disk(cell, 1) if c != cell and c in counts]
        ring_bad = sum(counts[c][0] for c in ring)
        ring_all = sum(counts[c][1] for c in ring)
        ring_shares = [counts[c][0] / counts[c][1] for c in ring if counts[c][1]]

        out.append(CellFeatures(
            h3=cell,
            n_aircraft=len(items),
            n_degraded=len(degraded),
            share=round(len(degraded) / len(items), 4),
            wilson=round(wilson_lower_bound(len(degraded), len(items)), 4),
            mean_nac_p=round(fmean(nacs), 2) if nacs else -1.0,
            min_nac_p=float(min(nacs)) if nacs else -1.0,
            share_missing_nac_p=round(1 - len(nacs) / len(items), 4),
            mean_alt_ft=round(fmean(alts)) if alts else -1.0,
            median_alt_ft=round(median(alts)) if alts else -1.0,
            spread_alt_ft=round(pstdev(alts)) if len(alts) > 1 else 0.0,
            mean_alt_degraded=round(fmean(alts_bad)) if alts_bad else -1.0,
            mean_alt_clean=round(fmean(alts_ok)) if alts_ok else -1.0,
            neighbour_share=round(ring_bad / ring_all, 4) if ring_all else 0.0,
            neighbour_aircraft=ring_all,
            neighbour_cells=len(ring),
            max_neighbour_share=round(max(ring_shares), 4) if ring_shares else 0.0,
        ))
    out.sort(key=lambda c: c.h3)
    return out


FEATURE_NAMES = [f for f in CellFeatures.__annotations__ if f != "h3"]
