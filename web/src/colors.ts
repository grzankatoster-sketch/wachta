import type { LiveAircraft } from "./api";

export const RED: [number, number, number] = [230, 57, 70];
/**
 * Civil aircraft. Dark enough to be seen on the basemap, light enough to stay background.
 *
 * Was [150,160,170], which scored 1.57:1 against the sea and 2.38:1 against land - under the 3:1
 * that WCAG 1.4.11 asks of a graphic carrying meaning, and in practice the civil traffic simply
 * disappeared over water, which is most of this map. Measured with contrastRatio() below:
 * land 5.15:1, sea 3.39:1, and 3.30:1 on the dark legend panel, so one value works on all three
 * and the legend still speaks the same colour as the map.
 */
export const GREY: [number, number, number] = [96, 103, 110];

/** Land fill of the OpenFreeMap "positron" basemap, sampled from a rendered tile. */
export const BASEMAP_LAND: [number, number, number] = [242, 243, 240];

/** Water fill of the same basemap - the darkest surface a label can land on. */
export const BASEMAP_SEA: [number, number, number] = [194, 200, 202];

/** Callsign labels. Near-black, because they sit on the light positron basemap, not on the dark UI chrome. */
export const LABEL: [number, number, number] = [17, 24, 33];

const channel = (c: number) => {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
};

/** WCAG 2.1 relative luminance, 0 (black) to 1 (white). */
export function luminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG 2.1 contrast ratio, 1 (identical) to 21 (black on white). */
export function contrastRatio(a: [number, number, number], b: [number, number, number]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Ships, in a cool family so that the sea does not borrow the air's colours.
 *
 * Two classes, not six. AIS knows two dozen ship types and naming them all on a legend would cost
 * the reader more than it tells: the split that matters here is the one the detectors care about -
 * hulls that carry something (cargo 70-79, tanker 80-89) against everything else, the tugs, pilots,
 * ferries and fishing boats that make up most of the traffic and most of the false alarms.
 *
 * Measured against the positron basemap: cargo 6.53:1 on land and 4.30:1 on water, other vessels
 * 5.71:1 and 3.76:1, both clear of the 3:1 WCAG asks of a meaningful graphic. They differ in hue
 * rather than lightness, because on a light basemap every mark has to be dark and there is no room
 * left to separate them by brightness - so size carries the same split a second time: cargo draws
 * larger. The exact type is named in words in the detail panel, where it cannot be misread at all.
 */
export const SHIP_CARGO: [number, number, number] = [11, 94, 120];
export const SHIP_OTHER: [number, number, number] = [70, 98, 125];

/** AIS type codes 70-89 carry freight; the rest work the port or fish. Unknown counts as "other". */
export function isCargo(shipType: string | null | undefined): boolean {
  const n = Number(shipType);
  return Number.isFinite(n) && n >= 70 && n <= 89;
}

export function shipColor(shipType: string | null | undefined): [number, number, number] {
  return isCargo(shipType) ? SHIP_CARGO : SHIP_OTHER;
}

export function aircraftColor(a: LiveAircraft): [number, number, number] {
  return a.isMilitary ? RED : GREY;
}

/** gpsjam.org thresholds: < 2% low (transparent), 2–10% medium (amber), >= 10% high (red). */
export function jammingColor(pct: number): [number, number, number, number] {
  if (pct >= 0.1) return [230, 57, 70, 150];
  if (pct >= 0.02) return [255, 190, 0, 110];
  return [0, 0, 0, 0];
}
