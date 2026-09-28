import type { LiveAircraft } from "./api";

export const RED: [number, number, number] = [230, 57, 70];
export const GREY: [number, number, number] = [150, 160, 170];

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

export function aircraftColor(a: LiveAircraft): [number, number, number] {
  return a.isMilitary ? RED : GREY;
}

/** gpsjam.org thresholds: < 2% low (transparent), 2–10% medium (amber), >= 10% high (red). */
export function jammingColor(pct: number): [number, number, number, number] {
  if (pct >= 0.1) return [230, 57, 70, 150];
  if (pct >= 0.02) return [255, 190, 0, 110];
  return [0, 0, 0, 0];
}
