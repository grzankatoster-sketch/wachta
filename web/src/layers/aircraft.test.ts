import { describe, expect, it } from "vitest";
import { aircraftLayers, zKursem } from "./aircraft";
import { KATEGORIE } from "../typy";
import { BASEMAP_LAND, BASEMAP_SEA, GREY, LABEL, contrastRatio } from "../colors";
import type { LiveAircraft } from "../api";

const plane = (over: Partial<LiveAircraft>): LiveAircraft => ({
  hex: "3c6444", flight: "FORTE10", typeCode: "Q4", isMilitary: true, lat: 55, lon: 19,
  altBaroFt: 30000, onGround: false, gsKt: 400, trackDeg: 90, ts: "2026-09-28T08:00:00Z", ...over,
});

describe("warstwy samolotow", () => {
  it("etykieta wojskowa ma kolor czytelny na podkladzie, a nie bialy", () => {
    // Regresja: getColor bylo wpisane na sztywno jako [240,240,240] i napisy znikaly w tle.
    const labels = aircraftLayers([plane({})]).find((l) => l.id === "aircraft-labels");
    expect(labels, "warstwa etykiet").toBeDefined();
    const color = (labels!.props as unknown as { getColor: [number, number, number] }).getColor;
    expect(contrastRatio(color, BASEMAP_LAND)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(color, BASEMAP_SEA)).toBeGreaterThanOrEqual(4.5);
  });

  it("pomija samoloty na ziemi", () => {
    const layers = aircraftLayers([plane({ onGround: true }), plane({ hex: "abc123" })]);
    expect((layers[0].props as unknown as { data: LiveAircraft[] }).data).toHaveLength(1);
  });
});

describe("widocznosc znacznikow na podkladzie", () => {
  it("cywilny samolot spelnia prog 3:1 na ladzie i na wodzie", () => {
    // WCAG 1.4.11 dla grafiki niosacej znaczenie. Poprzedni szary mial 1.57:1 na wodzie, czyli nad
    // morzem - a to wiekszosc tej mapy - cywilny ruch praktycznie znikal.
    expect(contrastRatio(GREY, BASEMAP_LAND)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(GREY, BASEMAP_SEA)).toBeGreaterThanOrEqual(3);
  });

  it("obwodka znacznika jest widoczna na obu powierzchniach podkladu", () => {
    // Czerwony wojskowy sam w sobie ma 2.46:1 na wodzie. Obwodka jest tym, co go ratuje, wiec to
    // ona musi trzymac prog - inaczej wystarczy ja usunac i nic tego nie zauwazy.
    expect(contrastRatio(LABEL, BASEMAP_LAND)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(LABEL, BASEMAP_SEA)).toBeGreaterThanOrEqual(3);
  });

  it("wojskowy i cywilny roznia sie czyms wiecej niz kolorem", () => {
    // Czerwony i szary maja zblizona jasnosc, wiec przy daltonizmie kolor nie wystarcza.
    // Rozmiar niesie te sama informacje: kazda kategoria wojskowa rysuje sie wieksza od cywilnej.
    expect(KATEGORIE.wojskowy.rozmiar).toBeGreaterThan(KATEGORIE.cywilny.rozmiar);
    expect(KATEGORIE.rozpoznanie.rozmiar).toBeGreaterThan(KATEGORIE.cywilny.rozmiar);
  });

  it("smiglowiec rysuje sie innym ksztaltem niz samolot", () => {
    // Ksztalt to jedyny sygnal, ktory dziala bez koloru i bez porownywania rozmiarow obok siebie.
    expect(KATEGORIE.smiglowiec.ksztalt).toBe("smiglowiec");
    expect(KATEGORIE.mysliwiec.ksztalt).toBe("samolot");
    expect(KATEGORIE.tankowiec.ksztalt).toBe("statek");
  });

  it("maszyna bez kursu jest kropka, a nie sylwetka wskazujaca polnoc", () => {
    // Obrocenie sylwetki na kurs, ktorego nie znamy, to narysowanie faktu, ktorego nie mamy.
    expect(zKursem(plane({ gsKt: 420, trackDeg: 90 }))).toBe(true);
    expect(zKursem(plane({ gsKt: 5, trackDeg: 90 }))).toBe(false);
    expect(zKursem(plane({ gsKt: 420, trackDeg: null }))).toBe(false);

    const warstwy = aircraftLayers([
      plane({ gsKt: 420, trackDeg: 90 }),
      plane({ hex: "bbb", gsKt: 0, trackDeg: null }),
    ]);
    const ile = (id: string) =>
      (warstwy.find((l) => l.id === id)!.props as unknown as { data: LiveAircraft[] }).data.length;
    expect(ile("aircraft")).toBe(1);
    expect(ile("aircraft-stopped")).toBe(1);
  });
});
