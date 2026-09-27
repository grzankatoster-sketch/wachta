import { ScatterplotLayer } from "@deck.gl/layers";
import type { AlertDto } from "../api";

export function alertsLayer(alerts: AlertDto[]) {
  return new ScatterplotLayer<AlertDto>({
    id: "alerts",
    data: alerts,
    getPosition: (a) => [a.lon, a.lat],
    getRadius: 14,
    radiusUnits: "pixels",
    stroked: true,
    filled: false,
    getLineColor: [255, 190, 0],
    lineWidthMinPixels: 2,
    pickable: true,
  });
}
