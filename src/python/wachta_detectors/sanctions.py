"""Matching ships against the OpenSanctions maritime dataset.

The dataset is one flat CSV (about 5 MB) with a row per vessel or organisation: IMO, MMSI, flag and a
semicolon-separated risk field. The tags that matter here:

  sanction      - on a sanctions list
  mare.shadow   - flagged as shadow-fleet
  mare.detained - detained by a port state control regime
  poi           - person/vessel of interest
  reg.warn      - registry warning

Matching is by IMO first (a hull keeps it for life) and only then by MMSI, which is reassigned with
the flag and therefore weaker evidence. A match is a reason to look, never a verdict.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

SHADOW = "mare.shadow"
SANCTION = "sanction"

# Polowa tego pliku to nie sankcje, tylko inspekcje i zatrzymania portowe (Tokyo/Paris/Abuja/Black
# Sea MoU). Statek zatrzymany za przeciekajaca pompe zeznaje o swoim stanie technicznym, a nie o
# tym, czyj wozi ladunek. Zlepienie obu w jedno "jest na liscie" bylo bledem i tu sie konczy.
INSPEKCJE = frozenset({
    "tokyo_mou_detention", "ext_tokyo_mou_psc", "black_sea_mou_detention",
    "ext_abuja_mou_psc", "abuja_mou_detention", "paris_mou_banned",
})
BADANIA = frozenset({"kp_rusi_reports"})


def digits(value: object) -> str:
    """'IMO9427366' and 9427366 both become '9427366'."""
    return "".join(c for c in str(value or "") if c.isdigit())


@dataclass(frozen=True)
class SanctionMatch:
    caption: str
    risk: tuple[str, ...]
    flag: str | None
    datasets: tuple[str, ...]
    url: str
    matched_on: str  # "imo" albo "mmsi"

    @property
    def category(self) -> str:
        """What kind of list this actually is - the difference decides what may be claimed."""
        if not self.datasets:
            return "lista nieokreslona"
        if any(d not in INSPEKCJE and d not in BADANIA for d in self.datasets):
            return "sankcje"
        if any(d in BADANIA for d in self.datasets):
            return "raport badawczy"
        return "inspekcje portowe"

    @property
    def is_sanctions_list(self) -> bool:
        return self.category == "sankcje"

    @property
    def is_shadow_fleet(self) -> bool:
        return SHADOW in self.risk

    @property
    def is_sanctioned(self) -> bool:
        return SANCTION in self.risk


class SanctionIndex:
    def __init__(self, by_imo: dict[str, SanctionMatch], by_mmsi: dict[str, SanctionMatch]):
        self._by_imo = by_imo
        self._by_mmsi = by_mmsi

    @classmethod
    def from_csv(cls, path: Path) -> "SanctionIndex":
        by_imo: dict[str, SanctionMatch] = {}
        by_mmsi: dict[str, SanctionMatch] = {}
        with Path(path).open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if (row.get("type") or "").upper() != "VESSEL":
                    continue
                risk = tuple(r for r in (row.get("risk") or "").split(";") if r)
                datasets = tuple(d for d in (row.get("datasets") or "").split(";") if d)
                base = dict(caption=row.get("caption") or "?", risk=risk, flag=(row.get("flag") or None),
                            datasets=datasets, url=row.get("url") or "")
                imo, mmsi = digits(row.get("imo")), digits(row.get("mmsi"))
                if imo:
                    by_imo.setdefault(imo, SanctionMatch(**base, matched_on="imo"))
                if mmsi:
                    by_mmsi.setdefault(mmsi, SanctionMatch(**base, matched_on="mmsi"))
        return cls(by_imo, by_mmsi)

    def __len__(self) -> int:
        return len(self._by_imo)

    def match(self, imo: object = None, mmsi: object = None) -> SanctionMatch | None:
        found = self._by_imo.get(digits(imo)) if digits(imo) else None
        if found is not None:
            return found
        return self._by_mmsi.get(digits(mmsi)) if digits(mmsi) else None
