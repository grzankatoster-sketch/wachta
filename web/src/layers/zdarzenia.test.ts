import { describe, expect, it } from "vitest";
import type { ZdarzenieDto } from "../konflikty";
import { kolorZdarzenia, podpisyDoPokazania, promienZdarzenia, zdarzeniaLayers } from "./zdarzenia";

const z = (o: Partial<ZdarzenieDto> & { id: string }): ZdarzenieDto => ({
  ts: "2026-09-28T10:00:00Z", kind: "walka", actor1: "RUS", actor2: "UKR", place: "Charków",
  lat: 50, lon: 36.2, goldstein: -9.5, sources: 4, url: "https://example.org/a", mentions: 12, ...o,
});

describe("kolor zdarzenia", () => {
  it("brak oceny to szary, a nie punkt na skali", () => {
    // Wpisanie tu wartosci srodkowej postawiloby nieocenione zdarzenie na skali z ta sama pewnoscia
    // co zmierzone.
    const szary = kolorZdarzenia(null);
    expect(szary).toEqual([139, 148, 158]);
    expect(szary).not.toEqual(kolorZdarzenia(0));
    expect(szary).not.toEqual(kolorZdarzenia(-3));
  });

  it("najciezsze, lzejsze i niekonfliktowe maja trzy rozne kolory", () => {
    const k = [kolorZdarzenia(-9), kolorZdarzenia(-3), kolorZdarzenia(2)].map((c) => c.join(","));
    expect(new Set(k).size).toBe(3);
  });

  it("NaN traktujemy jak brak oceny, a nie jak zero", () => {
    expect(kolorZdarzenia(Number.NaN)).toEqual(kolorZdarzenia(null));
  });
});

describe("promien zdarzenia", () => {
  it("rosnie z liczba redakcji, ale coraz wolniej", () => {
    // Zasieg to nie skala zdarzenia. Przy wzroscie liniowym przyrost z 1 na 2 redakcje i z 5 na 6
    // bylby taki sam, czyli krazek obiecywalby proporcje, ktorych GDELT nie zmierzyl.
    expect(promienZdarzenia(9)).toBeGreaterThan(promienZdarzenia(1));
    expect(promienZdarzenia(2) - promienZdarzenia(1))
      .toBeGreaterThan(promienZdarzenia(6) - promienZdarzenia(5));
  });

  it("ma sufit, zeby jedna historia nie zakryla mapy", () => {
    expect(promienZdarzenia(100000)).toBeLessThanOrEqual(20);
  });
});

describe("ktore zdarzenia dostaja podpis", () => {
  const wiele = [...Array(20)].map((_, i) => z({ id: `e${i}`, sources: i, place: `Miejsce ${i}` }));

  it("podpisujemy najszerzej opisane, nie wszystkie", () => {
    const podpisy = podpisyDoPokazania(wiele, null, 5);
    expect(podpisy).toHaveLength(5);
    expect(podpisy.map((p) => p.sources)).toEqual([19, 18, 17, 16, 15]);
  });

  it("otwarte zdarzenie dostaje podpis, nawet jesli jest najciszsze", () => {
    const podpisy = podpisyDoPokazania(wiele, "e0", 5);
    expect(podpisy.map((p) => p.id)).toContain("e0");
  });

  it("zdarzenie bez nazwy miejsca nie dostaje pustego podpisu", () => {
    expect(podpisyDoPokazania([z({ id: "x", place: null })], "x", 5)).toEqual([]);
  });
});

describe("warstwy zdarzen", () => {
  const warstwy = zdarzeniaLayers([z({ id: "a" }), z({ id: "b", lat: 47, lon: 35 })], "a");

  it("pusta lista nie tworzy zadnej warstwy", () => {
    expect(zdarzeniaLayers([], null)).toEqual([]);
  });

  it("krazki sa klikalne - inaczej nie ma jak dojsc do wersji z mapy", () => {
    const krazki = warstwy.find((l) => l.id === "zdarzenia-konfliktu");
    expect((krazki!.props as { pickable?: boolean }).pickable).toBe(true);
  });

  it("obwodka otwartego zdarzenia rysuje sie tylko wokol niego", () => {
    const wybor = warstwy.find((l) => l.id === "zdarzenie-wybrane");
    expect((wybor!.props as { data: ZdarzenieDto[] }).data.map((d) => d.id)).toEqual(["a"]);
  });

  it("podpisy miejsc maja atlas 'auto'", () => {
    // Domyslny atlas TextLayer to ASCII 32-127. Bez tego "Charków" i "Zaporiżżia" - czyli dokladnie
    // te nazwy, po ktore ta warstwa istnieje - rysuja sie jako puste prostokaty, bez zadnego bledu.
    const podpisy = warstwy.find((l) => l.id === "zdarzenia-podpisy");
    expect((podpisy!.props as { characterSet?: string }).characterSet).toBe("auto");
  });
});
