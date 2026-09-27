"""Feasibility probe for WACHTA: hits keyless data sources and reports what actually comes back."""
import json, time, statistics, collections, sys
import requests

sys.stdout.reconfigure(encoding="utf-8")
H = {"User-Agent": "wachta-feasibility-probe/0.1 (portfolio research)"}
BALTIC = dict(lat_min=53.5, lat_max=66.0, lon_min=9.0, lon_max=30.5)


def get(url, **kw):
    t = time.time()
    r = requests.get(url, headers=H, timeout=40, **kw)
    return r, round(time.time() - t, 2)


def in_baltic(lat, lon):
    return BALTIC["lat_min"] <= lat <= BALTIC["lat_max"] and BALTIC["lon_min"] <= lon <= BALTIC["lon_max"]


print("=== 1. adsb.lol /v2/mil (samoloty wojskowe, swiat) ===")
try:
    r, dt = get("https://api.adsb.lol/v2/mil")
    print("HTTP", r.status_code, "czas", dt, "s, rozmiar", len(r.content) // 1024, "KB")
    ac = r.json().get("ac", [])
    print("samolotow wojskowych na swiecie:", len(ac))
    types = collections.Counter(a.get("t", "?") for a in ac)
    print("najczestsze typy:", types.most_common(12))
    tankers = [a for a in ac if a.get("t") in ("K35R", "K35E", "KC46", "A332", "A330", "MRTT", "K46", "KC2", "A310", "KC10", "K767")]
    print("potencjalne tankowce (po typie):", [(a.get("flight", "").strip(), a.get("t"), a.get("lat"), a.get("lon")) for a in tankers][:10])
    bal = [a for a in ac if a.get("lat") is not None and in_baltic(a["lat"], a["lon"])]
    print("wojskowe nad Baltykiem teraz:", len(bal), [(a.get("flight", "").strip(), a.get("t")) for a in bal][:15])
    keys = collections.Counter(k for a in ac for k in a.keys())
    print("pola dostepne (czestosc):", {k: keys[k] for k in ("nic", "nac_p", "sil", "gva", "mlat", "tisb", "seen_pos", "alt_baro", "gs", "track") if k in keys})
except Exception as e:
    print("BLAD", e)

print("\n=== 2. adsb.lol punkt+promien: caly ruch nad Baltykiem (NIC/NACp do GPS jamming) ===")
try:
    # Gdansk area, 250 NM radius covers south Baltic + Kaliningrad
    r, dt = get("https://api.adsb.lol/v2/point/55.0/20.0/250")
    ac = r.json().get("ac", [])
    print("HTTP", r.status_code, "czas", dt, "s, samolotow:", len(ac))
    with_nacp = [a for a in ac if "nac_p" in a and a.get("alt_baro") not in (None, "ground")]
    low = [a for a in with_nacp if a["nac_p"] < 8]
    print("z polem nac_p (w powietrzu):", len(with_nacp), "| z nac_p<8 (slaba dokladnosc GPS):", len(low),
          f"({100*len(low)/max(1,len(with_nacp)):.0f}%)")
    if low:
        lat = statistics.mean(a["lat"] for a in low); lon = statistics.mean(a["lon"] for a in low)
        print(f"srodek ciezkosci slabego GPS: {lat:.2f}N {lon:.2f}E (Kaliningrad ~54.7N 20.5E)")
    json.dump(ac, open("adsb_baltic_snapshot.json", "w"), indent=0)
except Exception as e:
    print("BLAD", e)

print("\n=== 3. airplanes.live /v2/mil (zapasowe) ===")
try:
    r, dt = get("https://api.airplanes.live/v2/mil")
    print("HTTP", r.status_code, "czas", dt, "s, samolotow:", len(r.json().get("ac", [])))
except Exception as e:
    print("BLAD", e)

print("\n=== 4. Digitraffic AIS (Baltyk, bez klucza) ===")
try:
    r, dt = get("https://meri.digitraffic.fi/api/ais/v1/locations", headers={**H, "Accept-Encoding": "gzip", "Digitraffic-User": "wachta-probe"})
    feats = r.json().get("features", [])
    print("HTTP", r.status_code, "czas", dt, "s, pozycji statkow:", len(feats))
    now = time.time() * 1000
    ages = [(now - f["properties"]["timestampExternal"]) / 60000 for f in feats if "timestampExternal" in f["properties"]]
    if ages:
        print(f"swiezosc pozycji: mediana {statistics.median(ages):.1f} min, <10 min: {sum(a<10 for a in ages)}")
    lons = [f["geometry"]["coordinates"][0] for f in feats]; lats = [f["geometry"]["coordinates"][1] for f in feats]
    print(f"zasieg: lat {min(lats):.1f}-{max(lats):.1f}, lon {min(lons):.1f}-{max(lons):.1f}")
    south = sum(1 for la in lats if la < 57)
    print("statkow na poludnie od 57N (Baltyk poludniowy/PL):", south)
    r2, dt2 = get("https://meri.digitraffic.fi/api/ais/v1/vessels", headers={**H, "Digitraffic-User": "wachta-probe"})
    ves = r2.json()
    tank = [v for v in ves if 80 <= (v.get("shipType") or 0) <= 89]
    print("metadane statkow:", len(ves), "| tankowce (typ 80-89):", len(tank), "| pola:", list(ves[0].keys())[:12])
except Exception as e:
    print("BLAD", e)

print("\n=== 5. OpenSanctions: statki (dataset) ===")
try:
    r, dt = get("https://data.opensanctions.org/datasets/latest/index.json")
    ds = r.json().get("datasets", [])
    names = [d["name"] for d in ds]
    for n in ("sanctions", "ext_ua_war_sanctions", "ua_war_sanctions", "eu_fsf", "maritime"):
        print(" ", n, "->", "JEST" if n in names else "brak")
    mar = [n for n in names if "vessel" in n or "maritime" in n or "ship" in n]
    print("  zbiory morskie:", mar[:10])
except Exception as e:
    print("BLAD", e)

print("\n=== 6. EMODnet Human Activities (kable/rurociagi, WFS) ===")
try:
    r, dt = get("https://ows.emodnet-humanactivities.eu/wfs", params={"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"})
    txt = r.text
    import re
    layers = sorted(set(re.findall(r"<Name>([^<]*(?:cable|pipeline|Cable|Pipeline)[^<]*)</Name>", txt)))
    print("HTTP", r.status_code, "czas", dt, "s, warstwy kabli/rurociagow:", layers[:12])
except Exception as e:
    print("BLAD", e)

print("\n=== 7. GDELT DOC API (newsy) ===")
try:
    r, dt = get("https://api.gdeltproject.org/api/v2/doc/doc", params={"query": "Baltic cable", "mode": "artlist", "maxrecords": 10, "format": "json", "timespan": "7d"})
    arts = r.json().get("articles", []) if r.headers.get("content-type", "").startswith("application/json") else []
    print("HTTP", r.status_code, "czas", dt, "s, artykulow:", len(arts), [a.get("sourcecountry") for a in arts][:10])
except Exception as e:
    print("BLAD", e)
import json, time, statistics, sys, re
import requests

sys.stdout.reconfigure(encoding="utf-8")
H = {"User-Agent": "Mozilla/5.0 wachta-feasibility-probe/0.1", "Digitraffic-User": "wachta-probe", "Accept-Encoding": "gzip"}

def get(url, **kw):
    t = time.time(); r = requests.get(url, headers=H, timeout=60, **kw); return r, round(time.time() - t, 2)

print("=== 4. Digitraffic AIS ===")
try:
    r, dt = get("https://meri.digitraffic.fi/api/ais/v1/locations")
    feats = r.json().get("features", [])
    print("HTTP", r.status_code, "czas", dt, "s, pozycji:", len(feats))
    now = time.time() * 1000
    ages = [(now - f["properties"]["timestampExternal"]) / 60000 for f in feats]
    print(f"swiezosc: mediana {statistics.median(ages):.1f} min; <10 min: {sum(a < 10 for a in ages)}")
    lats = [f["geometry"]["coordinates"][1] for f in feats]; lons = [f["geometry"]["coordinates"][0] for f in feats]
    print(f"zasieg lat {min(lats):.1f}-{max(lats):.1f}, lon {min(lons):.1f}-{max(lons):.1f}; na pld od 57N: {sum(l < 57 for l in lats)}")
    print("pola pozycji:", list(feats[0]["properties"].keys()))
    r2, _ = get("https://meri.digitraffic.fi/api/ais/v1/vessels")
    ves = r2.json()
    tank = [v for v in ves if 80 <= (v.get("shipType") or 0) <= 89]
    print("metadane:", len(ves), "| tankowce:", len(tank), "| pola:", list(ves[0].keys()))
except Exception as e:
    print("BLAD", repr(e))

print("\n=== 3b. airplanes.live z innym UA ===")
try:
    r, dt = get("https://api.airplanes.live/v2/mil")
    print("HTTP", r.status_code, r.text[:120].replace("\n", " "))
except Exception as e:
    print("BLAD", repr(e))

print("\n=== 8. Tor lotu tankowca (adsb.lol trace) ===")
try:
    mil = requests.get("https://api.adsb.lol/v2/mil", headers=H, timeout=30).json()["ac"]
    tk = [a for a in mil if a.get("t") in ("K35R", "A332", "KC46", "K46") and a.get("lat")]
    for a in tk[:4]:
        hx = a["hex"]
        for url in (f"https://adsb.lol/data/traces/{hx[-2:]}/trace_full_{hx}.json",
                    f"https://globe.adsb.lol/data/traces/{hx[-2:]}/trace_full_{hx}.json"):
            r = requests.get(url, headers={**H, "Referer": "https://adsb.lol/"}, timeout=30)
            if r.status_code == 200:
                tr = r.json().get("trace", [])
                # trace rows: [sec_offset, lat, lon, alt, gs, track, ...]
                tracks = [p[5] for p in tr if len(p) > 5 and p[5] is not None]
                turns = sum(1 for i in range(1, len(tracks)) if abs(((tracks[i] - tracks[i-1] + 180) % 360) - 180) > 30)
                print(f"{a.get('flight','').strip() or hx} {a['t']}: {len(tr)} punktow, ostrych zmian kursu: {turns}, url ok")
                break
        else:
            print(hx, "trace niedostepny (HTTP", r.status_code, ")")
except Exception as e:
    print("BLAD", repr(e))

print("\n=== 6b. EMODnet: kable/rurociagi w Zatoce Finskiej (Estlink) ===")
bbox = "59.0,22.0,60.6,27.0"  # lat/lon order for WFS 2.0 EPSG:4326
for layer in ("emodnet:sigcables", "emodnet:pipelines", "emodnet:pcablesbshcontis", "emodnet:bshcontiscables"):
    try:
        r, dt = get("https://ows.emodnet-humanactivities.eu/wfs", params={"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                    "typeNames": layer, "bbox": bbox + ",urn:ogc:def:crs:EPSG::4326", "outputFormat": "application/json", "count": 200})
        js = r.json(); fs = js.get("features", [])
        names = sorted({str((f.get("properties") or {}).get("name") or (f.get("properties") or {}).get("NAME") or "")[:30] for f in fs})
        print(layer, "HTTP", r.status_code, "obiektow:", len(fs), names[:8])
    except Exception as e:
        print(layer, "BLAD", repr(e)[:150])

print("\n=== 7b. GDELT po przerwie ===")
time.sleep(6)
try:
    r, dt = get("https://api.gdeltproject.org/api/v2/doc/doc", params={"query": "Baltic cable", "mode": "artlist", "maxrecords": 10, "format": "json", "timespan": "7d"})
    print("HTTP", r.status_code, "czas", dt)
    if r.status_code == 200:
        arts = r.json().get("articles", []); print("artykulow:", len(arts), [(a.get("sourcecountry"), a.get("language")) for a in arts][:8])
except Exception as e:
    print("BLAD", repr(e))
