import { GREY, KABEL, RED, SHIP_CARGO, SHIP_OTHER } from "./colors";

/**
 * What is on the map, in words, together with the switch that isolates it.
 *
 * The legend and the layer control are one thing here on purpose. A separate legend is a block of
 * text next to a picture, and people skip it; a legend you can click is how you find out what a
 * mark means - turn it off, see what disappeared. The first version of this view had neither, and
 * the first person to open it said "some dots, nothing is clickable, I have no idea what this is".
 */

export type IdWarstwy =
  | "wojskowe" | "cywilne" | "ladunek" | "statki" | "infrastruktura" | "alarmy" | "zaklocenia";

/**
 * Legend headings.
 *
 * Six rows in one list read as six unrelated things. Grouped by domain they read as what they are:
 * what is in the air, what is on the water, and what the project's own rules made of it. The third
 * group is deliberately last and deliberately named after the detectors - everything in it is this
 * project's opinion, everything above it is somebody else's measurement.
 */
export type Grupa = "powietrze" | "morze" | "detektory";

export const NAZWY_GRUP: Record<Grupa, string> = {
  powietrze: "W powietrzu",
  morze: "Na morzu",
  detektory: "Co znalazły detektory",
};

export interface OpisWarstwy {
  id: IdWarstwy;
  grupa: Grupa;
  nazwa: string;
  /** One sentence: what the mark means, not what it is called. */
  opis: string;
  kolor: string;
  ksztalt: "kropka" | "obwodka" | "heksagon" | "linia";
}

const rgb = ([r, g, b]: [number, number, number]) => `rgb(${r},${g},${b})`;

export const WARSTWY: OpisWarstwy[] = [
  {
    id: "wojskowe",
    grupa: "powietrze",
    nazwa: "Samoloty wojskowe",
    opis: "Oznaczone jako wojskowe przez adsb.lol, ograniczone do obserwowanego obszaru. Wiele maszyn nie nadaje ADS-B wcale — widać tylko te, które nadają.",
    kolor: rgb(RED),
    ksztalt: "kropka",
  },
  {
    id: "cywilne",
    grupa: "powietrze",
    nazwa: "Samoloty cywilne",
    opis: "Reszta ruchu w zasięgu odbiorników. Służy za tło: to na ich tle widać, że gdzieś robi się pusto.",
    kolor: rgb(GREY),
    ksztalt: "kropka",
  },
  {
    id: "ladunek",
    grupa: "morze",
    nazwa: "Statki z ładunkiem",
    opis: "Masowce i tankowce (kod AIS 70–89). Linia przed dziobem pokazuje, dokąd statek dopłynie w pół godziny obecnym kursem — jej długość to prędkość. Stojący nie ma linii.",
    kolor: rgb(SHIP_CARGO),
    ksztalt: "kropka",
  },
  {
    id: "statki",
    grupa: "morze",
    nazwa: "Pozostałe jednostki",
    opis: "Holowniki, pilotówki, promy, kutry. Większość ruchu i większość fałszywych alarmów — dlatego są osobno.",
    kolor: rgb(SHIP_OTHER),
    ksztalt: "kropka",
  },
  {
    id: "infrastruktura",
    grupa: "morze",
    nazwa: "Kable i rurociągi",
    // "Rurociagi", nie "gazociagi": wsrod 16 linii tej klasy sa Nord Stream i Baltic Pipe, ale tez
    // wylot sciekow w Helsinkach i wodociag pod Wyborgiem. Nazwanie ich wszystkich gazociagami
    // byloby dopisaniem do danych czegos, czego w nich nie ma.
    opis: "Kable energetyczne i telekomunikacyjne (fioletowe) oraz rurociągi (brązowe) z OpenStreetMap. To od tych linii detektor D6 liczy odległość statku — trasy są przybliżone, bo rysowali je ludzie, a nie geodeci.",
    kolor: rgb(KABEL),
    ksztalt: "linia",
  },
  {
    id: "alarmy",
    grupa: "detektory",
    nazwa: "Alarmy detektorów",
    opis: "Miejsca, które detektory uznały za warte sprawdzenia. Kandydat do sprawdzenia, nigdy wyrok.",
    kolor: "rgb(255,190,0)",
    ksztalt: "obwodka",
  },
  {
    id: "zaklocenia",
    grupa: "detektory",
    nazwa: "Zakłócenia GPS",
    opis: "Udział samolotów zgłaszających obniżoną dokładność nawigacji. Bursztyn 2–10%, czerwony powyżej 10%.",
    kolor: "rgb(230,57,70)",
    ksztalt: "heksagon",
  },
];

/** The bounds behind every count on this screen, written out so a reader can check them. */
export const OBSZAR = { minLat: 48, maxLat: 70, minLon: 0, maxLon: 40 };

export function opisObszaru(): string {
  return `Obszar: ${OBSZAR.minLat}–${OBSZAR.maxLat}°N, ${OBSZAR.minLon}–${OBSZAR.maxLon}°E`;
}

export type Widoczne = Record<IdWarstwy, boolean>;

export const WSZYSTKO_WIDOCZNE: Widoczne = {
  wojskowe: true,
  cywilne: true,
  ladunek: true,
  statki: true,
  // Wlaczona domyslnie, bo alarm D6 mowi "0,1 km od linii" i bez tej linii jest nieweryfikowalny.
  infrastruktura: true,
  alarmy: true,
  zaklocenia: true,
};

/** The descriptors of one group, in the order they are declared. */
export function wGrupie(grupa: Grupa): OpisWarstwy[] {
  return WARSTWY.filter((w) => w.grupa === grupa);
}

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
export type Liczby = Record<IdWarstwy, number>;

export function policz(id: IdWarstwy, liczby: Liczby): number {
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
 *
 * The name is "obserwowany obszar" and the bounds are printed in the legend, because the first
 * wording - "Baltyk i podejscia" - was itself untrue: 48-70 N / 0-40 E takes in Paris, Prague,
 * Vienna and Moscow. Seen by looking at the map at 2560px, where red military marks sit over
 * Luxembourg and Warsaw, which is nobody's idea of a Baltic approach.
 */
export function stanDanych(
  polaczone: boolean,
  samolotow: number,
  statkow: number,
  sekundOdOdczytu: number | null,
): string {
  if (!polaczone) return "Brak połączenia z serwerem";
  if (samolotow === 0 && statkow === 0) return "Połączono — w obszarze nic nie widać";

  // Obie domeny w jednym zdaniu, bo obie sa na mapie. Wczesniej liczyly sie same samoloty i mapa
  // milczala o osmiuset statkach, ktore na niej byly.
  const czesci = [
    samolotow > 0 ? `${samolotow} ${odmiana(samolotow, "samolot", "samoloty", "samolotów")}` : null,
    statkow > 0 ? `${statkow} ${odmiana(statkow, "statek", "statki", "statków")}` : null,
  ].filter(Boolean);

  const wiek =
    sekundOdOdczytu === null
      ? ""
      : sekundOdOdczytu < 15
        ? " · odświeżono przed chwilą"
        : sekundOdOdczytu < 90
          ? ` · odświeżono ${sekundOdOdczytu} s temu`
          : ` · odświeżono ${Math.round(sekundOdOdczytu / 60)} min temu`;

  return `${czesci.join(" · ")}${wiek}`;
}

/** Polish counts three ways, and "126 samolot" in a header reads as a bug in the data. */
export function odmiana(n: number, jeden: string, kilka: string, wiele: string): string {
  const abs = Math.abs(n) % 100;
  const ostatnia = abs % 10;
  if (abs === 1) return jeden;
  if (ostatnia >= 2 && ostatnia <= 4 && (abs < 12 || abs > 14)) return kilka;
  return wiele;
}
