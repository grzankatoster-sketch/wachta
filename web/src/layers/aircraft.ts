import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveAircraft } from "../api";
import { aircraftColor } from "../colors";

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
      pickable: true,
    }),
    new TextLayer<LiveAircraft>({
      id: "aircraft-labels",
      data: airborne.filter((a) => a.isMilitary),
      getPosition: (a) => [a.lon, a.lat],
      getText: (a) => `${a.flight ?? a.hex} ${a.typeCode ?? ""}`.trim(),
      getSize: 11,
      getColor: [240, 240, 240],
      getPixelOffset: [0, -14],
    }),
  ];
}
