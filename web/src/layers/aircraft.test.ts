import { describe, expect, it } from "vitest";
import { aircraftLayers } from "./aircraft";
import { BASEMAP_LAND, BASEMAP_SEA, contrastRatio } from "../colors";
import type { LiveAircraft } from "../api";

const plane = (over: Partial<LiveAircraft>): LiveAircraft => ({
  hex: "3c6444", flight: "FORTE10", typeCode: "Q4", isMilitary: true, lat: 55, lon: 19,
  altBaroFt: 30000, onGround: false, gsKt: 400, trackDeg: 90, ts: "2026-09-28T08:00:00Z", ...over,
});

describe("warstwy samolotow", () => {
  it("etykieta wojskowa ma kolor czytelny na podkladzie, a nie bialy", () => {
    // Regresja: getColor bylo wpisane na sztywno jako [240,240,240] i napisy znikaly w tle.
    const labels = aircraftLayers([plane({})]).find((l) => l.id === "aircraft-labels");
    expect(labels, "warstwa etykiet").toBeDefined();
    const color = (labels!.props as unknown as { getColor: [number, number, number] }).getColor;
    expect(contrastRatio(color, BASEMAP_LAND)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(color, BASEMAP_SEA)).toBeGreaterThanOrEqual(4.5);
  });

  it("pomija samoloty na ziemi", () => {
    const layers = aircraftLayers([plane({ onGround: true }), plane({ hex: "abc123" })]);
    expect((layers[0].props as unknown as { data: LiveAircraft[] }).data).toHaveLength(1);
  });
});
