import { describe, expect, it } from "vitest";
import {
  LIMIT_SAMOLOT_S,
  LIMIT_STATEK_S,
  najnowszy,
  przezroczystosc,
  ruch,
  zegarDanych,
  zliczonaPozycja,
} from "./ruch";

const KM_NA_STOPIEN = 111.32;

describe("zliczanie drogi miedzy odczytami", () => {
  it("statek 12 w. przez minute przesuwa sie o ok. 370 m", () => {
    const [lon, lat] = zliczonaPozycja(60, 25, 12, 90, 60);
    const km = (lon - 25) * KM_NA_STOPIEN * Math.cos((60 * Math.PI) / 180);
    expect(km).toBeCloseTo((12 * 1.852) / 60, 2);
    expect(lat).toBeCloseTo(60, 6);
  });

  it("kurs 0 prowadzi na polnoc, 180 na poludnie", () => {
    expect(zliczonaPozycja(60, 25, 20, 0, 600)[1]).toBeGreaterThan(60);
    expect(zliczonaPozycja(60, 25, 20, 180, 600)[1]).toBeLessThan(60);
  });

  it("bez predkosci albo bez kursu nic sie nie przesuwa", () => {
    expect(zliczonaPozycja(60, 25, 0, 90, 600)).toEqual([25, 60]);
    expect(zliczonaPozycja(60, 25, null, 90, 600)).toEqual([25, 60]);
    expect(zliczonaPozycja(60, 25, 12, null, 600)).toEqual([25, 60]);
    expect(zliczonaPozycja(60, 25, 12, 90, 0)).toEqual([25, 60]);
  });

  it("nie wywraca sie na biegunie ani na bezsensownych liczbach", () => {
    expect(zliczonaPozycja(90, 25, 12, 90, 60).every(Number.isFinite)).toBe(true);
    expect(zliczonaPozycja(60, 25, NaN, 90, 60)).toEqual([25, 60]);
    expect(zliczonaPozycja(60, 25, 12, NaN, 60)).toEqual([25, 60]);
    expect(zliczonaPozycja(60, 25, 12, 90, NaN)).toEqual([25, 60]);
  });
});

describe("limit zliczania", () => {
  it("statek, ktory zamilkl, ZATRZYMUJE SIE na ekranie", () => {
    // Najwazniejsza wlasnosc w tym pliku. Kadlub plynacy dalej na zliczonej pozycji zamalowalby
    // dokladnie to zdarzenie, ktore wykrywa D4 - "statek zamilkl w ruchu". Mapa, ktora po cichu
    // prowadzi go dalej, jest gorsza niz mapa, ktora nie rusza sie wcale.
    const tuzPrzed = ruch(60, 25, 12, 90, LIMIT_STATEK_S - 1, LIMIT_STATEK_S);
    const dawno = ruch(60, 25, 12, 90, LIMIT_STATEK_S * 10, LIMIT_STATEK_S);

    expect(tuzPrzed.przestarzale).toBe(false);
    expect(dawno.przestarzale).toBe(true);
    // Po przekroczeniu limitu pozycja przestaje rosnac - zamarza tam, gdzie go ostatnio slyszano.
    expect(dawno.lon).toBeCloseTo(ruch(60, 25, 12, 90, LIMIT_STATEK_S, LIMIT_STATEK_S).lon, 9);
  });

  it("samolot ma krotszy limit niz statek, bo czesciej nadaje", () => {
    expect(LIMIT_SAMOLOT_S).toBeLessThan(LIMIT_STATEK_S);
    expect(ruch(55, 19, 450, 90, 200, LIMIT_SAMOLOT_S).przestarzale).toBe(true);
    expect(ruch(60, 25, 12, 90, 200, LIMIT_STATEK_S).przestarzale).toBe(false);
  });

  it("zamrozony znacznik blednie, ale nie znika", () => {
    // Zniknieciе bylo by kłamstwem w druga strone: "nie ma go tam" zamiast "nie wiemy".
    const swiezy = ruch(60, 25, 12, 90, 10, LIMIT_STATEK_S);
    const stary = ruch(60, 25, 12, 90, 9999, LIMIT_STATEK_S);
    expect(przezroczystosc(swiezy)).toBe(255);
    expect(przezroczystosc(stary)).toBeGreaterThan(0);
    expect(przezroczystosc(stary)).toBeLessThan(przezroczystosc(swiezy));
  });

  it("ujemny wiek (zegar do przodu) nie cofa znacznika", () => {
    const r = ruch(60, 25, 12, 90, -500, LIMIT_STATEK_S);
    expect(r.wiek).toBe(0);
    expect(r.lon).toBeCloseTo(25, 9);
    expect(r.przestarzale).toBe(false);
  });
});

describe("zegar danych", () => {
  it("rozjechany zegar przegladarki nie postarza calego ruchu", () => {
    // Laptop spozniony albo spieszacy sie o 5 minut oznaczalby caly ruch jako przestarzaly i
    // zamrozilby mape. Liczymy od najnowszego znacznika Z PACZKI plus czas, ktory realnie uplynal.
    const fix = Date.parse("2026-09-29T07:00:00Z");
    const odebrano = 1_000_000;            // dowolny moment na zegarze przegladarki
    expect(zegarDanych(fix, odebrano, odebrano)).toBe(fix);
    expect(zegarDanych(fix, odebrano, odebrano + 4000)).toBe(fix + 4000);
  });

  it("czas nie cofa sie, gdy zegar przegladarki skoczy w tyl", () => {
    const fix = 1_700_000_000_000;
    expect(zegarDanych(fix, 5000, 1000)).toBe(fix);
  });

  it("najnowszy znacznik z paczki, z pominieciem smieci", () => {
    expect(najnowszy(["2026-09-29T07:00:00Z", "2026-09-29T07:05:00Z"]))
      .toBe(Date.parse("2026-09-29T07:05:00Z"));
    expect(najnowszy(["nie-data", "2026-09-29T07:00:00Z"])).toBe(Date.parse("2026-09-29T07:00:00Z"));
    expect(najnowszy([])).toBeNull();
    expect(najnowszy(["zupelnie nie data"])).toBeNull();
  });
});
