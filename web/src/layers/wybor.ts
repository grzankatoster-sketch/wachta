import { LineLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { AlertDto, LiveShip } from "../api";
import { parseEvidence } from "../api";
import { LABEL } from "../colors";
import type { Selection } from "../detail";

/**
 * Showing WHICH mark on the map the open panel is talking about.
 *
 * Selecting an alert used to centre the map and open the panel, and that was all: the reader landed
 * on a patch of sea holding a dozen identical amber rings and several hundred hulls, with no way to
 * tell which of them the panel meant. The first person to try it said exactly that - "coś mi
 * pokazuje na mapie, ale nie wiem co".
 *
 * So the selection draws itself. The alert gets a ring nothing else on the map has, and - this is
 * the part that matters - the OBJECTS THE ALERT IS ABOUT get one too. A ship-to-ship transfer is a
 * claim about two named hulls; naming them in the panel while leaving them indistinguishable on the
 * map asks the reader to take the claim on trust. Drawing the pair, with the measured separation
 * written between them, lets them check it instead.
 *
 * Nothing here is pickable. It is an annotation of a choice the reader already made, not a new
 * object to click, and making it clickable would put a target on top of the very hulls it points at.
 */

/** Amber, matching the alert rings, but brighter - this one is the answer to a question. */
const WYBOR: [number, number, number] = [255, 190, 0];

/** Ring for the hulls an alert names. White so it reads against every vessel colour. */
const PODMIOT: [number, number, number] = [250, 250, 250];

interface Para {
  a: LiveShip;
  b: LiveShip;
  metry: number | null;
}

/** The two hulls a D5 alert is about, if both are still being heard. */
export function paraZAlarmu(a: AlertDto, statki: LiveShip[]): Para | null {
  if (a.detector !== "D5") return null;
  const ev = parseEvidence(a.evidence);
  const mmsiA = typeof ev.mmsi_a === "string" ? ev.mmsi_a : null;
  const mmsiB = typeof ev.mmsi_b === "string" ? ev.mmsi_b : null;
  if (!mmsiA || !mmsiB) return null;

  const znajdz = (m: string) => statki.find((s) => s.mmsi === m) ?? null;
  const pierwszy = znajdz(mmsiA);
  const drugi = znajdz(mmsiB);
  if (!pierwszy || !drugi) return null;

  const metry = typeof ev.min_separation_m === "number" ? ev.min_separation_m : null;
  return { a: pierwszy, b: drugi, metry };
}

export function wyborLayers(wybrany: Selection | null, statki: LiveShip[]): Layer[] {
  if (!wybrany || wybrany.kind !== "alert") return [];
  const alarm = wybrany.data;
  const para = paraZAlarmu(alarm, statki);
  const warstwy: Layer[] = [];

  // Pierscien na samym alarmie: dwa okregi, zeby odroznial sie od czternastopikselowych
  // pierscieni, ktorych na ekranie bywa setka.
  warstwy.push(
    new ScatterplotLayer<AlertDto>({
      id: "wybor-alarm",
      data: [alarm],
      getPosition: (a) => [a.lon, a.lat],
      getFillColor: [0, 0, 0, 0],
      getLineColor: WYBOR,
      getRadius: 26,
      radiusUnits: "pixels",
      stroked: true,
      filled: false,
      lineWidthMinPixels: 2.5,
      pickable: false,
    }),
    new ScatterplotLayer<AlertDto>({
      id: "wybor-alarm-zewnetrzny",
      data: [alarm],
      getPosition: (a) => [a.lon, a.lat],
      getFillColor: [0, 0, 0, 0],
      getLineColor: [...WYBOR, 110] as [number, number, number, number],
      getRadius: 38,
      radiusUnits: "pixels",
      stroked: true,
      filled: false,
      lineWidthMinPixels: 1.5,
      pickable: false,
    }),
  );

  if (para) {
    const kadluby = [para.a, para.b];
    warstwy.push(
      new LineLayer<Para>({
        id: "wybor-para-linia",
        data: [para],
        getSourcePosition: (p) => [p.a.lon, p.a.lat],
        getTargetPosition: (p) => [p.b.lon, p.b.lat],
        getColor: PODMIOT,
        getWidth: 1.6,
        widthUnits: "pixels",
        pickable: false,
      }),
      new ScatterplotLayer<LiveShip>({
        id: "wybor-para",
        data: kadluby,
        getPosition: (s) => [s.lon, s.lat],
        getFillColor: [0, 0, 0, 0],
        getLineColor: PODMIOT,
        getRadius: 13,
        radiusUnits: "pixels",
        stroked: true,
        filled: false,
        lineWidthMinPixels: 2,
        pickable: false,
      }),
      new TextLayer<LiveShip>({
        id: "wybor-para-nazwy",
        data: kadluby,
        getPosition: (s) => [s.lon, s.lat],
        getText: (s) => s.name?.trim() || s.mmsi,
        getSize: 11,
        getColor: LABEL,
        getPixelOffset: [0, 20],
        // Bez tego polskie znaki w nazwach statkow renderuja sie jako puste prostokaty:
        // domyslny atlas TextLayer to ASCII 32-127.
        characterSet: "auto",
        pickable: false,
      }),
    );

    if (para.metry !== null) {
      warstwy.push(
        new TextLayer<Para>({
          id: "wybor-para-odleglosc",
          data: [para],
          getPosition: (p) => [(p.a.lon + p.b.lon) / 2, (p.a.lat + p.b.lat) / 2],
          // "podczas spotkania", a nie samo "258 m".
          //
          // Pierwsza wersja pisala tu goly dystans i byla mylaca: alarm opisuje spotkanie sprzed
          // godzin, a pierscienie stoja na pozycjach BIEZACYCH. Na zrzucie z 2026-09-29 wyszlo
          // "258 m" napisane miedzy dwoma kadlubami oddalonymi juz o kilkanascie kilometrow - czyli
          // liczba prawdziwa, umieszczona tak, ze klamala. Linia laczy te dwa kadluby dlatego, ze
          // panel o nich mowi, a nie dlatego, ze sa blisko siebie teraz.
          getText: (p) => `${Math.round(p.metry ?? 0)} m podczas spotkania`,
          getSize: 12,
          getColor: LABEL,
          getPixelOffset: [0, -14],
          characterSet: "auto",
          pickable: false,
        }),
      );
    }
  }

  return warstwy;
}
