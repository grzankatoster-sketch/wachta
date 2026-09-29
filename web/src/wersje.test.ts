import { describe, expect, it } from "vitest";
import {
  etykietaStrony, formatujWydzwiek, jezykiZdanie, KODY_STRON, NAZWY_STRON, nieprzypisane,
  opisWydzwieku, ostrzezeniaStrony, ostrzezenieCalosci, rozjazd, wierszeStron,
  zdanieONieprzypisanych, ZASTRZEZENIE_WYDZWIEKU, type StronaDto, type WersjeDto,
} from "./wersje";

const strona = (o: Partial<StronaDto> & { side: string }): StronaDto => ({
  articles: 5, meanTone: -4, languages: [], examples: [], fromTld: 0, onlyGuessed: false, ...o,
});

const wersje = (o: Partial<WersjeDto> & { sides: StronaDto[] }): WersjeDto => ({
  eventId: "e1",
  totalArticles: o.sides.reduce((a, s) => a + s.articles, 0),
  toneGap: 0,
  isWeak: false,
  ...o,
});

describe("strony jako osobne glosy", () => {
  it("kazda strona ma wlasna, niepowtarzalna etykiete", () => {
    const krotkie = KODY_STRON.map((k) => NAZWY_STRON[k].krotka);
    expect(new Set(krotkie).size).toBe(KODY_STRON.length);
  });

  it("media panstwowe i niezalezne z tego samego kraju to DWA rozne podpisy", () => {
    // Celowa decyzja analityczna projektu: RU i RU-niezalezne pisza o tym samym uderzeniu w
    // przeciwnych rejestrach. Wspolna etykieta zlalaby je w "ton rosyjski", ktorego nikt nie
    // opublikowal, i schowala jedyna ciekawa rzecz w danych - spor WEWNATRZ kraju.
    expect(NAZWY_STRON.RU.krotka).not.toBe(NAZWY_STRON["RU-niezalezne"].krotka);
    expect(NAZWY_STRON.BY.krotka).not.toBe(NAZWY_STRON["BY-niezalezne"].krotka);
    expect(NAZWY_STRON["RU-niezalezne"].pelna).toMatch(/niezależn/);
  });

  it("nie laczy RU z RU-niezalezne w jeden wiersz", () => {
    const w = wersje({ sides: [strona({ side: "RU", articles: 8 }), strona({ side: "RU-niezalezne", articles: 3 })] });
    const wiersze = wierszeStron(w);
    expect(wiersze).toHaveLength(2);
    expect(wiersze.map((x) => x.kod)).toEqual(["RU", "RU-niezalezne"]);
    expect(wiersze.map((x) => x.artykuly)).toEqual([8, 3]);
  });

  it("kod spoza listy pokazuje sie soba, nie znika i nie zmienia nazwy", () => {
    expect(etykietaStrony("KZ").krotka).toBe("KZ");
    expect(etykietaStrony("KZ").pelna).toMatch(/spoza listy/);
  });
});

describe("wiersze stron", () => {
  it("najliczniejszy glos idzie pierwszy", () => {
    const w = wersje({ sides: [strona({ side: "PL", articles: 2 }), strona({ side: "UA", articles: 9 })] });
    expect(wierszeStron(w).map((s) => s.kod)).toEqual(["UA", "PL"]);
  });

  it("pasek liczy sie z WSZYSTKICH artykulow o zdarzeniu, takze nieprzypisanych", () => {
    // Trzy artykuly z czterdziestu to trzy artykuly z czterdziestu, a nie polowa glosow.
    const w = wersje({
      sides: [strona({ side: "UA", articles: 3 }), strona({ side: "RU", articles: 3 })],
      totalArticles: 40,
    });
    expect(wierszeStron(w)[0].udzial).toBeCloseTo(3 / 40);
  });

  it("zerowa suma z serwera nie daje NaN na szerokosci paska", () => {
    const w = wersje({ sides: [strona({ side: "UA", articles: 0 })], totalArticles: 0 });
    expect(Number.isFinite(wierszeStron(w)[0].udzial)).toBe(true);
  });
});

describe("wydzwiek mowi o TEKSCIE, nie o prawdzie", () => {
  it("kazdy opis wydzwieku nazywa tekst", () => {
    for (const t of [-9, -6, -3, -1, 0, 1, 3, 6, 9]) {
      expect(opisWydzwieku(t), `ton ${t}`).toMatch(/tekst/);
    }
  });

  it("zaden opis nie orzeka o prawdzie ani o klamstwie", () => {
    for (const t of [-9, -3, 0, 3, 9]) {
      expect(opisWydzwieku(t)).not.toMatch(/prawd|kłam|klam|fałsz|falsz|propagand/i);
    }
  });

  it("liczba ma przecinek i nie udaje minusowego zera", () => {
    expect(formatujWydzwiek(-6.23)).toBe("-6,2");
    // "-0,0" czyta sie jak celowy minus na zerze i sugeruje przechyl, ktory zaokraglenie wlasnie starlo.
    expect(formatujWydzwiek(-0.04)).toBe("0,0");
  });
});

describe("jezyki", () => {
  it("tlumaczy kody na polskie nazwy", () => {
    expect(jezykiZdanie(["rus", "ukr"])).toBe("rosyjski, ukraiński");
  });

  it("nieznany kod zostaje soba", () => {
    expect(jezykiZdanie(["xyz"])).toBe("xyz");
  });

  it("pusta lista to luka w metadanych GDELT, a nie fakt o prasie", () => {
    const tekst = jezykiZdanie([]);
    expect(tekst).toMatch(/GDELT/);
    expect(tekst).toMatch(/tłumaczeni/);
  });
});

describe("ostrzezenia przy jednej stronie", () => {
  it("jeden artykul to nie strona", () => {
    expect(ostrzezeniaStrony(strona({ side: "PL", articles: 1 })).join(" ")).toMatch(/1 artykuł/);
  });

  it("same zgadniete domeny to zgloszone ostrzezenie", () => {
    const o = ostrzezeniaStrony(strona({ side: "RU", articles: 4, fromTld: 4, onlyGuessed: true }));
    expect(o.join(" ")).toMatch(/wszystkie przypisania zgadnięte z domeny kraju/);
  });

  it("czesciowe zgadywanie tez jest widoczne, choc nie robi porownania slabym", () => {
    const o = ostrzezeniaStrony(strona({ side: "RU", articles: 6, fromTld: 2 }));
    expect(o.join(" ")).toMatch(/2 z 6/);
  });

  it("solidna strona nie dostaje zadnego ostrzezenia", () => {
    expect(ostrzezeniaStrony(strona({ side: "UA", articles: 7 }))).toEqual([]);
  });
});

describe("ostrzezenie o cienkiej podstawie stoi NAD liczbami", () => {
  it("solidne porownanie nie dostaje bannera", () => {
    const w = wersje({ sides: [strona({ side: "UA", articles: 9 }), strona({ side: "RU", articles: 6 })] });
    expect(ostrzezenieCalosci(w)).toBeNull();
  });

  it("strona z jednym artykulem wywoluje banner i jest w nim nazwana", () => {
    const w = wersje({
      sides: [strona({ side: "UA", articles: 9 }), strona({ side: "RU", articles: 1 })],
      isWeak: true,
    });
    const o = ostrzezenieCalosci(w);
    expect(o).not.toBeNull();
    expect(o!.punkty.join(" ")).toMatch(/RU · państwowe/);
    expect(o!.punkty.join(" ")).toMatch(/jeden artykuł/);
  });

  it("strona zebrana z samych domen wywoluje banner", () => {
    const w = wersje({
      sides: [strona({ side: "UA", articles: 9 }), strona({ side: "RU", articles: 5, fromTld: 5, onlyGuessed: true })],
      isWeak: true,
    });
    expect(ostrzezenieCalosci(w)!.punkty.join(" ")).toMatch(/po domenie kraju/);
  });

  it("ostrzega takze wtedy, gdy API zapomnialo flagi isWeak", () => {
    // Milczenie jest tu jedynym bledem, ktory naprawde boli: cienkie porownanie bez ostrzezenia
    // wyglada identycznie jak solidne. Warunek jest wiec liczony jeszcze raz z samych stron.
    const w = wersje({
      sides: [strona({ side: "UA", articles: 9 }), strona({ side: "RU", articles: 1 })],
      isWeak: false,
    });
    expect(ostrzezenieCalosci(w)).not.toBeNull();
  });

  it("flaga isWeak bez czytelnego powodu nadal ostrzega, nie zmyslajac powodu", () => {
    const w = wersje({
      sides: [strona({ side: "UA", articles: 9 }), strona({ side: "RU", articles: 6 })],
      isWeak: true,
    });
    expect(ostrzezenieCalosci(w)!.punkty).toEqual(["Detektor oznaczył to porównanie jako oparte na cienkich danych."]);
  });
});

describe("rozjazd: zero roznicy znaczy dwie rozne rzeczy", () => {
  it("jedna strona to BRAK porownania, nie zgoda", () => {
    const w = wersje({ sides: [strona({ side: "UA", articles: 12 })], toneGap: 0 });
    const r = rozjazd(w);
    expect(r.stan).toBe("brak-porownania");
    expect(r.zdanie).toMatch(/nie ma drugiego opisu/);
    expect(r.naglowek).not.toMatch(/podobnie/);
  });

  it("dwie strony o zblizonym tonie to zgoda co do TONU, nie co do tresci", () => {
    const w = wersje({ sides: [strona({ side: "UA" }), strona({ side: "RU" })], toneGap: 0.4 });
    const r = rozjazd(w);
    expect(r.stan).toBe("zbiezne");
    expect(r.zdanie).toMatch(/nie znaczy, że mówią to samo/);
  });

  it("srednia i duza roznica maja osobne progi", () => {
    const dwie = [strona({ side: "UA" }), strona({ side: "RU" })];
    expect(rozjazd(wersje({ sides: dwie, toneGap: 1.99 })).stan).toBe("zbiezne");
    expect(rozjazd(wersje({ sides: dwie, toneGap: 2 })).stan).toBe("rozne");
    expect(rozjazd(wersje({ sides: dwie, toneGap: 4.99 })).stan).toBe("rozne");
    expect(rozjazd(wersje({ sides: dwie, toneGap: 5 })).stan).toBe("skrajne");
  });

  it("nawet przy skrajnym rozjezdzie nie orzeka, ktora relacja jest prawdziwa", () => {
    const r = rozjazd(wersje({ sides: [strona({ side: "UA" }), strona({ side: "RU" })], toneGap: 9 }));
    expect(r.zdanie).toMatch(/nie o tym, która relacja jest bliższa prawdy/);
  });
});

describe("glosy, ktorych nie policzono", () => {
  it("nieprzypisane to roznica miedzy suma stron a calkowita liczba artykulow", () => {
    const w = wersje({ sides: [strona({ side: "UA", articles: 3 })], totalArticles: 40 });
    expect(nieprzypisane(w)).toBe(37);
  });

  it("suma stron wieksza niz total nie daje liczby ujemnej", () => {
    const w = wersje({ sides: [strona({ side: "UA", articles: 9 })], totalArticles: 4 });
    expect(nieprzypisane(w)).toBe(0);
  });

  it("brak nieprzypisanych to brak zdania - nie zdanie o zerze", () => {
    expect(zdanieONieprzypisanych(0, 10)).toBeNull();
    expect(zdanieONieprzypisanych(37, 40)).toMatch(/37 z 40/);
  });
});

describe("zastrzezenie", () => {
  it("mowi, ze wydzwiek jest cecha tekstu, i ze widok nie wskazuje klamcy", () => {
    expect(ZASTRZEZENIE_WYDZWIEKU).toMatch(/cecha tekstu, nie świata/);
    expect(ZASTRZEZENIE_WYDZWIEKU).toMatch(/nie, kto kłamie/);
  });
});
