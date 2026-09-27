"""Airports from OurAirports (public domain): https://davidmegginson.github.io/ourairports-data/airports.csv"""
import csv
from pathlib import Path

from wachta_detectors.geo import haversine_km

DEFAULT_TYPES = frozenset({"large_airport", "medium_airport", "small_airport"})


def load_airports(csv_path: Path, types: frozenset[str] = DEFAULT_TYPES) -> list[tuple[float, float]]:
    with csv_path.open(encoding="utf-8", newline="") as f:
        return [(float(r["latitude_deg"]), float(r["longitude_deg"])) for r in csv.DictReader(f) if r["type"] in types]


def nearest_airport_km(airports: list[tuple[float, float]], lat: float, lon: float) -> float:
    return min((haversine_km(lat, lon, a_lat, a_lon) for a_lat, a_lon in airports), default=float("inf"))
