import type { AlertEvidence } from "./api";

/**
 * Turning one alert into two lines a person can read.
 *
 * The evidence column is free-form jsonb and every detector writes its own shape: D1 describes an
 * aircraft (flight, type_code, gap_minutes), D4 and D6 describe a ship (name, mmsi, duration_minutes,
 * shift_km, min_distance_km). The panel was written when only D1 existed and read D1's keys from all
 * of them, so the first live maritime alerts showed up as a bare MMSI and "luka ? min" - the data was
 * there, the reader just could not see it.
 *
 * Unknown detectors are not a failure case. A new one appears in the database before anyone updates
 * this file, and it has to render as something honest rather than as a row of question marks.
 */

export const NAZWY: Record<string, string> = {
  D1: "Zgaszony transponder",
  D2: "Samolot na dyżurze",
  D3: "Zakłócenia GPS",
  D4: "Statek zamilkł w ruchu",
  D5: "Przeładunek burta w burtę",
  D6: "Podejrzenie wleczenia kotwicy",
  D7: "Jeden numer, dwa kadłuby",
  D8: "Nietypowe skupisko doniesień",
};

/** What the alert is about: a callsign, a ship's name, or - failing both - its bare identifier. */
export function podmiot(ev: AlertEvidence, entityId: string): string {
  const nazwa = ev.flight ?? ev.name;
  if (typeof nazwa === "string" && nazwa.trim()) return nazwa.trim();
  return entityId;
}

/** The short qualifier after the subject: aircraft type, or a ship's number when the name is shown. */
export function dopisek(ev: AlertEvidence): string {
  if (typeof ev.type_code === "string" && ev.type_code.trim()) return ev.type_code.trim();
  if (typeof ev.name === "string" && ev.name.trim() && ev.mmsi) return String(ev.mmsi);
  return "";
}

function liczba(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * The facts worth putting on the second line, in the detector's own terms.
 *
 * Only what is actually present is shown. A missing field is left out rather than printed as "?",
 * because a question mark reads as "the detector does not know", when the truth is usually that this
 * detector never measured that thing at all.
 */
export function szczegoly(ev: AlertEvidence): string[] {
  const out: string[] = [];
  const minuty = liczba(ev.gap_minutes) ?? liczba(ev.duration_minutes);
  if (minuty !== null) out.push(`${Math.round(minuty)} min`);

  const km = liczba(ev.shift_km);
  if (km !== null) out.push(`${km.toFixed(1)} km dalej`);

  const doLinii = liczba(ev.min_distance_km);
  if (doLinii !== null) out.push(`${doLinii.toFixed(1)} km od linii`);

  const linia = ev.line_name;
  if (typeof linia === "string" && linia.trim()) out.push(linia.trim());

  const swiadkowie = liczba(ev.listeners);
  if (swiadkowie !== null) out.push(`${swiadkowie} świadków`);

  const wezly = liczba(ev.implied_kt);
  if (wezly !== null) out.push(`${wezly.toFixed(1)} w.`);

  return out;
}
