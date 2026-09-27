from pathlib import Path

from wachta_detectors.airports import load_airports, nearest_airport_km

CSV = """id,ident,type,name,latitude_deg,longitude_deg
1,EPGD,large_airport,Gdansk,54.3776,18.4662
2,XHEL,heliport,Some heliport,54.0,18.0
3,EPOK,medium_airport,Oksywie,54.5797,18.5172
"""


def test_loads_only_selected_types(tmp_path: Path):
    f = tmp_path / "airports.csv"
    f.write_text(CSV, encoding="utf-8")
    assert load_airports(f) == [(54.3776, 18.4662), (54.5797, 18.5172)]


def test_nearest_airport_distance():
    airports = [(54.3776, 18.4662)]
    assert nearest_airport_km(airports, 54.3776, 18.4662) < 0.01
    assert 110 < nearest_airport_km(airports, 55.3776, 18.4662) < 112
