import { describe, expect, it } from "vitest";
import { dopisek, NAZWY, podmiot, szczegoly } from "./alert-text";

/**
 * Znalezione na zywym stosie: pierwsze alarmy morskie pokazaly sie jako goly numer MMSI i
 * "luka ? min". Panel powstal, gdy istnial tylko D1, i czytal jego klucze ze WSZYSTKICH alarmow -
 * dane byly w bazie, czytelnik ich nie widzial.
 */

const D1 = { flight: "FORTE10", type_code: "Q4", gap_minutes: 12 };
const D4 = {
  mmsi: "265762770", name: "DUX", duration_minutes: 78.8, shift_km: 5.0,
  listeners: 20, implied_kt: 2.1, verdict: "cisza przy dzialajacym odbiorze",
};
const D6 = { mmsi: "230007910", name: "SVEA", min_distance_km: 0.42, line_name: "Nord Stream 1" };

describe("kogo dotyczy alarm", () => {
  it("samolot pokazuje sie znakiem wywolawczym", () => {
    expect(podmiot(D1, "4ca7b3")).toBe("FORTE10");
  });

  it("statek pokazuje sie NAZWA, nie numerem", () => {
    expect(podmiot(D4, "265762770")).toBe("DUX");
  });

  it("bez nazwy zostaje identyfikator, a nie pustka", () => {
    expect(podmiot({}, "265762770")).toBe("265762770");
    expect(podmiot({ name: "   " }, "265762770")).toBe("265762770");
  });

  it("przy nazwie statku numer idzie jako dopisek, zeby nie zniknal", () => {
    expect(dopisek(D4)).toBe("265762770");
    expect(dopisek(D1)).toBe("Q4");
    expect(dopisek({})).toBe("");
  });
});

describe("szczegoly alarmu", () => {
  it("czas czyta z pola tego detektora, ktory go zapisal", () => {
    expect(szczegoly(D1)).toContain("12 min");
    expect(szczegoly(D4)).toContain("79 min");
  });

  it("pokazuje to, co detektor naprawde zmierzyl", () => {
    const s = szczegoly(D4);
    expect(s).toContain("5.0 km dalej");
    expect(s).toContain("20 świadków");
    expect(s).toContain("2.1 w.");
  });

  it("wleczenie kotwicy mowi o linii, a nie o luce", () => {
    const s = szczegoly(D6);
    expect(s).toContain("0.4 km od linii");
    expect(s).toContain("Nord Stream 1");
    expect(s.some((x) => x.includes("min"))).toBe(false);
  });

  it("czego detektor nie zmierzyl, tego nie pokazuje - zadnych znakow zapytania", () => {
    // Znak zapytania czyta sie jako "detektor nie wie", a prawda jest zwykle taka, ze ten detektor
    // tej rzeczy w ogole nie mierzy.
    expect(szczegoly({})).toEqual([]);
    expect(szczegoly(D6).join(" ")).not.toContain("?");
  });

  it("nie da sie wstawic smiecia zamiast liczby", () => {
    expect(szczegoly({ gap_minutes: NaN })).toEqual([]);
    expect(szczegoly({ shift_km: "duzo" as unknown as number })).toEqual([]);
    expect(szczegoly({ listeners: null as unknown as number })).toEqual([]);
  });
});

describe("nazwy detektorow", () => {
  it("kazdy zbudowany detektor ma nazwe po polsku", () => {
    for (const d of ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]) {
      expect(NAZWY[d], d).toBeTruthy();
    }
  });

  it("nieznany detektor nie jest bledem - pokaze sie swoim kodem", () => {
    expect(NAZWY["D99"]).toBeUndefined();
  });
});
