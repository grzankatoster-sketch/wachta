import type { LiveAircraft, LiveShip } from "./api";

/**
 * What kind of thing each mark is, and therefore what it looks like.
 *
 * Two classifications, both deliberately shallow. ADS-B gives an ICAO type designator and a military
 * flag; AIS gives a two-digit type code. Neither says what an aircraft or a ship is DOING, and this
 * file does not pretend otherwise - it turns a code into a category so the map can draw it, and the
 * category is named on screen so a reader can disagree with it.
 *
 * The aircraft table is a heuristic and is labelled as one wherever it is shown. A type designator
 * is a make and model, not a mission: a P-8 is a maritime patrol airframe and is also, sometimes, a
 * transport; an A330 is an airliner and is also, in some air forces, a tanker. The table catches the
 * airframes whose model settles the question in practice, and everything it does not recognise stays
 * "wojskowy" or "cywilny" rather than being guessed into a box.
 */

export type KategoriaPowietrzna =
  | "rozpoznanie" | "tankowanie" | "transport" | "smiglowiec" | "mysliwiec" | "wojskowy" | "cywilny";

export type KategoriaMorska =
  | "tankowiec" | "masowiec" | "pasazerski" | "rybacki" | "wojskowy-m" | "sluzbowy" | "inny";

export type Kategoria = KategoriaPowietrzna | KategoriaMorska;

export type Ksztalt = "samolot" | "smiglowiec" | "statek";

export interface OpisKategorii {
  nazwa: string;
  kolor: [number, number, number];
  ksztalt: Ksztalt;
  /** Relative mark size. Bigger is not "more important" - it is "there are fewer of them". */
  rozmiar: number;
}

/**
 * Colours are measured against the basemap, not against the panel they are listed on.
 *
 * Every value below clears 3:1 against both the land fill (242,243,240) and the sea fill
 * (194,200,202) of the positron basemap - the surfaces the marks actually sit on. Several of them
 * would fail against the dark legend panel, which is why the legend draws its swatch on a light
 * chip in the basemap's own colour: the key then has exactly the contrast the map has, instead of
 * the palette being bent to satisfy two backgrounds at once and serving neither.
 */
export const KATEGORIE: Record<Kategoria, OpisKategorii> = {
  rozpoznanie: { nazwa: "Rozpoznanie i dozór", kolor: [150, 20, 120], ksztalt: "samolot", rozmiar: 19 },
  tankowanie:  { nazwa: "Tankowanie w powietrzu", kolor: [176, 74, 0], ksztalt: "samolot", rozmiar: 20 },
  transport:   { nazwa: "Transport wojskowy", kolor: [120, 72, 20], ksztalt: "samolot", rozmiar: 20 },
  smiglowiec:  { nazwa: "Śmigłowce", kolor: [96, 48, 150], ksztalt: "smiglowiec", rozmiar: 16 },
  mysliwiec:   { nazwa: "Samoloty bojowe", kolor: [200, 30, 45], ksztalt: "samolot", rozmiar: 16 },
  wojskowy:    { nazwa: "Inne wojskowe", kolor: [230, 57, 70], ksztalt: "samolot", rozmiar: 17 },
  cywilny:     { nazwa: "Cywilne", kolor: [96, 103, 110], ksztalt: "samolot", rozmiar: 13 },

  tankowiec:   { nazwa: "Tankowce", kolor: [11, 94, 120], ksztalt: "statek", rozmiar: 17 },
  masowiec:    { nazwa: "Masowce i drobnicowce", kolor: [20, 86, 158], ksztalt: "statek", rozmiar: 16 },
  pasazerski:  { nazwa: "Pasażerskie i promy", kolor: [14, 110, 90], ksztalt: "statek", rozmiar: 15 },
  rybacki:     { nazwa: "Rybackie", kolor: [122, 86, 30], ksztalt: "statek", rozmiar: 12 },
  "wojskowy-m":{ nazwa: "Okręty", kolor: [140, 40, 40], ksztalt: "statek", rozmiar: 16 },
  sluzbowy:    { nazwa: "Holowniki i jednostki portowe", kolor: [70, 98, 125], ksztalt: "statek", rozmiar: 12 },
  inny:        { nazwa: "Pozostałe jednostki", kolor: [96, 110, 120], ksztalt: "statek", rozmiar: 11 },
};

/**
 * ICAO type designators whose airframe settles the mission in practice.
 *
 * Not a complete list and not meant to be - it covers what actually shows up over the Baltic. An
 * unlisted military airframe stays "wojskowy", which is true, rather than being pushed into the
 * nearest box, which might not be.
 */
const TYPY_POWIETRZNE: Array<[KategoriaPowietrzna, string[]]> = [
  ["rozpoznanie", ["RC13", "RC135", "RC12", "P8", "P3", "EP3", "RQ4", "MQ9", "E3TF", "E3CF", "E6",
                   "E8", "U2", "SW4", "CL60", "GLF5", "ASTR", "F900", "P1"]],
  ["tankowanie",  ["K35R", "K35E", "KC10", "KC30", "KC46", "VOYA", "A332", "A310", "TRIS"]],
  ["transport",   ["C17", "C130", "C30J", "C160", "A400", "C5M", "AN12", "AN26", "AN124", "C295",
                   "CN35", "C295", "C27J", "SB20"]],
  ["smiglowiec",  ["H60", "UH60", "H64", "H47", "EC35", "EC45", "EC20", "AS32", "AS50", "NH90",
                   "MI8", "MI17", "A139", "A169", "S92", "H225", "UH1", "EH10", "R44", "B06"]],
  ["mysliwiec",   ["F16", "F15", "F18", "F35", "F22", "EUFI", "TYPH", "GRIP", "RFAL", "MG29",
                   "SU27", "SU24", "A10", "HAWK", "M346", "L39"]],
];

export function kategoriaSamolotu(a: LiveAircraft): KategoriaPowietrzna {
  const kod = (a.typeCode ?? "").trim().toUpperCase();
  if (kod) {
    for (const [kategoria, kody] of TYPY_POWIETRZNE) {
      if (kody.includes(kod)) return kategoria;
    }
  }
  return a.isMilitary ? "wojskowy" : "cywilny";
}

/** AIS type codes. The ranges are the standard ones; 35 is the only single code worth its own class. */
export function kategoriaStatku(s: LiveShip): KategoriaMorska {
  const n = Number(s.shipType);
  if (!Number.isFinite(n) || n <= 0) return "inny";
  if (n >= 80 && n <= 89) return "tankowiec";
  if (n >= 70 && n <= 79) return "masowiec";
  if (n >= 60 && n <= 69) return "pasazerski";
  if (n === 35) return "wojskowy-m";
  if (n === 30) return "rybacki";
  if (n >= 50 && n <= 59) return "sluzbowy";
  return "inny";
}

/** Which categories are actually on screen, in the order KATEGORIE declares them. */
export function obecne(kategorie: Kategoria[]): Array<{ id: Kategoria; ile: number }> {
  const licznik = new Map<Kategoria, number>();
  for (const k of kategorie) licznik.set(k, (licznik.get(k) ?? 0) + 1);
  return (Object.keys(KATEGORIE) as Kategoria[])
    .filter((k) => licznik.has(k))
    .map((id) => ({ id, ile: licznik.get(id)! }));
}
