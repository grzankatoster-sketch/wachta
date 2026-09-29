import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { ZdarzenieDto } from "../konflikty";

/**
 * Land events of one conflict, drawn on the same map as the live traffic.
 *
 * They are deliberately a different shape from everything else on this map: a filled disc, where
 * alerts are rings and traffic is silhouettes. Air and sea marks are measurements of where a thing
 * physically was; these are places somebody WROTE about. Giving them the visual language of a
 * position fix would be the map's own way of claiming more than GDELT knows.
 */

/** Goldstein runs -10 (worst) .. +10 (best) on the CAMEO scale. Null means GDELT gave none. */
export function kolorZdarzenia(goldstein: number | null): [number, number, number] {
  // Grey, not "mildly bad": an unscored event is one whose severity nobody stated, and guessing a
  // middle value would place it on the scale with the same confidence as a measured one.
  if (goldstein === null || !Number.isFinite(goldstein)) return [139, 148, 158];
  if (goldstein <= -7) return [248, 81, 73];
  if (goldstein < 0) return [227, 179, 65];
  return [88, 166, 255];
}

/**
 * Disc size from the number of outlets that carried it, on a square root.
 *
 * Linear would make a story carried by two hundred outlets a hundred times the area of one carried
 * by two, which reads as "a hundred times bigger event" - and reach is not magnitude. The root
 * keeps the ordering visible while refusing to imply the ratio.
 */
export function promienZdarzenia(sources: number): number {
  return Math.min(20, 5 + Math.sqrt(Math.max(0, sources)) * 2.2);
}

/**
 * Which events get a place name printed next to them.
 *
 * Every one of them would be a wall of overlapping text at Baltic zoom levels. The widest-reported
 * ones, plus whichever is open, is enough to orient a reader; the rest are named in the list.
 */
export function podpisyDoPokazania(
  zdarzenia: ZdarzenieDto[],
  wybrane: string | null,
  ile = 10,
): ZdarzenieDto[] {
  const znazwa = zdarzenia.filter((z) => z.place);
  const czolo = [...znazwa].sort((a, b) => b.sources - a.sources).slice(0, ile);
  const otwarte = znazwa.find((z) => z.id === wybrane);
  return otwarte && !czolo.includes(otwarte) ? [...czolo, otwarte] : czolo;
}

export function zdarzeniaLayers(zdarzenia: ZdarzenieDto[], wybrane: string | null) {
  if (zdarzenia.length === 0) return [];
  return [
    new ScatterplotLayer<ZdarzenieDto>({
      id: "zdarzenia-konfliktu",
      data: zdarzenia,
      getPosition: (z) => [z.lon, z.lat],
      getRadius: (z) => promienZdarzenia(z.sources),
      radiusUnits: "pixels",
      filled: true,
      stroked: true,
      getFillColor: (z) => [...kolorZdarzenia(z.goldstein), 150] as [number, number, number, number],
      getLineColor: (z) => kolorZdarzenia(z.goldstein),
      lineWidthMinPixels: 1,
      // Bez tego klikniecie w zdarzenie nie otwiera zestawienia wersji - a to jest jedyny sposob,
      // zeby dojsc do niego z mapy.
      pickable: true,
      updateTriggers: { getFillColor: wybrane, getLineColor: wybrane },
    }),
    // Ktore zdarzenie jest otwarte. Przy kilkunastu jednakowych krazkach w jednym obwodzie bez tego
    // nie da sie powiedziec, ktorego dotyczy panel po prawej.
    new ScatterplotLayer<ZdarzenieDto>({
      id: "zdarzenie-wybrane",
      data: zdarzenia.filter((z) => z.id === wybrane),
      getPosition: (z) => [z.lon, z.lat],
      getRadius: (z) => promienZdarzenia(z.sources) + 7,
      radiusUnits: "pixels",
      filled: false,
      stroked: true,
      getLineColor: [255, 255, 255],
      lineWidthMinPixels: 2,
      pickable: false,
    }),
    new TextLayer<ZdarzenieDto>({
      id: "zdarzenia-podpisy",
      data: podpisyDoPokazania(zdarzenia, wybrane),
      getPosition: (z) => [z.lon, z.lat],
      getText: (z) => z.place ?? "",
      getSize: 12,
      getColor: [230, 237, 243],
      getPixelOffset: [0, -16],
      outlineWidth: 3,
      outlineColor: [13, 17, 23, 220],
      fontSettings: { sdf: true },
      // Domyslny atlas TextLayer to ASCII 32-127, wiec "Charków" i "Zaporiżżia" rysowaly sie jako
      // puste prostokaty - a to sa dokladnie te nazwy, ktore ta warstwa ma pokazywac.
      characterSet: "auto",
      pickable: false,
    }),
  ];
}
