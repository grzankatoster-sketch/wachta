import { describe, expect, it } from "vitest";
import { aircraftLayers } from "./aircraft";
import { BASEMAP_LAND, BASEMAP_SEA, GREY, LABEL, contrastRatio } from "../colors";
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

describe("widocznosc znacznikow na podkladzie", () => {
  it("cywilny samolot spelnia prog 3:1 na ladzie i na wodzie", () => {
    // WCAG 1.4.11 dla grafiki niosacej znaczenie. Poprzedni szary mial 1.57:1 na wodzie, czyli nad
    // morzem - a to wiekszosc tej mapy - cywilny ruch praktycznie znikal.
    expect(contrastRatio(GREY, BASEMAP_LAND)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(GREY, BASEMAP_SEA)).toBeGreaterThanOrEqual(3);
  });

  it("obwodka znacznika jest widoczna na obu powierzchniach podkladu", () => {
    // Czerwony wojskowy sam w sobie ma 2.46:1 na wodzie. Obwodka jest tym, co go ratuje, wiec to
    // ona musi trzymac prog - inaczej wystarczy ja usunac i nic tego nie zauwazy.
    expect(contrastRatio(LABEL, BASEMAP_LAND)).toBeGreaterThanOrEqual(3);
    expect(contrastRatio(LABEL, BASEMAP_SEA)).toBeGreaterThanOrEqual(3);
  });

  it("wojskowy i cywilny roznia sie czyms wiecej niz kolorem", () => {
    // Czerwony i szary maja zblizona jasnosc, wiec przy daltonizmie kolor nie wystarcza.
    // Rozmiar niesie te sama informacje: promien wojskowego jest dwukrotnie wiekszy.
    const [warstwa] = aircraftLayers([plane({ isMilitary: true }), plane({ hex: "bbb", isMilitary: false })]);
    const promien = (warstwa.props as unknown as { getRadius: (a: LiveAircraft) => number }).getRadius;
    expect(promien(plane({ isMilitary: true }))).toBeGreaterThanOrEqual(
      2 * promien(plane({ isMilitary: false })));
  });
});
