import { TripsLayer } from "@deck.gl/geo-layers";
import type { Trip } from "../replay";
import { RED } from "../colors";

export function tripsLayer(trips: Trip[], currentTime: number) {
  return new TripsLayer<Trip>({
    id: "trips",
    data: trips,
    getPath: (t) => t.path,
    getTimestamps: (t) => t.timestamps,
    getColor: RED,
    widthMinPixels: 2,
    trailLength: 1800,
    currentTime,
    pickable: false,
  });
}
