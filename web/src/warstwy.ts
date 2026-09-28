import { GREY, RED } from "./colors";

/**
 * What is on the map, in words, together with the switch that isolates it.
 *
 * The legend and the layer control are one thing here on purpose. A separate legend is a block of
 * text next to a picture, and people skip it; a legend you can click is how you find out what a
 * mark means - turn it off, see what disappeared. The first version of this view had neither, and
 * the first person to open it said "some dots, nothing is clickable, I have no idea what this is".
 */

export type IdWarstwy = "wojskowe" | "cywilne" | "alarmy" | "zaklocenia";

export interface OpisWarstwy {
  id: IdWarstwy;
  nazwa: string;
  /** One sentence: what the mark means, not what it is called. */
  opis: string;
  kolor: string;
  ksztalt: "kropka" | "obwodka" | "heksagon";
}

const rgb = ([r, g, b]: [number, number, number]) => `rgb(${r},${g},${b})`;

export const WARSTWY: OpisWarstwy[] = [
  {
    id: "wojskowe",
    nazwa: "Samoloty wojskowe",
    opis: "Oznaczone jako wojskowe przez adsb.lol, ograniczone do obserwowanego obszaru. Wiele maszyn nie nadaje ADS-B wcale — widać tylko te, które nadają.",
    kolor: rgb(RED),
    ksztalt: "kropka",
  },
  {
    id: "cywilne",
    nazwa: "Samoloty cywilne",
    opis: "Reszta ruchu w zasięgu odbiorników. Służy za tło: to na ich tle widać, że gdzieś robi się pusto.",
    kolor: rgb(GREY),
    ksztalt: "kropka",
  },
  {
    id: "alarmy",
    nazwa: "Alarmy detektorów",
    opis: "Miejsca, które detektory uznały za warte sprawdzenia. Kandydat do sprawdzenia, nigdy wyrok.",
    kolor: "rgb(255,190,0)",
    ksztalt: "obwodka",
  },
  {
    id: "zaklocenia",
    nazwa: "Zakłócenia GPS",
    opis: "Udział samolotów zgłaszających obniżoną dokładność nawigacji. Bursztyn 2–10%, czerwony powyżej 10%.",
    kolor: "rgb(230,57,70)",
    ksztalt: "heksagon",
  },
];

export type Widoczne = Record<IdWarstwy, boolean>;

export const WSZYSTKO_WIDOCZNE: Widoczne = {
  wojskowe: true,
  cywilne: true,
  alarmy: true,
  zaklocenia: true,
};

export function przelacz(stan: Widoczne, id: IdWarstwy): Widoczne {
  return { ...stan, [id]: !stan[id] };
}

/**
 * Whether the map is showing nothing at all.
 *
 * Worth knowing, because a map with every layer switched off looks exactly like a map with no data,
 * and the second one is somebody's fault while the first one is the reader's own doing.
 */
export function wszystkoWylaczone(stan: Widoczne): boolean {
  return Object.values(stan).every((v) => !v);
}

/** How many marks a layer currently contributes, for the counter next to its name. */
export function policz(
  id: IdWarstwy,
  liczby: { wojskowe: number; cywilne: number; alarmy: number; zaklocenia: number },
): number {
  return liczby[id];
}

/**
 * The sentence under the header: what the reader is looking at and how fresh it is.
 *
 * Freshness is not decoration. Every layer here is a snapshot of a moment, and a map that does not
 * say when it was taken invites the reader to assume it is now.
 *
 * The count names its area instead of saying "in range", because those were different numbers
 * until 2026-09-28. The military feed is worldwide and was broadcast unbounded, so the header
 * counted around three hundred aircraft on other continents - a 58% military share over a sea where
 * the measured figure is 5%. The broadcast is bounded now (WatchedArea.Baltic, 48-70 N / 0-40 E);
 * naming the area is what lets the number be checked against anything.
 */
export function stanDanych(polaczone: boolean, samolotow: number, sekundOdOdczytu: number | null): string {
  if (!polaczone) return "Łączenie z serwerem…";
  if (samolotow === 0) return "Połączono, ale żaden samolot nie jest teraz widoczny.";
  const wiek =
    sekundOdOdczytu === null
      ? ""
      : sekundOdOdczytu < 60
        ? " · dane sprzed chwili"
        : ` · dane sprzed ${Math.round(sekundOdOdczytu / 60)} min`;
  return `${samolotow} samolotów w obserwowanym obszarze (Bałtyk i podejścia)${wiek}`;
}
