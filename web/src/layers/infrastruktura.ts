import { PathLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { kolorLinii, type LiniaInfrastruktury } from "../infrastruktura";

/**
 * Cables and pipelines, drawn as thin lines under everything else.
 *
 * They are context, not traffic. Every other mark on this map is something that moved in the last
 * few minutes; this one has been on the seabed for years and its only job is to let a reader see
 * what a ship is sitting next to. So it is drawn the way context is drawn: one pixel wide at the
 * bottom of the stack, never over a hull.
 *
 * Two layers, not one, and the reason is picking. deck.gl picks by geometry, so a 1.2 px line is a
 * 1.2 px click target - a 2560x1440 map of the whole Baltic puts the whole of Nord Stream inside
 * about two pixels of width, and nobody hits that with a mouse. The invisible twin below carries
 * the clicks at 9 px, which at this zoom is about 6 km of sea either side of the line: wide enough
 * to hit, narrow enough that it cannot be mistaken for anything else nearby. It is listed FIRST so
 * that deck.gl, which picks the topmost layer, still gives ships and aircraft the click when they
 * overlap a line - the moving thing is what the reader meant.
 */

/** Wide enough to hit with a mouse; see the class comment for what 9 px is worth in kilometres. */
const SZEROKOSC_TRAFIENIA_PX = 9;

/** Hairline: the same weight as the ships' course lines (1.4 px), a shade under so it reads as ground. */
const SZEROKOSC_PX = 1.2;

/**
 * Not fully opaque, so that a ship crossing a line still reads as being on top of it. 190/255 was
 * the point where the line stopped competing with the hulls and stayed visible over open water.
 */
const ALFA = 190;

export function infrastructureLayers(linie: LiniaInfrastruktury[]): Layer[] {
  return [
    new PathLayer<LiniaInfrastruktury>({
      id: "infrastructure-hit",
      data: linie,
      getPath: (l) => l.sciezka,
      // Alfa 0: deck.gl rysuje bufor pickingu z geometrii, nie z koloru, wiec niewidoczna sciezka
      // nadal lapie klikniecia. Jedyne, co ten kolor robi, to nierysowanie niczego na ekranie.
      getColor: [0, 0, 0, 0],
      getWidth: SZEROKOSC_TRAFIENIA_PX,
      widthUnits: "pixels",
      widthMinPixels: SZEROKOSC_TRAFIENIA_PX,
      capRounded: true,
      jointRounded: true,
      pickable: true,
    }),
    new PathLayer<LiniaInfrastruktury>({
      id: "infrastructure",
      data: linie,
      getPath: (l) => l.sciezka,
      getColor: (l) => [...kolorLinii(l.rodzaj), ALFA] as [number, number, number, number],
      getWidth: SZEROKOSC_PX,
      widthUnits: "pixels",
      widthMinPixels: SZEROKOSC_PX,
      capRounded: true,
      jointRounded: true,
      // Klikniecia obsluguje blizniak wyzej; ta warstwa ma tylko byc widoczna.
      pickable: false,
    }),
  ];
}
