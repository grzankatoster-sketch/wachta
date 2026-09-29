/**
 * Moving the marks between fixes, so the map runs instead of twitching.
 *
 * Measured on ten live minutes: a new position for the same aircraft arrives every 60 s (median,
 * 138 s at the 90th percentile) and for the same ship every 140 s (200 s at the 90th). The hub
 * pushes every 5 s, but the CONTENT only changes when a fix lands. So an aircraft at 450 knots sits
 * perfectly still for a minute and then moves 14 km at once - and easing that over 900 ms turned a
 * jump into a twitch, which reads worse than the jump did.
 *
 * Between fixes the mark is advanced along its own reported course and speed. This is dead
 * reckoning, the same arithmetic the course line already draws, and it is what every traffic display
 * does; the position shown is computed, and the detail panel says so along with the age of the last
 * real fix.
 *
 * The cap is the part that matters. A vessel that stops reporting must STOP on the screen, because a
 * ship that keeps sailing on dead reckoning after going silent would paint over the exact event this
 * project exists to catch - D4 calls that "statek zamilkł w ruchu", and a map that quietly sails it
 * onwards is worse than a map that never moved. Past the cap the mark freezes where it was last
 * heard and fades, which is the honest picture: this is where it was, and we have stopped knowing.
 *
 * The caps come from the measurements above - each covers its 90th percentile with a little room, so
 * ordinary gaps are smoothed and unusual ones are shown as what they are.
 */

const KM_NA_MILE_MORSKA = 1.852;
const KM_NA_STOPIEN_SZER = 111.32;

/** Aircraft: 90th percentile gap is 138 s. */
export const LIMIT_SAMOLOT_S = 150;

/** Ships: 90th percentile gap is 200 s. */
export const LIMIT_STATEK_S = 240;

export interface Ruch {
  lon: number;
  lat: number;
  /** Seconds since the last real fix, never negative. */
  wiek: number;
  /** True once the fix is older than the cap: the mark has stopped and is fading. */
  przestarzale: boolean;
  /** 0..1, how much of the cap has been used - drives the fade. */
  zuzycie: number;
}

/** Dead reckoning: where something reported at (lat, lon) doing sog on cog is after `sekundy`. */
export function zliczonaPozycja(
  lat: number,
  lon: number,
  wezly: number | null | undefined,
  kursStopnie: number | null | undefined,
  sekundy: number,
): [number, number] {
  const sog = wezly ?? 0;
  if (!Number.isFinite(sog) || sog <= 0 || kursStopnie === null || kursStopnie === undefined
      || !Number.isFinite(kursStopnie) || !Number.isFinite(sekundy) || sekundy <= 0) {
    return [lon, lat];
  }

  const km = (sog * KM_NA_MILE_MORSKA * sekundy) / 3600;
  const kurs = (kursStopnie * Math.PI) / 180;
  const cosSzer = Math.cos((lat * Math.PI) / 180);
  return [
    lon + (km / (KM_NA_STOPIEN_SZER * (Math.abs(cosSzer) < 1e-6 ? 1e-6 : cosSzer))) * Math.sin(kurs),
    lat + (km / KM_NA_STOPIEN_SZER) * Math.cos(kurs),
  ];
}

/**
 * Where to draw something now, given when it was last heard.
 *
 * `wiekSekund` is worked out on the DATA clock, not the browser's - see zegarDanych below. A laptop
 * five minutes fast would otherwise mark every aircraft in the sky as stale and freeze the whole
 * map, which is a spectacular way to fail at "is this live".
 */
export function ruch(
  lat: number,
  lon: number,
  wezly: number | null | undefined,
  kurs: number | null | undefined,
  wiekSekund: number,
  limitS: number,
): Ruch {
  const wiek = Math.max(0, wiekSekund);
  const przestarzale = wiek > limitS;
  const uzyte = Math.min(wiek, limitS);
  const [lonTeraz, latTeraz] = zliczonaPozycja(lat, lon, wezly, kurs, uzyte);
  return { lon: lonTeraz, lat: latTeraz, wiek, przestarzale, zuzycie: limitS > 0 ? uzyte / limitS : 1 };
}

/**
 * The clock the ages are measured against.
 *
 * Taking `Date.now() - fix.ts` trusts two clocks to agree - the server's and the viewer's - and they
 * do not have to. Instead: the newest timestamp in a batch is treated as the moment that batch
 * describes, and real time is added on top from when the batch actually arrived. Any constant
 * offset between the two machines cancels out, and what is left is elapsed time, which both clocks
 * measure the same way.
 */
export function zegarDanych(najnowszyFixMs: number, odebranoMs: number, terazMs: number): number {
  return najnowszyFixMs + Math.max(0, terazMs - odebranoMs);
}

/** The newest timestamp in a batch, as epoch ms; null for an empty or unparseable batch. */
export function najnowszy(znaczniki: string[]): number | null {
  let max: number | null = null;
  for (const z of znaczniki) {
    const t = Date.parse(z);
    if (Number.isFinite(t) && (max === null || t > max)) max = t;
  }
  return max;
}

/** Opacity for a mark: full while fresh, fading once frozen, never invisible. */
export function przezroczystosc(r: Ruch): number {
  return r.przestarzale ? 90 : 255;
}
