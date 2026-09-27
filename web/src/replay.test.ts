import { describe, expect, it } from "vitest";
import { replayBounds, toTrips } from "./replay";
import type { ReplayPath } from "./api";

const paths: ReplayPath[] = [
  { hex: "a", flight: "FORTE10", typeCode: "Q4", path: [[30, 45], [30.1, 45.1]], timestamps: [1000, 1030] },
  { hex: "b", flight: null, typeCode: "K35R", path: [[20, 55]], timestamps: [1010] },
];

describe("replay", () => {
  it("computes global time bounds", () => {
    expect(replayBounds(paths)).toEqual({ start: 1000, end: 1030 });
    expect(replayBounds([])).toBeNull();
  });

  it("makes timestamps relative and builds labels", () => {
    const trips = toTrips(paths, 1000);
    expect(trips[0].timestamps).toEqual([0, 30]);
    expect(trips[0].label).toBe("FORTE10 Q4");
    expect(trips[1].label).toBe("b K35R");
  });
});
