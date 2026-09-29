import { describe, expect, it } from "vitest";
import { ETYKIETY, ocen } from "./ocena";

const DETEKTORY = ["D1", "D4", "D5", "D6", "D7"];

describe("ocena alarmu", () => {
  it("nigdy nie wydaje werdyktu bez kontrargumentu", () => {
    // To jest cala zasada tej warstwy. Ocena, ktora wypisuje tylko przeslanki za, jest adwokatura,
    // a nie ocena - a wlasnie w tych przypadkach niewinne wyjasnienie jest czeste i tanie.
    for (const d of DETEKTORY) {
      for (const ev of [{}, { gap_minutes: 300, listeners: 20, simultaneous: 0 },
                        { duration_minutes: 600, min_distance_km: 0.02 },
                        { shift_km: 9, course_spread_deg: 120, mean_sog_kn: 0.4 },
                        { nearest_airport_km: 900, cell_reports: 9000 },
                        { implied_kt: 5000 }]) {
        const o = ocen(d, ev)!;
        expect(o.przeciw.length, `${d} bez kontrargumentu`).toBeGreaterThan(0);
        expect(o.coBySprawdzic.length, `${d} bez propozycji sprawdzenia`).toBeGreaterThan(10);
      }
    }
  });

  it("brak dowodow daje niska pewnosc, a nie kompromis miedzy zgadywaniem", () => {
    for (const d of DETEKTORY) {
      const o = ocen(d, {})!;
      expect(o.pewnosc, `${d} na pustych dowodach`).toBe("niska");
      expect(["warte-sprawdzenia", "rutyna"]).toContain(o.werdykt);
    }
  });

  it("D4: kilka statkow milczacych naraz to awaria odbioru, nie decyzja zalogi", () => {
    const o = ocen("D4", { gap_minutes: 90, listeners: 14, simultaneous: 5 })!;
    expect(o.werdykt).toBe("rutyna");
    expect(o.pewnosc).toBe("wysoka");
    expect(o.teza).toMatch(/odbioru/);
  });

  it("D4: cisza przy wielu swiadkach i bez towarzyszy jest nietypowa", () => {
    const o = ocen("D4", { gap_minutes: 112, listeners: 11, simultaneous: 0 })!;
    expect(o.werdykt).toBe("nietypowe");
    expect(o.za.join(" ")).toMatch(/11 odbiorników/);
    expect(o.przeciw.join(" ")).toMatch(/awarii urządzenia/);
  });

  it("D4: malo odbiornikow oslabia wniosek zamiast go wzmacniac", () => {
    const o = ocen("D4", { gap_minutes: 50, listeners: 2, simultaneous: 0 })!;
    expect(o.werdykt).toBe("warte-sprawdzenia");
    expect(o.przeciw.join(" ")).toMatch(/Tylko 2 odbiorników/);
  });

  it("D5: nazwa pilotowki albo holownika zbija alarm do rutyny", () => {
    // Detektor tego nie odsiewa celowo - to decyzja produktowa, nie prog. Ocena moze to powiedziec.
    for (const name of ["PILOT STATION 3", "SVITZER MARKEN", "TUG HERKULES"]) {
      const o = ocen("D5", { name, duration_minutes: 400, min_distance_km: 0.03 })!;
      expect(o.werdykt, name).toBe("rutyna");
    }
  });

  it("D5: dlugi postoj dwoch kadlubow blisko siebie jest nietypowy", () => {
    const o = ocen("D5", { name: "SIVER", duration_minutes: 260, min_distance_km: 0.04 })!;
    expect(o.werdykt).toBe("nietypowe");
    expect(o.przeciw.join(" ")).toMatch(/12 451/);
  });

  it("D6: jedna cecha to za malo, trzy naraz to nietypowe", () => {
    expect(ocen("D6", { shift_km: 2 })!.werdykt).toBe("warte-sprawdzenia");
    const trzy = ocen("D6", { shift_km: 3.4, course_spread_deg: 75, mean_sog_kn: 1.2 })!;
    expect(trzy.werdykt).toBe("nietypowe");
    expect(trzy.pewnosc).toBe("wysoka");
  });

  it("D1: cisza tuz przy lotnisku to ladowanie, nie zniknieciе", () => {
    const o = ocen("D1", { nearest_airport_km: 4 })!;
    expect(o.werdykt).toBe("rutyna");
    expect(o.teza).toMatch(/lądowanie/);
  });

  it("D1: cisza daleko od lotniska przy dobrym pokryciu jest nietypowa", () => {
    const o = ocen("D1", { nearest_airport_km: 240, cell_reports: 900 })!;
    expect(o.werdykt).toBe("nietypowe");
  });

  it("D7: przeskok niemozliwy dla statku wskazuje na dwa kadluby", () => {
    const o = ocen("D7", { implied_kt: 420 })!;
    expect(o.werdykt).toBe("nietypowe");
    expect(o.przeciw.join(" ")).toMatch(/błąd konfiguracji/);
  });

  it("detektor bez oceny zwraca null, zamiast wymyslac werdykt", () => {
    expect(ocen("D2", {})).toBeNull();
    expect(ocen("D99", { cokolwiek: 1 })).toBeNull();
  });

  it("nie wywraca sie na dowodach o zlym typie", () => {
    // evidence to wolny jsonb - detektor moze zapisac napis tam, gdzie panel oczekuje liczby.
    const smieci = { gap_minutes: "duzo", listeners: null, simultaneous: "0",
                     duration_minutes: [], min_distance_km: {}, shift_km: "x",
                     nearest_airport_km: "blisko", implied_kt: NaN } as never;
    for (const d of DETEKTORY) {
      const o = ocen(d, smieci)!;
      expect(o.teza.length).toBeGreaterThan(0);
      expect(ETYKIETY[o.werdykt]).toBeTruthy();
    }
  });
});
