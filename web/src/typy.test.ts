import { describe, expect, it } from "vitest";
import { kategoriaSamolotu } from "./typy";
import type { LiveAircraft } from "./api";

const maszyna = (typeCode: string | null, isMilitary = true): LiveAircraft => ({
  hex: "a0ec98", flight: "BRIO66", typeCode, isMilitary, lat: 55.7, lon: 21.1,
  altBaroFt: 34000, onGround: false, gsKt: 430, trackDeg: 180, ts: "2026-09-29T10:00:00Z",
});

describe("kategoria samolotu z kodu typu", () => {
  it("odrzutowiec biznesowy NIE jest rozpoznaniem, nawet gdy leci jako wojskowy", () => {
    // Zlapane na zywym ruchu 2026-09-29: BRIO66 (CL60, rejestracja N159L) nad Klajpeda byl
    // podpisany "Rozpoznanie i dozor" tylko dlatego, ze tablica tak mowila. Challenger, Gulfstream,
    // Astra, Falcon i Metro to platowce biznesowe - z modelu nie wynika misja. Mutacja: dopisanie
    // ktoregokolwiek z tych kodow z powrotem do listy rozpoznania wywraca ten test.
    for (const kod of ["CL60", "CL30", "GLF5", "GLF6", "ASTR", "F900", "SW4"]) {
      expect(kategoriaSamolotu(maszyna(kod)), kod).toBe("wojskowy");
    }
  });

  it("platowce zbudowane do jednej roli nadal sa rozpoznawane", () => {
    expect(kategoriaSamolotu(maszyna("RC135"))).toBe("rozpoznanie");
    expect(kategoriaSamolotu(maszyna("P8"))).toBe("rozpoznanie");
    expect(kategoriaSamolotu(maszyna("RQ4"))).toBe("rozpoznanie");
    expect(kategoriaSamolotu(maszyna("K35R"))).toBe("tankowanie");
    expect(kategoriaSamolotu(maszyna("C17"))).toBe("transport");
    expect(kategoriaSamolotu(maszyna("H60"))).toBe("smiglowiec");
  });

  it("nieznany platowiec zostaje przy tym, co wiadomo", () => {
    // "wojskowy" to powtorzenie flagi z adsb.lol. "cywilny" to jej brak. Zadne z nich nie jest
    // zgadywaniem misji - a wpychanie nieznanego kodu do najblizszej szufladki by nim bylo.
    expect(kategoriaSamolotu(maszyna("ZZZZ", true))).toBe("wojskowy");
    expect(kategoriaSamolotu(maszyna(null, true))).toBe("wojskowy");
    expect(kategoriaSamolotu(maszyna("ZZZZ", false))).toBe("cywilny");
    expect(kategoriaSamolotu(maszyna("CL60", false))).toBe("cywilny");
  });
});
