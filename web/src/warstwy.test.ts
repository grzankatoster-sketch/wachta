import { describe, expect, it } from "vitest";
import {
  przelacz,
  odmiana,
  stanDanych,
  WARSTWY,
  wszystkoWylaczone,
  WSZYSTKO_WIDOCZNE,
  type Widoczne,
} from "./warstwy";

/**
 * Pierwsza osoba, ktora otworzyla aplikacje, powiedziala: "nie wiem o co chodzi, jakies kropki,
 * nic sie nie da klikac". Te testy pilnuja tego, co z tego wyniklo.
 */

describe("legenda", () => {
  it("kazdy znak na mapie ma nazwe I zdanie, co znaczy", () => {
    // Sama nazwa nie wystarczy: "alarmy" nie mowi, ze to kandydat do sprawdzenia, a nie wyrok.
    for (const w of WARSTWY) {
      expect(w.nazwa, w.id).toBeTruthy();
      expect(w.opis.length, `${w.id} ma za krotki opis`).toBeGreaterThan(40);
    }
  });

  it("opisy mowia o ograniczeniach, a nie tylko o tym, co widac", () => {
    const wojskowe = WARSTWY.find((w) => w.id === "wojskowe");
    expect(wojskowe?.opis).toMatch(/nie nadaje|widać tylko/i);
    const alarmy = WARSTWY.find((w) => w.id === "alarmy");
    expect(alarmy?.opis).toMatch(/sprawdzenia|nigdy wyrok/i);
  });

  it("kazda warstwa ma kolor i ksztalt, zeby znak w legendzie wygladal jak ten na mapie", () => {
    for (const w of WARSTWY) {
      expect(w.kolor, w.id).toMatch(/^rgb\(/);
      expect(["kropka", "obwodka", "heksagon", "linia"]).toContain(w.ksztalt);
    }
  });
});

describe("wlaczanie i wylaczanie", () => {
  it("na starcie widac wszystko", () => {
    expect(Object.values(WSZYSTKO_WIDOCZNE).every(Boolean)).toBe(true);
  });

  it("przelaczenie zmienia tylko jedna warstwe", () => {
    const po = przelacz(WSZYSTKO_WIDOCZNE, "cywilne");
    expect(po.cywilne).toBe(false);
    expect(po.wojskowe).toBe(true);
    expect(po.alarmy).toBe(true);
  });

  it("przelaczenie dwa razy wraca do punktu wyjscia", () => {
    expect(przelacz(przelacz(WSZYSTKO_WIDOCZNE, "alarmy"), "alarmy")).toEqual(WSZYSTKO_WIDOCZNE);
  });

  it("nie zmienia stanu w miejscu", () => {
    const przed = { ...WSZYSTKO_WIDOCZNE };
    przelacz(WSZYSTKO_WIDOCZNE, "alarmy");
    expect(WSZYSTKO_WIDOCZNE).toEqual(przed);
  });

  it("wie, kiedy mapa jest pusta z winy uzytkownika", () => {
    // Mapa z wylaczonymi warstwami wyglada identycznie jak mapa bez danych, a to dwie rozne rzeczy:
    // za jedna odpowiada czytelnik, za druga system.
    expect(wszystkoWylaczone(WSZYSTKO_WIDOCZNE)).toBe(false);
    const nic: Widoczne = { wojskowe: false, cywilne: false, ladunek: false, statki: false,
                            infrastruktura: false, alarmy: false, zaklocenia: false };
    expect(wszystkoWylaczone(nic)).toBe(true);
  });
});

describe("stan danych", () => {
  it("brak polaczenia mowi o polaczeniu, nie o braku samolotow", () => {
    expect(stanDanych(false, 0, 0, null)).toMatch(/Brak połączenia/);
  });

  it("polaczenie bez niczego mowi wprost, ze polaczenie jest", () => {
    // Inaczej pusta mapa wyglada jak awaria, a jest poprawnym stanem.
    expect(stanDanych(true, 0, 0, null)).toMatch(/Połączono/);
  });

  it("podaje wiek danych, bo migawka bez godziny udaje terazniejszosc", () => {
    expect(stanDanych(true, 120, 0, 3)).toMatch(/przed chwilą/);
    expect(stanDanych(true, 120, 0, 40)).toMatch(/40 s temu/);
    expect(stanDanych(true, 120, 0, 600)).toMatch(/10 min temu/);
    expect(stanDanych(true, 120, 0, null)).not.toMatch(/odświeżono/);
  });

  it("liczy oba zrodla, nie tylko samoloty", () => {
    // Regresja: naglowek mowil o samolotach, a na mapie bylo osiemset statkow, o ktorych milczal.
    const zdanie = stanDanych(true, 126, 817, null);
    expect(zdanie).toMatch(/126 samolotów/);
    expect(zdanie).toMatch(/817 statków/);
  });

  it("nie wymienia zrodla, ktorego nie ma", () => {
    expect(stanDanych(true, 126, 0, null)).not.toMatch(/statk/);
    expect(stanDanych(true, 0, 817, null)).not.toMatch(/samolot/);
  });

  it("odmienia liczebniki, bo '126 samolot' czyta sie jak blad danych", () => {
    expect(odmiana(1, "samolot", "samoloty", "samolotów")).toBe("samolot");
    expect(odmiana(3, "samolot", "samoloty", "samolotów")).toBe("samoloty");
    expect(odmiana(5, "samolot", "samoloty", "samolotów")).toBe("samolotów");
    expect(odmiana(12, "samolot", "samoloty", "samolotów")).toBe("samolotów");   // 12, nie 12-2
    expect(odmiana(22, "samolot", "samoloty", "samolotów")).toBe("samoloty");
    expect(odmiana(126, "samolot", "samoloty", "samolotów")).toBe("samolotów");
    expect(odmiana(0, "samolot", "samoloty", "samolotów")).toBe("samolotów");
  });
});
