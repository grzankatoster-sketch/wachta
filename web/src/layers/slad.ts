import { LineLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { LABEL } from "../colors";
import { czasSlownie, kmSlownie, type PostojSladu, type PrzerwaSladu, type PunktSladu, type StanSladu } from "../slad";

/**
 * The selected ship's past, drawn so it cannot be mistaken for its future.
 *
 * The map already has a line for each moving hull: thin, the vessel's own blue, reaching AHEAD of
 * the bow to where dead reckoning puts it in half an hour. That one is a projection. This one is
 * measurement, so it has to look like a different kind of thing, not like more of the same:
 *
 *  - violet, a hue nothing else on this map uses (ships are teal-blue, aircraft grey and red,
 *    alerts amber). Measured with colors.ts's contrastRatio against the positron basemap: 6.86:1 on
 *    land, 4.52:1 on water, both clear of the 3:1 WCAG 1.4.11 asks of a graphic that carries
 *    meaning, and 4.59:1 against the alert amber so the two cannot be swapped;
 *  - a taper instead of a fade. Age reads as width, 1.4 px at the oldest end to 3.2 px at the
 *    newest, because fading it was the obvious idea and the measurement killed it: composited over
 *    the basemap sea, this violet needs alpha 200 to reach 3:1 and is down to 1.71:1 by alpha 100,
 *    so the "old" end of a faded line would be a graphic nobody can see. Alpha is a flat 220
 *    (3.61:1 on water, 5.03:1 on land) all the way along and the thin end still says "this is where
 *    it started".
 *
 * Nothing here is pickable. The track lies under the hulls and would otherwise eat the click that
 * opened it.
 */

/** Violet, measured against the basemap in the docstring above. */
export const SLAD: [number, number, number] = [106, 61, 154];

/** Flat alpha: 3.61:1 over the basemap sea, which is the darker of the two surfaces. */
const ALFA = 220;

const NAJCIENSZY_PX = 1.4;
const NAJGRUBSZY_PX = 3.2;

/**
 * Podpisy siedza na wlasnej plakietce, bo lezy pod nimi wszystko naraz: linia sladu, nazwy
 * cieśnin z podkladu i inne statki. Bez tla napis "cisza 1 h 2 min" przecinal wlasna trase i
 * dawal sie odczytac dopiero po odsunieciu mapy - widac to na zrzucie sprzed tej zmiany.
 */
const PLAKIETKA = {
  // Bez tego napisy gubia polskie znaki. Domyslny atlas TextLayer to ASCII 32-127, wiec "stąd"
  // wyszlo na zrzucie jako "st d", a "·" jako dziura - kazdy znak spoza zakresu jest rysowany
  // jako pusty prostokat. "auto" buduje atlas z tego, co faktycznie jest w danych.
  characterSet: "auto" as const,
  background: true,
  getBackgroundColor: [255, 255, 255, 225] as [number, number, number, number],
  backgroundPadding: [5, 2, 5, 2] as [number, number, number, number],
  getBorderColor: [...SLAD, 160] as [number, number, number, number],
  getBorderWidth: 1,
};

interface Kreska {
  od: [number, number];
  do_: [number, number];
  /** 0 at the oldest fix of the whole track, 1 at the newest. Drives the taper. */
  udzial: number;
}

const xy = (p: PunktSladu): [number, number] => [p.lon, p.lat];

/**
 * Builds the layers. A state that is not a loaded, moving track yields nothing at all - a loading
 * spinner, an empty history and a moored hull each have their say in the panel, in words, and none
 * of them should put a mark on the map that a reader has to decode.
 */
export function sladLayers(stan: StanSladu): Layer[] {
  if (stan.stan !== "gotowy") return [];
  const s = stan.slad;
  if (s.nieruchomy || s.odcinki.length === 0 || s.poczatek === null) return [];

  const najstarszy = s.punkty[0].ts;
  const rozpietosc = Math.max(1, s.punkty[s.punkty.length - 1].ts - najstarszy);

  const kreski: Kreska[] = [];
  for (const odcinek of s.odcinki) {
    for (let i = 1; i < odcinek.punkty.length; i++) {
      const a = odcinek.punkty[i - 1];
      const b = odcinek.punkty[i];
      kreski.push({ od: xy(a), do_: xy(b), udzial: (b.ts - najstarszy) / rozpietosc });
    }
  }

  // Oba konce kazdej przerwy, jako jedna lista: dziura ma dwa brzegi i oba sa faktem pomiarowym
  // ("tu ostatni raz slyszano", "tu znow"). Bez obu z nich luka jest nieodroznialna od konca trasy.
  const konceLuk = s.przerwy.flatMap((p: PrzerwaSladu) => [p.od, p.do_]);
  const najdluzszaPrzerwa = s.przerwy.length
    ? s.przerwy.reduce((a, b) => (b.sekundy > a.sekundy ? b : a))
    : null;

  return [
    new LineLayer<Kreska>({
      id: "ship-track",
      data: kreski,
      getSourcePosition: (k) => k.od,
      getTargetPosition: (k) => k.do_,
      getColor: [...SLAD, ALFA] as [number, number, number, number],
      getWidth: (k) => NAJCIENSZY_PX + (NAJGRUBSZY_PX - NAJCIENSZY_PX) * k.udzial,
      widthUnits: "pixels",
      pickable: false,
    }),
    // Start: pusty pierscien. Wypelniona kropka znaczy tu postoj, a poczatek sladu to nie postoj -
    // to granica tego, co w ogole wiemy.
    new ScatterplotLayer<PunktSladu>({
      id: "ship-track-start",
      data: [s.poczatek],
      getPosition: xy,
      filled: false,
      stroked: true,
      getLineColor: [...SLAD, ALFA] as [number, number, number, number],
      getRadius: 5.5,
      radiusUnits: "pixels",
      lineWidthMinPixels: 1.6,
      pickable: false,
    }),
    new TextLayer<PunktSladu>({
      id: "ship-track-start-label",
      data: [s.poczatek],
      getPosition: xy,
      getText: () => `stąd, ${czasSlownie(s.sekundy)} temu`,
      getSize: 11,
      getColor: [...LABEL, 230] as [number, number, number, number],
      // Pod punktem, gdy podpis luki stoi nad swoim: dwie plakietki w jednym miejscu to znowu
      // stos, a na krotkim sladzie poczatek i przerwa potrafia wypasc kilkadziesiat metrow od siebie.
      getPixelOffset: [0, 20],
      pickable: false,
      ...PLAKIETKA,
    }),
    new ScatterplotLayer<PostojSladu>({
      id: "ship-track-stops",
      data: s.postoje,
      getPosition: (p) => xy(p.punkt),
      // Promien rosnie z dlugoscia postoju i jest przyciety: bez sufitu jeden statek stojacy cala
      // dobe zalewalby kropka pol Zatoki Finskiej.
      getRadius: (p) => Math.min(7, 3.5 + p.sekundy / 900),
      radiusUnits: "pixels",
      getFillColor: [...SLAD, ALFA] as [number, number, number, number],
      stroked: true,
      getLineColor: [255, 255, 255, 220],
      lineWidthMinPixels: 1.2,
      pickable: false,
    }),
    // Konce przerwy sa puste w srodku - to znak "tu sie urywa", nie "tu cos jest".
    new ScatterplotLayer<PunktSladu>({
      id: "ship-track-gaps",
      data: konceLuk,
      getPosition: xy,
      filled: false,
      stroked: true,
      getLineColor: [...SLAD, ALFA] as [number, number, number, number],
      getRadius: 6.5,
      radiusUnits: "pixels",
      lineWidthMinPixels: 2,
      pickable: false,
    }),
    // Podpisana jest TYLKO najdluzsza przerwa, a napis niesie liczbe pozostalych.
    //
    // Pierwsza wersja podpisywala kazda i na zrzucie z 2026-09-29 (MMSI 265649360, 4 przerwy w
    // sladzie dlugim na 8 km) cztery plakietki zlozyly sie w jeden nieczytelny stos - deck.gl nie
    // odsuwa kolidujacych napisow. Dziury i kolka zostaja przy kazdej przerwie, wiec z mapy nadal
    // widac, ILE ich jest; policzone i rozpisane sa w panelu.
    new TextLayer<PrzerwaSladu>({
      id: "ship-track-gap-labels",
      data: najdluzszaPrzerwa === null ? [] : [najdluzszaPrzerwa],
      getPosition: (p) => [(p.od.lon + p.do_.lon) / 2, (p.od.lat + p.do_.lat) / 2],
      getText: (p) =>
        s.przerwy.length === 1
          ? `cisza ${czasSlownie(p.sekundy)} · ${kmSlownie(p.km)}`
          : `najdłuższa z ${s.przerwy.length} przerw: ${czasSlownie(p.sekundy)} · ${kmSlownie(p.km)}`,
      getSize: 11,
      getColor: [...SLAD, 255] as [number, number, number, number],
      // Podpis odsuniety wyzej niz wysokosc plakietki: ma stac NAD dziura, a nie w niej. Przy
      // offsecie -12 tlo napisu zaslanialo dokladnie to miejsce, w ktorym czytelnik ma zobaczyc,
      // ze linii nie ma (widac to na zrzucie z 2026-09-29).
      getPixelOffset: [0, -24],
      pickable: false,
      ...PLAKIETKA,
    }),
  ];
}
