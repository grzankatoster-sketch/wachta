import { describe, expect, it } from "vitest";
import { paraZAlarmu, wyborLayers } from "./wybor";
import type { AlertDto, LiveShip } from "../api";

const statek = (mmsi: string, over: Partial<LiveShip> = {}): LiveShip => ({
  mmsi, name: "STATEK " + mmsi, shipType: "70", navStatus: "5",
  lat: 60, lon: 25, sogKt: 0, cogDeg: 0, ts: "2026-09-29T09:00:00Z", ...over,
});

const d5 = (ev: object): AlertDto => ({
  id: 1, detector: "D5", entityId: "x", startedAt: "2026-09-29T09:00:00Z",
  lat: 60, lon: 25, score: 0.8, evidence: JSON.stringify(ev), state: "new",
});

describe("wyroznienie wyboru na mapie", () => {
  it("nic nie rysuje, kiedy nic nie wybrano", () => {
    expect(wyborLayers(null, [])).toEqual([]);
  });

  it("statek wybrany bezposrednio nie dostaje adnotacji alarmu", () => {
    // Adnotacja odpowiada na pytanie "ktory z tych pierscieni", a przy kliknietym statku
    // takiego pytania nie ma - wiadomo, w co sie kliknelo.
    expect(wyborLayers({ kind: "ship", data: statek("1") }, [statek("1")])).toEqual([]);
  });

  it("wybrany alarm dostaje pierscien, ktorego nie ma nic innego na mapie", () => {
    const w = wyborLayers({ kind: "alert", data: d5({}) }, []);
    const promienie = w.filter(l => l.id.startsWith("wybor-alarm"))
      .map(l => (l.props as unknown as { getRadius: number }).getRadius);
    expect(promienie.length).toBe(2);
    // Zwykly pierscien alarmu ma 14 px - wyroznienie musi byc wyraznie wieksze.
    expect(Math.min(...promienie)).toBeGreaterThan(14);
  });

  it("przeladunek wskazuje OBA kadluby, o ktorych mowi panel", () => {
    // Panel wymienia dwie nazwy; zostawienie ich nierozroznialnymi na mapie kaze wierzyc na slowo.
    const alarm = d5({ mmsi_a: "111", mmsi_b: "222", min_separation_m: 258 });
    const statki = [statek("111"), statek("222", { lon: 25.01 }), statek("333")];
    const para = paraZAlarmu(alarm, statki);
    expect(para?.a.mmsi).toBe("111");
    expect(para?.b.mmsi).toBe("222");
    expect(para?.metry).toBe(258);

    const w = wyborLayers({ kind: "alert", data: alarm }, statki);
    const kadluby = w.find(l => l.id === "wybor-para");
    expect((kadluby!.props.data as LiveShip[]).map(s => s.mmsi)).toEqual(["111", "222"]);
    expect(w.some(l => l.id === "wybor-para-linia")).toBe(true);
    const etykieta = w.find(l => l.id === "wybor-para-odleglosc")!;
    const tekst = (etykieta.props as unknown as { getText: (p: unknown) => string }).getText;
    // Nie samo "258 m": pierscienie stoja na pozycjach BIEZACYCH, a pomiar pochodzi ze spotkania
    // sprzed godzin. Goly dystans miedzy dwoma kadlubami oddalonymi juz o kilometry to liczba
    // prawdziwa, umieszczona tak, ze klamie.
    expect(tekst(para)).toBe("258 m podczas spotkania");
  });

  it("nie wskazuje pary, ktorej juz nie slychac", () => {
    // Statek moze zamilknac po zgloszeniu alarmu. Narysowanie go tam, gdzie byl, bylaby
    // adnotacja o czyms, czego mapa juz nie widzi.
    const alarm = d5({ mmsi_a: "111", mmsi_b: "222" });
    expect(paraZAlarmu(alarm, [statek("111")])).toBeNull();
    const w = wyborLayers({ kind: "alert", data: alarm }, [statek("111")]);
    expect(w.some(l => l.id === "wybor-para")).toBe(false);
    expect(w.some(l => l.id.startsWith("wybor-alarm"))).toBe(true);   // sam alarm nadal wyrozniony
  });

  it("inny detektor niz D5 nie dostaje pary", () => {
    const d4 = { ...d5({ mmsi_a: "111", mmsi_b: "222" }), detector: "D4" };
    expect(paraZAlarmu(d4, [statek("111"), statek("222")])).toBeNull();
  });

  it("adnotacja nie lapie klikniec", () => {
    // Inaczej postawilaby cel na tych samych kadlubach, ktore wskazuje.
    const w = wyborLayers({ kind: "alert", data: d5({ mmsi_a: "111", mmsi_b: "222" }) },
                          [statek("111"), statek("222")]);
    expect(w.every(l => l.props.pickable === false)).toBe(true);
  });
});
