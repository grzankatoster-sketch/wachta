"""Reconnaissance: which AIS sources actually reach the SOUTHERN Baltic.

The map promises 48-70N / 0-40E but the only live AIS source is Digitraffic, whose receivers are
Finnish. This script does not read documentation - it calls every candidate and prints what came
back, because docs/SOURCES.md only accepts measured rows.

  py eval/feasibility/probe_ais_south.py

Probes (all read-only, none needs a paid account):
  digitraffic  - how far south the Finnish network really reaches, right now
  aisstream    - the endpoint is alive and what it answers to a missing/blank key
  kystverket   - Norwegian open AIS TCP stream: reachable, and how far south its hulls are
  dma          - Danish Maritime Authority daily archive: is yesterday's file there, how big
  helcom       - HELCOM AIS: is there anything downloadable without a member-state agreement
"""
import gzip
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")

# Ten sam naglowek co w produkcji: zrodla tego projektu odrzucaly zapytania bez opisowego
# User-Agent (adsb.lol 403, Digitraffic 403), wiec rekonesans klamalby, gdyby go nie wysylal.
UA = "wachta-project/0.1 (situational awareness, non-commercial)"
HEADERS = {"User-Agent": UA, "Digitraffic-User": "wachta/recon", "Accept-Encoding": "gzip"}

# Akweny, ktorych dzisiaj brakuje - kazdy probe raportuje, ile trafien ma w tych prostokatach.
BOXES = {
    "Zatoka Gdanska": (54.0, 55.0, 18.0, 19.8),
    "polskie wybrzeze": (53.9, 55.0, 14.0, 19.8),
    "Kaliningrad": (54.4, 55.4, 19.0, 21.0),
    "ciesniny dunskie": (54.5, 58.0, 9.0, 13.5),
}


def report(name, ok, detail):
    print(f"{'OK ' if ok else 'ERR'} {name}: {detail}")


def _boxes(points):
    return ", ".join(
        f"{n}: {sum(1 for la, lo in points if a <= la <= b and c <= lo <= d)}"
        for n, (a, b, c, d) in BOXES.items()
    )


def _get(url, timeout=90):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    # urllib NIE rozpakowuje gzipa sam - projekt przerabial to na zywym Digitrafficu.
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def digitraffic():
    started = time.time()
    data = json.loads(_get("https://meri.digitraffic.fi/api/ais/v1/locations").decode("utf-8"))
    points = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0])
              for f in data["features"]]
    lats = [la for la, _ in points]
    south = sum(1 for la in lats if la < 57.0)
    report("Digitraffic /locations", True,
           f"{len(points)} statkow w {time.time() - started:.1f} s, "
           f"lat {min(lats):.2f}..{max(lats):.2f}, ponizej 57N: {south} "
           f"({100 * south / len(points):.2f}%); {_boxes(points)}")


def aisstream():
    """Handshake only: is the endpoint alive, and what does it say to a key we do not have.

    No key in .env is the normal state of this repo, and the answer to a blank key is itself the
    measurement - it tells the implementation which failure to expect and translate.
    """
    key = os.environ.get("AISSTREAM_API_KEY", "")
    host, port = "stream.aisstream.io", 443
    try:
        raw = socket.create_connection((host, port), timeout=15)
    except OSError as exc:
        return report("AISStream TCP", False, repr(exc)[:120])
    with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as sock:
        report("AISStream TCP+TLS", True, f"{host}:{port} osiagalny, TLS {sock.version()}")
    if not key:
        return report("AISStream subskrypcja", False,
                      "AISSTREAM_API_KEY pusty - handshake WebSocket pominiety "
                      "(patrz instrukcja w docs/SOURCES.md)")
    report("AISStream subskrypcja", False, "klucz jest w .env - uzyj eval/feasibility/probe_keyed.py")


def kystverket():
    """Norwegian open AIS: raw NMEA over plain TCP, no key (NLOD). Question is only the coverage."""
    try:
        sock = socket.create_connection(("153.44.253.27", 5631), timeout=20)
    except OSError as exc:
        return report("Kystverket 153.44.253.27:5631", False, repr(exc)[:120])
    with sock:
        sock.settimeout(20)
        chunks, started = [], time.time()
        while time.time() - started < 10:
            try:
                piece = sock.recv(65536)
            except socket.timeout:
                break
            if not piece:
                break
            chunks.append(piece)
    text = b"".join(chunks).decode("ascii", "replace")
    lines = [ln for ln in text.splitlines() if ln.startswith("!")]
    report("Kystverket NMEA", bool(lines),
           f"{len(lines)} zdan AIVDM/AIVDO w 10 s, {len(text)} bajtow "
           f"(surowy NMEA - pozycje wymagaja dekodera 6-bitowego, nie ma go w repo)")


def dma():
    """Danish Maritime Authority: daily CSV archive. Historical, so never a live map source."""
    day = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    url = f"http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/{day[:4]}/aisdk-{day}.zip"
    request = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            size = int(response.headers.get("Content-Length", 0))
        report("DMA archiwum dobowe", True,
               f"aisdk-{day}.zip: HTTP 200, {size / 1_048_576:.0f} MB "
               f"(opoznienie ~1-2 doby, wiec material do backtestu, nie do mapy na zywo)")
    except urllib.error.HTTPError as exc:
        report("DMA archiwum dobowe", False, f"aisdk-{day}.zip: HTTP {exc.code}")


def helcom():
    """HELCOM: the AIS itself is member-state data behind an agreement; only products are public."""
    url = ("https://maps.helcom.fi/arcgis/rest/services/MADS/Shipping/MapServer?f=json")
    try:
        data = json.loads(_get(url, timeout=60).decode("utf-8"))
    except Exception as exc:  # recon: zapisz powod i jedz dalej
        return report("HELCOM MADS", False, repr(exc)[:120])
    layers = [layer["name"] for layer in data.get("layers", [])]
    report("HELCOM MADS", True,
           f"{len(layers)} warstw, np. {layers[:3]} - to gestosc ruchu w siatce, "
           f"nie pozycje pojedynczych statkow")


for check in (digitraffic, aisstream, kystverket, dma, helcom):
    try:
        check()
    except Exception as exc:  # skrypt rekonesansowy: raportuj i jedz dalej
        report(check.__name__, False, repr(exc)[:160])
