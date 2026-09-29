import { describe, expect, it } from "vitest";
import type { AlertDto, JammingDto, LiveAircraft } from "../api";
import { aircraftLayers } from "./aircraft";
import { alertsLayer } from "./alerts";
import { jammingLayer } from "./jamming";

/** Zegar testu rowny znacznikowi z fixture: wiek pozycji 0, wiec zadnego zliczania drogi. */
const TERAZ = Date.parse("2026-09-28T08:00:00Z");

/**
 * Regression guard for the click-to-detail feature: deck.gl only fires onClick for a layer whose
 * `pickable` prop is true. getTooltip() already worked on hover with pickable layers, which hid the
 * fact that jamming's hexagons were NOT pickable - hovering never told anyone that, only a click
 * (which produced nothing) would have.
 */

const plane: LiveAircraft = {
  hex: "3c6444", flight: "FORTE10", typeCode: "Q4", isMilitary: true, lat: 55, lon: 19,
  altBaroFt: 30000, onGround: false, gsKt: 400, trackDeg: 90, ts: "2026-09-28T08:00:00Z",
};

const alert: AlertDto = {
  id: 1, detector: "D4", entityId: "1", startedAt: "2026-09-28T08:00:00Z",
  lat: 55, lon: 19, score: 0.8, evidence: "{}", state: "open",
};

const cell: JammingDto = { h3: "841f24bffffffff", nAircraft: 20, nDegraded: 3 };

function pickable(props: unknown): boolean {
  return (props as { pickable?: boolean }).pickable === true;
}

describe("warstwy sa klikalne", () => {
  it("warstwa samolotow (scatterplot) jest pickable", () => {
    const scatter = aircraftLayers([plane], TERAZ).find((l) => l.id === "aircraft");
    expect(pickable(scatter!.props)).toBe(true);
  });

  it("warstwa alarmow jest pickable", () => {
    expect(pickable(alertsLayer([alert]).props)).toBe(true);
  });

  it("warstwa heksagonow zaklocen GPS jest pickable", () => {
    expect(pickable(jammingLayer([cell]).props)).toBe(true);
  });
});
