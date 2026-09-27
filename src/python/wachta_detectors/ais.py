"""Small AIS field decoders.

AIS packs some fields into integers to save bits on the radio. The estimated time of arrival is one
of them: month, day, hour and minute squeezed into twenty bits, with no year at all. Both the ETA and
the destination are typed in by the crew, so they say what the ship declares, not what it will do.
"""
from dataclasses import dataclass

ETA_NOT_AVAILABLE = (0, 0, 24, 60)   # AIS: "brak danych" dla kolejno miesiaca, dnia, godziny, minuty


@dataclass(frozen=True)
class Eta:
    month: int
    day: int
    hour: int
    minute: int

    def __str__(self) -> str:
        return f"{self.day:02d}.{self.month:02d}, {self.hour:02d}:{self.minute:02d} UTC"


def decode_eta(packed: object) -> Eta | None:
    """Unpacks the AIS ETA integer. Returns None when the ship says nothing or the value is nonsense.

    Layout, from the least significant bit: minute (6 b), hour (5 b), day (5 b), month (4 b).
    """
    if packed is None:
        return None
    try:
        value = int(packed)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None

    minute = value & 0x3F
    hour = (value >> 6) & 0x1F
    day = (value >> 11) & 0x1F
    month = (value >> 16) & 0x0F

    if (month, day, hour, minute) == ETA_NOT_AVAILABLE or month == 0 or day == 0:
        return None
    if month > 12 or day > 31 or hour > 23 or minute > 59:
        return None
    return Eta(month=month, day=day, hour=hour, minute=minute)
