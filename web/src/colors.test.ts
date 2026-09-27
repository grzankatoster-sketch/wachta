import { describe, expect, it } from "vitest";
import { aircraftColor, jammingColor } from "./colors";
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
