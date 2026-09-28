import { describe, expect, it } from "vitest";
import type { AlertDto } from "./api";
import { grupy, odfiltruj, pustaLista } from "./filtr-alarmow";

const a = (id: number, detector: string): AlertDto => ({
  id, detector, entityId: `e${id}`, startedAt: "2026-09-28T15:00:00Z",
  lat: 59, lon: 19, score: 0.7, evidence: "{}", state: "new",
});

// Rozklad z prawdziwej bazy po wpieciu D5: jeden detektor przytlacza pozostale.
const ALARMY = [...Array(19)].map((_, i) => a(i, "D5"))
  .concat([...Array(6)].map((_, i) => a(100 + i, "D4")))
  .concat([...Array(3)].map((_, i) => a(200 + i, "D6")));

describe("grupowanie po detektorze", () => {
  it("najliczniejszy detektor idzie pierwszy, zaraz po 'wszystkie'", () => {
    const g = grupy(ALARMY);
    expect(g[0]).toEqual({ detektor: null, etykieta: "wszystkie", ile: 28 });
    expect(g[1].detektor).toBe("D5");
    expect(g[1].ile).toBe(19);
  });

  it("uzywa nazw po polsku, nie kodow", () => {
    expect(grupy(ALARMY)[1].etykieta).toMatch(/Przeładunek/);
  });

  it("detektor bez alarmow nie dostaje przycisku", () => {
    // Pusty przycisk zaprasza do klikniecia i dowiedzenia sie, ze nic tam nie ma - gorszy sposob
    // na te sama wiadomosc niz po prostu brak przycisku.
    expect(grupy(ALARMY).some((g) => g.detektor === "D7")).toBe(false);
  });

  it("pusta lista alarmow daje sam przycisk 'wszystkie' z zerem", () => {
    expect(grupy([])).toEqual([{ detektor: null, etykieta: "wszystkie", ile: 0 }]);
  });

  it("nieznany detektor pokazuje sie swoim kodem", () => {
    expect(grupy([a(1, "D99")])[1].etykieta).toBe("D99");
  });
});

describe("filtrowanie", () => {
  it("brak wyboru pokazuje wszystko", () => {
    expect(odfiltruj(ALARMY, null)).toHaveLength(28);
  });

  it("wybor detektora zostawia tylko jego", () => {
    const tylkoD4 = odfiltruj(ALARMY, "D4");
    expect(tylkoD4).toHaveLength(6);
    expect(tylkoD4.every((x) => x.detector === "D4")).toBe(true);
  });

  it("nie zmienia oryginalnej listy", () => {
    odfiltruj(ALARMY, "D4");
    expect(ALARMY).toHaveLength(28);
  });
});

describe("pusta lista mowi, KTORA pustka to jest", () => {
  it("brak alarmow w ogole to wynik systemu", () => {
    // Detektory liczyly i nic nie znalazly - to jest informacja, nie awaria.
    expect(pustaLista(0, null)).toMatch(/Detektory liczą/);
  });

  it("brak alarmow tego typu to wybor czytelnika", () => {
    // Ta sama pustka z dwoch zupelnie roznych powodow; jedno zdanie na oba sprawia,
    // ze wlasny filtr wyglada jak awaria systemu.
    const tekst = pustaLista(28, "D7");
    expect(tekst).toMatch(/tego typu/);
    expect(tekst).toMatch(/wszystkie/);
    expect(tekst).not.toMatch(/Detektory liczą/);
  });
});

describe("pusta lista a brak polaczenia", () => {
  it("nie twierdzi, ze detektory cos sprawdzily, kiedy nie ma polaczenia", () => {
    const tekst = pustaLista(0, null, false);
    expect(tekst).toMatch(/Brak połączenia/);
    expect(tekst).not.toMatch(/nic nie znalazły/);
  });

  it("po polaczeniu pusta lista nadal znaczy cisze", () => {
    expect(pustaLista(0, null, true)).toMatch(/nic nie znalazły/);
  });

  it("brak polaczenia jest wazniejszy niz wybrany filtr", () => {
    // Inaczej przy padnietym API filtr tlumaczylby pustke swoim istnieniem.
    expect(pustaLista(5, "D5", false)).toMatch(/Brak połączenia/);
  });
});
