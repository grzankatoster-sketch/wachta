import { describe, expect, it } from "vitest";
import { przedDziobem, shipLayers, wRuchu } from "./ships";
import type { LiveShip } from "../api";

/** Zegar testu rowny znacznikowi z fixture: wiek pozycji 0, wiec zadnego zliczania drogi. */
const TERAZ = Date.parse("2026-09-29T07:00:00Z");

const statek = (over: Partial<LiveShip>): LiveShip => ({
  mmsi: "230011480", name: "SIVER", shipType: "70", navStatus: "under way using engine",
  lat: 60.0, lon: 25.0, sogKt: 12, cogDeg: 90, ts: "2026-09-29T07:00:00Z", ...over,
});

describe("statki na mapie", () => {
  it("stojacy statek nie dostaje linii kursu", () => {
    // Linia znaczy "tam dopłynie". Statek na kotwicy nigdzie nie płynie i nie moze tak wygladac.
    expect(wRuchu(statek({ sogKt: 0.2 }))).toBe(false);
    expect(wRuchu(statek({ sogKt: 12, cogDeg: null }))).toBe(false);
    expect(wRuchu(statek({}))).toBe(true);
  });

  it("dlugosc linii rosnie z predkoscia", () => {
    const wolny = przedDziobem(statek({ sogKt: 5 }), TERAZ);
    const szybki = przedDziobem(statek({ sogKt: 20 }), TERAZ);
    const od = (p: [number, number]) => Math.abs(p[0] - 25.0);
    expect(od(szybki)).toBeGreaterThan(od(wolny) * 3);
  });

  it("kurs 90 stopni prowadzi na wschod, 0 na polnoc", () => {
    const [lonE, latE] = przedDziobem(statek({ cogDeg: 90 }), TERAZ);
    expect(lonE).toBeGreaterThan(25.0);
    expect(latE).toBeCloseTo(60.0, 3);

    const [lonN, latN] = przedDziobem(statek({ cogDeg: 0 }), TERAZ);
    expect(latN).toBeGreaterThan(60.0);
    expect(lonN).toBeCloseTo(25.0, 3);
  });

  it("plynacy dostaje sylwetke i linie, stojacy sama kropke", () => {
    // Stojacy statek nie ma sensownego kursu - AIS podaje ostatni albo zero - wiec obrocona
    // sylwetka bylaby wymyslonym faktem. Kropka mowi "tu, i nigdzie nie plynie", czyli dokladnie
    // to, na co patrza detektory kotwicy i przeladunku.
    const dane = [statek({}), statek({ mmsi: "2", sogKt: 0 })];
    const w = shipLayers(dane, TERAZ);
    const ile = (id: string) => (w.find((l) => l.id === id)!.props.data as LiveShip[]).length;

    expect(ile("ship-course")).toBe(1);
    expect(ile("ships")).toBe(1);
    expect(ile("ships-stopped")).toBe(1);
    expect(ile("ships-obwodka")).toBe(1);
  });

  it("sylwetka jest obrocona na kurs, a obwodka na ten sam", () => {
    // Kat w deck.gl idzie przeciwnie do wskazowek zegara, namiar kompasowy zgodnie. Pomylka tutaj
    // daje mape, na ktorej wszystko plynie w zla strone i nadal wyglada wiarygodnie.
    const w = shipLayers([statek({ cogDeg: 135 })], TERAZ);
    const katFn = (id: string) =>
      (w.find((l) => l.id === id)!.props as unknown as { getAngle: (s: LiveShip) => number }).getAngle;
    expect(katFn("ships")(statek({ cogDeg: 135 }))).toBe(-135);
    expect(katFn("ships-obwodka")(statek({ cogDeg: 135 }))).toBe(-135);
  });
});
