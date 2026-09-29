import { useEffect, useState } from "react";
import { KABEL, RUROCIAG } from "./colors";
import type { Szczegoly } from "./detail";

/**
 * Submarine cables and pipelines - the lines detector D6 measures ships against.
 *
 * The map drew none of them until now, and D6 was already raising "ship 0.1 km from a line": a
 * claim about a thing the reader could not see, on a screen that showed only the ship. Drawing the
 * line is what turns that alarm into something checkable by looking.
 *
 * DELIVERY: a static file fetched at runtime (/dane/baltic_cables.geojson), not an import bundled
 * into the JS, and not an API endpoint.
 *  - Bundling it would add 221 152 B of JSON to a module that the browser parses and executes
 *    before the first frame - 9% on top of the app chunk, which `vite build` measures at 2 392 kB
 *    raw / 671 kB gzipped. Fetched separately it is 81 243 B over the wire (nginx gzip at its
 *    default comp level 1, measured on this exact file; level 6 gets it to 71 955 B), it travels in
 *    parallel with the basemap tiles, and nothing on the critical path waits for it.
 *  - An API endpoint would mean a round trip to the .NET service and a redeploy of it for a file
 *    that changes when somebody re-runs the Overpass fetch - maybe monthly. The API's job here is
 *    live positions; this is a fixture.
 *  - The fetch is lazy: it happens the first time the layer is switched on, and once only. With the
 *    layer off, those 81 KB are never requested at all.
 * Vite serves the file in dev and copies it into dist at build (see web/vite.config.ts), so the
 * path is the same under `vite dev`, `vite preview` and nginx.
 *
 * HONESTY: the geometry is OpenStreetMap, i.e. contributed and APPROXIMATE - see szczegolyLinii().
 */

export const SCIEZKA_DANYCH = "/dane/baltic_cables.geojson";

/** OSM's own vocabulary, kept as it is; "inny" is the bucket for a value we have not seen. */
export type RodzajLinii = "power" | "telecom" | "pipeline" | "inny";

export interface LiniaInfrastruktury {
  osmId: number;
  nazwa: string;
  rodzaj: RodzajLinii;
  operator: string | null;
  /** [lon, lat] pairs, exactly the GeoJSON order - PathLayer reads this array as it stands. */
  sciezka: [number, number][];
}

export const NAZWA_RODZAJU: Record<RodzajLinii, string> = {
  power: "kabel energetyczny",
  telecom: "kabel telekomunikacyjny",
  pipeline: "rurociąg",
  inny: "linia podmorska o nieopisanym rodzaju",
};

/**
 * Pipelines get their own colour, both kinds of cable share one.
 *
 * Three colours would be three things to remember for a split the panel already names in words.
 * The split that carries weight on the map is cable against pipeline: measured on the shipped file,
 * 73 of 89 lines are cables (38 power, 35 telecom) and 16 are pipelines.
 */
export function kolorLinii(rodzaj: RodzajLinii): [number, number, number] {
  return rodzaj === "pipeline" ? RUROCIAG : KABEL;
}

function rodzajZOsm(v: unknown): RodzajLinii {
  return v === "power" || v === "telecom" || v === "pipeline" ? v : "inny";
}

/**
 * Turns the GeoJSON into lines, dropping exactly what the Python side drops.
 *
 * wachta_detectors/infrastructure.py::load_lines skips anything that is not a LineString and
 * anything with fewer than two points, because a one-point "line" has no segment to measure a
 * distance against. The map has to skip the same features, or the picture and the alarms would be
 * describing different sets of infrastructure. Measured on the shipped file: 89 features, all
 * LineStrings, none shorter than 2 points, so today both sides keep all 89 - the filter is here so
 * that a future Overpass fetch cannot make them disagree quietly.
 */
export function parsujLinie(json: unknown): LiniaInfrastruktury[] {
  const features = (json as { features?: unknown })?.features;
  if (!Array.isArray(features)) return [];
  const linie: LiniaInfrastruktury[] = [];
  for (const f of features) {
    const geometry = (f as { geometry?: { type?: unknown; coordinates?: unknown } })?.geometry;
    const props = ((f as { properties?: Record<string, unknown> })?.properties ?? {});
    if (geometry?.type !== "LineString" || !Array.isArray(geometry.coordinates)) continue;
    const sciezka = geometry.coordinates
      .filter((p): p is [number, number] =>
        Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]))
      .map(([lon, lat]) => [lon, lat] as [number, number]);
    if (sciezka.length < 2) continue;
    linie.push({
      osmId: typeof props.osm_id === "number" ? props.osm_id : -1,
      nazwa: typeof props.name === "string" && props.name.trim() ? props.name.trim() : "bez nazwy w OSM",
      rodzaj: rodzajZOsm(props.kind),
      operator: typeof props.operator === "string" && props.operator.trim() ? props.operator.trim() : null,
      sciezka,
    });
  }
  return linie;
}

export async function pobierzLinie(
  sciezka: string = SCIEZKA_DANYCH,
  pobierz: typeof fetch = fetch,
): Promise<LiniaInfrastruktury[]> {
  const res = await pobierz(sciezka);
  if (!res.ok) throw new Error(`${sciezka}: HTTP ${res.status}`);
  return parsujLinie(await res.json());
}

/**
 * Loads the file once, the first time the layer is asked for.
 *
 * Once, not once per toggle: the geometry does not change while the page is open, and re-fetching
 * 221 KB every time somebody flicks the switch to see what disappeared - which is exactly how this
 * legend is meant to be used - would punish the reading technique the legend was built for.
 */
export function useInfrastruktura(wlaczona: boolean): LiniaInfrastruktury[] {
  const [linie, setLinie] = useState<LiniaInfrastruktury[]>([]);
  const [zazadano, setZazadano] = useState(false);

  useEffect(() => {
    if (!wlaczona || zazadano) return;
    setZazadano(true);
    pobierzLinie().then(setLinie).catch(() => undefined);
  }, [wlaczona, zazadano]);

  return linie;
}

/** Whole kilometres of one line, for the panel. Equirectangular, same as the Python detector. */
export function dlugoscKm(sciezka: [number, number][]): number {
  let suma = 0;
  for (let i = 1; i < sciezka.length; i++) {
    const [lon1, lat1] = sciezka[i - 1];
    const [lon2, lat2] = sciezka[i];
    const dx = (lon2 - lon1) * Math.cos(((lat1 + lat2) / 2) * (Math.PI / 180)) * 111.32;
    const dy = (lat2 - lat1) * 111.32;
    suma += Math.hypot(dx, dy);
  }
  return suma;
}

/**
 * The three sections of the detail panel for one line.
 *
 * "Na jakiej podstawie" says out loud that the route is approximate, and it has to, because D6
 * turns these same coordinates into alarms: it reports a ship's distance to the nearest line in
 * hundredths of a kilometre from geometry that was drawn by OSM contributors from charts and
 * announcements, not surveyed. A reader who sees "0.1 km od linii" next to a line on the screen
 * will believe the 0.1 unless this panel tells them what it is made of.
 */
export function szczegolyLinii(l: LiniaInfrastruktury): Szczegoly {
  const km = dlugoscKm(l.sciezka);

  return {
    tytul: l.nazwa,
    podtytul: NAZWA_RODZAJU[l.rodzaj],
    coToJest: [
      `Rodzaj: ${NAZWA_RODZAJU[l.rodzaj]}`,
      l.operator ? `Operator wg OSM: ${l.operator}` : "Operator: nie podany w OSM",
      `Długość narysowanego odcinka: ${km < 10 ? km.toFixed(1) : Math.round(km)} km (${l.sciezka.length} punktów trasy)`,
      l.osmId >= 0 ? `Identyfikator OpenStreetMap: ${l.osmId}` : "Bez identyfikatora OSM",
    ],
    coZTegoWynika: [
      "To infrastruktura leżąca na dnie — nie porusza się i nie nadaje o sobie żadnego sygnału. Na mapie jest po to, żeby dało się zobaczyć, obok czego przechodzi statek.",
      "Detektor D6 (podejrzenie wleczenia kotwicy) mierzy odległość statku właśnie od tych linii. Alarm D6 bez widocznej linii to twierdzenie, którego nie da się sprawdzić wzrokiem — dlatego linie są tutaj.",
      "Odcinek bywa pocięty na kawałki: jedna trasa potrafi występować w OSM jako kilka osobnych linii o tej samej nazwie. Długość powyżej dotyczy klikniętego kawałka, nie całej trasy.",
    ],
    naPodstawie: [
      "Źródło: OpenStreetMap (współtwórcy OSM, licencja ODbL), pobrane przez Overpass API.",
      "Trasy są PRZYBLIŻONE. To rysunek wykonany przez ludzi na podstawie map morskich i komunikatów, nie pomiar geodezyjny — rzeczywisty przebieg kabla czy rurociągu może leżeć o setki metrów obok.",
      "Czego to nie dowodzi: odległość statku od tej linii, którą podaje detektor D6, jest tak dokładna jak sam rysunek. „0,1 km od kabla” znaczy „0,1 km od tego, co narysowano w OSM”, a nie od kabla.",
      "Zbiór nie jest kompletny: w OSM jest to, co ktoś wprowadził. Brak linii na mapie nie znaczy, że dno w tym miejscu jest puste.",
    ],
    tor: null,
  };
}
