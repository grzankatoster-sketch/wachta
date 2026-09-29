import { IconLayer, LineLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { LiveShip } from "../api";
import { KATEGORIE, kategoriaStatku } from "../typy";
import { LIMIT_STATEK_S, przezroczystosc, ruch, type Ruch } from "../ruch";
import { GRUBOSC_OBWODKI, OBWODKA, ikona, kat } from "./ikony";

/**
 * Ships, drawn as hulls that point where they are going and keep going between fixes.
 *
 * A vessel making way is a silhouette turned to its course with a line ahead of it; a vessel that is
 * not is a plain dot. That is not decoration. A stopped ship has no meaningful heading - AIS keeps
 * reporting the last course, or zero - so drawing it as an oriented hull would be inventing a fact.
 * The dot says "here, and not going anywhere", which is what the anchor and rendezvous detectors are
 * looking at: two dots side by side in open water is what D5 calls a transfer.
 *
 * The course line reaches where the ship will be in half an hour on its present course and speed, so
 * its LENGTH is speed, readable without a legend.
 *
 * Positions are dead-reckoned between fixes (see ruch.ts) because AIS lands every 140 seconds and a
 * map that only moves then is a slideshow. A hull that stops reporting freezes and fades rather than
 * sailing on, which is the whole point: a ship going quiet is the finding, not a gap to paper over.
 */

/** Below this a vessel is manoeuvring or moored, not making way. */
const MIN_W_RUCHU_KT = 0.5;

/** Course line horizon. Aircraft use two minutes; 12 knots covers 0.7 km in two minutes, one pixel. */
const PROJEKCJA_MIN = 30;

const KM_NA_MILE_MORSKA = 1.852;

/**
 * Pick radius for every vessel, visible size notwithstanding.
 *
 * Eight pixels is a 16 px target, which is about the smallest a pointer hits reliably and still
 * narrow enough that neighbouring hulls in a shipping lane stay separable: the median distance
 * between a ship and its nearest neighbour in this data is far larger than that everywhere except
 * inside harbours, where the traffic is service craft anyway.
 */
const CEL_TRAFIENIA_PX = 8;

export function wRuchu(s: LiveShip): boolean {
  return (s.sogKt ?? 0) >= MIN_W_RUCHU_KT && s.cogDeg !== null && s.cogDeg !== undefined;
}

/** Where the ship is right now, counting from its last fix. */
export function teraz(s: LiveShip, terazMs: number): Ruch {
  return ruch(s.lat, s.lon, s.sogKt, s.cogDeg, (terazMs - Date.parse(s.ts)) / 1000, LIMIT_STATEK_S);
}

/** Where it will be at the end of the projection, measured from where it is now. */
export function przedDziobem(s: LiveShip, terazMs: number): [number, number] {
  const r = teraz(s, terazMs);
  const km = ((s.sogKt ?? 0) * KM_NA_MILE_MORSKA * PROJEKCJA_MIN) / 60;
  const kurs = ((s.cogDeg ?? 0) * Math.PI) / 180;
  return [
    r.lon + (km / (111.32 * Math.cos((r.lat * Math.PI) / 180) || 1)) * Math.sin(kurs),
    r.lat + (km / 111.32) * Math.cos(kurs),
  ];
}

const kolor = (s: LiveShip) => KATEGORIE[kategoriaStatku(s)].kolor;
const rozmiar = (s: LiveShip) => KATEGORIE[kategoriaStatku(s)].rozmiar;

export function shipLayers(data: LiveShip[], terazMs: number): Layer[] {
  const plynace = data.filter(wRuchu);
  const stojace = data.filter((s) => !wRuchu(s));
  const gdzie = (s: LiveShip): [number, number] => {
    const r = teraz(s, terazMs);
    return [r.lon, r.lat];
  };
  const alfa = (s: LiveShip) => przezroczystosc(teraz(s, terazMs));

  // Bez transitions na pozycji: znacznik i tak przesuwa sie co klatke, a przejscie deck.gl
  // startowaloby od nowa przy kazdym tyknieciu zegara i zostawaloby w tyle za wlasnym celem.
  const wyzwalacze = { updateTriggers: { getPosition: terazMs, getSourcePosition: terazMs, getTargetPosition: terazMs, getColor: terazMs, getFillColor: terazMs } };

  return [
    // Niewidoczny cel trafien pod wszystkim.
    //
    // Stojacy statek rysuje sie jako kropka o promieniu rozmiar/5, czyli 2.2-3.4 px - cel o
    // srednicy 4.4 px. To ponizej tego, w co czlowiek trafia mysza bez celowania, a stojacych
    // jednostek bywa na ekranie szescset naraz. Nie jest to drobiazg: stojace kadluby to dokladnie
    // material dla D5 (przeladunek burta w burte) i D6 (wleczona kotwica), wiec najtrudniejsze do
    // trafienia byly obiekty, po ktore czytelnik siega najczesciej.
    //
    // UCZCIWIE O DOWODACH: probowalem to potwierdzic skryptem klikajacym w wyliczone wspolrzedne
    // statkow i wyszlo "450 klikniec, zero paneli". Ten pomiar byl NIEWAZNY - moje przeliczanie
    // stopni na piksele bylo blednie, skrypt klikal w inne miejsca niz zamierzalem (kontrola na
    // duzych pierscieniach alarmow: 0/25 trafien). Zmiana zostaje, bo 4.4 px broni sie samo, ale
    // nie stoi za nia pomiar na zywym ekranie.
    //
    // Osobna warstwa, a nie wiekszy promien, bo znacznik ma zostac maly - gesty pas ruchu zlalby
    // sie w plame. Lezy na samym dole, wiec precyzyjne klikniecie w sylwetke nadal trafia w nia.
    new ScatterplotLayer<LiveShip>({
      id: "ships-hit",
      data,
      getPosition: gdzie,
      getFillColor: [0, 0, 0, 0],
      getRadius: CEL_TRAFIENIA_PX,
      radiusUnits: "pixels",
      pickable: true,
      ...wyzwalacze,
    }),
    new LineLayer<LiveShip>({
      id: "ship-course",
      data: plynace,
      getSourcePosition: gdzie,
      getTargetPosition: (s) => przedDziobem(s, terazMs),
      getColor: (s) => [...kolor(s), Math.min(150, alfa(s))] as [number, number, number, number],
      getWidth: 1.4,
      widthUnits: "pixels",
      ...wyzwalacze,
    }),
    new ScatterplotLayer<LiveShip>({
      id: "ships-stopped",
      data: stojace,
      getPosition: gdzie,
      getFillColor: (s) => [...kolor(s), alfa(s)] as [number, number, number, number],
      getRadius: (s) => rozmiar(s) / 5,
      radiusUnits: "pixels",
      stroked: true,
      getLineColor: OBWODKA,
      lineWidthMinPixels: 0.9,
      pickable: true,
      ...wyzwalacze,
    }),
    // Obwodka to ta sama sylwetka narysowana szerzej, pod spodem. Maska nie umie drugiego koloru,
    // a bez obrysu ciemny kadlub na ciemnej wodzie schodzi ponizej progu widocznosci.
    new IconLayer<LiveShip>({
      id: "ships-obwodka",
      data: plynace,
      getPosition: gdzie,
      getIcon: (s) => ikona(KATEGORIE[kategoriaStatku(s)].ksztalt),
      getSize: (s) => rozmiar(s) + GRUBOSC_OBWODKI,
      getAngle: (s) => kat(s.cogDeg),
      getColor: (s) => [...OBWODKA, alfa(s)] as [number, number, number, number],
      sizeUnits: "pixels",
      ...wyzwalacze,
    }),
    new IconLayer<LiveShip>({
      id: "ships",
      data: plynace,
      getPosition: gdzie,
      getIcon: (s) => ikona(KATEGORIE[kategoriaStatku(s)].ksztalt),
      getSize: rozmiar,
      getAngle: (s) => kat(s.cogDeg),
      getColor: (s) => [...kolor(s), alfa(s)] as [number, number, number, number],
      sizeUnits: "pixels",
      pickable: true,
      ...wyzwalacze,
    }),
  ];
}
