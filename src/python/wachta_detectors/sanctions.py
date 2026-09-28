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
# Lista DOZWOLONYCH, nie wykluczen. Pierwsza wersja dzialala odwrotnie - wszystko, czego nie znala,
# uznawala za sankcje - wiec nowy zbior OpenSanctions albo literowka w nazwie po cichu awansowaly
# statek do "sankcjonowanego". To ten sam blad, ktory ta kategoryzacja miala naprawic, tylko schowany
# glebiej. Nieznane ma spadac do slabszego twierdzenia, nigdy do mocniejszego.
SANKCJE = frozenset({
    "us_ofac_sdn", "us_trade_csl", "us_cbp_forced_labor", "eu_sanctions_map",
    "eu_journal_sanctions", "eu_fsf", "gb_fcdo_sanctions", "ca_dfatd_sema_sanctions",
    "ch_seco_sanctions", "fr_tresor_gels_avoir", "mc_fund_freezes", "un_1718_vessels",
    "ua_war_sanctions",
})
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
        if any(d in SANKCJE for d in self.datasets):
            return "sankcje"
        if any(d in BADANIA for d in self.datasets):
            return "raport badawczy"
        if any(d in INSPEKCJE for d in self.datasets):
            return "inspekcje portowe"
        return "nieznany wykaz"

    @property
    def is_sanctions_list(self) -> bool:
        return self.category == "sankcje"

    @property
    def is_shadow_fleet(self) -> bool:
        return SHADOW in self.risk

    @property
    def is_sanctioned(self) -> bool:
        return SANCTION in self.risk


def _merge(existing: "SanctionMatch | None", row: dict, matched_on: str) -> "SanctionMatch":
    """Combines several rows about the same hull instead of keeping whichever came first.

    OpenSanctions publishes one row per listing, not per ship: 5976 hulls in this file appear under
    more than one IMO row. Keeping only the first made the answer depend on the order of the CSV,
    and it was not a harmless dependency - in 484 cases the first row carried no sanctions while a
    later one did, so those ships were quietly reported as not sanctioned.

    Risk tags and datasets are unioned, because a ship detained by a port state AND listed by OFAC is
    both of those things. The caption and flag come from the first row that has them.
    """
    if existing is None:
        return SanctionMatch(**row, matched_on=matched_on)
    return SanctionMatch(
        caption=existing.caption if existing.caption != "?" else row["caption"],
        risk=tuple(sorted(set(existing.risk) | set(row["risk"]))),
        flag=existing.flag or row["flag"],
        datasets=tuple(sorted(set(existing.datasets) | set(row["datasets"]))),
        url=existing.url or row["url"],
        matched_on=matched_on,
    )


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
                    by_imo[imo] = _merge(by_imo.get(imo), base, "imo")
                if mmsi:
                    by_mmsi[mmsi] = _merge(by_mmsi.get(mmsi), base, "mmsi")
        return cls(by_imo, by_mmsi)

    def __len__(self) -> int:
        return len(self._by_imo)

    def match(self, imo: object = None, mmsi: object = None) -> SanctionMatch | None:
        found = self._by_imo.get(digits(imo)) if digits(imo) else None
        if found is not None:
            return found
        return self._by_mmsi.get(digits(mmsi)) if digits(mmsi) else None
