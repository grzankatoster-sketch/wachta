import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveAircraft } from "../api";
import { LABEL, aircraftColor } from "../colors";

export function aircraftLayers(data: LiveAircraft[]): Layer[] {
  const airborne = data.filter((a) => !a.onGround);
  return [
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
    }),
  ];
}
