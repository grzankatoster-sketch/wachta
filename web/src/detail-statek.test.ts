import { describe, expect, it } from "vitest";
import { kursSlownie, rodzajStatku, statusSlownie, zbudujSzczegoly } from "./detail";
import type { LiveShip } from "./api";

const statek = (over: Partial<LiveShip>): LiveShip => ({
  mmsi: "230722000", name: "FJARDVAGEN", shipType: "70", navStatus: "5",
  lat: 60.1, lon: 24.9, sogKt: 0.1, cogDeg: 31, ts: "2026-09-29T07:52:31Z", ...over,
});

describe("panel statku", () => {
  it("nie pokazuje surowych kodow AIS tam, gdzie da sie je nazwac", () => {
    // Regresja: panel pisal "Status nawigacyjny: 5", czyli dokladnie to, czego ten projekt
    // unika wszedzie indziej - liczbe zamiast tego, co ona znaczy.
    expect(statusSlownie("5")).toBe("zacumowany");
    expect(statusSlownie("0")).toBe("w drodze, na silniku");
    expect(rodzajStatku("70")).toBe("masowiec / drobnicowiec");
    expect(rodzajStatku("80")).toBe("tankowiec");
  });

  it("nieznanego kodu nie wyrzuca po cichu, tylko oznacza jako nieznany", () => {
    expect(statusSlownie("11")).toBe("kod 11 (nieznany)");
    expect(rodzajStatku("99")).toBe("inna jednostka");
    expect(statusSlownie(null)).toBeNull();
    expect(rodzajStatku(null)).toBeNull();
  });

  it("przepuszcza opis slowny, jesli zrodlo przyslalo slowa zamiast liczby", () => {
    expect(statusSlownie("under way using engine")).toBe("under way using engine");
  });

  it("kurs podaje stopnie i strone swiata", () => {
    expect(kursSlownie(31)).toBe("31° (NE)");
    expect(kursSlownie(0)).toBe("0° (N)");
    expect(kursSlownie(180)).toBe("180° (S)");
    expect(kursSlownie(359)).toBe("359° (N)");
    expect(kursSlownie(null)).toBeNull();
  });

  it("stojacy statek nie jest opisany jako plynacy", () => {
    const s = zbudujSzczegoly({ kind: "ship", data: statek({ sogKt: 0.1 }) });
    expect(s.coZTegoWynika.join(" ")).toMatch(/nie robi drogi/);
    const w = zbudujSzczegoly({ kind: "ship", data: statek({ sogKt: 11 }) });
    expect(w.coZTegoWynika.join(" ")).toMatch(/w drodze/);
  });

  it("tytulem jest nazwa, a bez nazwy MMSI - nigdy puste pole", () => {
    expect(zbudujSzczegoly({ kind: "ship", data: statek({}) }).tytul).toBe("FJARDVAGEN");
    expect(zbudujSzczegoly({ kind: "ship", data: statek({ name: null }) }).tytul).toBe("230722000");
    expect(zbudujSzczegoly({ kind: "ship", data: statek({ name: "  " }) }).tytul).toBe("230722000");
  });

  it("mowi, czego brak statku na mapie NIE dowodzi", () => {
    const s = zbudujSzczegoly({ kind: "ship", data: statek({}) });
    expect(s.naPodstawie.join(" ")).toMatch(/Brak statku na mapie nie znaczy/);
  });
});
