import { describe, expect, it } from "vitest";
import {
  cienkiKonflikt, nadSzuflada, osCzasu, podpisZdarzenia, pustoKonflikty, pustoWersje, pustoZdarzenia,
  szczyt, tytulZdarzenia, ZOOM_ZDARZENIA, type KonfliktDto, type ZdarzenieDto,
} from "./konflikty";

const z = (o: Partial<ZdarzenieDto> & { id: string }): ZdarzenieDto => ({
  ts: "2026-09-28T10:00:00Z", kind: "walka", actor1: "RUS", actor2: "UKR", place: "Charków",
  lat: 50, lon: 36.2, goldstein: -9.5, sources: 4, url: "https://example.org/a", mentions: 12, ...o,
});

const k = (o: Partial<KonfliktDto> & { id: string }): KonfliktDto => ({
  nazwa: "Rosja – Ukraina", actor1: "RUS", actor2: "UKR", events: 120,
  lastEventAt: "2026-09-28T10:00:00Z", ...o,
});

describe("opis zdarzenia", () => {
  it("dwaj aktorzy i rodzaj dzialania", () => {
    expect(tytulZdarzenia(z({ id: "1" }))).toBe("RUS → UKR: walka");
  });

  it("brak drugiego aktora nie zostawia wiszacej strzalki", () => {
    expect(tytulZdarzenia(z({ id: "1", actor2: null }))).toBe("RUS: walka");
  });

  it("brak pierwszego aktora jest nazwany, a nie pusty", () => {
    expect(tytulZdarzenia(z({ id: "1", actor1: null }))).toBe("nieznany aktor → UKR: walka");
  });
});

describe("podpis zdarzenia", () => {
  it("godzina jest w UTC i tak podpisana", () => {
    // Front ciagnie sie przez trzy strefy czasowe; godzina bez strefy znaczylaby co innego
    // dla kazdego czytelnika, a GDELT i tak podaje UTC.
    expect(podpisZdarzenia(z({ id: "1", ts: "2026-09-28T10:05:00Z" }))).toMatch(/^10:05 UTC/);
  });

  it("jedna redakcja odmienia sie inaczej niz wiele", () => {
    expect(podpisZdarzenia(z({ id: "1", sources: 1 }))).toMatch(/1 redakcja/);
    expect(podpisZdarzenia(z({ id: "1", sources: 9 }))).toMatch(/9 redakcji/);
  });

  it("brak miejsca nie zostawia pustego czlonu", () => {
    const czesci = podpisZdarzenia(z({ id: "1", place: null })).split(" · ");
    expect(czesci.every((c) => c.trim().length > 0)).toBe(true);
  });
});

describe("os czasu", () => {
  const godzina = (h: number) => z({ id: `e${h}`, ts: `2026-09-28T${String(h).padStart(2, "0")}:00:00Z` });

  it("kazde zdarzenie wpada do dokladnie jednego kubelka", () => {
    // Niezmiennik calej osi: gdyby oś liczyla sie z zadanego okna, a nie z danych, zdarzenie tuz
    // za jego krawedzia albo znikaloby z wykresu, albo rysowalo sie w zlym slupku.
    const dane = [0, 1, 2, 5, 5, 5, 9, 23].map(godzina);
    expect(osCzasu(dane).reduce((a, x) => a + x.ile, 0)).toBe(dane.length);
  });

  it("najpozniejsze zdarzenie ląduje w ostatnim kubelku, nie poza osia", () => {
    const os = osCzasu([godzina(0), godzina(23)], 24);
    expect(os).toHaveLength(24);
    expect(os[os.length - 1].ile).toBe(1);
  });

  it("brak zdarzen to brak osi, a nie os z zerami", () => {
    expect(osCzasu([])).toEqual([]);
  });

  it("wszystko w jednej chwili daje jeden slupek, nie 23 puste obok pelnego", () => {
    const os = osCzasu([godzina(7), godzina(7), godzina(7)]);
    expect(os).toHaveLength(1);
    expect(os[0].ile).toBe(3);
  });

  it("etykieta osi jest godzina UTC", () => {
    expect(osCzasu([godzina(6), godzina(18)], 2)[0].etykieta).toBe("06:00");
  });

  it("szczyt to najwyzszy slupek", () => {
    expect(szczyt(osCzasu([godzina(1), godzina(1), godzina(9)], 2))).toBe(2);
    expect(szczyt([])).toBe(0);
  });
});

describe("trzy rozne pustki maja trzy rozne zdania", () => {
  const teksty = [pustoKonflikty(true), pustoZdarzenia("Rosja – Ukraina", 24, true), pustoWersje(true)];

  it("zadne dwa nie brzmia tak samo", () => {
    expect(new Set(teksty).size).toBe(3);
  });

  it("brak konfliktow to stan zbioru, nie stan swiata", () => {
    expect(pustoKonflikty(true)).toMatch(/stan zbioru, nie stan świata/);
  });

  it("brak zdarzen nazywa konflikt i okno, i podpowiada szersze", () => {
    const t = pustoZdarzenia("Rosja – Ukraina", 6, true);
    expect(t).toMatch(/Rosja – Ukraina/);
    expect(t).toMatch(/6 h/);
    expect(t).toMatch(/szerszego okna/);
  });

  it("brak wersji mowi, ze zdarzenie ISTNIEJE, a porownania nie ma", () => {
    // Najglebsza z trzech pustek. Czytana jak najplytsza ("nic sie nie stalo") bylaby klamstwem.
    const t = pustoWersje(true);
    expect(t).toMatch(/Zdarzenie istnieje/);
    expect(t).toMatch(/nie zgadujemy/);
  });
});

describe("brak odpowiedzi to nie to samo co pusta odpowiedz", () => {
  it("na kazdym z trzech poziomow awaria brzmi inaczej niz cisza", () => {
    expect(pustoKonflikty(false)).not.toBe(pustoKonflikty(true));
    expect(pustoZdarzenia("X", 24, false)).not.toBe(pustoZdarzenia("X", 24, true));
    expect(pustoWersje(false)).not.toBe(pustoWersje(true));
  });

  it("awaria nie twierdzi, ze cokolwiek sprawdzono", () => {
    expect(pustoKonflikty(false)).toMatch(/nic nie widzimy/);
    expect(pustoKonflikty(false)).not.toMatch(/stan zbioru/);
    expect(pustoWersje(false)).not.toMatch(/Zdarzenie istnieje/);
  });
});

describe("wysrodkowanie nad szuflada", () => {
  it("bez zaslony srodek zostaje tam, gdzie jest zdarzenie", () => {
    expect(nadSzuflada(49.99, ZOOM_ZDARZENIA, 0)).toBe(49.99);
  });

  it("zaslonieta dol ekranu przesuwa SRODEK na poludnie, zeby zdarzenie wyszlo nad szuflade", () => {
    // Widoczny pasek mapy jest u gory, wiec srodek musi zejsc pod zdarzenie. Odwrotny znak wpycha
    // zdarzenie jeszcze glebiej pod panel, ktory je opisuje - i tak wygladal pierwszy zrzut.
    expect(nadSzuflada(49.99, ZOOM_ZDARZENIA, 600)).toBeLessThan(49.99);
  });

  it("im blizej, tym mniejsze przesuniecie w stopniach", () => {
    const daleko = 49.99 - nadSzuflada(49.99, 4, 600);
    const blisko = 49.99 - nadSzuflada(49.99, 9, 600);
    expect(blisko).toBeLessThan(daleko);
  });

  it("nie wyjezdza poza zakres Mercatora", () => {
    expect(nadSzuflada(-84.9, 2, 4000)).toBeGreaterThanOrEqual(-85);
  });
});

describe("cienki konflikt", () => {
  it("jedno zdarzenie to artefakt grupowania, nie wojna", () => {
    expect(cienkiKonflikt(k({ id: "a", events: 1 }))).toBe(true);
    expect(cienkiKonflikt(k({ id: "b", events: 2 }))).toBe(false);
  });
});
