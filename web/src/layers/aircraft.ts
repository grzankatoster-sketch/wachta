import { IconLayer, LineLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveAircraft } from "../api";
import { LABEL } from "../colors";
import { KATEGORIE, kategoriaSamolotu } from "../typy";
import { GRUBOSC_OBWODKI, OBWODKA, ikona, kat } from "./ikony";

/**
 * Aircraft, drawn the same way as ships: a silhouette pointing where it is going.
 *
 * The shape says fixed-wing or rotorcraft and the colour says what the type designator implies -
 * surveillance, tanker, transport, fighter, or nothing in particular. That last one matters: an
 * airframe the table does not recognise stays plain "military" rather than being pushed into the
 * nearest box. The classification is a heuristic over ICAO type codes and is labelled as one on the
 * legend, because a model is not a mission.
 *
 * An aircraft too slow to have a meaningful track, or reporting none, is a dot. Turning a silhouette
 * to a heading we do not have would be drawing a fact we do not hold.
 */

/** Below this there is no useful track - the aircraft is taxiing, hovering or the field is absent. */
const MIN_Z_KURSEM_KT = 40;

/** Two minutes ahead, the same reading the ship layer gives at its own horizon. */
function przedDziobem(a: LiveAircraft): [number, number] {
  const km = ((a.gsKt ?? 0) * 1.852 * 2) / 60;
  const kurs = ((a.trackDeg ?? 0) * Math.PI) / 180;
  return [
    a.lon + (km / (111.32 * Math.cos((a.lat * Math.PI) / 180) || 1)) * Math.sin(kurs),
    a.lat + (km / 111.32) * Math.cos(kurs),
  ];
}

export function zKursem(a: LiveAircraft): boolean {
  return (a.gsKt ?? 0) > MIN_Z_KURSEM_KT && a.trackDeg !== null && a.trackDeg !== undefined;
}

const kolor = (a: LiveAircraft) => KATEGORIE[kategoriaSamolotu(a)].kolor;
const rozmiar = (a: LiveAircraft) => KATEGORIE[kategoriaSamolotu(a)].rozmiar;

export function aircraftLayers(data: LiveAircraft[]): Layer[] {
  const airborne = data.filter((a) => !a.onGround);
  const lecace = airborne.filter(zKursem);
  const bezKursu = airborne.filter((a) => !zKursem(a));
  const przejscie = { getPosition: 900, getSourcePosition: 900, getTargetPosition: 900 };

  return [
    new LineLayer<LiveAircraft>({
      id: "aircraft-course",
      data: lecace,
      getSourcePosition: (a) => [a.lon, a.lat],
      getTargetPosition: przedDziobem,
      getColor: (a) => [...kolor(a), 130] as [number, number, number, number],
      getWidth: 1.2,
      widthUnits: "pixels",
      transitions: przejscie,
    }),
    new ScatterplotLayer<LiveAircraft>({
      id: "aircraft-stopped",
      data: bezKursu,
      getPosition: (a) => [a.lon, a.lat],
      getFillColor: kolor,
      getRadius: (a) => rozmiar(a) / 5,
      radiusUnits: "pixels",
      stroked: true,
      getLineColor: OBWODKA,
      lineWidthMinPixels: 0.9,
      pickable: true,
      transitions: przejscie,
    }),
    new IconLayer<LiveAircraft>({
      id: "aircraft-obwodka",
      data: lecace,
      getPosition: (a) => [a.lon, a.lat],
      getIcon: (a) => ikona(KATEGORIE[kategoriaSamolotu(a)].ksztalt),
      getSize: (a) => rozmiar(a) + GRUBOSC_OBWODKI,
      getAngle: (a) => kat(a.trackDeg),
      getColor: OBWODKA,
      sizeUnits: "pixels",
      transitions: przejscie,
    }),
    new IconLayer<LiveAircraft>({
      id: "aircraft",
      data: lecace,
      getPosition: (a) => [a.lon, a.lat],
      getIcon: (a) => ikona(KATEGORIE[kategoriaSamolotu(a)].ksztalt),
      getSize: rozmiar,
      getAngle: (a) => kat(a.trackDeg),
      getColor: kolor,
      sizeUnits: "pixels",
      pickable: true,
      transitions: przejscie,
    }),
    new TextLayer<LiveAircraft>({
      id: "aircraft-labels",
      data: airborne.filter((a) => a.isMilitary),
      getPosition: (a) => [a.lon, a.lat],
      getText: (a) => `${a.flight ?? a.hex} ${a.typeCode ?? ""}`.trim(),
      getSize: 11,
      // Podklad positron jest jasny - bialy napis byl na nim niewidoczny mimo poprawnego renderu.
      getColor: LABEL,
      getPixelOffset: [0, -16],
      transitions: przejscie,
    }),
  ];
}
