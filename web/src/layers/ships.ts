import { ScatterplotLayer, LineLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveShip } from "../api";
import { LABEL, isCargo, shipColor } from "../colors";

/**
 * Ships, drawn as a hull and the course it is making.
 *
 * The course line is not decoration and it is not a fixed arrow: it is where the ship will be in
 * two minutes if it holds speed and heading. So a line's LENGTH is its speed, read straight off the
 * map without a legend, and a ship at anchor has no line at all - which is the honest picture,
 * because a ship at anchor is not going anywhere and should not look like it is.
 *
 * That also answers what a static map could not: at a glance you can see which way the traffic in a
 * strait is running, and which hull is sitting still in the middle of it. Two hulls alongside with
 * no lines is what D5 calls a rendezvous, and now it looks like one.
 */

/** Below this a vessel is manoeuvring or moored, not making way, and gets no course line. */
const MIN_W_RUCHU_KT = 0.5;

/**
 * How far ahead the line reaches: half an hour.
 *
 * Aircraft use two minutes, and copying that here was the first attempt and a mistake: a 12-knot
 * ship covers 0.7 km in two minutes, which at the zoom this map opens on is less than one pixel.
 * Every ship had a course line and not one of them was visible. Half an hour puts the same ship
 * 11 km ahead - long enough to read a direction, short enough that a strait full of traffic does
 * not turn into a thicket. The unit is stated on the legend, because a projection whose horizon
 * the reader cannot see is a line that means nothing in particular.
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

export function shipLayers(data: LiveShip[]): Layer[] {
  const plynace = data.filter(wRuchu);

  return [
    new LineLayer<LiveShip>({
      id: "ship-course",
      data: plynace,
      getSourcePosition: (s) => [s.lon, s.lat],
      getTargetPosition: przedDziobem,
      getColor: (s) => [...shipColor(s.shipType), 150] as [number, number, number, number],
      getWidth: 1.4,
      widthUnits: "pixels",
      // Pozycje przychodza co kilka sekund skokowo. Bez przejscia mapa "mruga" i wyglada na
      // odswiezany obrazek; z przejsciem statki plyna, czyli wyglada na to, czym jest.
      transitions: { getSourcePosition: 900, getTargetPosition: 900 },
    }),
    new ScatterplotLayer<LiveShip>({
      id: "ships",
      data,
      getPosition: (s) => [s.lon, s.lat],
      getFillColor: (s) => shipColor(s.shipType),
      // Rozmiar powtarza podzial, ktory kolor niesie odcieniem: ladunek wiekszy. Na jasnym
      // podkladzie kazdy znacznik musi byc ciemny, wiec jasnoscia tych dwoch klas nie rozdziele.
      getRadius: (s) => (isCargo(s.shipType) ? 4 : 2.6),
      radiusUnits: "pixels",
      stroked: true,
      getLineColor: LABEL,
      lineWidthMinPixels: 0.8,
      pickable: true,
      transitions: { getPosition: 900 },
    }),
  ];
}
