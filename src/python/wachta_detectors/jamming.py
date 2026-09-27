"""D3: GPS interference map from ADS-B NACp values (method in the spirit of gpsjam.org).

A cell's level is decided on the **lower bound of a Wilson confidence interval**, not on the raw
share of affected aircraft. Measured on a real hour of Baltic traffic (2026-09-26, 13 781 positions):
with the raw share and five aircraft per cell, one affected aircraft already means 20 %, and 154 of
274 cells came out "high" — scattered over Germany and central Poland, which is not where jamming is.
With the lower bound and ten aircraft, 11 cells come out high and 82 % of them sit within 400 km of
the measured hotspot (56.2N 21.3E, eastern Baltic), median distance 189 km.
"""
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from math import sqrt

import h3

from wachta_detectors.models import Position

MEDIUM_THRESHOLD = 0.02
HIGH_THRESHOLD = 0.10
Z_95 = 1.96


def wilson_lower_bound(successes: int, total: int, z: float = Z_95) -> float:
    """Lower end of the confidence interval for a proportion: small samples have to earn their score."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denominator)


@dataclass(frozen=True)
class JammingCell:
    h3: str
    n_aircraft: int
    n_degraded: int

    @property
    def pct(self) -> float:
        """Raw share — for display. Do not threshold on it."""
        return self.n_degraded / self.n_aircraft

    @property
    def confidence_floor(self) -> float:
        return wilson_lower_bound(self.n_degraded, self.n_aircraft)

    @property
    def level(self) -> str:
        if self.confidence_floor >= HIGH_THRESHOLD:
            return "high"
        if self.confidence_floor >= MEDIUM_THRESHOLD:
            return "medium"
        return "low"


def aggregate_jamming(
    positions: Iterable[Position],
    resolution: int = 4,
    degraded_below: int = 8,
    min_aircraft: int = 10,
) -> list[JammingCell]:
    # cell -> hex -> [degraded_reports, total_reports]
    votes: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for p in positions:
        if p.on_ground or p.nac_p is None:
            continue
        v = votes[h3.latlng_to_cell(p.lat, p.lon, resolution)][p.hex]
        v[0] += p.nac_p < degraded_below
        v[1] += 1

    cells = []
    for cell, per_aircraft in votes.items():
        if len(per_aircraft) < min_aircraft:
            continue
        # Majority, not "any": over an hour a single bad report is noise, a jammed aircraft reports badly the whole way.
        degraded = sum(1 for bad, total in per_aircraft.values() if bad * 2 > total)
        cells.append(JammingCell(cell, len(per_aircraft), degraded))
    return cells
