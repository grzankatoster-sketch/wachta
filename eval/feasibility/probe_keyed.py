"""Checks keyed sources using values from .env. Prints status only, never the keys."""
import os
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
env = dict(l.split("=", 1) for l in Path(".env").read_text().splitlines() if "=" in l and not l.startswith("#"))


def report(name, ok, detail):
    print(f"{'OK ' if ok else 'ERR'} {name}: {detail}")


def opensky():
    tok = requests.post(
        "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
        data={"grant_type": "client_credentials", "client_id": env["OPENSKY_CLIENT_ID"], "client_secret": env["OPENSKY_CLIENT_SECRET"]},
        timeout=30,
    )
    if not tok.ok:
        return report("OpenSky token", False, tok.status_code)
    r = requests.get("https://opensky-network.org/api/states/all", params={"lamin": 53.5, "lomin": 9, "lamax": 60, "lomax": 30},
                     headers={"Authorization": f"Bearer {tok.json()['access_token']}"}, timeout=30)
    report("OpenSky states", r.ok, f"HTTP {r.status_code}, {len((r.json() or {}).get('states') or []) if r.ok else 0} aircraft")


def firms():
    r = requests.get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{env['FIRMS_MAP_KEY']}/VIIRS_SNPP_NRT/22,44,40,53/1", timeout=60)
    report("NASA FIRMS", r.ok and not r.text.startswith("Invalid"), f"HTTP {r.status_code}, {max(0, r.text.count(chr(10)) - 1)} hotspots (Ukraine bbox, 1 day)")


def gfw():
    r = requests.get("https://gateway.api.globalfishingwatch.org/v3/vessels/search",
                     params={"query": "EAGLE S", "datasets[0]": "public-global-vessel-identity:latest"},
                     headers={"Authorization": f"Bearer {env['GFW_TOKEN']}"}, timeout=60)
    report("GFW vessels", r.ok, f"HTTP {r.status_code}")


def aisstream():
    import asyncio
    import json

    import websockets

    async def run():
        async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
            await ws.send(json.dumps({"APIKey": env["AISSTREAM_API_KEY"], "BoundingBoxes": [[[53.5, 9.0], [57.0, 22.0]]]}))
            n, t = 0, time.time()
            while time.time() - t < 20:
                await asyncio.wait_for(ws.recv(), timeout=20)
                n += 1
            return n

    n = asyncio.run(run())
    report("AISStream (south Baltic, 20 s)", n > 0, f"{n} messages")


for check in (opensky, firms, gfw, aisstream):
    try:
        check()
    except Exception as e:  # probe script: report and continue
        report(check.__name__, False, repr(e)[:120])
