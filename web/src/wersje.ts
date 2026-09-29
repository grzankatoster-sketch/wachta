/**
 * One event, told by several sides: how many articles, in which languages, with what tone.
 *
 * This module is the front end of `wachta_detectors/versions.py` and inherits its discipline
 * word for word. Three rules govern every sentence produced here:
 *
 *   * it does not say who is lying. It shows that the coverage differs, and by how much;
 *   * tone is a property of the TEXT, not of the world. Every phrasing below talks about how
 *     something was written, never about whether it happened;
 *   * a side with one article is not "a side". The same is true of a side whose outlets were
 *     guessed from a country domain rather than named on the list.
 *
 * The third rule is the one that needs code rather than good intentions. A thin comparison and a
 * solid one look IDENTICAL on screen - two sides, two counts, a tone gap - so the thinness has to
 * be rendered as loudly as the numbers it undermines, or the view lies exactly when it knows least.
 */

/** Side codes as the detector emits them. Order here is the tie-break order on screen. */
export const KODY_STRON = ["UA", "RU", "RU-niezalezne", "BY", "BY-niezalezne", "PL", "ZACHOD"] as const;
export type KodStrony = (typeof KODY_STRON)[number];

export interface StronaDto {
  side: string;
  articles: number;
  meanTone: number;
  languages: string[];
  examples: string[];
  /** How many of this side's articles got their side GUESSED from the country domain. */
  fromTld: number;
  /** True when nothing on this side was a named outlet - the whole voice is an assumption. */
  onlyGuessed: boolean;
}

export interface WersjeDto {
  eventId: string;
  totalArticles: number;
  toneGap: number;
  isWeak: boolean;
  sides: StronaDto[];
}

export interface NazwaStrony {
  /** Fits in a table column. */
  krotka: string;
  /** One line: whose voice this is, said plainly. */
  pelna: string;
}

/**
 * Polish captions for the side codes.
 *
 * RU and RU-niezalezne are two entries and must stay two entries. Merging them is the single
 * easiest way to wreck this view: the state broadcasters and the exiled newsrooms write about the
 * same strike in opposite registers, so averaging them produces a "Russian tone" that nobody in
 * Russia published and that hides the only interesting fact in the data - that the disagreement
 * runs INSIDE a country as well as between countries. The same holds for BY. The labels therefore
 * never share a name, and `wierszeStron` never groups by the country prefix.
 */
export const NAZWY_STRON: Record<KodStrony, NazwaStrony> = {
  UA: { krotka: "UA · ukraińskie", pelna: "Ukraina — media ukraińskie" },
  RU: { krotka: "RU · państwowe", pelna: "Rosja — media państwowe i prorządowe" },
  "RU-niezalezne": {
    krotka: "RU · niezależne",
    pelna: "Rosja — redakcje niezależne, w większości nadające z emigracji",
  },
  BY: { krotka: "BY · państwowe", pelna: "Białoruś — media państwowe" },
  "BY-niezalezne": {
    krotka: "BY · niezależne",
    pelna: "Białoruś — redakcje niezależne, w większości nadające z emigracji",
  },
  PL: { krotka: "PL · polskie", pelna: "Polska — media polskie" },
  ZACHOD: { krotka: "Zachód", pelna: "Zachód — redakcje z Europy Zachodniej i Ameryki Północnej" },
};

/**
 * Caption for one side code.
 *
 * An unknown code is shown as itself rather than swallowed or renamed. A new side appearing in the
 * data policy is a change somebody made on purpose; the view should show it arriving, not hide it
 * behind "inne" until a front-end developer notices.
 */
export function etykietaStrony(kod: string): NazwaStrony {
  return NAZWY_STRON[kod as KodStrony] ?? { krotka: kod, pelna: `Strona spoza listy (${kod})` };
}

/** GDELT's srclc codes for the languages that actually show up around this war. */
const JEZYKI: Record<string, string> = {
  ara: "arabski", bel: "białoruski", ces: "czeski", dan: "duński", deu: "niemiecki",
  ell: "grecki", eng: "angielski", est: "estoński", fin: "fiński", fra: "francuski",
  hun: "węgierski", hye: "ormiański", ita: "włoski", jpn: "japoński", kat: "gruziński",
  kaz: "kazachski", lav: "łotewski", lit: "litewski", nld: "niderlandzki", nor: "norweski",
  pol: "polski", ron: "rumuński", rus: "rosyjski", slk: "słowacki", spa: "hiszpański",
  swe: "szwedzki", tur: "turecki", ukr: "ukraiński", zho: "chiński",
};

/**
 * The languages of a side, as a sentence.
 *
 * An empty list is NOT "no languages". GDELT records a source language only for articles it
 * translated, so an empty list means "everything here came in already-English text, or the feed
 * did not say". Printing "brak" would turn a gap in the metadata into a fact about the press.
 */
export function jezykiZdanie(kody: string[]): string {
  if (kody.length === 0) return "język oryginału nieodnotowany (GDELT podaje go tylko przy tłumaczeniu)";
  return kody.map((k) => JEZYKI[k] ?? k).join(", ");
}

/**
 * A tone number as text: "-6,2".
 *
 * `toFixed` produces "-0.0" for a small negative, which reads as a deliberate minus sign on a zero
 * and invites the reader to see a leaning that the rounding just erased.
 */
export function formatujWydzwiek(t: number): string {
  const s = t.toFixed(1);
  return (s === "-0.0" ? "0.0" : s).replace(".", ",");
}

/**
 * What the tone number says ABOUT THE TEXT.
 *
 * Every adjective here has "tekst" in front of it on purpose. "Negatywny" alone slides into a
 * verdict on the event; "tekst negatywny" stays a statement about the writing, which is all GDELT
 * measured.
 */
export function opisWydzwieku(t: number): string {
  const liczba = formatujWydzwiek(t);
  if (t <= -5) return `${liczba} — tekst skrajnie negatywny w wyrazie`;
  if (t <= -2) return `${liczba} — tekst negatywny w wyrazie`;
  if (t < 2) return `${liczba} — tekst neutralny w wyrazie`;
  if (t < 5) return `${liczba} — tekst pozytywny w wyrazie`;
  return `${liczba} — tekst bardzo pozytywny w wyrazie`;
}

export interface WierszStrony {
  kod: string;
  krotka: string;
  pelna: string;
  artykuly: number;
  /** Share of ALL articles on the event, including the ones assigned to no side (0..1). */
  udzial: number;
  wydzwiek: number;
  opisWydzwieku: string;
  jezyki: string;
  przyklady: string[];
  /** Why this row on its own makes the comparison thin. Empty when it does not. */
  ostrzezenia: string[];
  slaba: boolean;
}

/**
 * Warnings that belong to ONE side.
 *
 * Kept separate from the whole-comparison warning because they answer a different question: not
 * "can I trust this comparison" but "which of these two bars is the hollow one". A reader who sees
 * only the banner still has to guess which side to discount.
 */
export function ostrzezeniaStrony(s: StronaDto): string[] {
  const out: string[] = [];
  if (s.articles < 2) out.push("tylko 1 artykuł — to jeden tekst, nie „strona”");
  if (s.onlyGuessed) {
    out.push("wszystkie przypisania zgadnięte z domeny kraju, żadnej redakcji z listy");
  } else if (s.fromTld > 0) {
    // Not enough to make the detector call the comparison weak, but the reader still deserves to
    // know that part of this voice is an assumption about what a country domain implies.
    out.push(`${s.fromTld} z ${s.articles} przypisań zgadnięte z domeny kraju`);
  }
  return out;
}

/**
 * Articles counted on the event that belong to no side at all.
 *
 * The detector drops an unassigned outlet rather than guess (see versions.py: "better a missing
 * voice than a wrongly labelled one"). That silence is information: a comparison where 4 of 40
 * articles were placed is a comparison of the margins, and the bars alone would never say so.
 */
export function nieprzypisane(w: WersjeDto): number {
  const suma = w.sides.reduce((acc, s) => acc + s.articles, 0);
  return Math.max(0, w.totalArticles - suma);
}

/**
 * Display rows, biggest voice first.
 *
 * Denominator for the bars is every article on the event, not just the placed ones, so a side with
 * three articles out of forty draws a short bar instead of a full one.
 */
export function wierszeStron(w: WersjeDto): WierszStrony[] {
  const suma = w.sides.reduce((acc, s) => acc + s.articles, 0);
  const mianownik = Math.max(w.totalArticles, suma, 1);
  return [...w.sides]
    .sort((a, b) => b.articles - a.articles || etykietaStrony(a.side).krotka.localeCompare(etykietaStrony(b.side).krotka, "pl"))
    .map((s) => {
      const ostrzezenia = ostrzezeniaStrony(s);
      return {
        kod: s.side,
        krotka: etykietaStrony(s.side).krotka,
        pelna: etykietaStrony(s.side).pelna,
        artykuly: s.articles,
        udzial: s.articles / mianownik,
        wydzwiek: s.meanTone,
        opisWydzwieku: opisWydzwieku(s.meanTone),
        jezyki: jezykiZdanie(s.languages),
        przyklady: s.examples,
        ostrzezenia,
        slaba: s.articles < 2 || s.onlyGuessed,
      };
    });
}

export interface OstrzezenieCalosci {
  naglowek: string;
  punkty: string[];
}

/**
 * The banner that has to sit ABOVE the numbers when the comparison rests on thin ground.
 *
 * It trusts the detector's `isWeak` but does not depend on it: the same condition is re-derived
 * from the sides, so an API that forgets the flag still produces the warning. Getting this wrong
 * in the direction of silence is the failure mode this whole view was built to avoid, and a
 * duplicated three-line check is a cheap insurance against it.
 */
export function ostrzezenieCalosci(w: WersjeDto): OstrzezenieCalosci | null {
  const cienkie = w.sides.filter((s) => s.articles < 2);
  const zgadniete = w.sides.filter((s) => s.onlyGuessed);
  if (!w.isWeak && cienkie.length === 0 && zgadniete.length === 0) return null;

  const punkty: string[] = [];
  for (const s of cienkie) {
    punkty.push(`„${etykietaStrony(s.side).krotka}” to jeden artykuł — jeden tekst nie reprezentuje strony.`);
  }
  for (const s of zgadniete) {
    punkty.push(
      `„${etykietaStrony(s.side).krotka}” zebrano wyłącznie po domenie kraju, bez żadnej redakcji z listy — ` +
      "pod krajową domeną publikuje też sklep rowerowy.",
    );
  }
  if (punkty.length === 0) {
    // isWeak came from the detector for a reason this build cannot name. Say that, do not invent one.
    punkty.push("Detektor oznaczył to porównanie jako oparte na cienkich danych.");
  }
  return { naglowek: "Cienka podstawa — czytaj te liczby z rezerwą", punkty };
}

export type StanRozjazdu = "brak-porownania" | "zbiezne" | "rozne" | "skrajne";

export interface Rozjazd {
  stan: StanRozjazdu;
  naglowek: string;
  zdanie: string;
}

/**
 * Whether the tellings diverge - and the case where that question has no answer.
 *
 * `toneGap` is 0.0 both when two sides wrote in the same register and when there is only one side
 * to look at. Those two zeros mean opposite things: "they agree" and "nobody checked". Rendering
 * them the same way is how a single article becomes evidence of consensus.
 */
export function rozjazd(w: WersjeDto): Rozjazd {
  if (w.sides.length < 2) {
    return {
      stan: "brak-porownania",
      naglowek: "Nie ma czego porównywać",
      zdanie:
        "Tylko jedna strona opisała to zdarzenie w tym zbiorze. Zerowa różnica wydźwięku nie znaczy " +
        "tu zgody — znaczy, że nie ma drugiego opisu.",
    };
  }
  const luka = formatujWydzwiek(w.toneGap);
  if (w.toneGap < 2) {
    return {
      stan: "zbiezne",
      naglowek: "Opisy brzmią podobnie",
      zdanie:
        `Między skrajnymi stronami ${luka} punktu różnicy wydźwięku. Teksty są utrzymane w zbliżonym ` +
        "tonie — co nie znaczy, że mówią to samo: ton mierzy wyraz, nie treść.",
    };
  }
  if (w.toneGap < 5) {
    return {
      stan: "rozne",
      naglowek: "Opisy się rozjeżdżają",
      zdanie: `Między skrajnymi stronami ${luka} punktu różnicy wydźwięku. Te same zdarzenie opisano w różnym tonie.`,
    };
  }
  return {
    stan: "skrajne",
    naglowek: "Opisy rozjeżdżają się mocno",
    zdanie:
      `Między skrajnymi stronami ${luka} punktu różnicy wydźwięku. To jedne z najdalszych opisów, ` +
      "jakie ta skala pokazuje — nadal jednak mówimy o tonie tekstów, nie o tym, która relacja jest bliższa prawdy.",
  };
}

/**
 * The sentence that must never be dropped from the versions panel.
 *
 * Without it the view is two bars and a difference, which any reader will finish in their head as
 * "so the other side is lying". The whole point of the module is that it cannot say that.
 */
export const ZASTRZEZENIE_WYDZWIEKU =
  "Wydźwięk to cecha tekstu, nie świata: mierzy, JAK coś napisano, nie czy to prawda. Ten widok " +
  "pokazuje, że relacje się różnią — nie, kto kłamie.";

/**
 * The sentence about what is missing from the bars.
 *
 * Only shown when something actually is missing, so it stays a fact about this event rather than
 * boilerplate the reader learns to skip.
 */
export function zdanieONieprzypisanych(ile: number, wszystkich: number): string | null {
  if (ile <= 0) return null;
  return (
    `${ile} z ${wszystkich} artykułów nie trafiło do żadnej strony — ich redakcji nie ma na liście ` +
    "przypisań. Nie zgadujemy za nie: lepiej brakujący głos niż źle podpisany."
  );
}
