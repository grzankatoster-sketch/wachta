import { IconLayer, LineLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveShip } from "../api";
import { KATEGORIE, kategoriaStatku } from "../typy";
import { GRUBOSC_OBWODKI, OBWODKA, ikona, kat } from "./ikony";

/**
 * Ships, drawn as hulls that point where they are going.
 *
 * A vessel making way is a silhouette turned to its course with a line ahead of it; a vessel that is
 * not is a plain dot. That is not decoration. A stopped ship has no meaningful heading - AIS keeps
 * reporting the last course, or zero - so drawing it as an oriented hull would be inventing a fact.
 * The dot says "here, and not going anywhere", which is exactly what the anchor and rendezvous
 * detectors are looking at: two dots side by side in open water is what D5 calls a transfer.
 *
 * The course line reaches where the ship will be in half an hour on its present course and speed, so
 * its LENGTH is speed, readable without a legend.
 */

/** Below this a vessel is manoeuvring or moored, not making way. */
const MIN_W_RUCHU_KT = 0.5;

/**
 * How far ahead the line reaches: half an hour.
 *
 * Aircraft use two minutes, and copying that here was the first attempt and a mistake: a 12-knot
 * ship covers 0.7 km in two minutes, under one pixel at the zoom this map opens on. Every ship had
 * a course line and not one was visible.
 */
const PROJEKCJA_MIN = 30;

const KM_NA_MILE_MORSKA = 1.852;

/** Where a ship will be in PROJEKCJA_MIN if nothing changes. Plain dead reckoning, no smoothing. */
export function przedDziobem(s: LiveShip): [number, number] {
  const wezly = s.sogKt ?? 0;
  const kurs = ((s.cogDeg ?? 0) * Math.PI) / 180;
  const km = (wezly * KM_NA_MILE_MORSKA * PROJEKCJA_MIN) / 60;

  const dLat = (km / 111.32) * Math.cos(kurs);
  const dLon = (km / (111.32 * Math.cos((s.lat * Math.PI) / 180) || 1)) * Math.sin(kurs);
  return [s.lon + dLon, s.lat + dLat];
}

export function wRuchu(s: LiveShip): boolean {
  return (s.sogKt ?? 0) >= MIN_W_RUCHU_KT && s.cogDeg !== null && s.cogDeg !== undefined;
}

const kolor = (s: LiveShip) => KATEGORIE[kategoriaStatku(s)].kolor;
const rozmiar = (s: LiveShip) => KATEGORIE[kategoriaStatku(s)].rozmiar;

export function shipLayers(data: LiveShip[]): Layer[] {
  const plynace = data.filter(wRuchu);
  const stojace = data.filter((s) => !wRuchu(s));
  const przejscie = { getPosition: 900, getSourcePosition: 900, getTargetPosition: 900 };

  return [
    new LineLayer<LiveShip>({
      id: "ship-course",
      data: plynace,
      getSourcePosition: (s) => [s.lon, s.lat],
      getTargetPosition: przedDziobem,
      getColor: (s) => [...kolor(s), 150] as [number, number, number, number],
      getWidth: 1.4,
      widthUnits: "pixels",
      transitions: przejscie,
    }),
    new ScatterplotLayer<LiveShip>({
      id: "ships-stopped",
      data: stojace,
      getPosition: (s) => [s.lon, s.lat],
      getFillColor: kolor,
      getRadius: (s) => rozmiar(s) / 5,
      radiusUnits: "pixels",
      stroked: true,
      getLineColor: OBWODKA,
      lineWidthMinPixels: 0.9,
      pickable: true,
      transitions: przejscie,
    }),
    // Obwodka to ta sama sylwetka narysowana szerzej, pod spodem. Maska nie umie drugiego koloru,
    // a bez obrysu ciemny kadlub na ciemnej wodzie schodzi ponizej progu widocznosci.
    new IconLayer<LiveShip>({
      id: "ships-obwodka",
      data: plynace,
      getPosition: (s) => [s.lon, s.lat],
      getIcon: (s) => ikona(KATEGORIE[kategoriaStatku(s)].ksztalt),
      getSize: (s) => rozmiar(s) + GRUBOSC_OBWODKI,
      getAngle: (s) => kat(s.cogDeg),
      getColor: OBWODKA,
      sizeUnits: "pixels",
      transitions: przejscie,
    }),
    new IconLayer<LiveShip>({
      id: "ships",
      data: plynace,
      getPosition: (s) => [s.lon, s.lat],
      getIcon: (s) => ikona(KATEGORIE[kategoriaStatku(s)].ksztalt),
      getSize: rozmiar,
      getAngle: (s) => kat(s.cogDeg),
      getColor: kolor,
      sizeUnits: "pixels",
      pickable: true,
      transitions: przejscie,
    }),
  ];
}
