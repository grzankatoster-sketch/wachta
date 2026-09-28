import { describe, expect, it, vi } from "vitest";
import { search, type SearchResult } from "./api";
import { sila, stanZBledu, stanZOdpowiedzi, zapytanie } from "./search-view";

const PUSTA: SearchResult = {
  query: "cokolwiek",
  model: "bge-m3",
  minScore: 0.5,
  found: 0,
  hits: [],
  caveat: "Nic w korpusie nie przekroczylo progu podobienstwa.",
};

describe("sila trafienia", () => {
  it("nazywa slabym to, co ledwo przekracza prog", () => {
    // Prog 0,50 zmierzono tak, ze pytania bez odpowiedzi w korpusie siegaly 0,445. Wynik 0,51 jest
    // wiec ledwo odrozninalny od szumu i nie wolno go pokazywac jako trafienia.
    expect(sila(0.51).klasa).toBe("slabe");
    expect(sila(0.54).klasa).toBe("slabe");
  });

  it("rozroznia srednie i mocne", () => {
    expect(sila(0.55).klasa).toBe("srednie");
    expect(sila(0.64).klasa).toBe("srednie");
    expect(sila(0.65).klasa).toBe("mocne");
    expect(sila(0.78).klasa).toBe("mocne");
  });

  it("ma etykiete slowna, nie tylko klase", () => {
    expect(sila(0.7).etykieta).toBeTruthy();
  });
});

describe("pusty wynik kontra awaria", () => {
  it("brak trafien to WYNIK, nie blad", () => {
    // To jest cala racja bytu tego modulu. "W korpusie nic takiego nie ma" jest odpowiedzia
    // o swiecie; zlanie tego z awaria sprawia, ze narzedzie po cichu raportuje spokojny swiat.
    const stan = stanZOdpowiedzi(PUSTA);
    expect(stan.rodzaj).toBe("wynik");
    if (stan.rodzaj === "wynik") {
      expect(stan.dane.found).toBe(0);
      expect(stan.dane.caveat).toContain("progu");
    }
  });

  it("awaria modelu to BLAD, nie pusty wynik", () => {
    const stan = stanZBledu(new Error("/api/search: HTTP 503"));
    expect(stan.rodzaj).toBe("blad");
    if (stan.rodzaj === "blad") expect(stan.komunikat).toContain("503");
  });

  it("wyjatek, ktory nie jest bledem, tez ma czytelny komunikat", () => {
    const stan = stanZBledu("cos poszlo nie tak");
    expect(stan.rodzaj).toBe("blad");
    if (stan.rodzaj === "blad") expect(stan.komunikat).toBe("cos poszlo nie tak");
  });
});

describe("budowanie zapytania", () => {
  it("koduje pytanie, wiec polskie znaki i spacje przechodza", () => {
    const q = zapytanie("statek przy kablu podmorskim");
    expect(q).toContain("q=statek+przy+kablu+podmorskim");
    expect(q).toContain("limit=8");
  });

  it("nie wysyla filtru, gdy czytelnik chce wszystkiego", () => {
    expect(zapytanie("cos", undefined)).not.toContain("kind=");
  });

  it("wysyla filtr, gdy zostal wybrany", () => {
    expect(zapytanie("cos", "alert")).toContain("kind=alert");
  });

  it("nie da sie wstrzyknac wlasnych parametrow przez tresc pytania", () => {
    const q = zapytanie("cos&limit=9999&kind=alert");
    expect(q).toContain("limit=8");
    expect(q.match(/limit=/g)).toHaveLength(1);
    expect(q).not.toContain("&kind=alert");
  });
});

describe("klient wyszukiwania", () => {
  it("pyta wlasciwy adres i oddaje odpowiedz", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => PUSTA,
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      const wynik = await search("protesty", "event", 3);
      expect(fetchMock).toHaveBeenCalledWith("/api/search?q=protesty&limit=3&kind=event");
      expect(wynik.found).toBe(0);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("HTTP 503 z modelu rzuca bledem, a nie oddaje pustej listy", async () => {
    // Gdyby to zwrocilo pusta liste, awaria modelu wygladalaby dokladnie tak jak pusty korpus.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    try {
      await expect(search("cokolwiek")).rejects.toThrow("503");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
