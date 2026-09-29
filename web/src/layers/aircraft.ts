import { LineLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveAircraft } from "../api";
import { LABEL, aircraftColor } from "../colors";

/** Two minutes ahead on the present heading - the same reading the ship layer gives, so one glance
 * answers "which way is this going" for both domains. */
function przedDziobem(a: LiveAircraft): [number, number] {
  const km = ((a.gsKt ?? 0) * 1.852 * 2) / 60;
  const kurs = ((a.trackDeg ?? 0) * Math.PI) / 180;
  return [
    a.lon + (km / (111.32 * Math.cos((a.lat * Math.PI) / 180) || 1)) * Math.sin(kurs),
    a.lat + (km / 111.32) * Math.cos(kurs),
  ];
}

export function aircraftLayers(data: LiveAircraft[]): Layer[] {
  const airborne = data.filter((a) => !a.onGround);
  const zKursem = airborne.filter((a) => (a.gsKt ?? 0) > 40 && a.trackDeg !== null);
  return [
    new LineLayer<LiveAircraft>({
      id: "aircraft-course",
      data: zKursem,
      getSourcePosition: (a) => [a.lon, a.lat],
      getTargetPosition: przedDziobem,
      getColor: (a) => [...aircraftColor(a), 130] as [number, number, number, number],
      getWidth: 1.2,
      widthUnits: "pixels",
      transitions: { getSourcePosition: 900, getTargetPosition: 900 },
    }),
    new ScatterplotLayer<LiveAircraft>({
      id: "aircraft",
      data: airborne,
      getPosition: (a) => [a.lon, a.lat],
      getFillColor: (a) => aircraftColor(a),
      getRadius: (a) => (a.isMilitary ? 6 : 3),
      radiusUnits: "pixels",
      // Obwodka, bo samo wypelnienie nie wystarczy: czerwony wojskowy ma 2.46:1 wzgledem wody,
      // czyli ponizej progu 3:1. Ciemny obrys ma 10.55:1 na wodzie i 16.03:1 na ladzie, wiec
      // znacznik jest widoczny niezaleznie od tego, na czym wyladuje. Rozroznienie wojskowy/cywilny
      // nie opiera sie na kolorze - promien jest dwa razy wiekszy, a maszyna ma podpis.
      stroked: true,
      getLineColor: LABEL,
      lineWidthMinPixels: 1,
      pickable: true,
      // Pozycje przychodza skokowo co 5 s. Bez przejscia mapa mruga jak odswiezany obrazek.
      transitions: { getPosition: 900 },
    }),
    new TextLayer<LiveAircraft>({
      id: "aircraft-labels",
      data: airborne.filter((a) => a.isMilitary),
      getPosition: (a) => [a.lon, a.lat],
      getText: (a) => `${a.flight ?? a.hex} ${a.typeCode ?? ""}`.trim(),
      getSize: 11,
      // Podklad positron jest jasny - bialy napis byl na nim niewidoczny mimo poprawnego renderu.
      getColor: LABEL,
      getPixelOffset: [0, -14],
      transitions: { getPosition: 900 },
    }),
  ];
}
