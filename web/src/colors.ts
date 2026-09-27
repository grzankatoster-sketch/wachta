import type { LiveAircraft } from "./api";

export const RED: [number, number, number] = [230, 57, 70];
export const GREY: [number, number, number] = [150, 160, 170];

export function aircraftColor(a: LiveAircraft): [number, number, number] {
  return a.isMilitary ? RED : GREY;
}

/** gpsjam.org thresholds: < 2% low (transparent), 2–10% medium (amber), >= 10% high (red). */
export function jammingColor(pct: number): [number, number, number, number] {
  if (pct >= 0.1) return [230, 57, 70, 150];
  if (pct >= 0.02) return [255, 190, 0, 110];
  return [0, 0, 0, 0];
}
