import { IconLayer, LineLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveAircraft } from "../api";
import { LABEL } from "../colors";
import { KATEGORIE, kategoriaSamolotu } from "../typy";
import { LIMIT_SAMOLOT_S, przezroczystosc, ruch, type Ruch } from "../ruch";
import { GRUBOSC_OBWODKI, OBWODKA, ikona, kat } from "./ikony";

/**
 * Aircraft, drawn the same way as ships: a silhouette pointing where it is going, moving between
 * fixes instead of waiting for them.
 *
 * The shape says fixed-wing or rotorcraft and the colour says what the type designator implies -
 * surveillance, tanker, transport, fighter, or nothing in particular. That last one matters: an
 * airframe the table does not recognise stays plain "military" rather than being pushed into the
 * nearest box. The classification is a heuristic over ICAO type codes and is labelled as one on the
 * legend, because a model is not a mission.
 *
 * An aircraft too slow to have a meaningful track, or reporting none, is a dot. Turning a silhouette
 * to a heading we do not have would be drawing a fact we do not hold.
 *
 * A fix lands every 60 seconds and a 450-knot aircraft covers 14 km in that time, so without dead
 * reckoning the mark stands still for a minute and then leaps. Past the cap in ruch.ts it freezes
 * and fades: an aircraft that stopped reporting is what D1 is looking for, not something to smooth
 * over.
 */

/** Below this there is no useful track - the aircraft is taxiing, hovering or the field is absent. */
const MIN_Z_KURSEM_KT = 40;

/** Course line horizon: two minutes, the same reading the ship layer gives at its own. */
const PROJEKCJA_MIN = 2;

export function zKursem(a: LiveAircraft): boolean {
  return (a.gsKt ?? 0) > MIN_Z_KURSEM_KT && a.trackDeg !== null && a.trackDeg !== undefined;
}

/** Where the aircraft is right now, counting from its last fix. */
export function teraz(a: LiveAircraft, terazMs: number): Ruch {
  return ruch(a.lat, a.lon, a.gsKt, a.trackDeg, (terazMs - Date.parse(a.ts)) / 1000, LIMIT_SAMOLOT_S);
}

function przedDziobem(a: LiveAircraft, terazMs: number): [number, number] {
  const r = teraz(a, terazMs);
  const km = ((a.gsKt ?? 0) * 1.852 * PROJEKCJA_MIN) / 60;
  const kurs = ((a.trackDeg ?? 0) * Math.PI) / 180;
  return [
    r.lon + (km / (111.32 * Math.cos((r.lat * Math.PI) / 180) || 1)) * Math.sin(kurs),
    r.lat + (km / 111.32) * Math.cos(kurs),
  ];
}

const kolor = (a: LiveAircraft) => KATEGORIE[kategoriaSamolotu(a)].kolor;
const rozmiar = (a: LiveAircraft) => KATEGORIE[kategoriaSamolotu(a)].rozmiar;

export function aircraftLayers(data: LiveAircraft[], terazMs: number): Layer[] {
  const airborne = data.filter((a) => !a.onGround);
  const lecace = airborne.filter(zKursem);
  const bezKursu = airborne.filter((a) => !zKursem(a));
  const gdzie = (a: LiveAircraft): [number, number] => {
    const r = teraz(a, terazMs);
    return [r.lon, r.lat];
  };
  const alfa = (a: LiveAircraft) => przezroczystosc(teraz(a, terazMs));

  const wyzwalacze = { updateTriggers: { getPosition: terazMs, getSourcePosition: terazMs, getTargetPosition: terazMs, getColor: terazMs, getFillColor: terazMs } };

  return [
    new LineLayer<LiveAircraft>({
      id: "aircraft-course",
      data: lecace,
      getSourcePosition: gdzie,
      getTargetPosition: (a) => przedDziobem(a, terazMs),
      getColor: (a) => [...kolor(a), Math.min(130, alfa(a))] as [number, number, number, number],
      getWidth: 1.2,
      widthUnits: "pixels",
      ...wyzwalacze,
    }),
    new ScatterplotLayer<LiveAircraft>({
      id: "aircraft-stopped",
      data: bezKursu,
      getPosition: gdzie,
      getFillColor: (a) => [...kolor(a), alfa(a)] as [number, number, number, number],
      getRadius: (a) => rozmiar(a) / 5,
      radiusUnits: "pixels",
      stroked: true,
      getLineColor: OBWODKA,
      lineWidthMinPixels: 0.9,
      pickable: true,
      ...wyzwalacze,
    }),
    new IconLayer<LiveAircraft>({
      id: "aircraft-obwodka",
      data: lecace,
      getPosition: gdzie,
      getIcon: (a) => ikona(KATEGORIE[kategoriaSamolotu(a)].ksztalt),
      getSize: (a) => rozmiar(a) + GRUBOSC_OBWODKI,
      getAngle: (a) => kat(a.trackDeg),
      getColor: (a) => [...OBWODKA, alfa(a)] as [number, number, number, number],
      sizeUnits: "pixels",
      ...wyzwalacze,
    }),
    new IconLayer<LiveAircraft>({
      id: "aircraft",
      data: lecace,
      getPosition: gdzie,
      getIcon: (a) => ikona(KATEGORIE[kategoriaSamolotu(a)].ksztalt),
      getSize: rozmiar,
      getAngle: (a) => kat(a.trackDeg),
      getColor: (a) => [...kolor(a), alfa(a)] as [number, number, number, number],
      sizeUnits: "pixels",
      pickable: true,
      ...wyzwalacze,
    }),
    new TextLayer<LiveAircraft>({
      id: "aircraft-labels",
      data: airborne.filter((a) => a.isMilitary),
      getPosition: gdzie,
      getText: (a) => `${a.flight ?? a.hex} ${a.typeCode ?? ""}`.trim(),
      getSize: 11,
      // Podklad positron jest jasny - bialy napis byl na nim niewidoczny mimo poprawnego renderu.
      getColor: (a) => [...LABEL, alfa(a)] as [number, number, number, number],
      getPixelOffset: [0, -16],
      ...wyzwalacze,
    }),
  ];
}
