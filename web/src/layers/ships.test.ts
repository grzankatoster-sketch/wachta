import { describe, expect, it } from "vitest";
import { przedDziobem, shipLayers, wRuchu } from "./ships";
import type { LiveShip } from "../api";

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
    const wolny = przedDziobem(statek({ sogKt: 5 }));
    const szybki = przedDziobem(statek({ sogKt: 20 }));
    const od = (p: [number, number]) => Math.abs(p[0] - 25.0);
    expect(od(szybki)).toBeGreaterThan(od(wolny) * 3);
  });

  it("kurs 90 stopni prowadzi na wschod, 0 na polnoc", () => {
    const [lonE, latE] = przedDziobem(statek({ cogDeg: 90 }));
    expect(lonE).toBeGreaterThan(25.0);
    expect(latE).toBeCloseTo(60.0, 3);

    const [lonN, latN] = przedDziobem(statek({ cogDeg: 0 }));
    expect(latN).toBeGreaterThan(60.0);
    expect(lonN).toBeCloseTo(25.0, 3);
  });

  it("linie rysuja sie tylko dla plynacych, znaczniki dla wszystkich", () => {
    const dane = [statek({}), statek({ mmsi: "2", sogKt: 0 })];
    const linie = shipLayers(dane).find((l) => l.id === "ship-course");
    const znaczniki = shipLayers(dane).find((l) => l.id === "ships");
    expect((linie!.props.data as LiveShip[]).length).toBe(1);
    expect((znaczniki!.props.data as LiveShip[]).length).toBe(2);
  });
});
