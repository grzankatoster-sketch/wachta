from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Position:
    hex: str
    lat: float
    lon: float
    alt_ft: int | None
    on_ground: bool
    nac_p: int | None
    ts: datetime
