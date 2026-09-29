import type { ShipTrackPoint } from "./api";

/**
 * Where a ship has been, read out of `/api/ships/{mmsi}/track`.
 *
 * The map already draws where a vessel is GOING - the line ahead of the bow reaches where it will be
 * in half an hour. That line is a guess. This file is the other half of the question, the one a
 * reader actually asks when a hull catches their eye: where did it come from. That half is not a
 * guess, it is measurement, and it is the only thing on this map that is.
 *
 * The one decision that matters here is what to do with a hole in the data. AIS goes quiet for all
 * sorts of reasons and a polyline joins its vertices whatever happened between them, so a track
 * drawn naively turns a silence into a confident straight line across water nobody watched. That is
 * the exact event detector D4 exists to find - "statek zamilkl w ruchu" - so this file refuses to
 * bridge it: a gap stays a gap on screen, with both of its ends marked, and gets named in words.
 *
 * All thresholds below come from a measurement over 882 live tracks (49 813 intervals) pulled from
 * the running stack on 2026-09-29; the numbers are quoted where each one is set.
 */

/**
 * What counts as a break in transmission rather than the normal cadence.
 *
 * Measured over 49 813 intervals between consecutive fixes: median 150.1 s (that is the ingest poll
 * period - a ship is either in a poll or it is not), p90 214.1 s, p95 356.2 s, p99 598.6 s. 600 s is
 * four poll periods and sits past the 99th percentile: only 0.99% of intervals exceed it and it
 * shows up on 203 of 881 ships (23%), rare enough that seeing one means something. The obvious
 * alternative, 300 s, fires on 63% of ships and would therefore mean nothing.
 *
 * What a bridging line would be inventing, measured on the same data: over a gap longer than 600 s a
 * moving ship's endpoints are a median 3.3 km apart (p90 5.6 km, max 9.9 km in the 600-900 s bucket).
 *
 * It also sits well under D4's 45-minute floor, so every alert that detector raises is visible here
 * as a hole before anyone reads the alert list.
 */
export const PROG_PRZERWY_S = 600;

/**
 * A stop worth marking, in seconds below MIN_W_RUCHU_KT.
 *
 * Histogram of 724 slow runs found inside otherwise moving tracks: 248 end within 2.5 min and 98
 * more within 5 min, then the curve flattens to roughly 20-45 runs per 2.5-minute bin all the way
 * out past 90 min. Two populations - short dips while manoeuvring, and actual stops. 600 s (the same
 * four poll periods as the gap rule, so one measured number does both jobs) keeps 296 of the 724 and
 * puts a marker on 184 of 882 ships (21%).
 */
export const PROG_POSTOJU_S = 600;

/** Same floor the ship marks use (layers/ships.ts): below it a hull is manoeuvring or moored. */
export const MIN_W_RUCHU_KT = 0.5;

/**
 * Below this the track is a dot, not a route.
 *
 * Per-track maximum distance from the oldest fix is sharply bimodal: 496 of 881 tracks (56%) stay
 * inside 50 m and 542 (62%) inside 100 m, then 20 tracks land in 0.1-0.2 km, 18 in 0.2-0.5 km, and
 * the rest run out to 111 km. 0.2 km is the floor of that valley, so the classification barely moves
 * if the threshold does.
 */
export const PROG_STOI_KM = 0.2;

/** The window the panel asks the API for. The endpoint clamps to 1-24 h. */
export const OKNO_H = 6;

const R_KM = 6371.0088;
const rad = (d: number) => (d * Math.PI) / 180;

export function kmMiedzy(a: PunktSladu, b: PunktSladu): number {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Compass bearing from a to b, 0-360. */
export function namiar(a: PunktSladu, b: PunktSladu): number {
  const dLon = rad(b.lon - a.lon);
  const y = Math.sin(dLon) * Math.cos(rad(b.lat));
  const x =
    Math.cos(rad(a.lat)) * Math.sin(rad(b.lat)) -
    Math.sin(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

const ROZA = ["północy", "północnego wschodu", "wschodu", "południowego wschodu",
              "południa", "południowego zachodu", "zachodu", "północnego zachodu"];

/** A bearing said the way a person says it, in the genitive: "z południowego zachodu". */
export function stronaSwiata(deg: number): string {
  return ROZA[Math.round((((deg % 360) + 360) % 360) / 45) % 8];
}

/** Durations in words. "2 h 24 min", "36 min", "45 s" - never a raw number of seconds. */
export function czasSlownie(sekundy: number): string {
  const s = Math.max(0, Math.round(sekundy));
  if (s < 60) return `${s} s`;
  const minuty = Math.round(s / 60);
  if (minuty < 60) return `${minuty} min`;
  const h = Math.floor(minuty / 60);
  const reszta = minuty % 60;
  return reszta === 0 ? `${h} h` : `${h} h ${reszta} min`;
}

/** Distances in words. Under a kilometre a decimal point is noise, over it two digits are. */
export function kmSlownie(km: number): string {
  if (km < 1) return `${Math.round(km * 1000)} m`;
  if (km < 10) return `${km.toFixed(1).replace(".", ",")} km`;
  return `${Math.round(km)} km`;
}

export interface PunktSladu {
  lat: number;
  lon: number;
  /** Epoch ms, so arithmetic on it never goes through a string. */
  ts: number;
  sogKt: number | null;
}

/** A run of fixes with no break longer than PROG_PRZERWY_S: one continuous piece of line. */
export interface OdcinekSladu {
  punkty: PunktSladu[];
}

export interface PrzerwaSladu {
  /** Last fix heard before the silence. */
  od: PunktSladu;
  /** First fix heard after it. */
  do_: PunktSladu;
  sekundy: number;
  /** Straight-line distance between the two ends - the water nobody watched. */
  km: number;
}

export interface PostojSladu {
  punkt: PunktSladu;
  sekundy: number;
}

export interface Slad {
  mmsi: string;
  punkty: PunktSladu[];
  odcinki: OdcinekSladu[];
  przerwy: PrzerwaSladu[];
  postoje: PostojSladu[];
  poczatek: PunktSladu | null;
  koniec: PunktSladu | null;
  /** Distance along the observed pieces only. Gaps are NOT counted: we did not see them. */
  przebytaKm: number;
  /** Oldest fix to newest, straight line. */
  wLiniiKm: number;
  sekundy: number;
  /** Bearing from the newest position back to the oldest: where it came FROM. */
  zNamiaru: number | null;
  /** The whole window fits inside PROG_STOI_KM: this hull did not go anywhere. */
  nieruchomy: boolean;
}

export type StanSladu =
  | { stan: "nic" }
  | { stan: "ladowanie"; mmsi: string }
  | { stan: "gotowy"; slad: Slad }
  | { stan: "blad"; powod: string };

function poprawny(p: ShipTrackPoint): boolean {
  const t = Date.parse(p.ts);
  return Number.isFinite(p.lat) && Number.isFinite(p.lon) && Number.isFinite(t)
    && Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180;
}

/**
 * Turns the endpoint's rows into everything the map and the panel need.
 *
 * Rows that cannot be a position are dropped rather than drawn: the SQL orders by ts, but a NaN
 * latitude anywhere in the list would otherwise put one vertex of the polyline at the origin and
 * quietly draw a line to the Gulf of Guinea, which looks exactly like a finding.
 */
export function przeanalizujSlad(mmsi: string, surowe: ShipTrackPoint[]): Slad {
  const punkty: PunktSladu[] = surowe
    .filter(poprawny)
    .map((p) => ({ lat: p.lat, lon: p.lon, ts: Date.parse(p.ts), sogKt: p.sogKt }))
    .sort((a, b) => a.ts - b.ts);

  const odcinki: OdcinekSladu[] = [];
  const przerwy: PrzerwaSladu[] = [];
  let biezacy: PunktSladu[] = [];
  let przebytaKm = 0;

  for (const p of punkty) {
    if (biezacy.length === 0) {
      biezacy.push(p);
      continue;
    }
    const poprzedni = biezacy[biezacy.length - 1];
    const sekundy = (p.ts - poprzedni.ts) / 1000;
    if (sekundy > PROG_PRZERWY_S) {
      przerwy.push({ od: poprzedni, do_: p, sekundy, km: kmMiedzy(poprzedni, p) });
      if (biezacy.length > 1) odcinki.push({ punkty: biezacy });
      biezacy = [p];
      continue;
    }
    przebytaKm += kmMiedzy(poprzedni, p);
    biezacy.push(p);
  }
  if (biezacy.length > 1) odcinki.push({ punkty: biezacy });

  const poczatek = punkty[0] ?? null;
  const koniec = punkty[punkty.length - 1] ?? null;

  return {
    mmsi,
    punkty,
    odcinki,
    przerwy,
    postoje: znajdzPostoje(punkty),
    poczatek,
    koniec,
    przebytaKm,
    wLiniiKm: poczatek && koniec ? kmMiedzy(poczatek, koniec) : 0,
    sekundy: poczatek && koniec ? (koniec.ts - poczatek.ts) / 1000 : 0,
    // Namiar liczony OD nowej pozycji DO starej - to jest kierunek, z ktorego statek przyplynal.
    zNamiaru: poczatek && koniec && kmMiedzy(poczatek, koniec) >= PROG_STOI_KM
      ? namiar(koniec, poczatek)
      : null,
    nieruchomy: poczatek !== null && punkty.every((p) => kmMiedzy(poczatek, p) < PROG_STOI_KM),
  };
}

/**
 * Runs of fixes below MIN_W_RUCHU_KT that last at least PROG_POSTOJU_S.
 *
 * The marker goes on the middle of the run rather than its first fix: a ship swinging on an anchor
 * for an hour reports from a circle, and pinning the label to the first report of that circle points
 * at its edge.
 */
export function znajdzPostoje(punkty: PunktSladu[]): PostojSladu[] {
  const out: PostojSladu[] = [];
  let start: number | null = null;
  for (let i = 0; i <= punkty.length; i++) {
    const wolno = i < punkty.length && (punkty[i].sogKt ?? 0) < MIN_W_RUCHU_KT;
    if (wolno && start === null) start = i;
    if (!wolno && start !== null) {
      const sekundy = (punkty[i - 1].ts - punkty[start].ts) / 1000;
      if (sekundy >= PROG_POSTOJU_S) {
        out.push({ punkt: punkty[Math.floor((start + i - 1) / 2)], sekundy });
      }
      start = null;
    }
  }
  return out;
}

/** Polish counts three ways; "2 przerwy" and "5 przerw" are different words. */
function odmiana(n: number, jeden: string, kilka: string, wiele: string): string {
  const abs = Math.abs(n) % 100;
  const ostatnia = abs % 10;
  if (abs === 1) return jeden;
  if (ostatnia >= 2 && ostatnia <= 4 && (abs < 12 || abs > 14)) return kilka;
  return wiele;
}

/**
 * The answer to "where is it coming from", in sentences.
 *
 * Every branch has to be a statement about the data, including the empty ones. A hull that has no
 * history is not a broken panel - it is a hull that came into range a moment ago, and saying so is
 * information. The previous version of this panel said nothing at all in that case, which reads as a
 * bug and makes a reader distrust the lines that ARE drawn.
 */
export function skadPlynie(stan: StanSladu): string[] {
  if (stan.stan === "nic") return [];
  if (stan.stan === "ladowanie") return ["Wczytuję trasę z ostatnich godzin…"];
  if (stan.stan === "blad") {
    return [`Nie udało się pobrać trasy (${stan.powod}). Sama pozycja statku wyżej jest aktualna.`];
  }

  const s = stan.slad;
  if (s.punkty.length === 0) {
    return [
      `Serwer nie ma jeszcze żadnej wcześniejszej pozycji tej jednostki z ostatnich ${OKNO_H} h. ` +
        "To nie błąd: statek mógł wejść w zasięg odbioru przed chwilą albo dopiero włączyć AIS.",
    ];
  }
  if (s.punkty.length === 1) {
    return [
      `W oknie ${OKNO_H} h jest tylko jedna pozycja tej jednostki — za mało, żeby narysować trasę. ` +
        "Sam brak historii niczego nie znaczy; znaczy tyle, że nikt jej wcześniej stąd nie słyszał.",
    ];
  }

  const zdania: string[] = [];

  if (s.nieruchomy) {
    zdania.push(
      `Przez ostatnie ${czasSlownie(s.sekundy)} nie ruszyła się z miejsca (${s.punkty.length} ` +
        `${odmiana(s.punkty.length, "pozycja", "pozycje", "pozycji")} w promieniu ` +
        `${kmSlownie(PROG_STOI_KM)}). Trasy nie ma, bo nie ma dokąd — to postój, nie brak danych.`,
    );
    // Cisza stojacego statku dostaje osobne zdanie, bo znaczy co innego niz cisza w ruchu, a mapa
    // nie rysuje tu ani linii, ani kolek. Zlapane na zywym panelu (MMSI 255804570, 2026-09-29):
    // wspolny tekst obiecywal "dziure i kolka" tam, gdzie nie ma zadnego znaku, i podawal 27 minut
    // ciszy przy kei jako znalezisko. D4 liczy wylacznie cisze statku, ktory PLYNAL.
    if (s.przerwy.length > 0) {
      const najdluzsza = s.przerwy.reduce((a, b) => (b.sekundy > a.sekundy ? b : a));
      zdania.push(
        `AIS milczał w tym czasie ${s.przerwy.length} ` +
          `${odmiana(s.przerwy.length, "raz", "razy", "razy")} (najdłużej ` +
          `${czasSlownie(najdluzsza.sekundy)}), ale statek przez cały czas stał — cisza stojącej ` +
          "jednostki nie mówi nic. Detektor zaniku liczy tylko ciszę statku, który płynął.",
      );
    }
    return zdania;
  } else {
    zdania.push(
      `Przypłynęła z kierunku ${stronaSwiata(s.zNamiaru ?? 0)}: przez ostatnie ` +
        `${czasSlownie(s.sekundy)} przesunęła się o ${kmSlownie(s.wLiniiKm)} w linii prostej, ` +
        `a po zaobserwowanym śladzie przebyła ${kmSlownie(s.przebytaKm)}. ` +
        "Fioletowa linia na mapie to przeszłość — cienki koniec jest najstarszy.",
    );
  }

  if (s.przerwy.length > 0) {
    const najdluzsza = s.przerwy.reduce((a, b) => (b.sekundy > a.sekundy ? b : a));
    zdania.push(
      `W śladzie ${s.przerwy.length === 1 ? "jest" : "są"} ${s.przerwy.length} ` +
        `${odmiana(s.przerwy.length, "przerwa", "przerwy", "przerw")} w nadawaniu; najdłuższa trwała ` +
        `${czasSlownie(najdluzsza.sekundy)}, a jej końce dzieli ${kmSlownie(najdluzsza.km)}. ` +
        "Mapa zostawia tam dziurę i zaznacza oba końce kółkami — linia przez to miejsce byłaby " +
        "zmyślona, bo nikt nie słyszał, którędy statek płynął.",
    );
  } else {
    zdania.push("Ślad jest ciągły — w tym oknie nie ma ani jednej przerwy w nadawaniu.");
  }

  if (s.postoje.length > 0) {
    const najdluzszy = s.postoje.reduce((a, b) => (b.sekundy > a.sekundy ? b : a));
    zdania.push(
      `Po drodze ${s.postoje.length === 1 ? "stanęła raz" : `stawała ${s.postoje.length} razy`}; ` +
        `najdłuższy postój trwał ${czasSlownie(najdluzszy.sekundy)}. Na mapie to wypełnione kropki.`,
    );
  }

  return zdania;
}

/** What the sentences above rest on: window, thresholds, and what a gap does NOT prove. */
export function podstawaSladu(stan: StanSladu): string[] {
  if (stan.stan !== "gotowy" || stan.slad.punkty.length < 2) return [];
  const wiersze = [
    `Trasa to surowe pozycje AIS z ostatnich ${OKNO_H} h (${stan.slad.punkty.length} ` +
      `${odmiana(stan.slad.punkty.length, "pozycja", "pozycje", "pozycji")}), bez wygładzania i bez ` +
      "dopowiadania punktów pośrednich.",
    `Przerwa to odstęp dłuższy niż ${PROG_PRZERWY_S / 60} min między kolejnymi pozycjami. Próg ` +
      "zmierzony na 49 813 odstępach z 882 żywych tras: mediana 150 s, 99. percentyl 599 s — " +
      `powyżej ${PROG_PRZERWY_S / 60} min jest 0,99% odstępów.`,
    `Postój to co najmniej ${PROG_POSTOJU_S / 60} min poniżej ${String(MIN_W_RUCHU_KT).replace(".", ",")} w.`,
  ];
  if (stan.slad.przerwy.length > 0) {
    wiersze.push(
      "Czego przerwa nie dowodzi: wyłączony transponder i zwykła utrata zasięgu wyglądają w danych " +
        "identycznie. Tu widać tylko tyle, że pozycji nie było — nie dlaczego.",
    );
  }
  return wiersze;
}
