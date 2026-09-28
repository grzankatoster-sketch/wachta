import DeckGL from "@deck.gl/react";
import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { configureMaplibreWorker } from "../maplibre-worker";

// Musi pasc przed pierwszym <Map>: MapLibre czyta config.WORKER_URL dopiero przy tworzeniu mapy,
// ale pozniejsza zmiana nie odratuje juz puli workerow zbudowanej na zlym adresie.
configureMaplibreWorker();

export const BALTIC_VIEW: MapViewState = { longitude: 20, latitude: 57, zoom: 5 };
const STYLE = "https://tiles.openfreemap.org/styles/positron";

interface Props {
  layers: Layer[];
  viewState?: MapViewState;
  onViewStateChange?: (v: MapViewState) => void;
}

function tooltip({ object }: PickingInfo) {
  if (!object) return null;
  if ("hex" in object) return `${object.flight ?? object.hex} · ${object.typeCode ?? "?"} · ${object.altBaroFt ?? "?"} ft`;
  if ("detector" in object) return `${object.detector} · ${object.entityId} · wynik ${object.score}`;
  return null;
}

export function MapView({ layers, viewState, onViewStateChange }: Props) {
  return (
    <DeckGL
      initialViewState={viewState ? undefined : BALTIC_VIEW}
      viewState={viewState}
      onViewStateChange={onViewStateChange ? ({ viewState: v }) => onViewStateChange(v as MapViewState) : undefined}
      controller
      layers={layers}
      getTooltip={tooltip}
    >
      <Map mapStyle={STYLE} />
    </DeckGL>
  );
}
