import { describe, expect, it } from "vitest";
import { BASEMAP_LAND, BASEMAP_SEA, LABEL, aircraftColor, contrastRatio, jammingColor } from "./colors";
import type { LiveAircraft } from "./api";

const base: LiveAircraft = {
  hex: "a", flight: null, typeCode: null, isMilitary: false, lat: 0, lon: 0,
  altBaroFt: 30000, onGround: false, gsKt: 400, trackDeg: 0, ts: "2026-09-22T12:00:00Z",
};

describe("aircraftColor", () => {
  it("military is red, civil is grey", () => {
    expect(aircraftColor({ ...base, isMilitary: true })).toEqual([230, 57, 70]);
    expect(aircraftColor(base)).toEqual([150, 160, 170]);
  });
});

describe("jammingColor", () => {
  it("follows gpsjam thresholds", () => {
    expect(jammingColor(0.01)[3]).toBe(0);
    expect(jammingColor(0.05)).toEqual([255, 190, 0, 110]);
    expect(jammingColor(0.2)).toEqual([230, 57, 70, 150]);
  });
});

describe("etykiety samolotow", () => {
  it("sa czytelne na jasnym podkladzie positron", () => {
    // Etykiety byly [240,240,240] na tle [242,243,240]: render dzialal, napisu nie dalo sie odczytac.
    expect(contrastRatio(LABEL, BASEMAP_LAND)).toBeGreaterThanOrEqual(4.5);
  });

  it("sa czytelne takze nad morzem, czyli na najciemniejszej powierzchni podkladu", () => {
    expect(contrastRatio(LABEL, BASEMAP_SEA)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("contrastRatio", () => {
  it("liczy skrajne przypadki wg WCAG", () => {
    expect(contrastRatio([0, 0, 0], [255, 255, 255])).toBeCloseTo(21, 1);
    expect(contrastRatio([120, 120, 120], [120, 120, 120])).toBeCloseTo(1, 5);
  });
});
